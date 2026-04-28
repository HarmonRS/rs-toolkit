from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from sentinel_orbit_downloader.api.deps import get_db_path
from sentinel_orbit_downloader.api.schemas import (
    RegionDetail,
    RegionImportRequest,
    RegionImportResponse,
    RegionSummary,
)
from sentinel_orbit_downloader.api.serializers import region_detail, region_summary
from sentinel_orbit_downloader.services.region_catalog import (
    get_region,
    import_regions,
    search_regions,
)


router = APIRouter(prefix="/regions", tags=["regions"])


@router.post("/import", response_model=RegionImportResponse)
def import_region_catalog(
    request: RegionImportRequest,
    db_path=Depends(get_db_path),
) -> RegionImportResponse:
    source_path = Path(request.source_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"GeoJSON file not found: {source_path}")
    stats = import_regions(db_path, source_path, simplify_tolerance=request.simplify_tolerance)
    return RegionImportResponse(
        source_path=str(stats.source_path),
        simplify_tolerance=stats.simplify_tolerance,
        total_features=stats.total_features,
        imported=stats.imported,
    )


@router.get("/search", response_model=list[RegionSummary])
def search_region_catalog(
    q: str = Query(..., min_length=1),
    level: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    db_path=Depends(get_db_path),
) -> list[RegionSummary]:
    return [
        region_summary(region)
        for region in search_regions(db_path, q, limit=limit, level=level)
    ]


@router.get("/{adcode}", response_model=RegionDetail)
def get_region_detail(adcode: str, db_path=Depends(get_db_path)) -> RegionDetail:
    region = get_region(db_path, adcode)
    if region is None:
        raise HTTPException(status_code=404, detail=f"Region not found: {adcode}")
    return region_detail(region)
