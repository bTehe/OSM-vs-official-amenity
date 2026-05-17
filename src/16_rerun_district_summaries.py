from __future__ import annotations

import pandas as pd

from config import CRS_METRIC, PROCESSED_DIR, TABLES_DIR, ensure_directories
from utils import import_geopandas, require_file, safe_write_csv


ORIGIN_SET_POINTS = {
    "full": PROCESSED_DIR / "origins_points_500m_full.gpkg",
    "clean100": PROCESSED_DIR / "origins_points_500m_clean100.gpkg",
    "clean250": PROCESSED_DIR / "origins_points_500m_clean250.gpkg",
}

ACCESSIBILITY_INPUTS = {
    "full": TABLES_DIR / "origin_accessibility_classified_full.csv",
    "clean100": TABLES_DIR / "origin_accessibility_classified_clean100.csv",
    "clean250": TABLES_DIR / "origin_accessibility_classified_clean250.csv",
}

SUMMARY_OUTPUTS = {
    "full": TABLES_DIR / "district_accessibility_summary_full_corrected.csv",
    "clean100": TABLES_DIR / "district_accessibility_summary_clean100.csv",
    "clean250": TABLES_DIR / "district_accessibility_summary_clean250.csv",
}


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def valid_district(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip()
    return (text != "") & (text.str.lower() != "unassigned") & (text.str.lower() != "no district overlap")


def summarize(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (district, amenity_type), group in data.groupby(["assigned_district", "amenity_type"], dropna=False):
        official_share = group["official_access_15"].mean()
        osm_share = group["osm_access_15"].mean()
        rows.append(
            {
                "district": district,
                "amenity_type": amenity_type,
                "n_origins": int(group["origin_id"].nunique()),
                "official_share_accessible_15": official_share,
                "osm_share_accessible_15": osm_share,
                "difference_share_percentage_points": (osm_share - official_share) * 100.0,
                "share_osm_false_access": (group["distortion_class"] == "osm_false_access").mean(),
                "share_osm_hidden_access": (group["distortion_class"] == "osm_hidden_access").mean(),
                "median_time_difference": group["difference_minutes"].median(),
            }
        )
    return pd.DataFrame(rows).sort_values(["district", "amenity_type"]).reset_index(drop=True)


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()
    remaining_unassigned = []

    # District-level summaries are used for interpretation of spatial inequality
    # across Copenhagen. If many origins are unassigned, district-level results
    # are incomplete and may overrepresent or underrepresent specific areas.
    # Correcting district assignment by largest overlap makes the summaries more
    # reliable.
    for origin_set in ["full", "clean100", "clean250"]:
        origins = gpd.read_file(require_file(ORIGIN_SET_POINTS[origin_set])).to_crs(CRS_METRIC)
        assignments = origins[
            [
                "origin_id",
                "assigned_district",
                "overlap_share",
                "largest_overlap_area_m2",
                "low_overlap_edge_cell",
            ]
        ].copy()
        accessibility = pd.read_csv(require_file(ACCESSIBILITY_INPUTS[origin_set]))
        accessibility["official_access_15"] = accessibility["official_access_15"].apply(to_bool)
        accessibility["osm_access_15"] = accessibility["osm_access_15"].apply(to_bool)
        accessibility["difference_minutes"] = pd.to_numeric(accessibility["difference_minutes"], errors="coerce")

        data = accessibility.merge(assignments, on="origin_id", how="left")
        assigned_mask = valid_district(data["assigned_district"])
        if (~assigned_mask).any():
            remaining = data.loc[
                ~assigned_mask,
                [
                    "origin_set",
                    "origin_id",
                    "amenity_type",
                    "assigned_district",
                    "overlap_share",
                    "largest_overlap_area_m2",
                    "low_overlap_edge_cell",
                ],
            ].drop_duplicates()
            remaining_unassigned.append(remaining)

        summary = summarize(data[assigned_mask].copy())
        safe_write_csv(summary, SUMMARY_OUTPUTS[origin_set])
        print(
            f"Saved corrected district summary for {origin_set}: "
            f"{summary['district'].nunique() if not summary.empty else 0} districts."
        )

    if remaining_unassigned:
        out = pd.concat(remaining_unassigned, ignore_index=True)
    else:
        out = pd.DataFrame(
            columns=[
                "origin_set",
                "origin_id",
                "amenity_type",
                "assigned_district",
                "overlap_share",
                "largest_overlap_area_m2",
                "low_overlap_edge_cell",
            ]
        )
    safe_write_csv(out, TABLES_DIR / "remaining_unassigned_origins.csv")


if __name__ == "__main__":
    main()
