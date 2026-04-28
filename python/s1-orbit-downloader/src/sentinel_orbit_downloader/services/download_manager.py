from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Sequence
import zipfile

import asf_search as asf
from asf_search.download.download import strip_auth_if_aws

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


@dataclass(frozen=True)
class ProductDownloadResult:
    scene_id: str
    status: str
    path: Path | None
    url: str | None
    bytes_total: float | None
    bytes_done: float | None
    error_message: str | None = None


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
            products = select_data_products(results, scene_ids, job.processing_level)
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
            session = build_session(username=request.username, password=request.password)
            product_attempts = max(1, min(5, request.processes))
            product_results: list[ProductDownloadResult] = []
            for index, product in enumerate(ordered_products, start=1):
                scene_id = scene_name_from_product(product) or f"scene #{index}"
                record_job_event(
                    db_path,
                    request.job_id,
                    "info",
                    f"Product download {index}/{len(ordered_products)} started: {scene_id}",
                )
                result = download_product_with_retries(
                    product,
                    paths.data_dir,
                    session,
                    attempts=product_attempts,
                )
                product_results.append(result)
                record_product_download_result(db_path, request.job_id, result)
                if result.status == "succeeded":
                    record_job_event(
                        db_path,
                        request.job_id,
                        "info",
                        f"Product download {index}/{len(ordered_products)} succeeded: {scene_id}",
                    )
                else:
                    record_job_event(
                        db_path,
                        request.job_id,
                        "warning",
                        f"Product download {index}/{len(ordered_products)} failed: {scene_id}; {result.error_message}",
                    )

            product_failures = sum(1 for result in product_results if result.status == "failed") + len(
                missing_scene_ids
            )
            product_successes = sum(1 for result in product_results if result.status == "succeeded")
            if product_failures:
                product_error = f"Product download failed for {product_failures} of {len(scene_ids)} scene(s)"
            record_job_event(
                db_path,
                request.job_id,
                "info",
                f"Product download finished: {product_successes} ok, {product_failures} failed",
            )

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
        product_successes = count_download_status(db_path, request.job_id, "product", "succeeded")
        effective_orbit_failures = 0 if request.ignore_orbit_errors else orbit_failures
        final_status = "succeeded"
        if product_failures or effective_orbit_failures:
            final_status = "partial_failed"

        if not request.skip_data and product_failures and product_successes == 0:
            final_status = "failed"
        elif request.skip_data and not request.skip_orbits and effective_orbit_failures == len(scene_ids):
            final_status = "failed"

        error_message = None
        if final_status != "succeeded":
            error_message = summarize_failure(
                product_failures=product_failures if not request.skip_data else 0,
                orbit_failures=effective_orbit_failures if not request.skip_orbits else 0,
                scene_count=len(scene_ids),
                fallback=product_error,
            )

        update_search_job(
            db_path,
            request.job_id,
            status=final_status,
            result_count=job.result_count,
            data_dir=str(paths.data_dir),
            orbit_dir=str(paths.orbit_dir),
            manifest_path=str(paths.manifest_path),
            error_message=error_message,
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


def record_product_download_result(db_path: Path, job_id: int, result: ProductDownloadResult) -> None:
    record_download_result(
        db_path,
        job_id=job_id,
        scene_id=result.scene_id,
        kind="product",
        status=result.status,
        path=str(result.path) if result.path is not None else None,
        url=result.url,
        bytes_total=result.bytes_total,
        bytes_done=result.bytes_done,
        error_message=result.error_message,
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


def select_data_products(results, scene_ids: Sequence[str], processing_level: str) -> dict[str, object]:
    wanted = set(scene_ids)
    selected: dict[str, object] = {}
    selected_rank: dict[str, int] = {}
    for product in results:
        scene_id = scene_name_from_product(product)
        if scene_id not in wanted:
            continue
        rank = data_product_rank(product, processing_level)
        if rank is None:
            continue
        current_rank = selected_rank.get(scene_id)
        if current_rank is None or rank < current_rank:
            selected[scene_id] = product
            selected_rank[scene_id] = rank
    return selected


def data_product_rank(product, processing_level: str) -> int | None:
    props = product.properties
    product_level = string_value(props.get("processingLevel"))
    file_name = string_value(props.get("fileName")) or ""
    url = string_value(props.get("url")) or ""
    lower_name = file_name.lower()
    lower_url = url.lower()

    if product_level and product_level.upper().startswith("METADATA"):
        return None
    if lower_name.endswith(".iso.xml") or lower_url.endswith(".iso.xml"):
        return None
    if processing_level and product_level and product_level.upper() == processing_level.upper():
        return 0
    if lower_name.endswith(".zip") or lower_url.endswith(".zip"):
        return 1
    return None


def download_product_with_retries(product, data_dir: Path, session, attempts: int = 3) -> ProductDownloadResult:
    scene_id = scene_name_from_product(product) or "unknown_scene"
    props = product.properties
    expected = expected_product_path(product, data_dir)
    bytes_total = float(props["bytes"]) if props.get("bytes") is not None else None
    expected_size = int(props["bytes"]) if props.get("bytes") is not None else None
    url = product_download_url(product)

    if file_complete(expected, expected_size):
        return ProductDownloadResult(
            scene_id=scene_id,
            status="succeeded",
            path=expected,
            url=url,
            bytes_total=bytes_total,
            bytes_done=float(expected.stat().st_size),
        )

    last_error = "Downloaded file not found at expected path"
    for attempt in range(1, max(1, attempts) + 1):
        try:
            if url is None:
                raise ValueError("Product has no downloadable URL")
            download_product_file(url, expected, session, expected_size)
            if file_complete(expected, expected_size):
                return ProductDownloadResult(
                    scene_id=scene_id,
                    status="succeeded",
                    path=expected,
                    url=url,
                    bytes_total=bytes_total,
                    bytes_done=float(expected.stat().st_size),
                )
            if expected.exists():
                last_error = (
                    f"Downloaded file size mismatch: got {expected.stat().st_size}, expected {expected_size}"
                )
            else:
                last_error = "Downloaded file not found at expected path"
        except Exception as exc:
            last_error = str(exc) or exc.__class__.__name__

        if attempt < attempts:
            time.sleep(min(15, attempt * 3))

    part_path = partial_product_path(expected)
    return ProductDownloadResult(
        scene_id=scene_id,
        status="failed",
        path=None,
        url=url,
        bytes_total=bytes_total,
        bytes_done=partial_size(expected, part_path),
        error_message=last_error,
    )


def product_download_url(product) -> str | None:
    try:
        urls = product.get_urls()
    except Exception:
        urls = []
    if urls:
        return str(urls[0])
    return string_value(product.properties.get("url"))


def download_product_file(url: str, final_path: Path, session, expected_size: int | None) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    if file_complete(final_path, expected_size):
        return

    part_path = prepare_partial_file(final_path, expected_size)
    if validate_product_file(part_path, expected_size) is None:
        part_path.replace(final_path)
        return

    resume_from = part_path.stat().st_size if part_path.exists() else 0
    headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
    response = session.get(
        url,
        stream=True,
        headers=headers,
        hooks={"response": strip_auth_if_aws},
        timeout=(30, 120),
    )
    try:
        response.raise_for_status()

        if resume_from and response.status_code != 206:
            part_path.unlink(missing_ok=True)
            resume_from = 0
        elif resume_from:
            validate_content_range(response.headers.get("Content-Range"), resume_from)

        mode = "ab" if resume_from else "wb"
        with part_path.open(mode) as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    finally:
        response.close()

    validation_error = validate_product_file(part_path, expected_size)
    if validation_error is not None:
        raise IOError(validation_error)

    part_path.replace(final_path)


def prepare_partial_file(final_path: Path, expected_size: int | None) -> Path:
    part_path = partial_product_path(final_path)

    if final_path.exists() and not file_complete(final_path, expected_size):
        final_size = final_path.stat().st_size
        if expected_size is not None and final_size < expected_size and not part_path.exists():
            final_path.replace(part_path)
        else:
            final_path.unlink()

    if part_path.exists() and expected_size is not None:
        part_size = part_path.stat().st_size
        if part_size > expected_size or (
            part_size == expected_size and validate_product_file(part_path, expected_size)
        ):
            part_path.unlink()

    return part_path


def partial_product_path(final_path: Path) -> Path:
    return final_path.with_name(f"{final_path.name}.part")


def file_complete(path: Path, expected_size: int | None) -> bool:
    return validate_product_file(path, expected_size) is None


def validate_product_file(path: Path, expected_size: int | None) -> str | None:
    if not path.exists() or not path.is_file():
        return "Downloaded file not found at expected path"
    actual_size = path.stat().st_size
    if expected_size is not None and actual_size != expected_size:
        return f"Downloaded file size mismatch: got {actual_size}, expected {expected_size}"
    lower_name = path.name.lower()
    if (lower_name.endswith(".zip") or lower_name.endswith(".zip.part")) and not zipfile.is_zipfile(path):
        return "Downloaded ZIP failed integrity check"
    return None


def validate_content_range(content_range: str | None, expected_start: int) -> None:
    if not content_range:
        return
    prefix = f"bytes {expected_start}-"
    if not content_range.startswith(prefix):
        raise IOError(f"Unexpected resume range from server: {content_range}")


def partial_size(final_path: Path, part_path: Path) -> float | None:
    if final_path.exists():
        return float(final_path.stat().st_size)
    if part_path.exists():
        return float(part_path.stat().st_size)
    return None


def string_value(value) -> str | None:
    if value is None:
        return None
    return str(value)


def count_download_failures(db_path: Path, job_id: int, kind: str) -> int:
    return count_download_status(db_path, job_id, kind, "failed")


def count_download_status(db_path: Path, job_id: int, kind: str, status: str) -> int:
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
            SELECT COUNT(*) AS status_count
            FROM job_scenes
            WHERE job_id = ? AND {column} = ?
            """,
            (job_id, status),
        ).fetchone()
    return int(row["status_count"])


def summarize_failure(
    *,
    product_failures: int,
    orbit_failures: int,
    scene_count: int,
    fallback: str | None,
) -> str:
    parts = []
    if product_failures:
        parts.append(f"Product failed for {product_failures}/{scene_count} scene(s)")
    if orbit_failures:
        parts.append(f"Orbit failed for {orbit_failures}/{scene_count} scene(s)")
    if parts:
        return "; ".join(parts)
    return fallback or "Download finished with failures"
