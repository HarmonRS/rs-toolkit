from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from sentinel_orbit_downloader.api.deps import get_db_path
from sentinel_orbit_downloader.api.schemas import ProjectCreateRequest, ProjectResponse
from sentinel_orbit_downloader.services.project_store import create_project, get_project, list_projects


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def projects(db_path=Depends(get_db_path)) -> list[ProjectResponse]:
    return [ProjectResponse.model_validate(project) for project in list_projects(db_path)]


@router.post("", response_model=ProjectResponse)
def create_project_endpoint(
    request: ProjectCreateRequest,
    db_path=Depends(get_db_path),
) -> ProjectResponse:
    try:
        project = create_project(
            db_path,
            name=request.name,
            data_root=Path(request.data_root),
            description=request.description,
            slug=request.slug,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
def project_detail(project_id: int, db_path=Depends(get_db_path)) -> ProjectResponse:
    project = get_project(db_path, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return ProjectResponse.model_validate(project)
