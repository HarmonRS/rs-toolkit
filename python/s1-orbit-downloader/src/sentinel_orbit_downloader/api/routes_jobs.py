from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from sentinel_orbit_downloader.api.deps import get_db_path
from sentinel_orbit_downloader.api.schemas import (
    JobDeleteResponse,
    JobDetailResponse,
    JobEventResponse,
    JobSceneResponse,
    JobSummary,
)
from sentinel_orbit_downloader.services.project_store import (
    clear_jobs,
    delete_job,
    get_job,
    list_job_events,
    list_job_scenes,
    list_jobs,
)


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobSummary])
def jobs(
    project_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    db_path=Depends(get_db_path),
) -> list[JobSummary]:
    return [JobSummary.model_validate(job) for job in list_jobs(db_path, project_id=project_id, limit=limit)]


@router.delete("", response_model=JobDeleteResponse)
def clear_jobs_endpoint(
    project_id: int | None = Query(default=None),
    force: bool = Query(default=False),
    db_path=Depends(get_db_path),
) -> JobDeleteResponse:
    deleted_job_ids = clear_jobs(db_path, project_id=project_id, include_running=force)
    return JobDeleteResponse(
        message="任务已清空" if deleted_job_ids else "没有可清空的任务",
        deleted_count=len(deleted_job_ids),
        deleted_job_ids=deleted_job_ids,
    )


@router.get("/{job_id}", response_model=JobDetailResponse)
def job_detail(
    job_id: int,
    include_events: bool = Query(default=False),
    db_path=Depends(get_db_path),
) -> JobDetailResponse:
    job = get_job(db_path, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    scenes = [JobSceneResponse(**scene) for scene in list_job_scenes(db_path, job_id)]
    events = []
    if include_events:
        events = [JobEventResponse(**event) for event in list_job_events(db_path, job_id)]
    return JobDetailResponse(
        job=JobSummary.model_validate(job),
        scenes=scenes,
        events=events,
    )


@router.delete("/{job_id}", response_model=JobDeleteResponse, status_code=status.HTTP_200_OK)
def delete_job_endpoint(
    job_id: int,
    force: bool = Query(default=False),
    db_path=Depends(get_db_path),
) -> JobDeleteResponse:
    job = get_job(db_path, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if job.status == "running" and not force:
        raise HTTPException(
            status_code=409,
            detail="任务仍在运行。请先停止服务后再删，或使用强制删除。",
        )
    deleted = delete_job(db_path, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return JobDeleteResponse(
        message="任务已删除",
        deleted_count=1,
        deleted_job_ids=[job_id],
    )
