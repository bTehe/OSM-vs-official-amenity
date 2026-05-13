from __future__ import annotations

import numpy as np

from config import (
    CRS_WGS84,
    CRS_METRIC,
    GRID_SIZE_M,
    ORIGINS_GRID_FILE,
    ORIGINS_POINTS_FILE,
    ensure_directories,
)
from utils import import_geopandas, import_shapely_geometry, load_boundary, safe_write_gdf


def create_grid(boundary, cell_size_m: int):
    gpd = import_geopandas()
    _, box, _, _ = import_shapely_geometry()

    boundary = boundary.to_crs(CRS_METRIC)
    minx, miny, maxx, maxy = boundary.total_bounds
    x_coords = np.arange(np.floor(minx / cell_size_m) * cell_size_m, maxx + cell_size_m, cell_size_m)
    y_coords = np.arange(np.floor(miny / cell_size_m) * cell_size_m, maxy + cell_size_m, cell_size_m)

    cells = []
    for x in x_coords:
        for y in y_coords:
            cells.append(box(x, y, x + cell_size_m, y + cell_size_m))

    grid = gpd.GeoDataFrame({"cell_id": range(1, len(cells) + 1)}, geometry=cells, crs=CRS_METRIC)
    mask = grid.intersects(boundary.geometry.iloc[0])
    grid = grid[mask].copy().reset_index(drop=True)
    grid["origin_id"] = [f"origin_{i + 1:05d}" for i in range(len(grid))]
    grid["grid_size_m"] = cell_size_m
    return grid[["origin_id", "grid_size_m", "geometry"]]


def main() -> None:
    ensure_directories()
    gpd = import_geopandas()
    boundary = load_boundary(metric=True)
    grid = create_grid(boundary, GRID_SIZE_M)
    centroids_metric = grid.geometry.centroid
    centroids_wgs84 = gpd.GeoSeries(centroids_metric, crs=CRS_METRIC).to_crs(CRS_WGS84)

    points = gpd.GeoDataFrame(
        {
            "origin_id": grid["origin_id"],
            "grid_size_m": grid["grid_size_m"],
            "longitude": centroids_wgs84.x,
            "latitude": centroids_wgs84.y,
        },
        geometry=centroids_metric,
        crs=CRS_METRIC,
    )

    safe_write_gdf(grid, ORIGINS_GRID_FILE, layer="origins_grid_500m")
    safe_write_gdf(points, ORIGINS_POINTS_FILE, layer="origins_points_500m")
    print(f"Saved {len(grid)} origin grid cells and centroid points.")


if __name__ == "__main__":
    main()
