from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from sentinel_orbit_downloader.api.deps import get_db_path
from sentinel_orbit_downloader.api.schemas import (
    JobSceneResponse,
    JobSummary,
    SearchJobCreateRequest,
    SearchJobCreateResponse,
    UploadedAoiResponse,
)
from sentinel_orbit_downloader.services.aoi import bbox_to_wkt, parse_uploaded_aoi
from sentinel_orbit_downloader.services.asf_client import SearchParams, query_scenes
from sentinel_orbit_downloader.services.project_store import (
    create_search_job,
    get_job,
    get_project,
    list_job_scenes,
    record_job_event,
    save_query_results,
    update_search_job,
)
from sentinel_orbit_downloader.services.region_catalog import get_region, region_wkt


router = APIRouter(prefix="/search-jobs", tags=["search-jobs"])


@router.post("/upload-aoi", response_model=UploadedAoiResponse)
async def upload_search_aoi_endpoint(
    files: list[UploadFile] = File(...),
) -> UploadedAoiResponse:
    uploads: list[tuple[str, bytes]] = []
    for file in files:
        if not file.filename:
            continue
        content = await file.read()
        uploads.append((file.filename, content))

    try:
        parsed = parse_uploaded_aoi(uploads)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return UploadedAoiResponse(
        name=parsed.name,
        source_format=parsed.source_format,
        geometry_type=parsed.geometry_type,
        feature_count=parsed.feature_count,
        bbox=parsed.bbox,
        wkt=parsed.wkt,
    )


@router.post("", response_model=SearchJobCreateResponse)
def create_search_job_endpoint(
    request: SearchJobCreateRequest,
    db_path=Depends(get_db_path),
) -> SearchJobCreateResponse:
    if request.project_id is not None and get_project(db_path, request.project_id) is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {request.project_id}")

    try:
        aoi_meta = resolve_search_aoi(request, db_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = create_search_job(
        db_path,
        project_id=request.project_id,
        source_type=aoi_meta["source_type"],
        source_value=aoi_meta["source_value"],
        region_adcode=aoi_meta["region_adcode"],
        region_name=aoi_meta["region_name"],
        start_time=request.start,
        end_time=request.end,
        processing_level=request.processing_level,
        beam_mode=request.beam_mode,
        flight_direction=request.flight_direction.upper() if request.flight_direction else None,
        polarization=request.polarization,
        relative_orbit=request.relative_orbit,
        max_results=request.max_results,
        manifest_path=request.manifest_path,
    )
    record_job_event(db_path, job.id, "info", "API search job created")

    try:
        params = SearchParams(
            aoi_wkt=aoi_meta["aoi_wkt"],
            start=request.start,
            end=request.end,
            processing_level=request.processing_level,
            beam_mode=request.beam_mode,
            flight_direction=request.flight_direction,
            polarization=request.polarization,
            relative_orbit=request.relative_orbit,
            max_results=request.max_results,
        )
        results = query_scenes(params)
        save_query_results(db_path, job.id, results)
        update_search_job(
            db_path,
            job.id,
            status="succeeded",
            result_count=len(results),
            manifest_path=request.manifest_path,
        )
        record_job_event(db_path, job.id, "info", f"API query returned {len(results)} scene(s)")
    except Exception as exc:
        update_search_job(db_path, job.id, status="failed", error_message=str(exc))
        record_job_event(db_path, job.id, "error", f"API search failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    final_job = get_job(db_path, job.id)
    if final_job is None:
        raise HTTPException(status_code=500, detail=f"Job disappeared after creation: {job.id}")
    scenes = [JobSceneResponse(**scene) for scene in list_job_scenes(db_path, job.id)]
    return SearchJobCreateResponse(
        job=JobSummary.model_validate(final_job),
        scenes=scenes,
    )


def resolve_search_aoi(request: SearchJobCreateRequest, db_path) -> dict[str, str | None]:
    if request.bbox:
        return {
            "aoi_wkt": bbox_to_wkt(request.bbox),
            "source_type": "bbox",
            "source_value": request.bbox,
            "region_adcode": None,
            "region_name": None,
        }
    if request.wkt:
        return {
            "aoi_wkt": request.wkt.strip(),
            "source_type": "aoi_file" if request.source_name else "wkt",
            "source_value": request.source_name.strip() if request.source_name else request.wkt.strip(),
            "region_adcode": None,
            "region_name": None,
        }
    if request.region_adcode:
        region = get_region(db_path, request.region_adcode)
        if region is None:
            raise ValueError(f"Region not found: {request.region_adcode}")
        return {
            "aoi_wkt": region_wkt(db_path, region.adcode, simplified=not request.raw_region),
            "source_type": "region",
            "source_value": region.label,
            "region_adcode": region.adcode,
            "region_name": region.label,
        }
    raise ValueError("one AOI input is required")
