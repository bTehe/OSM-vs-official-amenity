from __future__ import annotations

import math

import networkx as nx
import pandas as pd

from config import (
    ACCESS_THRESHOLD_MINUTES,
    AMENITY_LAYER_KEYS,
    AMENITY_TYPE_BY_LAYER,
    CRS_METRIC,
    OSM_WALKING_EDGES_CLEAN_FILE,
    OSM_WALKING_GRAPH_FILE,
    OSM_WALKING_NODES_CLEAN_FILE,
    PROCESSED_DIR,
    TABLES_DIR,
    ensure_directories,
)
from utils import classify_accessibility, clean_numeric_difference, import_geopandas, require_file, safe_write_csv


ORIGIN_SET_POINTS = {
    "full": PROCESSED_DIR / "origins_points_500m_full.gpkg",
    "clean100": PROCESSED_DIR / "origins_points_500m_clean100.gpkg",
    "clean250": PROCESSED_DIR / "origins_points_500m_clean250.gpkg",
}

ACCESSIBILITY_OUTPUTS = {
    "full": TABLES_DIR / "origin_accessibility_classified_full.csv",
    "clean100": TABLES_DIR / "origin_accessibility_classified_clean100.csv",
    "clean250": TABLES_DIR / "origin_accessibility_classified_clean250.csv",
}

COMPOSITE_OUTPUTS = {
    "full": TABLES_DIR / "composite_disagreement_scores_full.csv",
    "clean100": TABLES_DIR / "composite_disagreement_scores_clean100.csv",
    "clean250": TABLES_DIR / "composite_disagreement_scores_clean250.csv",
}


def load_graph() -> nx.Graph:
    if OSM_WALKING_GRAPH_FILE.exists():
        graph = nx.read_graphml(OSM_WALKING_GRAPH_FILE)
    else:
        gpd = import_geopandas()
        nodes = gpd.read_file(require_file(OSM_WALKING_NODES_CLEAN_FILE)).to_crs(CRS_METRIC)
        edges = gpd.read_file(require_file(OSM_WALKING_EDGES_CLEAN_FILE)).to_crs(CRS_METRIC)
        graph = nx.Graph()
        for row in nodes.itertuples(index=False):
            graph.add_node(str(row.node_id), x=float(row.geometry.x), y=float(row.geometry.y))
        for row in edges.itertuples(index=False):
            graph.add_edge(
                str(row.u),
                str(row.v),
                length_m=float(row.length_m),
                walking_time_minutes=float(row.walking_time_minutes),
            )

    for _, _, data in graph.edges(data=True):
        data["walking_time_minutes"] = float(data["walking_time_minutes"])
    return graph


def node_column(gdf) -> str:
    for col in ["nearest_node_id", "nearest_node", "origin_nearest_node"]:
        if col in gdf.columns:
            return col
    raise ValueError(f"No snapped node column found. Columns: {list(gdf.columns)}")


def load_amenity_nodes():
    gpd = import_geopandas()
    amenity_nodes = {}
    for layer_key in AMENITY_LAYER_KEYS:
        amenity_type = AMENITY_TYPE_BY_LAYER[layer_key]
        for source in ["official", "osm"]:
            path = PROCESSED_DIR / f"{source}_{layer_key}_snapped.gpkg"
            gdf = gpd.read_file(require_file(path)).to_crs(CRS_METRIC)
            col = node_column(gdf)
            amenity_nodes[(source, amenity_type)] = set(gdf[col].dropna().astype(str))
    return amenity_nodes


def shortest_times_to_sources(graph: nx.Graph, source_nodes: set[str]) -> dict[str, float]:
    valid_sources = {node for node in source_nodes if node in graph}
    if not valid_sources:
        return {}
    return nx.multi_source_dijkstra_path_length(
        graph,
        sources=valid_sources,
        weight="walking_time_minutes",
    )


def finite_access(value: float) -> bool:
    return math.isfinite(value) and value <= ACCESS_THRESHOLD_MINUTES


def compute_for_origin_set(origin_set: str, graph, time_cache) -> pd.DataFrame:
    gpd = import_geopandas()
    origins = gpd.read_file(require_file(ORIGIN_SET_POINTS[origin_set])).to_crs(CRS_METRIC)
    col = node_column(origins)
    origins["origin_nearest_node"] = origins[col].astype(str)

    rows = []
    for amenity_type in AMENITY_TYPE_BY_LAYER.values():
        official_lengths = time_cache[("official", amenity_type)]
        osm_lengths = time_cache[("osm", amenity_type)]
        for origin in origins[["origin_id", "origin_nearest_node"]].itertuples(index=False):
            node = str(origin.origin_nearest_node)
            official_time = official_lengths.get(node, float("inf"))
            osm_time = osm_lengths.get(node, float("inf"))
            official_access = finite_access(official_time)
            osm_access = finite_access(osm_time)
            distortion_class = classify_accessibility(official_access, osm_access)
            rows.append(
                {
                    "origin_set": origin_set,
                    "origin_id": origin.origin_id,
                    "amenity_type": amenity_type,
                    "official_nearest_time": official_time if math.isfinite(official_time) else None,
                    "osm_nearest_time": osm_time if math.isfinite(osm_time) else None,
                    "official_access_15": official_access,
                    "osm_access_15": osm_access,
                    "difference_minutes": clean_numeric_difference(osm_time, official_time),
                    "origin_nearest_node": node,
                    "distortion_class": distortion_class,
                    "disagrees": distortion_class in {"osm_false_access", "osm_hidden_access"},
                }
            )
    return pd.DataFrame(rows)


def save_composite(origin_set: str, classified: pd.DataFrame) -> None:
    composite = (
        classified.groupby("origin_id", as_index=False)["disagrees"]
        .sum()
        .rename(columns={"disagrees": "composite_disagreement_score"})
    )
    composite.insert(0, "origin_set", origin_set)
    safe_write_csv(composite, COMPOSITE_OUTPUTS[origin_set])


def main() -> None:
    ensure_directories()
    graph = load_graph()
    amenity_nodes = load_amenity_nodes()

    # The goal is to test whether the main conclusion depends on problematic
    # grid origins. The walking network and POI datasets stay fixed; only the
    # origin set changes. Stable results after removing poorly snapped origins
    # support robustness, while large changes must be discussed as a limitation.
    time_cache = {
        key: shortest_times_to_sources(graph, nodes)
        for key, nodes in amenity_nodes.items()
    }

    for origin_set in ["full", "clean100", "clean250"]:
        classified = compute_for_origin_set(origin_set, graph, time_cache)
        safe_write_csv(classified, ACCESSIBILITY_OUTPUTS[origin_set])
        save_composite(origin_set, classified)
        print(f"Saved accessibility for {origin_set}: {classified['origin_id'].nunique()} origins.")


if __name__ == "__main__":
    main()
