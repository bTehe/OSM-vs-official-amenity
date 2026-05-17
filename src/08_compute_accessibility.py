from __future__ import annotations

import math

import networkx as nx
import pandas as pd

from config import (
    ACCESSIBILITY_GPKG,
    ACCESSIBILITY_TABLE,
    ACCESS_THRESHOLD_MINUTES,
    AMENITY_LAYER_KEYS,
    AMENITY_TYPE_BY_LAYER,
    CRS_METRIC,
    OFFICIAL_CLEAN_FILES,
    ORIGINS_POINTS_FILE,
    ORIGINS_POINTS_SNAPPED_FILE,
    OSM_CLEAN_FILES,
    OSM_WALKING_EDGES_CLEAN_FILE,
    OSM_WALKING_GRAPH_FILE,
    OSM_WALKING_NODES_CLEAN_FILE,
    PROCESSED_DIR,
    SNAP_WARNING_DISTANCE_M,
    TABLES_DIR,
    ensure_directories,
)
from utils import (
    clean_numeric_difference,
    import_geopandas,
    nearest_node_snap,
    require_file,
    resolve_node_id_column,
    safe_write_csv,
    safe_write_gdf,
)


def coerce_graph_weights(graph: nx.Graph) -> nx.Graph:
    for _, _, data in graph.edges(data=True):
        for key in ["length_m", "walking_time_minutes"]:
            if key in data:
                data[key] = float(data[key])
    return graph


def load_graph() -> nx.Graph:
    if OSM_WALKING_GRAPH_FILE.exists():
        return coerce_graph_weights(nx.read_graphml(OSM_WALKING_GRAPH_FILE))

    gpd = import_geopandas()
    nodes = gpd.read_file(require_file(OSM_WALKING_NODES_CLEAN_FILE)).to_crs(CRS_METRIC)
    edges = gpd.read_file(require_file(OSM_WALKING_EDGES_CLEAN_FILE)).to_crs(CRS_METRIC)
    graph = nx.Graph()
    for row in nodes.itertuples(index=False):
        graph.add_node(str(row.node_id), x=float(row.geometry.x), y=float(row.geometry.y))
    for row in edges.itertuples(index=False):
        if not hasattr(row, "u") or not hasattr(row, "v"):
            raise ValueError("Clean walking edges must include u and v columns.")
        graph.add_edge(
            str(row.u),
            str(row.v),
            length_m=float(row.length_m),
            walking_time_minutes=float(row.walking_time_minutes),
        )
    return graph


def add_snap_columns(points, nodes, point_id_col: str):
    snap = nearest_node_snap(points, nodes, point_id_col=point_id_col)
    out = points.merge(snap, on=point_id_col, how="left")
    out["snap_flag_gt_100m"] = out["snap_distance_m"] > SNAP_WARNING_DISTANCE_M
    out["nearest_node"] = out["nearest_node"].astype(str)
    return out


def snapping_summary(label: str, source: str, amenity_type: str | None, snapped) -> dict:
    distances = pd.to_numeric(snapped["snap_distance_m"], errors="coerce")
    return {
        "layer": label,
        "source": source,
        "amenity_type": amenity_type or "",
        "record_count": len(snapped),
        "flagged_gt_100m_count": int((distances > SNAP_WARNING_DISTANCE_M).sum()),
        "flagged_gt_100m_share": float((distances > SNAP_WARNING_DISTANCE_M).mean()) if len(snapped) else None,
        "median_snap_distance_m": float(distances.median()) if len(snapped) else None,
        "max_snap_distance_m": float(distances.max()) if len(snapped) else None,
    }


def shortest_times_to_sources(graph: nx.Graph, source_nodes: set[str]) -> dict[str, float]:
    source_nodes = {str(node) for node in source_nodes if str(node) in graph}
    if not source_nodes:
        return {}
    return nx.multi_source_dijkstra_path_length(
        graph,
        sources=source_nodes,
        weight="walking_time_minutes",
    )


def finite_access(value: float) -> bool:
    return math.isfinite(value) and value <= ACCESS_THRESHOLD_MINUTES


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()
    graph = load_graph()

    nodes = gpd.read_file(require_file(OSM_WALKING_NODES_CLEAN_FILE)).to_crs(CRS_METRIC)
    node_col = resolve_node_id_column(nodes)
    nodes[node_col] = nodes[node_col].astype(str)

    origins = gpd.read_file(require_file(ORIGINS_POINTS_FILE)).to_crs(CRS_METRIC)
    origins_snapped = add_snap_columns(origins, nodes, "origin_id")
    safe_write_gdf(origins_snapped, ORIGINS_POINTS_SNAPPED_FILE, layer="origins_points_500m")

    diagnostics = [snapping_summary("origins_points_500m", "origin", None, origins_snapped)]
    snapped_layers = {"official": {}, "osm": {}}

    for layer_key in AMENITY_LAYER_KEYS:
        amenity_type = AMENITY_TYPE_BY_LAYER[layer_key]
        for source, files in [("official", OFFICIAL_CLEAN_FILES), ("osm", OSM_CLEAN_FILES)]:
            amenities = gpd.read_file(require_file(files[layer_key])).to_crs(CRS_METRIC)
            snapped = add_snap_columns(amenities, nodes, "amenity_id")
            output = PROCESSED_DIR / f"{source}_{layer_key}_snapped.gpkg"
            safe_write_gdf(snapped, output, layer=f"{source}_{layer_key}_snapped")
            diagnostics.append(snapping_summary(f"{source}_{layer_key}", source, amenity_type, snapped))
            snapped_layers[source][amenity_type] = snapped

    safe_write_csv(pd.DataFrame(diagnostics), TABLES_DIR / "snapping_diagnostics.csv")

    origin_nodes = origins_snapped.set_index("origin_id")["nearest_node"].astype(str).to_dict()
    rows = []

    for amenity_type in AMENITY_TYPE_BY_LAYER.values():
        official_nodes = set(snapped_layers["official"][amenity_type]["nearest_node"].dropna().astype(str))
        osm_nodes = set(snapped_layers["osm"][amenity_type]["nearest_node"].dropna().astype(str))
        official_lengths = shortest_times_to_sources(graph, official_nodes)
        osm_lengths = shortest_times_to_sources(graph, osm_nodes)

        for origin_id, origin_node in origin_nodes.items():
            official_time = official_lengths.get(origin_node, float("inf"))
            osm_time = osm_lengths.get(origin_node, float("inf"))
            official_access = finite_access(official_time)
            osm_access = finite_access(osm_time)
            rows.append(
                {
                    "origin_id": origin_id,
                    "amenity_type": amenity_type,
                    "official_nearest_time": official_time if math.isfinite(official_time) else None,
                    "osm_nearest_time": osm_time if math.isfinite(osm_time) else None,
                    "official_access_15": official_access,
                    "osm_access_15": osm_access,
                    "difference_minutes": clean_numeric_difference(osm_time, official_time),
                    "origin_nearest_node": origin_node,
                }
            )

    results = pd.DataFrame(rows)
    safe_write_csv(results, ACCESSIBILITY_TABLE)

    result_gdf = results.merge(
        origins_snapped[["origin_id", "snap_distance_m", "snap_flag_gt_100m", "geometry"]],
        on="origin_id",
        how="left",
    )
    result_gdf = gpd.GeoDataFrame(result_gdf, geometry="geometry", crs=CRS_METRIC)
    safe_write_gdf(result_gdf, ACCESSIBILITY_GPKG, layer="origin_accessibility_comparison")

    print(f"Saved accessibility comparison for {len(results)} origin/category rows.")


if __name__ == "__main__":
    main()
