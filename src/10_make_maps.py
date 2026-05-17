from __future__ import annotations

import pandas as pd

from config import (
    BYDELE_FILE,
    CLASSIFIED_ACCESSIBILITY_TABLE,
    COMPOSITE_DISAGREEMENT_GPKG,
    CRS_METRIC,
    FIGURES_DIR,
    MAPS_DIR,
    ORIGINS_GRID_FILE,
    ensure_directories,
)
from utils import import_geopandas, require_file


ACCESS_COLORS = {
    True: "#2ca25f",
    False: "#f0f0f0",
}

DISAGREEMENT_COLORS = {
    "agreement_accessible": "#2ca25f",
    "agreement_inaccessible": "#d9d9d9",
    "osm_false_access": "#d73027",
    "osm_hidden_access": "#4575b4",
}

POI_STATUS_COLORS = {
    "matched_official": "#1b9e77",
    "matched_osm": "#66a61e",
    "unmatched_official": "#d95f02",
    "unmatched_osm": "#7570b3",
}


def setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def add_basemap(ax, crs) -> None:
    try:
        import contextily as ctx
    except ImportError:
        return
    try:
        ctx.add_basemap(ax, crs=crs, source=ctx.providers.CartoDB.PositronNoLabels, attribution_size=6)
    except Exception:
        return


def finish_map(fig, ax, output, title: str) -> None:
    ax.set_title(title, fontsize=13)
    ax.set_axis_off()
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220, bbox_inches="tight")
    import matplotlib.pyplot as plt

    plt.close(fig)


def plot_access_map(grid, boundary, amenity_type: str, source: str, column: str) -> None:
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 8))
    for value, color in ACCESS_COLORS.items():
        subset = grid[grid[column] == value]
        if not subset.empty:
            subset.plot(ax=ax, color=color, edgecolor="white", linewidth=0.15, label="accessible" if value else "not accessible")
    boundary.boundary.plot(ax=ax, color="#222222", linewidth=0.7)
    ax.legend(loc="lower left", frameon=True)
    add_basemap(ax, grid.crs)
    output = FIGURES_DIR / f"{source}_{amenity_type}_access_15min.png"
    finish_map(fig, ax, output, f"{source.title()} 15-minute access: {amenity_type}")


def plot_disagreement_map(grid, boundary, amenity_type: str) -> None:
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 8))
    for status, color in DISAGREEMENT_COLORS.items():
        subset = grid[grid["distortion_class"] == status]
        if not subset.empty:
            subset.plot(ax=ax, color=color, edgecolor="white", linewidth=0.15, label=status)
    boundary.boundary.plot(ax=ax, color="#222222", linewidth=0.7)
    ax.legend(loc="lower left", frameon=True, fontsize=8)
    add_basemap(ax, grid.crs)
    output = FIGURES_DIR / f"osm_vs_official_{amenity_type}_disagreement.png"
    finish_map(fig, ax, output, f"OSM vs official disagreement: {amenity_type}")


def plot_difference_map(grid, boundary, amenity_type: str) -> None:
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
    output = FIGURES_DIR / f"osm_minus_official_{amenity_type}_walking_time_difference.png"
    finish_map(fig, ax, output, f"Walking-time difference, OSM minus official: {amenity_type}")


def plot_composite_map(boundary) -> None:
    gpd = import_geopandas()
    composite = gpd.read_file(require_file(COMPOSITE_DISAGREEMENT_GPKG)).to_crs(CRS_METRIC)
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 8))
    composite.plot(
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
    add_basemap(ax, composite.crs)
    finish_map(fig, ax, FIGURES_DIR / "composite_disagreement_score.png", "Composite disagreement score")


def plot_matched_unmatched_pois(boundary) -> None:
    gpd = import_geopandas()
    path = MAPS_DIR / "matched_unmatched_pois.gpkg"
    if not path.exists():
        print("Matched/unmatched POI GeoPackage not found; skipping POI PNG map.")
        return
    pois = gpd.read_file(path).to_crs(CRS_METRIC)
    if pois.empty:
        return
    plt = setup_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 8))
    boundary.boundary.plot(ax=ax, color="#222222", linewidth=0.7)
    for status, color in POI_STATUS_COLORS.items():
        subset = pois[pois["match_status"] == status]
        if not subset.empty:
            subset.plot(ax=ax, color=color, markersize=12, label=status, alpha=0.85)
    ax.legend(loc="lower left", frameon=True, fontsize=8)
    add_basemap(ax, pois.crs)
    finish_map(fig, ax, FIGURES_DIR / "matched_unmatched_pois.png", "Matched and unmatched POIs")


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()
    classified = pd.read_csv(require_file(CLASSIFIED_ACCESSIBILITY_TABLE))
    grid = gpd.read_file(require_file(ORIGINS_GRID_FILE)).to_crs(CRS_METRIC)
    boundary = gpd.read_file(require_file(BYDELE_FILE)).to_crs(CRS_METRIC)

    for column in ["official_access_15", "osm_access_15"]:
        classified[column] = classified[column].astype(str).str.lower().isin({"true", "1", "yes"})

    for amenity_type, group in classified.groupby("amenity_type"):
        mapped = grid.merge(group, on="origin_id", how="left")
        mapped = gpd.GeoDataFrame(mapped, geometry="geometry", crs=CRS_METRIC)
        plot_access_map(mapped, boundary, amenity_type, "official", "official_access_15")
        plot_access_map(mapped, boundary, amenity_type, "osm", "osm_access_15")
        plot_disagreement_map(mapped, boundary, amenity_type)
        plot_difference_map(mapped, boundary, amenity_type)

    plot_matched_unmatched_pois(boundary)
    plot_composite_map(boundary)
    print(f"Saved static PNG maps in {FIGURES_DIR}.")


if __name__ == "__main__":
    main()
