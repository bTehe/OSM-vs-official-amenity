from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

from config import (
    CKAN_API_BASE,
    CKAN_ORGANIZATION,
    OFFICIAL_DATASETS,
    RAW_OFFICIAL_DIR,
    TABLES_DIR,
    ensure_directories,
)
from utils import safe_write_csv, slugify, utc_now_iso


FORMAT_PRIORITY = {"geojson": 0, "shp": 1, "csv": 2}


def ckan_action(action: str, **params) -> dict:
    response = requests.get(f"{CKAN_API_BASE}/{action}", params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN action {action} failed: {payload}")
    return payload["result"]


def package_is_copenhagen(package: dict) -> bool:
    organization = package.get("organization") or {}
    return organization.get("name") == CKAN_ORGANIZATION


def find_package(dataset_key: str, spec: dict) -> dict:
    for package_id in spec["package_ids"]:
        try:
            package = ckan_action("package_show", id=package_id)
        except requests.HTTPError:
            continue
        if package_is_copenhagen(package):
            return package

    result = ckan_action("package_search", q=spec["search_query"], rows=10)
    for package in result.get("results", []):
        if package_is_copenhagen(package):
            return package

    raise RuntimeError(f"Could not find a Copenhagen CKAN package for {dataset_key}.")


def normalize_resource_format(resource: dict) -> str | None:
    fmt = str(resource.get("format") or "").lower()
    name = str(resource.get("name") or "").lower()
    url = str(resource.get("url") or "").lower()

    if "geojson" in fmt or name.endswith(".geojson") or "outputformat=json" in url:
        return "geojson"
    if fmt in {"shp", "shape", "shapefile"} or name.endswith(".zip") or "outputformat=shape-zip" in url:
        return "shp"
    if "csv" in fmt or name.endswith(".csv") or "outputformat=csv" in url:
        return "csv"
    return None


def choose_resource(package: dict) -> tuple[dict, str]:
    candidates = []
    for resource in package.get("resources", []):
        normalized = normalize_resource_format(resource)
        if normalized in FORMAT_PRIORITY and resource.get("url"):
            candidates.append((FORMAT_PRIORITY[normalized], resource, normalized))

    if not candidates:
        raise RuntimeError(f"No GeoJSON, SHP, or CSV resource found for {package.get('name')}.")

    _, resource, normalized = sorted(candidates, key=lambda item: item[0])[0]
    return resource, normalized


def resource_extension(resource: dict, normalized_format: str) -> str:
    name = str(resource.get("name") or "")
    suffix = Path(urlparse(name).path).suffix.lower()
    if suffix in {".geojson", ".json", ".csv", ".zip"}:
        return ".geojson" if suffix == ".json" and normalized_format == "geojson" else suffix
    return { "geojson": ".geojson", "shp": ".zip", "csv": ".csv" }[normalized_format]


def download_resource(url: str, destination: Path) -> None:
    headers = {"User-Agent": "copenhagen-osm-accessibility-analysis/1.0"}
    with requests.get(url, stream=True, timeout=180, headers=headers) as response:
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_obj.write(chunk)


def main() -> None:
    ensure_directories()
    rows = []

    for dataset_key, spec in OFFICIAL_DATASETS.items():
        package = find_package(dataset_key, spec)
        resource, normalized_format = choose_resource(package)
        extension = resource_extension(resource, normalized_format)
        file_name = f"{dataset_key}_{slugify(resource.get('name'), dataset_key)}{extension}"
        destination = RAW_OFFICIAL_DIR / file_name

        print(f"Downloading {dataset_key}: {resource.get('name')} -> {destination}")
        download_resource(resource["url"], destination)

        rows.append(
            {
                "dataset_key": dataset_key,
                "dataset_name": package.get("title") or spec["dataset_name"],
                "package_id": package.get("name"),
                "resource_id": resource.get("id"),
                "resource_name": resource.get("name"),
                "source_url": resource.get("url"),
                "package_url": f"https://www.opendata.dk/city-of-copenhagen/{package.get('name')}",
                "downloaded_file": str(destination),
                "format": normalized_format,
                "download_date": utc_now_iso(),
                "license": package.get("license_title") or package.get("license_id") or "",
            }
        )

    metadata = pd.DataFrame(rows)
    safe_write_csv(metadata, RAW_OFFICIAL_DIR / "official_download_metadata.csv")
    safe_write_csv(metadata, TABLES_DIR / "official_download_metadata.csv")
    print(f"Saved metadata for {len(metadata)} official datasets.")


if __name__ == "__main__":
    main()
