from __future__ import annotations

import os
import signal
import time

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status

from sentinel_orbit_downloader.api.deps import get_db_path
from sentinel_orbit_downloader.api.schemas import HealthResponse, MessageResponse


router = APIRouter(tags=["health"])


def _terminate_current_process() -> None:
    time.sleep(0.2)
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


@router.get("/health", response_model=HealthResponse)
def health(db_path=Depends(get_db_path)) -> HealthResponse:
    return HealthResponse(status="ok", db_path=str(db_path))


@router.post("/shutdown", response_model=MessageResponse, include_in_schema=False)
def shutdown(
    background_tasks: BackgroundTasks,
    request: Request,
    x_s1dl_shutdown_token: str | None = Header(default=None, alias="X-S1DL-Shutdown-Token"),
) -> MessageResponse:
    expected_token = getattr(request.app.state, "shutdown_token", None)
    if not expected_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Shutdown is disabled.")
    if x_s1dl_shutdown_token != expected_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid shutdown token.")

    background_tasks.add_task(_terminate_current_process)
    return MessageResponse(message="Shutdown requested.")
