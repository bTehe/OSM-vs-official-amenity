from __future__ import annotations

import math

import networkx as nx

from config import (
    CRS_METRIC,
    OSM_WALKING_EDGES_CLEAN_FILE,
    OSM_WALKING_EDGES_FILE,
    OSM_WALKING_GRAPH_FILE,
    OSM_WALKING_NODES_CLEAN_FILE,
    OSM_WALKING_NODES_FILE,
    WALKING_SPEED_KMH,
    ensure_directories,
)
from utils import (
    ensure_crs,
    import_geopandas,
    make_valid_geometries,
    require_file,
    resolve_edge_endpoint_columns,
    resolve_node_id_column,
    safe_write_gdf,
)


NON_WALKABLE_HIGHWAYS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "construction",
    "proposed",
    "raceway",
}

BLOCKING_VALUES = {"no", "private", "customers"}


def lower_text(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).lower()


def filter_walkable_edges(edges):
    keep = edges.geometry.notna() & ~edges.geometry.is_empty
    if "highway" in edges.columns:
        keep &= ~edges["highway"].apply(lambda value: lower_text(value) in NON_WALKABLE_HIGHWAYS)
    if "access" in edges.columns:
        keep &= ~edges["access"].apply(lambda value: lower_text(value) in BLOCKING_VALUES)
    if "foot" in edges.columns:
        keep &= ~edges["foot"].apply(lambda value: lower_text(value) in {"no", "private"})
    return edges[keep].copy()


def prepare_nodes(nodes):
    nodes = make_valid_geometries(ensure_crs(nodes)).to_crs(CRS_METRIC)
    node_col = resolve_node_id_column(nodes)
    nodes = nodes.copy()
    nodes["node_id"] = nodes[node_col].astype(str)
    nodes["x"] = nodes.geometry.x
    nodes["y"] = nodes.geometry.y
    return nodes


def prepare_edges(edges):
    edges = make_valid_geometries(ensure_crs(edges)).to_crs(CRS_METRIC)
    edges = filter_walkable_edges(edges)
    u_col, v_col = resolve_edge_endpoint_columns(edges)
    edges = edges.copy()
    edges["u"] = edges[u_col].astype(str)
    edges["v"] = edges[v_col].astype(str)
    edges["length_m"] = edges.geometry.length
    speed_m_per_min = WALKING_SPEED_KMH * 1000.0 / 60.0
    edges["walking_time_minutes"] = edges["length_m"] / speed_m_per_min
    return edges


def build_graph(nodes, edges) -> nx.Graph:
    graph = nx.Graph()

    for row in nodes.itertuples(index=False):
        node_id = str(row.node_id)
        graph.add_node(node_id, x=float(row.x), y=float(row.y))

    for row in edges.itertuples(index=False):
        u = str(row.u)
        v = str(row.v)
        if u not in graph or v not in graph or u == v:
            continue
        attrs = {
            "length_m": float(row.length_m),
            "walking_time_minutes": float(row.walking_time_minutes),
        }
        if hasattr(row, "highway"):
            attrs["highway"] = str(getattr(row, "highway"))
        if hasattr(row, "name"):
            attrs["name"] = str(getattr(row, "name"))

        if graph.has_edge(u, v):
            if attrs["walking_time_minutes"] < graph[u][v].get("walking_time_minutes", float("inf")):
                graph[u][v].update(attrs)
        else:
            graph.add_edge(u, v, **attrs)

    return graph


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()

    raw_edges = gpd.read_file(require_file(OSM_WALKING_EDGES_FILE))
    raw_nodes = gpd.read_file(require_file(OSM_WALKING_NODES_FILE))

    nodes = prepare_nodes(raw_nodes)
    edges = prepare_edges(raw_edges)
    used_nodes = set(edges["u"]) | set(edges["v"])
    nodes = nodes[nodes["node_id"].isin(used_nodes)].copy()
    edges = edges[edges["u"].isin(set(nodes["node_id"])) & edges["v"].isin(set(nodes["node_id"]))].copy()

    graph = build_graph(nodes, edges)
    safe_write_gdf(edges, OSM_WALKING_EDGES_CLEAN_FILE, layer="osm_walking_edges")
    safe_write_gdf(nodes, OSM_WALKING_NODES_CLEAN_FILE, layer="osm_walking_nodes")

    try:
        nx.write_graphml(graph, OSM_WALKING_GRAPH_FILE)
        print(f"Saved GraphML: {OSM_WALKING_GRAPH_FILE}")
    except Exception as exc:
        print(f"Could not save GraphML ({exc}). Clean edge/node GeoPackages were still saved.")

    print(
        "Prepared walking network: "
        f"{graph.number_of_nodes()} nodes, {graph.number_of_edges()} undirected edges."
    )


if __name__ == "__main__":
    main()
