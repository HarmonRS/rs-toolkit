from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from sentinel_orbit_downloader.api.deps import get_db_path
from sentinel_orbit_downloader.api.schemas import (
    EarthdataSettingsRequest,
    EarthdataSettingsResponse,
    MessageResponse,
)
from sentinel_orbit_downloader.services.settings_store import (
    clear_earthdata_credentials,
    get_earthdata_settings,
    save_earthdata_credentials,
)


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/earthdata", response_model=EarthdataSettingsResponse)
def earthdata_settings(db_path=Depends(get_db_path)) -> EarthdataSettingsResponse:
    settings = get_earthdata_settings(db_path)
    return EarthdataSettingsResponse(
        username=settings.username,
        has_password=settings.has_password,
    )


@router.put("/earthdata", response_model=EarthdataSettingsResponse, status_code=status.HTTP_200_OK)
def save_earthdata_settings(
    request: EarthdataSettingsRequest,
    db_path=Depends(get_db_path),
) -> EarthdataSettingsResponse:
    try:
        settings = save_earthdata_credentials(
            db_path,
            username=request.username,
            password=request.password,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EarthdataSettingsResponse(
        username=settings.username,
        has_password=settings.has_password,
    )


@router.delete("/earthdata", response_model=MessageResponse)
def delete_earthdata_settings(db_path=Depends(get_db_path)) -> MessageResponse:
    clear_earthdata_credentials(db_path)
    return MessageResponse(message="Earthdata 凭据已清除")
