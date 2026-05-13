from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent

PIPELINE = [
    "01_download_official_data.py",
    "03_clean_official_amenities.py",
    "02_extract_osm_data.py",
    "04_clean_osm_amenities.py",
    "05_prepare_walking_network.py",
    "06_create_origin_grid.py",
    "07_match_osm_to_official.py",
    "08_compute_accessibility.py",
    "09_compare_accessibility.py",
    "10_make_maps.py",
    "11_diagnose_origin_quality.py",
    "12_assign_districts_by_overlap.py",
    "13_diagnose_snapping_outliers.py",
    "14_create_clean_origin_set.py",
    "15_rerun_accessibility_for_clean_origins.py",
    "16_rerun_district_summaries.py",
    "17_compare_baseline_vs_cleaned.py",
    "18_make_cleaned_maps.py",
]


def main() -> None:
    for script in PIPELINE:
        path = SCRIPT_DIR / script
        print(f"\n=== Running {script} ===")
        subprocess.run([sys.executable, str(path)], check=True)


if __name__ == "__main__":
    main()
