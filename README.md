# Copenhagen OSM vs official amenity access

This project asks a narrow question: if the walking network stays the same, how much does the destination data change a 15-minute walking access map?

We compare two versions of the same accessibility calculation for Copenhagen Municipality:

- OSM walking network plus official Copenhagen amenities
- OSM walking network plus OSM amenities

That means the street network is held fixed. The comparison is about amenity completeness and classification, not whether OSM streets are better or worse than an official street network.

The amenity types are libraries, playgrounds, and sports facilities.

## how to run it

There are two ways to run the project.

For the command line version:

```powershell
python src/run_pipeline.py
```

For the notebook version, open:

```text
notebooks/copenhagen_osm_accessibility_pipeline.ipynb
```

The notebook is a readable runner around the scripts in `src/`. We kept the actual code in scripts because it is easier to rerun, test, and fix there. The notebook gives the same workflow in smaller chunks with notes.

## data you need

The official Copenhagen data are downloaded automatically from Open Data DK / Copenhagen CKAN:

```text
https://admin.opendata.dk/api/3/action
```

The downloader looks for GeoJSON first, then SHP, then CSV. It saves the source links and local filenames in:

```text
data/raw/official/official_download_metadata.csv
outputs/tables/official_download_metadata.csv
```

The OSM PBF is different. This project does not download it.

Put the Denmark PBF here:

```text
data/raw/osm/denmark-latest.osm.pbf
```

The OSM extraction script checks that exact path before doing anything else. If the file is missing, it stops with a clear error.

## environment

On Windows, we would use conda-forge. `pyrosm` is the package most likely to be annoying from plain pip.

```powershell
conda create -n cph-osm-access -c conda-forge python=3.11 geopandas pyrosm networkx scipy matplotlib contextily folium mapclassify libpysal esda requests
conda activate cph-osm-access
```

Pip can also work if your geospatial stack is already behaving:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## pipeline order

The order looks a little odd because the Copenhagen boundary has to exist before the OSM PBF can be clipped to the study area.

1. `src/01_download_official_data.py`
2. `src/03_clean_official_amenities.py`
3. `src/02_extract_osm_data.py`
4. `src/04_clean_osm_amenities.py`
5. `src/05_prepare_walking_network.py`
6. `src/06_create_origin_grid.py`
7. `src/07_match_osm_to_official.py`
8. `src/08_compute_accessibility.py`
9. `src/09_compare_accessibility.py`
10. `src/10_make_maps.py`
11. `src/11_diagnose_origin_quality.py`
12. `src/12_assign_districts_by_overlap.py`
13. `src/13_diagnose_snapping_outliers.py`
14. `src/14_create_clean_origin_set.py`
15. `src/15_rerun_accessibility_for_clean_origins.py`
16. `src/16_rerun_district_summaries.py`
17. `src/17_compare_baseline_vs_cleaned.py`
18. `src/18_make_cleaned_maps.py`

Optional Moran / LISA analysis:

```powershell
python src/09_compare_accessibility.py --moran
```

## amenity definitions

Official Copenhagen layers:

- libraries: `Biblioteker`
- playgrounds: `Legepladser`
- sports facilities: `Idraetsanlaeg`
- districts and boundary: `Bydele`

OSM tags:

- libraries: `amenity=library`
- playgrounds: `leisure=playground`
- sports facilities: `leisure=sports_centre` or `leisure=sports_hall`

We leave out `leisure=pitch` in the main analysis. In Copenhagen, pitches can be individual fields rather than whole sports facilities, so mixing them into the main sports category would change the meaning of the comparison.

## origin-quality fix

The first baseline run exposed two problems that were too large to ignore:

- 103 origin points ended up with district `Unassigned`
- 87 of 475 origins snapped more than 100 m from the walking network

The fix is now part of the pipeline.

Districts are assigned by largest area overlap between the 500 m grid cell and the Bydele polygons. That works better than centroid assignment for coastal and harbour-edge cells.

The project also keeps three origin sets:

- `full`: all 475 origins, kept as the baseline
- `clean100`: removes origins snapped more than 100 m away and weak district-overlap cells
- `clean250`: a softer sensitivity version that removes origins snapped more than 250 m away

For the final maps, we use `clean100`. The baseline stays in the outputs so the cleaning choice is visible instead of hidden.

## outputs we check first

These are the files we usually open before looking at the maps:

```text
outputs/tables/poi_completeness_summary.csv
outputs/tables/snapping_diagnostics.csv
outputs/tables/district_assignment_diagnostics.csv
outputs/tables/origin_cleaning_summary.csv
outputs/tables/robustness_summary_by_origin_set.csv
outputs/tables/robustness_interpretation.md
```

The corrected district summaries are:

```text
outputs/tables/district_accessibility_summary_full_corrected.csv
outputs/tables/district_accessibility_summary_clean100.csv
outputs/tables/district_accessibility_summary_clean250.csv
```

The recommended final maps are written as:

```text
outputs/figures/clean100_*.png
```

The baseline maps are still in `outputs/figures/` without the `clean100_` prefix.

## main processed files

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

All distance work uses EPSG:25832. The scripts also keep WGS84 copies where that is useful for storage or web mapping.
