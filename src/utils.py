from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from config import CRS_METRIC, CRS_WGS84, PROCESSED_DIR


NAME_CANDIDATES = [
    "name",
    "navn",
    "titel",
    "title",
    "lokalitet",
    "facilitet",
    "bibliotek",
    "legeplads",
    "halnavn",
]

ID_CANDIDATES = [
    "amenity_id",
    "original_id",
    "id",
    "fid",
    "objectid",
    "ogc_fid",
    "osm_id",
    "element_id",
    "uuid",
    "globalid",
]

CATEGORY_CANDIDATES = [
    "amenity",
    "leisure",
    "type",
    "kategori",
    "category",
    "klasse",
    "funktion",
    "facilitetstype",
]

DISTRICT_NAME_CANDIDATES = [
    "bydel",
    "navn",
    "name",
    "district",
    "district_name",
    "bydelsnavn",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: object, fallback: str = "value") -> str:
    text = str(value or fallback).strip().lower()
    text = text.replace("ae", "ae").replace("oe", "oe").replace("aa", "aa")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or fallback


def require_file(path: Path, message: str | None = None) -> Path:
    if not path.exists():
        raise FileNotFoundError(message or f"Required file not found: {path}")
    return path


def import_geopandas():
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise ImportError(
            "This script requires geopandas. Install dependencies with "
            "`python -m pip install -r requirements.txt` or the conda commands in README.md."
        ) from exc
    return gpd


def import_shapely_geometry():
    try:
        from shapely import wkt
        from shapely.geometry import Point, box
        from shapely.ops import unary_union
    except ImportError as exc:
        raise ImportError(
            "This script requires shapely. Install dependencies from requirements.txt."
        ) from exc
    return Point, box, unary_union, wkt


def infer_crs_from_bounds(gdf) -> str:
    if gdf.empty:
        return CRS_WGS84
    minx, miny, maxx, maxy = gdf.total_bounds
    if all(math.isfinite(v) for v in [minx, miny, maxx, maxy]):
        if -180 <= minx <= 180 and -90 <= miny <= 90 and -180 <= maxx <= 180 and -90 <= maxy <= 90:
            return CRS_WGS84
    return CRS_METRIC


def ensure_crs(gdf, default: str | None = None):
    if gdf.crs is None:
        gdf = gdf.set_crs(default or infer_crs_from_bounds(gdf), allow_override=True)
    return gdf


def make_valid_geometries(gdf):
    if gdf.empty:
        return gdf
    gdf = gdf.copy()
    gdf = gdf[gdf.geometry.notna()].copy()
    try:
        gdf["geometry"] = gdf.geometry.make_valid()
    except Exception:
        gdf["geometry"] = gdf.geometry.buffer(0)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    return gdf


def find_column(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    lower_map = {str(col).lower(): col for col in columns}
    for candidate in candidates:
        key = candidate.lower()
        if key in lower_map:
            return lower_map[key]
    for candidate in candidates:
        key = candidate.lower()
        for lower, original in lower_map.items():
            if key in lower:
                return original
    return None


def read_metadata_table(path: Path) -> pd.DataFrame:
    require_file(path)
    return pd.read_csv(path)


def get_downloaded_resource(metadata: pd.DataFrame, dataset_key: str) -> Path:
    row = metadata.loc[metadata["dataset_key"] == dataset_key]
    if row.empty:
        raise ValueError(f"No downloaded official resource is recorded for {dataset_key}.")
    path = Path(row.iloc[0]["downloaded_file"])
    if not path.is_absolute():
        path = Path.cwd() / path
    return require_file(path)


def read_vector_any(path: Path, data_format: str | None = None):
    gpd = import_geopandas()
    Point, _, _, wkt = import_shapely_geometry()
    path = Path(path)
    suffix = path.suffix.lower().lstrip(".")
    fmt = (data_format or suffix).lower()

    if suffix == "csv" or fmt == "csv":
        df = pd.read_csv(path)
        geometry_col = find_column(df.columns, ["geometry", "geom", "wkt", "the_geom"])
        if geometry_col:
            geometries = df[geometry_col].apply(lambda val: wkt.loads(val) if pd.notna(val) else None)
            gdf = gpd.GeoDataFrame(df, geometry=geometries, crs=CRS_WGS84)
            return ensure_crs(gdf)

        lon_col = find_column(
            df.columns,
            ["lon", "lng", "longitude", "x", "xcoord", "x_koord", "koord_x", "easting"],
        )
        lat_col = find_column(
            df.columns,
            ["lat", "latitude", "y", "ycoord", "y_koord", "koord_y", "northing"],
        )
        if not lon_col or not lat_col:
            raise ValueError(
                f"CSV {path} has no geometry/WKT column and no recognizable coordinate columns. "
                f"Columns: {list(df.columns)}"
            )

        coords = df[[lon_col, lat_col]].apply(pd.to_numeric, errors="coerce")
        geometries = [Point(xy) if pd.notna(xy[0]) and pd.notna(xy[1]) else None for xy in coords.to_numpy()]
        gdf = gpd.GeoDataFrame(df, geometry=geometries)
        return ensure_crs(gdf)

    try:
        gdf = gpd.read_file(path)
    except Exception:
        if suffix == "zip":
            gdf = gpd.read_file(f"zip://{path}")
        else:
            raise
    return ensure_crs(gdf)


def safe_write_gdf(gdf, path: Path, layer: str | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    kwargs = {"driver": "GPKG"}
    if layer:
        kwargs["layer"] = layer
    gdf.to_file(path, **kwargs)


def safe_write_csv(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def save_json(data: object, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def dissolve_to_boundary(gdf):
    gpd = import_geopandas()
    gdf = make_valid_geometries(ensure_crs(gdf)).to_crs(CRS_METRIC)
    if hasattr(gdf.geometry, "union_all"):
        geom = gdf.geometry.union_all()
    else:
        geom = gdf.geometry.unary_union
    return gpd.GeoDataFrame({"name": ["Copenhagen Municipality"]}, geometry=[geom], crs=CRS_METRIC)


def load_boundary(metric: bool = True):
    gpd = import_geopandas()
    boundary_path = PROCESSED_DIR / "copenhagen_boundary.gpkg"
    bydele_path = PROCESSED_DIR / "bydele.gpkg"
    if boundary_path.exists():
        boundary = gpd.read_file(boundary_path)
    elif bydele_path.exists():
        boundary = dissolve_to_boundary(gpd.read_file(bydele_path))
    else:
        raise FileNotFoundError(
            "Copenhagen boundary not found. Run 01_download_official_data.py and "
            "03_clean_official_amenities.py first."
        )
    boundary = ensure_crs(boundary)
    return boundary.to_crs(CRS_METRIC if metric else CRS_WGS84)


def clip_to_boundary(gdf, boundary):
    gpd = import_geopandas()
    if gdf.empty:
        return gdf
    gdf = make_valid_geometries(ensure_crs(gdf)).to_crs(boundary.crs)
    boundary = make_valid_geometries(ensure_crs(boundary)).to_crs(gdf.crs)
    try:
        clipped = gpd.clip(gdf, boundary)
    except Exception:
        clipped = gdf[gdf.intersects(boundary.geometry.iloc[0])].copy()
    return clipped.reset_index(drop=True)


def representative_points(gdf):
    gdf = gdf.copy()
    geometries = []
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            geometries.append(None)
        elif geom.geom_type in {"Point", "MultiPoint"}:
            geometries.append(geom.representative_point())
        elif geom.geom_type in {"LineString", "MultiLineString"}:
            geometries.append(geom.interpolate(0.5, normalized=True))
        else:
            geometries.append(geom.representative_point())
    gdf["geometry"] = geometries
    return make_valid_geometries(gdf)


def standardize_amenities(gdf, amenity_type: str, source: str, dataset_label: str, id_prefix: str):
    gpd = import_geopandas()
    gdf = make_valid_geometries(ensure_crs(gdf))
    if gdf.empty:
        return gpd.GeoDataFrame(
            columns=[
                "amenity_id",
                "amenity_type",
                "source",
                "name",
                "original_category",
                "original_id",
                "longitude",
                "latitude",
                "geometry",
            ],
            geometry="geometry",
            crs=CRS_METRIC,
        )

    name_col = find_column(gdf.columns, NAME_CANDIDATES)
    id_col = find_column(gdf.columns, ID_CANDIDATES)
    category_col = find_column(gdf.columns, CATEGORY_CANDIDATES)

    points = representative_points(gdf).to_crs(CRS_METRIC).reset_index(drop=True)
    lonlat = points.to_crs(CRS_WGS84)

    names = points[name_col].astype(str) if name_col else pd.Series([""] * len(points))
    original_ids = points[id_col].astype(str) if id_col else pd.Series(points.index.astype(str))
    categories = points[category_col].astype(str) if category_col else pd.Series([dataset_label] * len(points))

    out = gpd.GeoDataFrame(
        {
            "amenity_id": [f"{id_prefix}_{i + 1:05d}" for i in range(len(points))],
            "amenity_type": amenity_type,
            "source": source,
            "name": names.fillna("").replace("nan", ""),
            "original_category": categories.fillna(dataset_label).replace("nan", dataset_label),
            "original_id": original_ids.fillna("").replace("nan", ""),
            "longitude": lonlat.geometry.x,
            "latitude": lonlat.geometry.y,
        },
        geometry=points.geometry,
        crs=CRS_METRIC,
    )

    out["_name_norm"] = out["name"].fillna("").str.lower().str.strip()
    out["_x_round"] = out.geometry.x.round(1)
    out["_y_round"] = out.geometry.y.round(1)
    out = out.drop_duplicates(subset=["source", "amenity_type", "_name_norm", "_x_round", "_y_round"])
    out = out.drop(columns=["_name_norm", "_x_round", "_y_round"]).reset_index(drop=True)
    out["amenity_id"] = [f"{id_prefix}_{i + 1:05d}" for i in range(len(out))]
    return out[
        [
            "amenity_id",
            "amenity_type",
            "source",
            "name",
            "original_category",
            "original_id",
            "longitude",
            "latitude",
            "geometry",
        ]
    ]


def inspect_gdf(dataset_name: str, gdf) -> dict:
    geom_types = []
    if "geometry" in gdf:
        geom_types = sorted([str(value) for value in gdf.geometry.geom_type.dropna().unique()])
    return {
        "dataset_name": dataset_name,
        "crs": str(gdf.crs),
        "geometry_type": ";".join(geom_types),
        "row_count": int(len(gdf)),
        "column_names": "|".join([str(col) for col in gdf.columns]),
        "missing_geometry_count": int(gdf.geometry.isna().sum()) if "geometry" in gdf else len(gdf),
    }


def resolve_node_id_column(nodes) -> str:
    for col in ["node_id", "id", "osm_id", "osmid"]:
        if col in nodes.columns:
            return col
    raise ValueError(f"Could not identify node ID column. Columns: {list(nodes.columns)}")


def resolve_edge_endpoint_columns(edges) -> tuple[str, str]:
    candidates = [("u", "v"), ("from", "to"), ("source", "target")]
    for left, right in candidates:
        if left in edges.columns and right in edges.columns:
            return left, right
    raise ValueError(f"Could not identify edge endpoint columns. Columns: {list(edges.columns)}")


def nearest_node_snap(points, nodes, point_id_col: str = "amenity_id") -> pd.DataFrame:
    try:
        from scipy.spatial import cKDTree
    except ImportError as exc:
        raise ImportError("Snapping requires scipy. Install dependencies from requirements.txt.") from exc

    points = ensure_crs(points).to_crs(CRS_METRIC)
    nodes = ensure_crs(nodes).to_crs(CRS_METRIC)
    node_col = resolve_node_id_column(nodes)

    node_coords = list(zip(nodes.geometry.x, nodes.geometry.y))
    tree = cKDTree(node_coords)
    point_coords = list(zip(points.geometry.x, points.geometry.y))
    distances, indices = tree.query(point_coords, k=1)

    ids = points[point_id_col].astype(str).to_numpy() if point_id_col in points.columns else points.index.astype(str).to_numpy()
    snapped = pd.DataFrame(
        {
            point_id_col: ids,
            "nearest_node": nodes.iloc[indices][node_col].astype(str).to_numpy(),
            "snap_distance_m": distances,
        }
    )
    return snapped


def finite_or_none(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clean_numeric_difference(osm_time: object, official_time: object) -> float | None:
    osm_value = finite_or_none(osm_time)
    official_value = finite_or_none(official_time)
    if osm_value is None or official_value is None:
        return None
    return osm_value - official_value


def classify_accessibility(official_access: bool, osm_access: bool) -> str:
    if official_access and osm_access:
        return "agreement_accessible"
    if (not official_access) and (not osm_access):
        return "agreement_inaccessible"
    if (not official_access) and osm_access:
        return "osm_false_access"
    return "osm_hidden_access"
