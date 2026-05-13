from __future__ import annotations

import pandas as pd

from config import (
    BYDELE_FILE,
    CRS_METRIC,
    FIGURES_DIR,
    OSM_WALKING_EDGES_CLEAN_FILE,
    PROCESSED_DIR,
    TABLES_DIR,
    ensure_directories,
)
from utils import import_geopandas, require_file


CLASSIFIED_CLEAN100 = TABLES_DIR / "origin_accessibility_classified_clean100.csv"
COMPOSITE_CLEAN100 = TABLES_DIR / "composite_disagreement_scores_clean100.csv"
GRID_CLEAN100 = PROCESSED_DIR / "origins_grid_500m_clean100.gpkg"
SNAP_OUTLIERS = PROCESSED_DIR / "origin_snapping_outliers.gpkg"


ACCESS_COLORS = {True: "#2ca25f", False: "#f0f0f0"}
DISAGREEMENT_COLORS = {
    "agreement_accessible": "#2ca25f",
    "agreement_inaccessible": "#d9d9d9",
    "osm_false_access": "#d73027",
    "osm_hidden_access": "#4575b4",
}


def setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def add_basemap(ax, crs) -> None:
    try:
        import contextily as ctx
        ctx.add_basemap(ax, crs=crs, source=ctx.providers.CartoDB.PositronNoLabels, attribution_size=6)
    except Exception:
        return


def finish(fig, ax, output, title):
    ax.set_title(title, fontsize=13)
    ax.set_axis_off()
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220, bbox_inches="tight")
    import matplotlib.pyplot as plt

    plt.close(fig)


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def plot_access(grid, boundary, amenity_type, source, column):
    plt = setup_matplotlib()
    from matplotlib.patches import Patch

    fig, ax = plt.subplots(figsize=(8, 8))
    for value, color in ACCESS_COLORS.items():
        subset = grid[grid[column] == value]
        if not subset.empty:
            subset.plot(
                ax=ax,
                color=color,
                edgecolor="white",
                linewidth=0.15,
                label="accessible" if value else "not accessible",
            )
    boundary.boundary.plot(ax=ax, color="#222222", linewidth=0.7)
    handles = [
        Patch(facecolor=ACCESS_COLORS[True], edgecolor="white", label="accessible"),
        Patch(facecolor=ACCESS_COLORS[False], edgecolor="white", label="not accessible"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True)
    add_basemap(ax, grid.crs)
    output = FIGURES_DIR / f"clean100_{source}_{amenity_type}_access_15min.png"
    finish(fig, ax, output, f"Clean100 {source} 15-minute access: {amenity_type}")


def plot_disagreement(grid, boundary, amenity_type):
    plt = setup_matplotlib()
    from matplotlib.patches import Patch

    fig, ax = plt.subplots(figsize=(8, 8))
    for status, color in DISAGREEMENT_COLORS.items():
        subset = grid[grid["distortion_class"] == status]
        if not subset.empty:
            subset.plot(ax=ax, color=color, edgecolor="white", linewidth=0.15, label=status)
    boundary.boundary.plot(ax=ax, color="#222222", linewidth=0.7)
    handles = [
        Patch(facecolor=color, edgecolor="white", label=status)
        for status, color in DISAGREEMENT_COLORS.items()
        if not grid[grid["distortion_class"] == status].empty
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True, fontsize=8)
    add_basemap(ax, grid.crs)
    finish(fig, ax, FIGURES_DIR / f"clean100_{amenity_type}_disagreement.png", f"Clean100 disagreement: {amenity_type}")


def plot_difference(grid, boundary, amenity_type):
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 8))
    grid.plot(
        ax=ax,
        column="difference_minutes",
        cmap="RdBu_r",
        legend=True,
        edgecolor="white",
        linewidth=0.15,
        missing_kwds={"color": "#efefef", "label": "no route"},
    )
    boundary.boundary.plot(ax=ax, color="#222222", linewidth=0.7)
    add_basemap(ax, grid.crs)
    finish(
        fig,
        ax,
        FIGURES_DIR / f"clean100_{amenity_type}_walking_time_difference.png",
        f"Clean100 walking-time difference: {amenity_type}",
    )


def plot_composite(grid, boundary, composite):
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 8))
    mapped = grid.merge(composite, on="origin_id", how="left")
    mapped["composite_disagreement_score"] = mapped["composite_disagreement_score"].fillna(0).astype(int)
    mapped.plot(
        ax=ax,
        column="composite_disagreement_score",
        cmap="YlOrRd",
        vmin=0,
        vmax=3,
        legend=True,
        edgecolor="white",
        linewidth=0.15,
    )
    boundary.boundary.plot(ax=ax, color="#222222", linewidth=0.7)
    add_basemap(ax, mapped.crs)
    finish(fig, ax, FIGURES_DIR / "clean100_composite_disagreement_score.png", "Clean100 composite disagreement score")


def plot_snapping_outliers():
    gpd = import_geopandas()
    if not SNAP_OUTLIERS.exists():
        print("Snapping outlier GeoPackage not found; skipping cleaned snapping outlier map.")
        return
    outliers = gpd.read_file(SNAP_OUTLIERS).to_crs(CRS_METRIC)
    edges = gpd.read_file(require_file(OSM_WALKING_EDGES_CLEAN_FILE)).to_crs(CRS_METRIC)
    if outliers.empty:
        return

    plt = setup_matplotlib()
    colors = {
        "50-100 m": "#fee08b",
        "100-250 m": "#fdae61",
        "250-500 m": "#d73027",
        ">500 m": "#7f0000",
    }
    fig, ax = plt.subplots(figsize=(8, 8))
    edges.plot(ax=ax, color="#d0d0d0", linewidth=0.25, alpha=0.55)
    for category, color in colors.items():
        subset = outliers[outliers["snap_category"] == category]
        if not subset.empty:
            subset.plot(ax=ax, color=color, markersize=18, label=category, alpha=0.9)
    minx, miny, maxx, maxy = outliers.total_bounds
    pad = 800
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.legend(loc="lower left", frameon=True, fontsize=8)
    finish(fig, ax, FIGURES_DIR / "origin_snapping_outliers_map.png", "Origin snapping outliers")


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()

    classified = pd.read_csv(require_file(CLASSIFIED_CLEAN100))
    for column in ["official_access_15", "osm_access_15"]:
        classified[column] = classified[column].apply(to_bool)

    grid = gpd.read_file(require_file(GRID_CLEAN100)).to_crs(CRS_METRIC)
    boundary = gpd.read_file(require_file(BYDELE_FILE)).to_crs(CRS_METRIC)
    composite = pd.read_csv(require_file(COMPOSITE_CLEAN100))

    cleaning_summary = pd.read_csv(TABLES_DIR / "origin_cleaning_summary.csv") if (TABLES_DIR / "origin_cleaning_summary.csv").exists() else pd.DataFrame()
    if not cleaning_summary.empty:
        clean100_share = cleaning_summary.loc[cleaning_summary["origin_set"] == "clean100", "share_removed"]
        if not clean100_share.empty and float(clean100_share.iloc[0]) > 0.30:
            print("Warning: clean100 removes more than 30% of origins; inspect robustness outputs before final reporting.")

    # The final report should use maps based on the cleaned and corrected origin
    # set, because these better represent valid land-based origins and corrected
    # district assignment. The baseline results are preserved and checked through
    # robustness analysis.
    for amenity_type, group in classified.groupby("amenity_type"):
        mapped = grid.merge(group, on="origin_id", how="left")
        mapped = gpd.GeoDataFrame(mapped, geometry="geometry", crs=CRS_METRIC)
        plot_access(mapped, boundary, amenity_type, "official", "official_access_15")
        plot_access(mapped, boundary, amenity_type, "osm", "osm_access_15")
        plot_disagreement(mapped, boundary, amenity_type)
        plot_difference(mapped, boundary, amenity_type)

    plot_composite(grid, boundary, composite)
    plot_snapping_outliers()
    print("Saved clean100 maps.")


if __name__ == "__main__":
    main()
