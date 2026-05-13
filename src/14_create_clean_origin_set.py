from __future__ import annotations

import pandas as pd

from config import (
    CRS_METRIC,
    ORIGINS_GRID_FILE,
    PROCESSED_DIR,
    TABLES_DIR,
    ensure_directories,
)
from utils import import_geopandas, require_file, safe_write_csv, safe_write_gdf


POINTS_WITH_SNAPS = PROCESSED_DIR / "origin_snapping_distances_all.gpkg"
GRID_WITH_DISTRICT = PROCESSED_DIR / "origins_grid_500m_with_district_overlap.gpkg"


ORIGIN_SET_OUTPUTS = {
    "full": {
        "points": PROCESSED_DIR / "origins_points_500m_full.gpkg",
        "grid": PROCESSED_DIR / "origins_grid_500m_full.gpkg",
    },
    "clean100": {
        "points": PROCESSED_DIR / "origins_points_500m_clean100.gpkg",
        "grid": PROCESSED_DIR / "origins_grid_500m_clean100.gpkg",
    },
    "clean250": {
        "points": PROCESSED_DIR / "origins_points_500m_clean250.gpkg",
        "grid": PROCESSED_DIR / "origins_grid_500m_clean250.gpkg",
    },
}


def valid_district(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip()
    return (text != "") & (text.str.lower() != "no district overlap") & (text.str.lower() != "unassigned")


def summarize_set(origin_set: str, keep_mask, all_points) -> dict:
    removed = ~keep_mask
    kept = all_points[keep_mask]
    unassigned = ~valid_district(kept["assigned_district"])
    return {
        "origin_set": origin_set,
        "n_origins": int(len(kept)),
        "removed_due_to_snap_gt_100m": int((removed & all_points["snap_gt_100m"]).sum()),
        "removed_due_to_snap_gt_250m": int((removed & all_points["snap_gt_250m"]).sum()),
        "removed_due_to_low_overlap": int((removed & all_points["low_overlap_edge_cell"]).sum()),
        "removed_total": int(removed.sum()),
        "share_removed": float(removed.mean()) if len(all_points) else 0.0,
        "median_snap_distance_m": float(kept["snap_distance_m"].median()) if len(kept) else None,
        "max_snap_distance_m": float(kept["snap_distance_m"].max()) if len(kept) else None,
        "n_unassigned_districts": int(unassigned.sum()),
    }


def save_origin_set(origin_set: str, keep_mask, points, grid, summaries: list[dict]) -> None:
    outputs = ORIGIN_SET_OUTPUTS[origin_set]
    kept_points = points[keep_mask].copy()
    kept_grid = grid[grid["origin_id"].isin(kept_points["origin_id"])].copy()
    safe_write_gdf(kept_points, outputs["points"], layer=outputs["points"].stem)
    safe_write_gdf(kept_grid, outputs["grid"], layer=outputs["grid"].stem)
    summaries.append(summarize_set(origin_set, keep_mask, points))


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()

    points = gpd.read_file(require_file(POINTS_WITH_SNAPS)).to_crs(CRS_METRIC)
    grid_base = gpd.read_file(require_file(GRID_WITH_DISTRICT)).to_crs(CRS_METRIC)
    require_file(ORIGINS_GRID_FILE)

    points["snap_gt_100m"] = points["snap_distance_m"] > 100
    points["snap_gt_250m"] = points["snap_distance_m"] > 250
    points["low_overlap_edge_cell"] = points["overlap_share"] < 0.10
    valid_assignment = valid_district(points["assigned_district"])

    grid_attrs = points.drop(columns="geometry")
    grid = grid_base[["origin_id", "geometry"]].merge(grid_attrs, on="origin_id", how="left")
    grid = gpd.GeoDataFrame(grid, geometry="geometry", crs=CRS_METRIC)

    # Do not simply delete problematic origins without preserving the original
    # baseline. The project should report both the original result and cleaned
    # sensitivity results. This makes the methodology transparent and shows
    # whether conclusions are robust to removing origins that are poorly
    # connected to the walking network or poorly assigned to districts.
    full_keep = pd.Series(True, index=points.index)
    clean100_keep = (~points["snap_gt_100m"]) & (~points["low_overlap_edge_cell"]) & valid_assignment
    clean250_keep = (~points["snap_gt_250m"]) & (~points["low_overlap_edge_cell"]) & valid_assignment

    summaries: list[dict] = []
    save_origin_set("full", full_keep, points, grid, summaries)
    save_origin_set("clean100", clean100_keep, points, grid, summaries)
    save_origin_set("clean250", clean250_keep, points, grid, summaries)

    safe_write_csv(pd.DataFrame(summaries), TABLES_DIR / "origin_cleaning_summary.csv")
    print("Saved full, clean100, and clean250 origin sets.")


if __name__ == "__main__":
    main()
