from __future__ import annotations

import pandas as pd

from config import (
    AMENITY_LAYER_KEYS,
    BYDELE_FILE,
    BOUNDARY_FILE,
    CRS_METRIC,
    CRS_WGS84,
    OFFICIAL_CLEAN_FILES,
    OFFICIAL_DATASETS,
    PROCESSED_DIR,
    RAW_OFFICIAL_DIR,
    TABLES_DIR,
    ensure_directories,
)
from utils import (
    clip_to_boundary,
    dissolve_to_boundary,
    get_downloaded_resource,
    inspect_gdf,
    make_valid_geometries,
    read_metadata_table,
    read_vector_any,
    safe_write_csv,
    safe_write_gdf,
    standardize_amenities,
)


METADATA_FILE = RAW_OFFICIAL_DIR / "official_download_metadata.csv"


def load_raw_official(dataset_key: str, metadata: pd.DataFrame):
    path = get_downloaded_resource(metadata, dataset_key)
    data_format = metadata.loc[metadata["dataset_key"] == dataset_key, "format"].iloc[0]
    return read_vector_any(path, data_format=data_format)


def clean_bydele(metadata: pd.DataFrame):
    bydele = load_raw_official("bydele", metadata)
    print("Bydele columns:", list(bydele.columns))
    bydele = make_valid_geometries(bydele).to_crs(CRS_WGS84)
    safe_write_gdf(bydele, PROCESSED_DIR / "bydele_wgs84.gpkg", layer="bydele")

    bydele_metric = bydele.to_crs(CRS_METRIC)
    safe_write_gdf(bydele_metric, BYDELE_FILE, layer="bydele")

    boundary = dissolve_to_boundary(bydele_metric)
    safe_write_gdf(boundary, BOUNDARY_FILE, layer="copenhagen_boundary")
    safe_write_gdf(boundary.to_crs(CRS_WGS84), PROCESSED_DIR / "copenhagen_boundary_wgs84.gpkg", layer="copenhagen_boundary")
    return bydele, boundary


def clean_amenity_layer(dataset_key: str, metadata: pd.DataFrame, boundary) -> dict:
    spec = OFFICIAL_DATASETS[dataset_key]
    raw = load_raw_official(dataset_key, metadata)
    print(f"{dataset_key} columns:", list(raw.columns))

    inspection = inspect_gdf(spec["dataset_name"], raw)
    raw = make_valid_geometries(raw).to_crs(CRS_WGS84)
    clipped = clip_to_boundary(raw, boundary).to_crs(CRS_METRIC)

    original_path = PROCESSED_DIR / f"official_{dataset_key}_original_geometries.gpkg"
    safe_write_gdf(clipped.to_crs(CRS_WGS84), original_path, layer=f"official_{dataset_key}_original")

    standardized = standardize_amenities(
        clipped,
        amenity_type=spec["amenity_type"],
        source="official",
        dataset_label=spec["dataset_name"],
        id_prefix=f"official_{spec['amenity_type']}",
    )
    safe_write_gdf(standardized, OFFICIAL_CLEAN_FILES[dataset_key], layer=f"official_{dataset_key}")

    inspection["cleaned_row_count"] = len(standardized)
    inspection["cleaned_file"] = str(OFFICIAL_CLEAN_FILES[dataset_key])
    inspection["original_geometry_file"] = str(original_path)
    return inspection


def main() -> None:
    ensure_directories()
    metadata = read_metadata_table(METADATA_FILE)

    inspection_rows = []
    bydele_raw = load_raw_official("bydele", metadata)
    inspection_rows.append(inspect_gdf("Bydele", bydele_raw))
    _, boundary = clean_bydele(metadata)

    for dataset_key in AMENITY_LAYER_KEYS:
        inspection_rows.append(clean_amenity_layer(dataset_key, metadata, boundary))

    inspection = pd.DataFrame(inspection_rows)
    safe_write_csv(inspection, TABLES_DIR / "official_dataset_inspection.csv")
    print(f"Saved official inspection table with {len(inspection)} rows.")


if __name__ == "__main__":
    main()
