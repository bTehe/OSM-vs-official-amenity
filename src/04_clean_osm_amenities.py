from __future__ import annotations

import pandas as pd

from config import (
    AMENITY_LAYER_KEYS,
    AMENITY_TYPE_BY_LAYER,
    OSM_CLEAN_FILES,
    OSM_RAW_FILES,
    PROCESSED_DIR,
    TABLES_DIR,
    ensure_directories,
)
from utils import (
    clip_to_boundary,
    import_geopandas,
    inspect_gdf,
    load_boundary,
    make_valid_geometries,
    require_file,
    safe_write_csv,
    safe_write_gdf,
    standardize_amenities,
)


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()
    boundary = load_boundary(metric=True)
    inspection_rows = []

    for layer_key in AMENITY_LAYER_KEYS:
        source_path = require_file(OSM_RAW_FILES[layer_key])
        raw = gpd.read_file(source_path)
        print(f"OSM {layer_key} columns:", list(raw.columns))

        inspection = inspect_gdf(f"osm_{layer_key}", raw)
        raw = make_valid_geometries(raw)
        clipped = clip_to_boundary(raw, boundary)

        original_path = PROCESSED_DIR / f"osm_{layer_key}_original_geometries.gpkg"
        safe_write_gdf(clipped, original_path, layer=f"osm_{layer_key}_original")

        amenity_type = AMENITY_TYPE_BY_LAYER[layer_key]
        standardized = standardize_amenities(
            clipped,
            amenity_type=amenity_type,
            source="osm",
            dataset_label=f"osm_{layer_key}",
            id_prefix=f"osm_{amenity_type}",
        )
        safe_write_gdf(standardized, OSM_CLEAN_FILES[layer_key], layer=f"osm_{layer_key}")

        inspection["cleaned_row_count"] = len(standardized)
        inspection["cleaned_file"] = str(OSM_CLEAN_FILES[layer_key])
        inspection["original_geometry_file"] = str(original_path)
        inspection_rows.append(inspection)

    safe_write_csv(pd.DataFrame(inspection_rows), TABLES_DIR / "osm_dataset_inspection.csv")
    print(f"Saved cleaned OSM amenity layers for {len(inspection_rows)} amenity types.")


if __name__ == "__main__":
    main()
