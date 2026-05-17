from __future__ import annotations

import pandas as pd

from config import (
    BYDELE_FILE,
    CLASSIFIED_ACCESSIBILITY_TABLE,
    CRS_METRIC,
    ORIGINS_GRID_FILE,
    ORIGINS_POINTS_FILE,
    TABLES_DIR,
    ensure_directories,
)
from origin_quality import (
    calculate_district_overlaps,
    dissolved_boundary,
    load_districts,
    load_existing_origin_snaps,
)
from utils import import_geopandas, require_file, safe_write_csv


def load_optional_csv(path):
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def inference_basis(row) -> str:
    reasons = []
    if row["municipality_overlap_share"] < 0.95:
        reasons.append("partial municipality overlap")
    if row["overlap_share"] < 0.10:
        reasons.append("low district overlap")
    if not bool(row["centroid_within_any_district"]):
        reasons.append("centroid outside dissolved district boundary")
    return "; ".join(reasons) if reasons else "no edge inference"


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()

    grid = gpd.read_file(require_file(ORIGINS_GRID_FILE)).to_crs(CRS_METRIC)
    points = gpd.read_file(require_file(ORIGINS_POINTS_FILE)).to_crs(CRS_METRIC)
    districts = load_districts()
    require_file(BYDELE_FILE)

    snapping_diagnostics = load_optional_csv(TABLES_DIR / "snapping_diagnostics.csv")
    accessibility = pd.read_csv(require_file(CLASSIFIED_ACCESSIBILITY_TABLE))
    district_summary = pd.read_csv(require_file(TABLES_DIR / "district_accessibility_summary.csv"))

    assignments, overlap_details = calculate_district_overlaps(grid, points, districts)
    snapped_points = load_existing_origin_snaps(points)
    if snapped_points is not None:
        assignments = assignments.merge(
            snapped_points[["origin_id", "nearest_node_id", "snap_distance_m"]],
            on="origin_id",
            how="left",
        )
    else:
        assignments["nearest_node_id"] = None
        assignments["snap_distance_m"] = None

    # The current district summary has 103 unassigned origins, which is too high
    # to treat as a minor issue. This likely happens because the origin grid was
    # created by keeping cells that intersect Copenhagen Municipality, while the
    # old district assignment used origin centroids. For edge cells, harbour
    # cells and irregular district boundaries, a grid cell can intersect the
    # municipality even if its centroid falls outside a Bydele polygon. District
    # assignment should therefore use largest-area overlap between grid cells
    # and Bydele polygons, not only centroid containment.
    unassigned = assignments[
        assignments["previous_district_assignment_if_available"].isna()
        | (assignments["previous_district_assignment_if_available"].astype(str).str.strip() == "")
    ].copy()

    boundary = dissolved_boundary(districts)
    unassigned_points = points[points["origin_id"].isin(unassigned["origin_id"])].copy()
    unassigned["point_within_copenhagen_boundary"] = unassigned_points.set_index("origin_id").geometry.within(
        boundary.geometry.iloc[0]
    ).reindex(unassigned["origin_id"]).to_numpy()
    unassigned["point_within_any_bydele_polygon"] = unassigned["centroid_within_any_district"]
    unassigned["edge_harbour_inference_basis"] = unassigned.apply(inference_basis, axis=1)

    overlap_lists = (
        overlap_details.assign(
            district_overlap=lambda df: df["district"].astype(str)
            + ":"
            + df["overlap_area_m2"].round(1).astype(str)
            + "m2"
        )
        .groupby("origin_id", as_index=False)
        .agg(
            intersecting_bydele_polygons=("district", lambda values: "|".join(sorted(map(str, values)))),
            bydele_overlap_areas=("district_overlap", lambda values: "|".join(values)),
        )
    )
    unassigned = unassigned.merge(overlap_lists, on="origin_id", how="left")

    unassigned_detail = overlap_details[overlap_details["origin_id"].isin(unassigned["origin_id"])].copy()
    unassigned_detail = unassigned_detail.sort_values(["origin_id", "overlap_area_m2"], ascending=[True, False])

    diagnostic_counts = pd.DataFrame(
        [
            {
                "metric": "origin_count",
                "value": int(points["origin_id"].nunique()),
            },
            {
                "metric": "origins_in_accessibility_table",
                "value": int(accessibility["origin_id"].nunique()),
            },
            {
                "metric": "reconstructed_previous_unassigned_origins",
                "value": int(len(unassigned)),
            },
            {
                "metric": "district_summary_unassigned_n_origins",
                "value": int(
                    district_summary.loc[
                        district_summary["district"].astype(str).str.lower() == "unassigned",
                        "n_origins",
                    ].max()
                    if (district_summary["district"].astype(str).str.lower() == "unassigned").any()
                    else 0
                ),
            },
            {
                "metric": "snapping_diagnostic_gt_100m_count",
                "value": int(
                    snapping_diagnostics.loc[
                        snapping_diagnostics["layer"].eq("origins_points_500m"),
                        "flagged_gt_100m_count",
                    ].iloc[0]
                    if not snapping_diagnostics.empty
                    and snapping_diagnostics["layer"].eq("origins_points_500m").any()
                    else 0
                ),
            },
        ]
    )

    all_diagnostics = assignments.drop(columns="geometry").copy()
    unassigned_summary = unassigned.drop(columns="geometry").sort_values("origin_id")

    safe_write_csv(all_diagnostics, TABLES_DIR / "origin_quality_diagnostics_all.csv")
    safe_write_csv(unassigned_summary, TABLES_DIR / "unassigned_origin_diagnostics.csv")
    safe_write_csv(unassigned_detail, TABLES_DIR / "unassigned_origin_overlap_details.csv")
    safe_write_csv(diagnostic_counts, TABLES_DIR / "origin_quality_diagnostic_counts.csv")

    print(
        "Saved origin-quality diagnostics: "
        f"{len(unassigned)} reconstructed previously unassigned origins."
    )


if __name__ == "__main__":
    main()
