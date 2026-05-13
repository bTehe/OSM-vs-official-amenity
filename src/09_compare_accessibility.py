from __future__ import annotations

import argparse

import pandas as pd

from config import (
    ACCESSIBILITY_TABLE,
    BYDELE_FILE,
    CLASSIFIED_ACCESSIBILITY_GPKG,
    CLASSIFIED_ACCESSIBILITY_TABLE,
    COMPOSITE_DISAGREEMENT_GPKG,
    COMPOSITE_DISAGREEMENT_TABLE,
    CRS_METRIC,
    ORIGINS_GRID_FILE,
    ORIGINS_POINTS_SNAPPED_FILE,
    TABLES_DIR,
    ensure_directories,
)
from utils import (
    DISTRICT_NAME_CANDIDATES,
    classify_accessibility,
    find_column,
    import_geopandas,
    require_file,
    safe_write_csv,
    safe_write_gdf,
)


DISAGREEMENT_CLASSES = {"osm_false_access", "osm_hidden_access"}


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def classify_rows(accessibility: pd.DataFrame) -> pd.DataFrame:
    out = accessibility.copy()
    out["official_access_15"] = out["official_access_15"].apply(to_bool)
    out["osm_access_15"] = out["osm_access_15"].apply(to_bool)
    out["distortion_class"] = [
        classify_accessibility(official, osm)
        for official, osm in zip(out["official_access_15"], out["osm_access_15"])
    ]
    out["disagrees"] = out["distortion_class"].isin(DISAGREEMENT_CLASSES)
    return out


def save_classified_geodata(classified: pd.DataFrame):
    gpd = import_geopandas()
    origins = gpd.read_file(require_file(ORIGINS_POINTS_SNAPPED_FILE)).to_crs(CRS_METRIC)
    gdf = classified.merge(origins[["origin_id", "geometry"]], on="origin_id", how="left")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=CRS_METRIC)
    safe_write_gdf(gdf, CLASSIFIED_ACCESSIBILITY_GPKG, layer="origin_accessibility_classified")


def save_composite_disagreement(classified: pd.DataFrame):
    gpd = import_geopandas()
    composite = (
        classified.assign(disagreement=classified["distortion_class"].isin(DISAGREEMENT_CLASSES).astype(int))
        .groupby("origin_id", as_index=False)["disagreement"]
        .sum()
        .rename(columns={"disagreement": "composite_disagreement_score"})
    )
    safe_write_csv(composite, COMPOSITE_DISAGREEMENT_TABLE)

    grid = gpd.read_file(require_file(ORIGINS_GRID_FILE)).to_crs(CRS_METRIC)
    composite_gdf = grid.merge(composite, on="origin_id", how="left")
    composite_gdf["composite_disagreement_score"] = composite_gdf["composite_disagreement_score"].fillna(0).astype(int)
    safe_write_gdf(composite_gdf, COMPOSITE_DISAGREEMENT_GPKG, layer="composite_disagreement")
    return composite_gdf


def district_summary(classified: pd.DataFrame) -> pd.DataFrame:
    gpd = import_geopandas()
    origins = gpd.read_file(require_file(ORIGINS_POINTS_SNAPPED_FILE)).to_crs(CRS_METRIC)
    bydele = gpd.read_file(require_file(BYDELE_FILE)).to_crs(CRS_METRIC)
    district_col = find_column(bydele.columns, DISTRICT_NAME_CANDIDATES)
    if district_col is None:
        bydele = bydele.reset_index().rename(columns={"index": "district"})
        district_col = "district"

    districts = bydele[[district_col, "geometry"]].rename(columns={district_col: "district"})
    origin_districts = gpd.sjoin(
        origins[["origin_id", "geometry"]],
        districts,
        how="left",
        predicate="intersects",
    )[["origin_id", "district"]].drop_duplicates(subset=["origin_id"])
    data = classified.merge(origin_districts, on="origin_id", how="left")
    data["district"] = data["district"].fillna("Unassigned")
    data["difference_minutes"] = pd.to_numeric(data["difference_minutes"], errors="coerce")

    rows = []
    for (district, amenity_type), group in data.groupby(["district", "amenity_type"], dropna=False):
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
    return pd.DataFrame(rows)


def optional_spatial_autocorrelation(composite_gdf) -> None:
    try:
        from esda.moran import Moran, Moran_Local
        from libpysal.weights import Queen
    except ImportError:
        print("libpysal/esda are not installed; skipping optional Moran analysis.")
        return

    weights = Queen.from_dataframe(composite_gdf, use_index=False)
    weights.transform = "r"
    values = composite_gdf["composite_disagreement_score"].astype(float).to_numpy()
    moran = Moran(values, weights)
    local = Moran_Local(values, weights)

    summary = pd.DataFrame(
        [
            {
                "statistic": "global_moran_i",
                "value": moran.I,
                "p_sim": moran.p_sim,
                "permutations": moran.permutations,
            }
        ]
    )
    safe_write_csv(summary, TABLES_DIR / "spatial_autocorrelation_summary.csv")

    lisa = composite_gdf.copy()
    lisa["local_moran_i"] = local.Is
    lisa["local_moran_p_sim"] = local.p_sim
    lisa["local_moran_quadrant"] = local.q
    safe_write_gdf(lisa, TABLES_DIR / "local_moran_composite.gpkg", layer="local_moran_composite")
    print("Saved optional Moran and Local Moran outputs.")


def write_limitations_notes() -> None:
    text = """# Limitations notes

1. Official datasets are treated as reference data but may also be incomplete or maintained for municipal purposes.
2. OSM is volunteered geographic information and can contain missing, duplicated or differently classified amenities.
3. Sports facilities are especially sensitive to classification because OSM may map whole sports centres, halls or individual pitches differently.
4. Using the same OSM walking network isolates amenity-data distortion but does not test OSM network distortion.
5. Point/polygon conversion can affect measured walking distance.
6. A 500 m grid reduces but does not eliminate aggregation bias.
7. The 15-minute threshold depends on assumed walking speed.
8. Opening hours are not included unless available consistently in both sources.
9. Some amenities may be private, restricted or not publicly accessible even if they appear in the data.
10. Results should be interpreted as data-source sensitivity, not as absolute ground truth.

## Origin-grid and snapping quality

1. The original analysis used a 500 m grid of origins.
2. Some grid cells were located near harbour, water, parks, industrial areas or irregular municipal edges.
3. These cells can produce large snapping distances to the walking network.
4. District assignment based only on centroids can leave valid edge cells unassigned.
5. To reduce this problem, the revised analysis assigns districts by largest-area overlap and runs a sensitivity analysis excluding origins with large snapping distances.
6. Results should therefore be interpreted as grid-based accessibility estimates, not exact household-level accessibility.
"""
    output = TABLES_DIR / "limitations_notes.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moran", action="store_true", help="Run optional spatial autocorrelation analysis.")
    args = parser.parse_args()

    ensure_directories()
    accessibility = pd.read_csv(require_file(ACCESSIBILITY_TABLE))
    classified = classify_rows(accessibility)
    safe_write_csv(classified, CLASSIFIED_ACCESSIBILITY_TABLE)
    save_classified_geodata(classified)

    composite_gdf = save_composite_disagreement(classified)
    summary = district_summary(classified)
    safe_write_csv(summary, TABLES_DIR / "district_accessibility_summary.csv")
    write_limitations_notes()

    if args.moran:
        optional_spatial_autocorrelation(composite_gdf)

    print("Saved classified accessibility, composite disagreement, district summary, and limitations notes.")


if __name__ == "__main__":
    main()
