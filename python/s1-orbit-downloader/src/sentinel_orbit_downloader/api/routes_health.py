from __future__ import annotations

from fastapi import APIRouter, Depends

from sentinel_orbit_downloader.api.deps import get_db_path
from sentinel_orbit_downloader.api.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db_path=Depends(get_db_path)) -> HealthResponse:
    return HealthResponse(status="ok", db_path=str(db_path))
