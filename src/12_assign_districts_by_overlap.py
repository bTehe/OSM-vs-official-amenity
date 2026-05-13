from __future__ import annotations

from config import (
    CRS_METRIC,
    ORIGINS_GRID_FILE,
    ORIGINS_POINTS_FILE,
    PROCESSED_DIR,
    TABLES_DIR,
    ensure_directories,
)
from origin_quality import (
    MIN_DISTRICT_OVERLAP_SHARE,
    attach_assignment_to_points,
    calculate_district_overlaps,
    load_districts,
)
from utils import import_geopandas, require_file, safe_write_csv, safe_write_gdf


GRID_OUTPUT = PROCESSED_DIR / "origins_grid_500m_with_district_overlap.gpkg"
POINTS_OUTPUT = PROCESSED_DIR / "origins_points_500m_with_district_overlap.gpkg"


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()

    grid = gpd.read_file(require_file(ORIGINS_GRID_FILE)).to_crs(CRS_METRIC)
    points = gpd.read_file(require_file(ORIGINS_POINTS_FILE)).to_crs(CRS_METRIC)
    districts = load_districts()

    # Largest-area overlap is more robust than centroid-within assignment for a
    # regular grid clipped to an irregular coastal municipality. Copenhagen
    # contains harbour basins, islands, and boundary-edge cells, so some grid
    # centroids may fall outside a district even though the cell meaningfully
    # overlaps one. Using largest-area overlap avoids losing valid edge cells
    # from district-level summaries.
    assignments, overlap_details = calculate_district_overlaps(
        grid,
        points,
        districts,
        min_overlap_share=MIN_DISTRICT_OVERLAP_SHARE,
    )

    grid_out = grid.merge(assignments.drop(columns="geometry"), on="origin_id", how="left")
    points_out = attach_assignment_to_points(points, assignments)

    safe_write_gdf(grid_out, GRID_OUTPUT, layer="origins_grid_500m_with_district_overlap")
    safe_write_gdf(points_out, POINTS_OUTPUT, layer="origins_points_500m_with_district_overlap")

    required_columns = [
        "origin_id",
        "assigned_district",
        "largest_overlap_area_m2",
        "origin_cell_area_m2",
        "overlap_share",
        "low_overlap_edge_cell",
        "centroid_within_any_district",
        "previous_district_assignment_if_available",
        "district_assignment_changed",
    ]
    diagnostics = assignments.drop(columns="geometry")[required_columns].sort_values("origin_id")
    safe_write_csv(diagnostics, TABLES_DIR / "district_assignment_diagnostics.csv")
    safe_write_csv(overlap_details, TABLES_DIR / "district_assignment_overlap_details.csv")

    print(
        "Saved largest-overlap district assignment for "
        f"{len(assignments)} origin grid cells."
    )


if __name__ == "__main__":
    main()
