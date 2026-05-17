from __future__ import annotations

from config import (
    AMENITY_LAYER_KEYS,
    CRS_WGS84,
    OSM_RAW_FILES,
    OSM_WALKING_EDGES_FILE,
    OSM_WALKING_NODES_FILE,
    PBF_PATH,
    ensure_directories,
)
from utils import (
    clip_to_boundary,
    ensure_crs,
    import_geopandas,
    load_boundary,
    make_valid_geometries,
    require_file,
    resolve_edge_endpoint_columns,
    resolve_node_id_column,
    safe_write_gdf,
)


OSM_AMENITY_FILTERS = {
    "libraries": {"amenity": ["library"]},
    "playgrounds": {"leisure": ["playground"]},
    "sports_facilities": {"leisure": ["sports_centre", "sports_hall"]},
}


def import_pyrosm():
    try:
        from pyrosm import OSM
    except ImportError as exc:
        raise ImportError(
            "OSM extraction requires pyrosm. Install it with the conda-forge environment "
            "recommended in README.md. The script will not use Overpass or download a PBF."
        ) from exc
    return OSM


def load_osm_reader(boundary_wgs84):
    OSM = import_pyrosm()
    minx, miny, maxx, maxy = boundary_wgs84.total_bounds
    return OSM(str(PBF_PATH), bounding_box=[minx, miny, maxx, maxy])


def extract_amenities(osm, boundary_wgs84) -> None:
    gpd = import_geopandas()
    for layer_key in AMENITY_LAYER_KEYS:
        custom_filter = OSM_AMENITY_FILTERS[layer_key]
        print(f"Extracting OSM {layer_key}: {custom_filter}")
        data = osm.get_data_by_custom_criteria(
            custom_filter=custom_filter,
            filter_type="keep",
            keep_nodes=True,
            keep_ways=True,
            keep_relations=True,
        )
        if data is None or len(data) == 0:
            data = gpd.GeoDataFrame(geometry=[], crs=CRS_WGS84)
        data = ensure_crs(data, CRS_WGS84)
        data = clip_to_boundary(data, boundary_wgs84)
        safe_write_gdf(data.to_crs(CRS_WGS84), OSM_RAW_FILES[layer_key], layer=f"osm_{layer_key}")
        print(f"Saved {len(data)} OSM {layer_key} features.")


def extract_walking_network(osm, boundary_wgs84) -> None:
    print("Extracting OSM walking network from local PBF.")
    nodes, edges = osm.get_network(network_type="walking", nodes=True)
    nodes = make_valid_geometries(ensure_crs(nodes, CRS_WGS84))
    edges = make_valid_geometries(ensure_crs(edges, CRS_WGS84))

    boundary_geom = boundary_wgs84.geometry.iloc[0]
    edges = edges[edges.intersects(boundary_geom)].copy()

    try:
        u_col, v_col = resolve_edge_endpoint_columns(edges)
        node_col = resolve_node_id_column(nodes)
        used_nodes = set(edges[u_col].astype(str)) | set(edges[v_col].astype(str))
        nodes = nodes[nodes[node_col].astype(str).isin(used_nodes)].copy()
    except ValueError:
        nodes = nodes[nodes.intersects(boundary_geom)].copy()

    safe_write_gdf(edges.to_crs(CRS_WGS84), OSM_WALKING_EDGES_FILE, layer="osm_walking_edges")
    safe_write_gdf(nodes.to_crs(CRS_WGS84), OSM_WALKING_NODES_FILE, layer="osm_walking_nodes")
    print(f"Saved walking network: {len(nodes)} nodes, {len(edges)} edges.")


def main() -> None:
    ensure_directories()
    require_file(
        PBF_PATH,
        f"Local OSM PBF not found at {PBF_PATH}. Place the Denmark OSM PBF there and "
        "name it denmark-latest.osm.pbf. This project does not download the PBF.",
    )
    boundary_wgs84 = load_boundary(metric=False).to_crs(CRS_WGS84)
    osm = load_osm_reader(boundary_wgs84)
    extract_amenities(osm, boundary_wgs84)
    extract_walking_network(osm, boundary_wgs84)


if __name__ == "__main__":
    main()
