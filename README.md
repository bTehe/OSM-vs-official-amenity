# Copenhagen OSM vs Official Amenity Access

This project investigates how sensitive 15-minute walking accessibility estimates are to the choice of amenity dataset.

The analysis compares two versions of the same accessibility workflow for Copenhagen Municipality:

1. an OSM walking network with official Copenhagen amenity data,
2. the same OSM walking network with OSM amenity data.

The walking network is held constant in both cases. This means the comparison focuses on amenity completeness and classification, rather than differences between OSM streets and an official street network.

The amenity categories analysed are:

- libraries,
- playgrounds,
- sports facilities.

## How to run the project

The project can be run either from the command line or through the notebook.

To run the full command-line pipeline:

```bash
python src/run_pipeline.py
```

To run the notebook version, open:

```text
notebooks/copenhagen_osm_accessibility_pipeline.ipynb
```

The notebook provides a readable walkthrough of the workflow. The main implementation is kept in the scripts in `src/`, which makes the pipeline easier to rerun, test, and maintain.

## Data requirements

Official Copenhagen amenity and boundary data are downloaded automatically from Open Data DK / Københavns Kommune CKAN:

```text
https://admin.opendata.dk/api/3/action
```

The downloader searches for available resources in the following order:

1. GeoJSON,
2. SHP,
3. CSV.

Source links and local filenames are saved in:

```text
data/raw/official/official_download_metadata.csv
outputs/tables/official_download_metadata.csv
```

The OpenStreetMap PBF extract is not downloaded automatically. The Denmark PBF file must be placed manually at:

```text
data/raw/osm/denmark-latest.osm.pbf
```

The OSM extraction script checks this path before running. If the file is missing, the script stops with a clear error message.

## Environment

On Windows, the recommended setup uses `conda-forge`, especially because geospatial dependencies and `pyrosm` are easier to install through conda.

```bash
conda create -n cph-osm-access -c conda-forge python=3.11 geopandas pyrosm networkx scipy matplotlib contextily folium mapclassify libpysal esda requests
conda activate cph-osm-access
```

A pip-based setup can also be used if the local geospatial Python environment is already configured correctly:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Pipeline order

The processing order is structured so that the Copenhagen boundary is available before the OSM PBF extract is clipped to the study area.

```text
src/01_download_official_data.py
src/03_clean_official_amenities.py
src/02_extract_osm_data.py
src/04_clean_osm_amenities.py
src/05_prepare_walking_network.py
src/06_create_origin_grid.py
src/07_match_osm_to_official.py
src/08_compute_accessibility.py
src/09_compare_accessibility.py
src/10_make_maps.py
src/11_diagnose_origin_quality.py
src/12_assign_districts_by_overlap.py
src/13_diagnose_snapping_outliers.py
src/14_create_clean_origin_set.py
src/15_rerun_accessibility_for_clean_origins.py
src/16_rerun_district_summaries.py
src/17_compare_baseline_vs_cleaned.py
src/18_make_cleaned_maps.py
```

Optional Moran / LISA analysis can be run with:

```bash
python src/09_compare_accessibility.py --moran
```

## Amenity definitions

Official Copenhagen layers:

| Amenity type | Official dataset |
|---|---|
| Libraries | Biblioteker |
| Playgrounds | Legepladser |
| Sports facilities | Idrætsanlæg |
| Districts and boundary | Bydele |

OSM tags:

| Amenity type | OSM tags |
|---|---|
| Libraries | `amenity=library` |
| Playgrounds | `leisure=playground` |
| Sports facilities | `leisure=sports_centre` or `leisure=sports_hall` |

The main analysis excludes `leisure=pitch`. In Copenhagen, pitches can represent individual fields rather than complete sports facilities, so including them would change the meaning of the sports-facility comparison.

## Origin-quality correction

The first baseline run identified two origin-quality issues:

- 103 origin points were assigned to `Unassigned`,
- 87 of 475 origins snapped more than 100 m from the walking network.

These issues were addressed in the final workflow.

District assignment is now based on the largest area overlap between each 500 m grid cell and the Bydele district polygons. This is more reliable than centroid-based assignment for coastal and harbour-edge cells.

The project keeps three origin sets:

| Origin set | Description |
|---|---|
| `full` | All 475 origins, retained as the baseline |
| `clean100` | Removes origins snapped more than 100 m from the walking network and origins with weak district overlap |
| `clean250` | A less strict sensitivity version that removes origins snapped more than 250 m from the walking network |

The final maps use the `clean100` origin set. The baseline outputs are retained so that the effect of the cleaning step remains visible.

## Output files used for validation

Before interpreting the maps, the following diagnostic outputs are reviewed:

```text
outputs/tables/poi_completeness_summary.csv
outputs/tables/snapping_diagnostics.csv
outputs/tables/district_assignment_diagnostics.csv
outputs/tables/origin_cleaning_summary.csv
outputs/tables/robustness_summary_by_origin_set.csv
outputs/tables/robustness_interpretation.md
```

The corrected district-level accessibility summaries are stored in:

```text
outputs/tables/district_accessibility_summary_full_corrected.csv
outputs/tables/district_accessibility_summary_clean100.csv
outputs/tables/district_accessibility_summary_clean250.csv
```

The final maps used for the main `clean100` analysis are saved as:

```text
outputs/figures/clean100_*.png
```

Baseline maps without the `clean100_` prefix are also available in:

```text
outputs/figures/
```

## Main processed files

The main processed spatial outputs are stored in `data/processed/`:

```text
data/processed/official_libraries.gpkg
data/processed/official_playgrounds.gpkg
data/processed/official_sports_facilities.gpkg
data/processed/osm_libraries_clean.gpkg
data/processed/osm_playgrounds_clean.gpkg
data/processed/osm_sports_facilities_clean.gpkg
data/processed/osm_walking_edges_clean.gpkg
data/processed/osm_walking_nodes_clean.gpkg
data/processed/osm_walking_graph.graphml
data/processed/origins_grid_500m_clean100.gpkg
data/processed/origins_points_500m_clean100.gpkg
```

All distance-based processing is carried out in EPSG:25832, which allows distances to be measured in metres. WGS84 copies are also retained where useful for storage, sharing, or web mapping.
