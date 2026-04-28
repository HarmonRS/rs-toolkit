from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HealthResponse(BaseModel):
    status: str
    db_path: str


class RegionSummary(BaseModel):
    adcode: str
    name: str
    level: str
    parent_adcode: str | None = None
    parent_name: str | None = None
    province_adcode: str | None = None
    province_name: str | None = None
    label: str
    bbox: list[float] | None = None
    simplify_tolerance: float


class RegionDetail(RegionSummary):
    center: list[float] | None = None
    centroid: list[float] | None = None
    geometry_json: dict[str, Any]
    wkt: str
    simplified_wkt: str
    children_num: int | None = None
    tree_id: str | None = None


class RegionImportRequest(BaseModel):
    source_path: str = Field(default="\u5168\u56fd\u884c\u653f\u533a.geojson")
    simplify_tolerance: float = Field(default=0.01, gt=0)


class RegionImportResponse(BaseModel):
    source_path: str
    simplify_tolerance: float
    total_features: int
    imported: int


class ProjectCreateRequest(BaseModel):
    name: str
    data_root: str
    description: str | None = None
    slug: str | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    data_root: str
    description: str | None = None
    created_at: str
    updated_at: str


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None = None
    source_type: str
    source_value: str | None = None
    region_adcode: str | None = None
    region_name: str | None = None
    start_time: str
    end_time: str
    processing_level: str
    beam_mode: str | None = None
    flight_direction: str | None = None
    polarization: str | None = None
    relative_orbit: int | None = None
    max_results: int
    status: str
    result_count: int | None = None
    data_dir: str | None = None
    orbit_dir: str | None = None
    manifest_path: str | None = None
    error_message: str | None = None
    created_at: str
    finished_at: str | None = None


class JobSceneResponse(BaseModel):
    job_id: int
    scene_id: str
    selected: int
    product_status: str
    orbit_status: str
    product_path: str | None = None
    orbit_path: str | None = None
    platform: str | None = None
    start_time: str | None = None
    stop_time: str | None = None
    processing_level: str | None = None
    flight_direction: str | None = None
    relative_orbit: int | None = None
    size_mb: float | None = None


class JobEventResponse(BaseModel):
    id: int
    level: str
    message: str
    created_at: str


class JobDetailResponse(BaseModel):
    job: JobSummary
    scenes: list[JobSceneResponse]
    events: list[JobEventResponse] = Field(default_factory=list)


class SearchJobCreateRequest(BaseModel):
    project_id: int | None = None
    bbox: str | None = None
    wkt: str | None = None
    region_adcode: str | None = None
    start: str
    end: str
    processing_level: str = "SLC"
    beam_mode: str | None = "IW"
    flight_direction: str | None = None
    polarization: str | None = None
    relative_orbit: int | None = None
    max_results: int = Field(default=50, ge=1)
    manifest_path: str | None = None
    raw_region: bool = False

    @model_validator(mode="after")
    def validate_aoi(self) -> "SearchJobCreateRequest":
        provided = [self.bbox, self.wkt, self.region_adcode]
        count = sum(1 for value in provided if value)
        if count != 1:
            raise ValueError("provide exactly one of bbox, wkt, or region_adcode")
        return self


class SearchJobCreateResponse(BaseModel):
    job: JobSummary
    scenes: list[JobSceneResponse]


class DownloadJobCreateRequest(BaseModel):
    job_id: int = Field(ge=1)
    data_dir: str | None = None
    orbit_dir: str | None = None
    manifest_path: str | None = None
    skip_data: bool = False
    skip_orbits: bool = False
    processes: int = Field(default=2, ge=1)
    ignore_orbit_errors: bool = False
    username: str | None = None
    password: str | None = None

    @model_validator(mode="after")
    def validate_download_flags(self) -> "DownloadJobCreateRequest":
        if self.skip_data and self.skip_orbits:
            raise ValueError("skip_data and skip_orbits cannot both be true")
        return self


class DownloadJobCreateResponse(BaseModel):
    message: str
    job: JobSummary


class MessageResponse(BaseModel):
    message: str


class EarthdataSettingsRequest(BaseModel):
    username: str
    password: str


class EarthdataSettingsResponse(BaseModel):
    username: str | None = None
    has_password: bool = False


class JobDeleteResponse(BaseModel):
    message: str
    deleted_count: int
    deleted_job_ids: list[int] = Field(default_factory=list)
