from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import asf_search as asf

from sentinel_orbit_downloader.services.asf_client import build_session, credentials_available, scene_name_from_product
from sentinel_orbit_downloader.services.orbit_client import download_orbits
from sentinel_orbit_downloader.services.project_store import (
    get_job,
    get_project,
    list_job_scenes,
    record_download_result,
    record_job_event,
    update_search_job,
)


@dataclass(frozen=True)
class DownloadJobRequest:
    job_id: int
    data_dir: Path | None = None
    orbit_dir: Path | None = None
    manifest_path: Path | None = None
    skip_data: bool = False
    skip_orbits: bool = False
    processes: int = 2
    ignore_orbit_errors: bool = False
    username: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class DownloadJobPaths:
    root: Path
    data_dir: Path
    orbit_dir: Path
    manifest_path: Path


def resolve_download_paths(db_path: Path, request: DownloadJobRequest) -> DownloadJobPaths:
    job = get_job(db_path, request.job_id)
    if job is None:
        raise ValueError(f"Job not found: {request.job_id}")

    root = None
    if request.data_dir is not None:
        root = request.data_dir.parent if request.orbit_dir is None else request.data_dir.parent
    elif request.orbit_dir is not None:
        root = request.orbit_dir.parent
    elif job.data_dir:
        root = Path(job.data_dir).parent
    elif job.project_id is not None:
        project = get_project(db_path, job.project_id)
        if project is not None:
            root = Path(project.data_root) / "jobs" / f"job-{job.id:06d}"
    if root is None:
        root = Path(".s1dl") / "downloads" / f"job-{job.id:06d}"

    data_dir = request.data_dir or (Path(job.data_dir) if job.data_dir else root / "data")
    orbit_dir = request.orbit_dir or (Path(job.orbit_dir) if job.orbit_dir else root / "orbits")
    manifest_path = request.manifest_path or (
        Path(job.manifest_path) if job.manifest_path else root / "manifest.csv"
    )
    return DownloadJobPaths(root=root, data_dir=data_dir, orbit_dir=orbit_dir, manifest_path=manifest_path)


def queue_download_job(db_path: Path, request: DownloadJobRequest) -> DownloadJobPaths:
    job = get_job(db_path, request.job_id)
    if job is None:
        raise ValueError(f"Job not found: {request.job_id}")
    scenes = list_job_scenes(db_path, request.job_id)
    if not scenes:
        raise ValueError(f"Job has no scenes to download: {request.job_id}")

    paths = resolve_download_paths(db_path, request)
    paths.root.mkdir(parents=True, exist_ok=True)
    update_search_job(
        db_path,
        request.job_id,
        status="running",
        result_count=job.result_count,
        data_dir=str(paths.data_dir),
        orbit_dir=str(paths.orbit_dir),
        manifest_path=str(paths.manifest_path),
        error_message=None,
    )
    record_job_event(
        db_path,
        request.job_id,
        "info",
        f"Download queued for {len(scenes)} scene(s) into {paths.root}",
    )
    return paths


def execute_download_job(db_path: Path, request: DownloadJobRequest) -> None:
    job = get_job(db_path, request.job_id)
    if job is None:
        return

    paths = resolve_download_paths(db_path, request)
    paths.root.mkdir(parents=True, exist_ok=True)

    try:
        scenes = list_job_scenes(db_path, request.job_id)
        scene_ids = [scene["scene_id"] for scene in scenes]
        if not scene_ids:
            update_search_job(
                db_path,
                request.job_id,
                status="failed",
                result_count=0,
                data_dir=str(paths.data_dir),
                orbit_dir=str(paths.orbit_dir),
                manifest_path=str(paths.manifest_path),
                error_message="No scenes available for download",
            )
            record_job_event(db_path, request.job_id, "error", "Download job failed: no scenes available")
            return

        if not request.skip_data and not credentials_available(request.username, request.password):
            message = (
                "Download failed: Sentinel-1 product downloads require NASA Earthdata credentials. "
                "Fill in Earthdata username/password, or set EARTHDATA_USER and EARTHDATA_PASS first."
            )
            for scene_id in scene_ids:
                record_download_result(
                    db_path,
                    job_id=request.job_id,
                    scene_id=scene_id,
                    kind="product",
                    status="failed",
                    path=None,
                    error_message=message,
                )
                record_download_result(
                    db_path,
                    job_id=request.job_id,
                    scene_id=scene_id,
                    kind="orbit",
                    status="skipped",
                    path=None,
                )
            update_search_job(
                db_path,
                request.job_id,
                status="failed",
                result_count=job.result_count,
                data_dir=str(paths.data_dir),
                orbit_dir=str(paths.orbit_dir),
                manifest_path=str(paths.manifest_path),
                error_message=message,
            )
            record_job_event(db_path, request.job_id, "error", message)
            return

        product_error: str | None = None
        if request.skip_data:
            record_job_event(db_path, request.job_id, "info", "Product download skipped by request")
            record_product_skips(db_path, request.job_id, scene_ids)
        else:
            results = asf.granule_search(scene_ids)
            products = {scene_name_from_product(product): product for product in results}
            ordered_products = [products[scene_id] for scene_id in scene_ids if scene_id in products]
            missing_scene_ids = [scene_id for scene_id in scene_ids if scene_id not in products]
            if missing_scene_ids:
                record_job_event(
                    db_path,
                    request.job_id,
                    "warning",
                    f"{len(missing_scene_ids)} scene(s) could not be reloaded from ASF search",
                )
                for scene_id in missing_scene_ids:
                    record_download_result(
                        db_path,
                        job_id=request.job_id,
                        scene_id=scene_id,
                        kind="product",
                        status="failed",
                        path=None,
                        error_message="Scene was not returned by ASF granule_search",
                    )
                    if request.skip_orbits:
                        record_download_result(
                            db_path,
                            job_id=request.job_id,
                            scene_id=scene_id,
                            kind="orbit",
                            status="skipped",
                            path=None,
                        )
            paths.data_dir.mkdir(parents=True, exist_ok=True)
            try:
                session = build_session(username=request.username, password=request.password)
                results.download(path=str(paths.data_dir), session=session, processes=request.processes)
                record_job_event(
                    db_path,
                    request.job_id,
                    "info",
                    f"Product download finished into {paths.data_dir}",
                )
            except Exception as exc:
                product_error = str(exc)
                record_job_event(db_path, request.job_id, "error", f"Product download error: {exc}")
            record_product_downloads(db_path, request.job_id, ordered_products, paths.data_dir, product_error)

        orbit_failures = 0
        if request.skip_orbits:
            record_job_event(db_path, request.job_id, "info", "Orbit download skipped by request")
            record_orbit_skips(db_path, request.job_id, scene_ids)
        else:
            paths.orbit_dir.mkdir(parents=True, exist_ok=True)
            orbit_results = download_orbits(scene_ids, paths.orbit_dir)
            orbit_failures = sum(1 for result in orbit_results if result.error)
            for result in orbit_results:
                record_download_result(
                    db_path,
                    job_id=request.job_id,
                    scene_id=result.scene,
                    kind="orbit",
                    status="succeeded" if result.error is None else "failed",
                    path=str(result.path) if result.path is not None else None,
                    error_message=result.error,
                )
            record_job_event(
                db_path,
                request.job_id,
                "info",
                f"Orbit download finished: {len(orbit_results) - orbit_failures} ok, {orbit_failures} failed",
            )

        product_failures = count_download_failures(db_path, request.job_id, "product")
        effective_orbit_failures = 0 if request.ignore_orbit_errors else orbit_failures
        final_status = "succeeded"
        if product_failures or effective_orbit_failures:
            final_status = "partial_failed"
        if product_failures and (request.skip_orbits or effective_orbit_failures == len(scene_ids)):
            final_status = "failed"

        update_search_job(
            db_path,
            request.job_id,
            status=final_status,
            result_count=job.result_count,
            data_dir=str(paths.data_dir),
            orbit_dir=str(paths.orbit_dir),
            manifest_path=str(paths.manifest_path),
            error_message=product_error,
        )
    except Exception as exc:
        update_search_job(
            db_path,
            request.job_id,
            status="failed",
            result_count=job.result_count,
            data_dir=str(paths.data_dir),
            orbit_dir=str(paths.orbit_dir),
            manifest_path=str(paths.manifest_path),
            error_message=str(exc),
        )
        record_job_event(db_path, request.job_id, "error", f"Download execution failed: {exc}")


def record_product_downloads(
    db_path: Path,
    job_id: int,
    products: Sequence,
    data_dir: Path | None,
    fallback_error: str | None = None,
) -> None:
    for product in products:
        scene_id = scene_name_from_product(product)
        if scene_id is None:
            continue
        props = product.properties
        if data_dir is None:
            record_download_result(
                db_path,
                job_id=job_id,
                scene_id=scene_id,
                kind="product",
                status="skipped",
                path=None,
                url=string_value(props.get("url")),
                bytes_total=float(props["bytes"]) if props.get("bytes") is not None else None,
                bytes_done=0,
            )
            continue

        expected = expected_product_path(product, data_dir)
        exists = expected.exists()
        record_download_result(
            db_path,
            job_id=job_id,
            scene_id=scene_id,
            kind="product",
            status="succeeded" if exists else "failed",
            path=str(expected) if exists else None,
            url=string_value(props.get("url")),
            bytes_total=float(props["bytes"]) if props.get("bytes") is not None else None,
            bytes_done=float(props["bytes"]) if exists and props.get("bytes") is not None else None,
            error_message=None if exists else (fallback_error or "Downloaded file not found at expected path"),
        )


def record_product_skips(db_path: Path, job_id: int, scene_ids: Sequence[str]) -> None:
    for scene_id in scene_ids:
        record_download_result(
            db_path,
            job_id=job_id,
            scene_id=scene_id,
            kind="product",
            status="skipped",
            path=None,
        )


def record_orbit_skips(db_path: Path, job_id: int, scene_ids: Sequence[str]) -> None:
    for scene_id in scene_ids:
        record_download_result(
            db_path,
            job_id=job_id,
            scene_id=scene_id,
            kind="orbit",
            status="skipped",
            path=None,
        )


def expected_product_path(product, data_dir: Path) -> Path:
    props = product.properties
    file_name = props.get("fileName")
    if file_name:
        return data_dir / str(file_name)
    url = props.get("url")
    if url:
        return data_dir / Path(str(url)).name
    scene = scene_name_from_product(product) or "unknown_scene"
    return data_dir / f"{scene}.zip"


def string_value(value) -> str | None:
    if value is None:
        return None
    return str(value)


def count_download_failures(db_path: Path, job_id: int, kind: str) -> int:
    from sentinel_orbit_downloader.storage.db import connect

    if kind == "product":
        column = "product_status"
    elif kind == "orbit":
        column = "orbit_status"
    else:
        raise ValueError(f"unsupported download kind: {kind}")

    with connect(db_path) as connection:
        row = connection.execute(
            f"""
            SELECT COUNT(*) AS failure_count
            FROM job_scenes
            WHERE job_id = ? AND {column} = 'failed'
            """,
            (job_id,),
        ).fetchone()
    return int(row["failure_count"])
