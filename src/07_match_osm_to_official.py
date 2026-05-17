from __future__ import annotations

import math

import pandas as pd

from config import (
    AMENITY_LAYER_KEYS,
    AMENITY_TYPE_BY_LAYER,
    CRS_METRIC,
    CRS_WGS84,
    MATCH_THRESHOLDS_M,
    OSM_CLEAN_FILES,
    OFFICIAL_CLEAN_FILES,
    MAPS_DIR,
    TABLES_DIR,
    ensure_directories,
)
from utils import import_geopandas, safe_write_csv, safe_write_gdf


def one_to_one_nearest_matches(official, osm, threshold_m: float) -> list[dict]:
    try:
        from scipy.spatial import cKDTree
    except ImportError as exc:
        raise ImportError("POI matching requires scipy. Install dependencies from requirements.txt.") from exc

    official = official.to_crs(CRS_METRIC).reset_index(drop=True)
    osm = osm.to_crs(CRS_METRIC).reset_index(drop=True)
    if official.empty or osm.empty:
        return []

    official_coords = list(zip(official.geometry.x, official.geometry.y))
    osm_coords = list(zip(osm.geometry.x, osm.geometry.y))
    tree = cKDTree(osm_coords)

    candidate_pairs = []
    for official_idx, coord in enumerate(official_coords):
        osm_indices = tree.query_ball_point(coord, r=threshold_m)
        ox, oy = coord
        for osm_idx in osm_indices:
            sx, sy = osm_coords[osm_idx]
            distance = math.hypot(ox - sx, oy - sy)
            candidate_pairs.append((distance, official_idx, osm_idx))

    matched_official = set()
    matched_osm = set()
    matches = []
    for distance, official_idx, osm_idx in sorted(candidate_pairs, key=lambda item: item[0]):
        if official_idx in matched_official or osm_idx in matched_osm:
            continue
        matched_official.add(official_idx)
        matched_osm.add(osm_idx)
        matches.append(
            {
                "official_index": official_idx,
                "osm_index": osm_idx,
                "match_distance_m": distance,
                "official_amenity_id": official.iloc[official_idx]["amenity_id"],
                "osm_amenity_id": osm.iloc[osm_idx]["amenity_id"],
            }
        )
    return matches


def build_match_status_layer(official, osm, matches, amenity_type: str):
    gpd = import_geopandas()
    official = official.to_crs(CRS_WGS84).reset_index(drop=True)
    osm = osm.to_crs(CRS_WGS84).reset_index(drop=True)
    official_matched = {match["official_index"] for match in matches}
    osm_matched = {match["osm_index"] for match in matches}

    official_status = official.copy()
    official_status["match_status"] = [
        "matched_official" if idx in official_matched else "unmatched_official"
        for idx in range(len(official_status))
    ]

    osm_status = osm.copy()
    osm_status["match_status"] = [
        "matched_osm" if idx in osm_matched else "unmatched_osm"
        for idx in range(len(osm_status))
    ]

    combined = pd.concat([official_status, osm_status], ignore_index=True)
    combined["amenity_type"] = amenity_type
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=CRS_WGS84)


def make_interactive_poi_map(status_layers) -> None:
    try:
        import folium
    except ImportError:
        print("folium is not installed; skipping matched_unmatched_pois.html.")
        return

    if not status_layers:
        return

    all_points = pd.concat(status_layers, ignore_index=True)
    if all_points.empty:
        return

    center = [all_points.geometry.y.mean(), all_points.geometry.x.mean()]
    fmap = folium.Map(location=center, zoom_start=12, tiles="CartoDB positron")
    colors = {
        "matched_official": "#1b9e77",
        "matched_osm": "#66a61e",
        "unmatched_official": "#d95f02",
        "unmatched_osm": "#7570b3",
    }

    for _, row in all_points.iterrows():
        tooltip = (
            f"{row.get('amenity_type', '')} | {row.get('source', '')} | "
            f"{row.get('match_status', '')} | {row.get('name', '')}"
        )
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=4,
            color=colors.get(row["match_status"], "#333333"),
            fill=True,
            fill_opacity=0.75,
            tooltip=tooltip,
        ).add_to(fmap)

    output = MAPS_DIR / "matched_unmatched_pois.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(output)
    print(f"Saved {output}")


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()
    summary_rows = []
    detail_rows = []
    status_layers = []

    for layer_key in AMENITY_LAYER_KEYS:
        amenity_type = AMENITY_TYPE_BY_LAYER[layer_key]
        official = gpd.read_file(OFFICIAL_CLEAN_FILES[layer_key]).to_crs(CRS_METRIC)
        osm = gpd.read_file(OSM_CLEAN_FILES[layer_key]).to_crs(CRS_METRIC)
        threshold = MATCH_THRESHOLDS_M[amenity_type]

        matches = one_to_one_nearest_matches(official, osm, threshold)
        for match in matches:
            match["amenity_type"] = amenity_type
            match["threshold_m"] = threshold
        detail_rows.extend(matches)

        matched_count = len(matches)
        official_count = len(official)
        osm_count = len(osm)
        distances = [match["match_distance_m"] for match in matches]
        summary_rows.append(
            {
                "amenity_type": amenity_type,
                "threshold_m": threshold,
                "official_count": official_count,
                "osm_count": osm_count,
                "matched_count": matched_count,
                "unmatched_official_count": official_count - matched_count,
                "unmatched_osm_count": osm_count - matched_count,
                "recall": matched_count / official_count if official_count else None,
                "precision": matched_count / osm_count if osm_count else None,
                "median_match_distance": pd.Series(distances).median() if distances else None,
            }
        )

        status_layer = build_match_status_layer(official, osm, matches, amenity_type)
        status_layers.append(status_layer)

    safe_write_csv(pd.DataFrame(summary_rows), TABLES_DIR / "poi_completeness_summary.csv")
    safe_write_csv(pd.DataFrame(detail_rows), TABLES_DIR / "poi_match_details.csv")

    if status_layers:
        combined_status = pd.concat(status_layers, ignore_index=True)
        combined_status = gpd.GeoDataFrame(combined_status, geometry="geometry", crs=CRS_WGS84)
        safe_write_gdf(combined_status, MAPS_DIR / "matched_unmatched_pois.gpkg", layer="matched_unmatched_pois")
        make_interactive_poi_map(status_layers)

    print("Saved POI completeness summary and match details.")


if __name__ == "__main__":
    main()
