from __future__ import annotations

import json

from sentinel_orbit_downloader.api.schemas import RegionDetail, RegionSummary


def region_summary(region) -> RegionSummary:
    bbox = list(region.bbox) if region.bbox is not None else None
    return RegionSummary(
        adcode=region.adcode,
        name=region.name,
        level=region.level,
        parent_adcode=region.parent_adcode,
        parent_name=region.parent_name,
        province_adcode=region.province_adcode,
        province_name=region.province_name,
        label=region.label,
        bbox=bbox,
        simplify_tolerance=region.simplify_tolerance,
    )


def region_detail(region) -> RegionDetail:
    summary = region_summary(region)
    center = (
        [region.center_lon, region.center_lat]
        if region.center_lon is not None and region.center_lat is not None
        else None
    )
    centroid = (
        [region.centroid_lon, region.centroid_lat]
        if region.centroid_lon is not None and region.centroid_lat is not None
        else None
    )
    return RegionDetail(
        **summary.model_dump(),
        center=center,
        centroid=centroid,
        geometry_json=json.loads(region.geometry_json),
        wkt=region.wkt,
        simplified_wkt=region.simplified_wkt,
        children_num=region.children_num,
        tree_id=region.tree_id,
    )
