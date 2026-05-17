from __future__ import annotations

import pandas as pd

from config import (
    CRS_METRIC,
    FIGURES_DIR,
    MAPS_DIR,
    OSM_WALKING_EDGES_CLEAN_FILE,
    OSM_WALKING_NODES_CLEAN_FILE,
    PROCESSED_DIR,
    TABLES_DIR,
    ensure_directories,
)
from origin_quality import add_snap_flags, calculate_origin_snaps
from utils import import_geopandas, require_file, safe_write_csv, safe_write_gdf


POINTS_WITH_DISTRICT = PROCESSED_DIR / "origins_points_500m_with_district_overlap.gpkg"
SNAP_OUTLIERS_GPKG = PROCESSED_DIR / "origin_snapping_outliers.gpkg"
SNAP_ALL_GPKG = PROCESSED_DIR / "origin_snapping_distances_all.gpkg"


def setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def snap_category(distance: float) -> str:
    if distance > 500:
        return ">500 m"
    if distance > 250:
        return "250-500 m"
    if distance > 100:
        return "100-250 m"
    if distance > 50:
        return "50-100 m"
    return "<=50 m"


def save_histogram(snapped) -> None:
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 5))
    snapped["snap_distance_m"].plot(kind="hist", bins=40, color="#4c78a8", edgecolor="white", ax=ax)
    ax.axvline(100, color="#d95f02", linestyle="--", linewidth=1.2, label="100 m")
    ax.axvline(250, color="#7570b3", linestyle="--", linewidth=1.2, label="250 m")
    ax.set_xlabel("Distance to nearest walking-network node (m)")
    ax.set_ylabel("Origin count")
    ax.set_title("Origin snapping distances")
    ax.legend()
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / "origin_snapping_distance_histogram.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def save_outlier_map(snapped, edges) -> None:
    plt = setup_matplotlib()
    colors = {
        "50-100 m": "#fee08b",
        "100-250 m": "#fdae61",
        "250-500 m": "#d73027",
        ">500 m": "#7f0000",
    }
    flagged = snapped[snapped["snap_gt_50m"]].copy()
    fig, ax = plt.subplots(figsize=(8, 8))
    edges.to_crs(CRS_METRIC).plot(ax=ax, color="#d0d0d0", linewidth=0.25, alpha=0.55)
    for category, color in colors.items():
        subset = flagged[flagged["snap_category"] == category]
        if not subset.empty:
            subset.plot(ax=ax, color=color, markersize=18, label=category, alpha=0.9)
    if not flagged.empty:
        minx, miny, maxx, maxy = flagged.total_bounds
        pad = 800
        ax.set_xlim(minx - pad, maxx + pad)
        ax.set_ylim(miny - pad, maxy + pad)
    ax.set_title("Origin snapping outliers")
    ax.set_axis_off()
    ax.legend(loc="lower left", frameon=True, fontsize=8)
    fig.tight_layout()
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(MAPS_DIR / "origin_snapping_outliers_map.png", dpi=220, bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "origin_snapping_outliers_map.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()

    points = gpd.read_file(require_file(POINTS_WITH_DISTRICT)).to_crs(CRS_METRIC)
    nodes = gpd.read_file(require_file(OSM_WALKING_NODES_CLEAN_FILE)).to_crs(CRS_METRIC)
    edges = gpd.read_file(require_file(OSM_WALKING_EDGES_CLEAN_FILE)).to_crs(CRS_METRIC)

    # Origin snapping distance is a direct source of accessibility error. If a
    # grid origin is snapped hundreds of metres away from its actual centroid,
    # the calculated 15-minute walking access may represent the network position
    # rather than the intended origin location. The existing diagnostics show 87
    # origins snapped more than 100 m away and a maximum snapping distance of
    # about 882 m, so a cleaning or sensitivity strategy is needed.
    snapped = calculate_origin_snaps(points, nodes)
    snapped = add_snap_flags(snapped)
    snapped["snap_category"] = snapped["snap_distance_m"].apply(snap_category)
    snapped["assigned_district"] = snapped["assigned_district"].fillna("No district overlap")

    flagged = snapped[snapped["snap_gt_50m"]].copy()
    required_columns = [
        "origin_id",
        "assigned_district",
        "snap_distance_m",
        "snap_gt_50m",
        "snap_gt_100m",
        "snap_gt_250m",
        "snap_gt_500m",
        "nearest_node_id",
        "geometry",
    ]

    safe_write_gdf(snapped, SNAP_ALL_GPKG, layer="origin_snapping_distances_all")
    safe_write_gdf(flagged, SNAP_OUTLIERS_GPKG, layer="origin_snapping_outliers")
    safe_write_csv(flagged[required_columns + ["snap_category"]], TABLES_DIR / "origin_snapping_outliers.csv")

    summary = (
        snapped.groupby("assigned_district", dropna=False)
        .agg(
            n_origins=("origin_id", "count"),
            median_snap_distance_m=("snap_distance_m", "median"),
            mean_snap_distance_m=("snap_distance_m", "mean"),
            max_snap_distance_m=("snap_distance_m", "max"),
            n_snap_gt_50m=("snap_gt_50m", "sum"),
            n_snap_gt_100m=("snap_gt_100m", "sum"),
            n_snap_gt_250m=("snap_gt_250m", "sum"),
            n_snap_gt_500m=("snap_gt_500m", "sum"),
        )
        .reset_index()
    )
    for col in ["n_snap_gt_50m", "n_snap_gt_100m", "n_snap_gt_250m", "n_snap_gt_500m"]:
        summary[col] = summary[col].astype(int)
    safe_write_csv(summary, TABLES_DIR / "origin_snapping_summary_by_district.csv")

    save_histogram(snapped)
    save_outlier_map(snapped, edges)

    print(
        "Saved snapping diagnostics: "
        f"{len(flagged)} origins >50 m, {int(snapped['snap_gt_100m'].sum())} origins >100 m."
    )


if __name__ == "__main__":
    main()
