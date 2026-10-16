from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from sentinel_orbit_downloader.api.deps import get_db_path
from sentinel_orbit_downloader.api.schemas import DownloadJobCreateRequest, DownloadJobCreateResponse, JobSummary
from sentinel_orbit_downloader.services.asf_client import credentials_available
from sentinel_orbit_downloader.services.download_manager import DownloadJobRequest, execute_download_job, queue_download_job
from sentinel_orbit_downloader.services.project_store import get_job
from sentinel_orbit_downloader.services.settings_store import get_saved_earthdata_credentials


router = APIRouter(prefix="/download-jobs", tags=["download-jobs"])


@router.post("", response_model=DownloadJobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_download_job_endpoint(
    request: DownloadJobCreateRequest,
    background_tasks: BackgroundTasks,
    db_path=Depends(get_db_path),
) -> DownloadJobCreateResponse:
    job = get_job(db_path, request.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {request.job_id}")

    saved_username, saved_password = get_saved_earthdata_credentials(db_path)
    resolved_username = request.username or saved_username
    resolved_password = request.password or saved_password

    if not request.skip_data and not credentials_available(resolved_username, resolved_password):
        raise HTTPException(
            status_code=400,
            detail=(
                "下载 Sentinel-1 原始产品需要 Earthdata 用户名和密码。"
                "请在页面填写 Earthdata 用户名/密码，或先保存到本地配置，或先设置 EARTHDATA_USER 和 EARTHDATA_PASS。"
                "如果这次只想补轨道，请把“跳过产品”设为“是”。"
            ),
        )

    manager_request = DownloadJobRequest(
        job_id=request.job_id,
        data_dir=Path(request.data_dir) if request.data_dir else None,
        orbit_dir=Path(request.orbit_dir) if request.orbit_dir else None,
        manifest_path=Path(request.manifest_path) if request.manifest_path else None,
        skip_data=request.skip_data,
        skip_orbits=request.skip_orbits,
        processes=request.processes,
        ignore_orbit_errors=request.ignore_orbit_errors,
        username=resolved_username,
        password=resolved_password,
    )

    try:
        queue_download_job(db_path, manager_request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(execute_download_job, db_path, manager_request)
    queued_job = get_job(db_path, request.job_id)
    if queued_job is None:
        raise HTTPException(status_code=500, detail=f"Job disappeared after queueing: {request.job_id}")
    return DownloadJobCreateResponse(
        message="Download job queued",
        job=JobSummary.model_validate(queued_job),
    )
