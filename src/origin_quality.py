from __future__ import annotations

import pandas as pd

from config import (
    BYDELE_FILE,
    CRS_METRIC,
    ORIGINS_POINTS_SNAPPED_FILE,
)
from utils import (
    DISTRICT_NAME_CANDIDATES,
    find_column,
    import_geopandas,
    nearest_node_snap,
    require_file,
    resolve_node_id_column,
)


MIN_DISTRICT_OVERLAP_SHARE = 0.10


def load_districts():
    gpd = import_geopandas()
    bydele = gpd.read_file(require_file(BYDELE_FILE)).to_crs(CRS_METRIC)
    district_col = find_column(bydele.columns, DISTRICT_NAME_CANDIDATES)
    if district_col is None:
        bydele = bydele.reset_index().rename(columns={"index": "district"})
        district_col = "district"
    districts = bydele[[district_col, "geometry"]].rename(columns={district_col: "district"}).copy()
    districts["district"] = districts["district"].astype(str)
    return districts


def dissolved_boundary(districts):
    gpd = import_geopandas()
    if hasattr(districts.geometry, "union_all"):
        geometry = districts.geometry.union_all()
    else:
        geometry = districts.geometry.unary_union
    return gpd.GeoDataFrame({"name": ["Copenhagen Municipality"]}, geometry=[geometry], crs=districts.crs)


def previous_centroid_assignment(points, districts) -> pd.DataFrame:
    """Reconstruct the earlier centroid-based district assignment for diagnostics."""
    gpd = import_geopandas()
    points = points.to_crs(CRS_METRIC)
    districts = districts.to_crs(CRS_METRIC)
    joined = gpd.sjoin(
        points[["origin_id", "geometry"]],
        districts[["district", "geometry"]],
        how="left",
        predicate="intersects",
    )[["origin_id", "district"]]
    joined = joined.drop_duplicates(subset=["origin_id"]).rename(
        columns={"district": "previous_district_assignment_if_available"}
    )
    boundary = dissolved_boundary(districts)
    within = points[["origin_id", "geometry"]].copy()
    within["centroid_within_any_district"] = within.geometry.within(boundary.geometry.iloc[0])
    return joined.merge(within[["origin_id", "centroid_within_any_district"]], on="origin_id", how="right")


def calculate_district_overlaps(grid, points, districts, min_overlap_share: float = MIN_DISTRICT_OVERLAP_SHARE):
    gpd = import_geopandas()
    grid = grid.to_crs(CRS_METRIC).copy()
    points = points.to_crs(CRS_METRIC).copy()
    districts = districts.to_crs(CRS_METRIC).copy()

    grid["origin_cell_area_m2"] = grid.geometry.area
    intersections = gpd.overlay(
        grid[["origin_id", "origin_cell_area_m2", "geometry"]],
        districts[["district", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )

    if intersections.empty:
        overlap_details = pd.DataFrame(
            columns=["origin_id", "district", "overlap_area_m2", "origin_cell_area_m2", "overlap_share"]
        )
    else:
        intersections["overlap_area_m2"] = intersections.geometry.area
        intersections["overlap_share"] = intersections["overlap_area_m2"] / intersections["origin_cell_area_m2"]
        overlap_details = pd.DataFrame(intersections.drop(columns="geometry"))

    ranked = overlap_details.sort_values(
        ["origin_id", "overlap_area_m2", "district"],
        ascending=[True, False, True],
    )
    top = ranked.drop_duplicates(subset=["origin_id"]).rename(
        columns={
            "district": "assigned_district",
            "overlap_area_m2": "largest_overlap_area_m2",
        }
    )

    assignments = grid[["origin_id", "origin_cell_area_m2", "geometry"]].merge(
        top[["origin_id", "assigned_district", "largest_overlap_area_m2", "overlap_share"]],
        on="origin_id",
        how="left",
    )
    assignments["largest_overlap_area_m2"] = assignments["largest_overlap_area_m2"].fillna(0.0)
    assignments["overlap_share"] = assignments["overlap_share"].fillna(0.0)
    assignments["low_overlap_edge_cell"] = assignments["overlap_share"] < min_overlap_share

    previous = previous_centroid_assignment(points, districts)
    assignments = assignments.merge(previous, on="origin_id", how="left")
    assignments["district_assignment_changed"] = (
        assignments["assigned_district"].fillna("")
        != assignments["previous_district_assignment_if_available"].fillna("")
    )

    boundary = dissolved_boundary(districts)
    municipality_overlap = gpd.overlay(
        grid[["origin_id", "origin_cell_area_m2", "geometry"]],
        boundary[["geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    if municipality_overlap.empty:
        municipality_shares = pd.DataFrame(columns=["origin_id", "municipality_overlap_share"])
    else:
        municipality_overlap["municipality_overlap_area_m2"] = municipality_overlap.geometry.area
        municipality_shares = (
            municipality_overlap.groupby("origin_id", as_index=False)["municipality_overlap_area_m2"]
            .sum()
            .merge(grid[["origin_id", "origin_cell_area_m2"]], on="origin_id", how="left")
        )
        municipality_shares["municipality_overlap_share"] = (
            municipality_shares["municipality_overlap_area_m2"] / municipality_shares["origin_cell_area_m2"]
        )
        municipality_shares = municipality_shares[["origin_id", "municipality_overlap_share"]]

    assignments = assignments.merge(municipality_shares, on="origin_id", how="left")
    assignments["municipality_overlap_share"] = assignments["municipality_overlap_share"].fillna(0.0)
    assignments["inferred_edge_or_harbour_cell"] = (
        (assignments["municipality_overlap_share"] < 0.95)
        | assignments["low_overlap_edge_cell"]
        | ~assignments["centroid_within_any_district"].fillna(False)
    )
    return assignments, overlap_details


def attach_assignment_to_points(points, assignments):
    columns = [
        "origin_id",
        "assigned_district",
        "largest_overlap_area_m2",
        "origin_cell_area_m2",
        "overlap_share",
        "low_overlap_edge_cell",
        "centroid_within_any_district",
        "previous_district_assignment_if_available",
        "district_assignment_changed",
        "municipality_overlap_share",
        "inferred_edge_or_harbour_cell",
    ]
    return points.drop(
        columns=[col for col in columns if col != "origin_id" and col in points.columns],
        errors="ignore",
    ).merge(assignments[columns], on="origin_id", how="left")


def load_existing_origin_snaps(points):
    if not ORIGINS_POINTS_SNAPPED_FILE.exists():
        return None
    gpd = import_geopandas()
    snapped = gpd.read_file(ORIGINS_POINTS_SNAPPED_FILE).to_crs(CRS_METRIC)
    columns = ["origin_id"]
    for col in ["nearest_node", "nearest_node_id", "snap_distance_m", "snap_flag_gt_100m"]:
        if col in snapped.columns:
            columns.append(col)
    snap = snapped[columns].copy()
    if "nearest_node" in snap.columns and "nearest_node_id" not in snap.columns:
        snap = snap.rename(columns={"nearest_node": "nearest_node_id"})
    return points.merge(snap, on="origin_id", how="left")


def calculate_origin_snaps(points, nodes):
    nodes = nodes.to_crs(CRS_METRIC).copy()
    node_col = resolve_node_id_column(nodes)
    nodes[node_col] = nodes[node_col].astype(str)
    snapped = nearest_node_snap(points.to_crs(CRS_METRIC), nodes, point_id_col="origin_id")
    snapped = snapped.rename(columns={"nearest_node": "nearest_node_id"})
    out = points.merge(snapped, on="origin_id", how="left")
    out["nearest_node_id"] = out["nearest_node_id"].astype(str)
    return out


def add_snap_flags(origins):
    out = origins.copy()
    out["snap_gt_50m"] = out["snap_distance_m"] > 50
    out["snap_gt_100m"] = out["snap_distance_m"] > 100
    out["snap_gt_250m"] = out["snap_distance_m"] > 250
    out["snap_gt_500m"] = out["snap_distance_m"] > 500
    return out
