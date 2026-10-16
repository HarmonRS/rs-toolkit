from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sentinel_orbit_downloader.storage.db import connect


NON_SLUG_RE = re.compile(r"[^\w\u4e00-\u9fff-]+", re.UNICODE)


@dataclass(frozen=True)
class ProjectRecord:
    id: int
    name: str
    slug: str
    data_root: str
    description: str | None
    created_at: str
    updated_at: str


def create_project(
    db_path: Path,
    name: str,
    data_root: Path,
    description: str | None = None,
    slug: str | None = None,
) -> ProjectRecord:
    final_slug = slug or slugify(name)
    if not final_slug:
        raise ValueError("project slug is empty; choose a clearer project name")

    data_root.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as connection:
        exists = connection.execute("SELECT id FROM projects WHERE slug = ?", (final_slug,)).fetchone()
        if exists is not None:
            raise ValueError(f"project slug already exists: {final_slug}")

        cursor = connection.execute(
            """
            INSERT INTO projects(name, slug, data_root, description)
            VALUES (?, ?, ?, ?)
            """,
            (name, final_slug, str(data_root), description),
        )
        project_id = int(cursor.lastrowid)
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    return row_to_project(row)


def list_projects(db_path: Path) -> list[ProjectRecord]:
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM projects ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [row_to_project(row) for row in rows]


def get_project(db_path: Path, project_id: int) -> ProjectRecord | None:
    with connect(db_path) as connection:
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    return row_to_project(row)


def slugify(value: str) -> str:
    text = value.strip().lower().replace(" ", "-")
    text = NON_SLUG_RE.sub("-", text)
    text = re.sub(r"-{2,}", "-", text)
    text = text.strip("-")
    return text


def row_to_project(row) -> ProjectRecord:
    return ProjectRecord(
        id=int(row["id"]),
        name=str(row["name"]),
        slug=str(row["slug"]),
        data_root=str(row["data_root"]),
        description=row["description"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


@dataclass(frozen=True)
class SearchJobRecord:
    id: int
    project_id: int | None
    aoi_id: int | None
    source_type: str
    source_value: str | None
    region_adcode: str | None
    region_name: str | None
    start_time: str
    end_time: str
    processing_level: str
    beam_mode: str | None
    flight_direction: str | None
    polarization: str | None
    relative_orbit: int | None
    max_results: int
    status: str
    result_count: int | None
    data_dir: str | None
    orbit_dir: str | None
    manifest_path: str | None
    error_message: str | None
    created_at: str
    finished_at: str | None


def create_search_job(
    db_path: Path,
    *,
    project_id: int | None,
    source_type: str,
    source_value: str | None,
    region_adcode: str | None,
    region_name: str | None,
    start_time: str,
    end_time: str,
    processing_level: str,
    beam_mode: str | None,
    flight_direction: str | None,
    polarization: str | None,
    relative_orbit: int | None,
    max_results: int,
    status: str = "running",
    data_dir: str | None = None,
    orbit_dir: str | None = None,
    manifest_path: str | None = None,
) -> SearchJobRecord:
    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO search_jobs(
                project_id, aoi_id, source_type, source_value, region_adcode, region_name,
                start_time, end_time, processing_level, beam_mode, flight_direction,
                polarization, relative_orbit, max_results, status, data_dir, orbit_dir, manifest_path
            )
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                source_type,
                source_value,
                region_adcode,
                region_name,
                start_time,
                end_time,
                processing_level,
                beam_mode,
                flight_direction,
                polarization,
                relative_orbit,
                max_results,
                status,
                data_dir,
                orbit_dir,
                manifest_path,
            ),
        )
        job_id = int(cursor.lastrowid)
        row = connection.execute("SELECT * FROM search_jobs WHERE id = ?", (job_id,)).fetchone()
    return row_to_search_job(row)


def update_search_job(
    db_path: Path,
    job_id: int,
    *,
    status: str,
    result_count: int | None = None,
    data_dir: str | None = None,
    orbit_dir: str | None = None,
    manifest_path: str | None = None,
    error_message: str | None = None,
) -> None:
    final_statuses = {"succeeded", "failed", "partial_failed", "canceled"}
    with connect(db_path) as connection:
        if status in final_statuses:
            connection.execute(
                """
                UPDATE search_jobs
                SET
                    status = ?,
                    result_count = COALESCE(?, result_count),
                    data_dir = COALESCE(?, data_dir),
                    orbit_dir = COALESCE(?, orbit_dir),
                    manifest_path = COALESCE(?, manifest_path),
                    error_message = ?,
                    finished_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    status,
                    result_count,
                    data_dir,
                    orbit_dir,
                    manifest_path,
                    error_message,
                    job_id,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE search_jobs
                SET
                    status = ?,
                    result_count = COALESCE(?, result_count),
                    data_dir = COALESCE(?, data_dir),
                    orbit_dir = COALESCE(?, orbit_dir),
                    manifest_path = COALESCE(?, manifest_path),
                    error_message = ?,
                    finished_at = NULL
                WHERE id = ?
                """,
                (
                    status,
                    result_count,
                    data_dir,
                    orbit_dir,
                    manifest_path,
                    error_message,
                    job_id,
                ),
            )


def record_job_event(db_path: Path, job_id: int, level: str, message: str) -> None:
    with connect(db_path) as connection:
        if not job_exists(connection, job_id):
            return
        connection.execute(
            "INSERT INTO job_events(job_id, level, message) VALUES (?, ?, ?)",
            (job_id, level, message),
        )


def save_query_results(db_path: Path, job_id: int, results) -> None:
    with connect(db_path) as connection:
        if not job_exists(connection, job_id):
            return
        for product in results:
            scene_id = scene_id_from_product(product)
            if scene_id is None:
                continue
            props = product.properties
            geometry_json = json.dumps(product.geometry, ensure_ascii=False, default=str)
            properties_json = json.dumps(props, ensure_ascii=False, default=str)
            connection.execute(
                """
                INSERT INTO scenes(
                    scene_id, platform, start_time, stop_time, processing_level, beam_mode,
                    flight_direction, polarization, relative_orbit, size_bytes, size_mb,
                    download_url, geometry_json, properties_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scene_id) DO UPDATE SET
                    platform = excluded.platform,
                    start_time = excluded.start_time,
                    stop_time = excluded.stop_time,
                    processing_level = excluded.processing_level,
                    beam_mode = excluded.beam_mode,
                    flight_direction = excluded.flight_direction,
                    polarization = excluded.polarization,
                    relative_orbit = excluded.relative_orbit,
                    size_bytes = excluded.size_bytes,
                    size_mb = excluded.size_mb,
                    download_url = excluded.download_url,
                    geometry_json = excluded.geometry_json,
                    properties_json = excluded.properties_json
                """,
                (
                    scene_id,
                    platform_from_scene(scene_id),
                    string_value(props.get("startTime")),
                    string_value(props.get("stopTime")),
                    string_value(props.get("processingLevel")),
                    string_value(props.get("beamModeType")),
                    string_value(props.get("flightDirection")),
                    string_value(props.get("polarization")),
                    int(props["pathNumber"]) if props.get("pathNumber") is not None else None,
                    float(props["bytes"]) if props.get("bytes") is not None else None,
                    product_size_mb(props),
                    string_value(props.get("url")),
                    geometry_json,
                    properties_json,
                ),
            )
            connection.execute(
                """
                INSERT INTO job_scenes(job_id, scene_id, selected, product_status, orbit_status)
                VALUES (?, ?, 1, 'pending', 'pending')
                ON CONFLICT(job_id, scene_id) DO NOTHING
                """,
                (job_id, scene_id),
            )


def record_download_result(
    db_path: Path,
    *,
    job_id: int,
    scene_id: str,
    kind: str,
    status: str,
    path: str | None,
    url: str | None = None,
    bytes_total: float | None = None,
    bytes_done: float | None = None,
    error_message: str | None = None,
) -> None:
    with connect(db_path) as connection:
        if not job_exists(connection, job_id):
            return
        connection.execute(
            """
            INSERT INTO downloads(
                job_id, scene_id, kind, status, url, path, bytes_total, bytes_done, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                scene_id,
                kind,
                status,
                url,
                path,
                bytes_total,
                bytes_done,
                error_message,
            ),
        )
        if kind == "product":
            connection.execute(
                """
                UPDATE job_scenes
                SET product_status = ?, product_path = COALESCE(?, product_path)
                WHERE job_id = ? AND scene_id = ?
                """,
                (status, path, job_id, scene_id),
            )
        elif kind == "orbit":
            connection.execute(
                """
                UPDATE job_scenes
                SET orbit_status = ?, orbit_path = COALESCE(?, orbit_path)
                WHERE job_id = ? AND scene_id = ?
                """,
                (status, path, job_id, scene_id),
            )


def delete_job(db_path: Path, job_id: int) -> bool:
    with connect(db_path) as connection:
        if not job_exists(connection, job_id):
            return False
        delete_job_rows(connection, job_id)
        prune_orphan_scenes(connection)
    return True


def clear_jobs(
    db_path: Path,
    project_id: int | None = None,
    include_running: bool = False,
) -> list[int]:
    sql = "SELECT id FROM search_jobs"
    conditions: list[str] = []
    params: list[Any] = []

    if project_id is not None:
        conditions.append("project_id = ?")
        params.append(project_id)
    if not include_running:
        conditions.append("status != 'running'")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id"

    with connect(db_path) as connection:
        rows = connection.execute(sql, params).fetchall()
        job_ids = [int(row["id"]) for row in rows]
        for job_id in job_ids:
            delete_job_rows(connection, job_id)
        prune_orphan_scenes(connection)
    return job_ids


def list_jobs(db_path: Path, project_id: int | None = None, limit: int = 20) -> list[SearchJobRecord]:
    sql = """
    SELECT *
    FROM search_jobs
    """
    params: list[Any] = []
    if project_id is not None:
        sql += " WHERE project_id = ?"
        params.append(project_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with connect(db_path) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [row_to_search_job(row) for row in rows]


def get_job(db_path: Path, job_id: int) -> SearchJobRecord | None:
    with connect(db_path) as connection:
        row = connection.execute("SELECT * FROM search_jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return row_to_search_job(row)


def list_job_scenes(db_path: Path, job_id: int) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                js.job_id,
                js.scene_id,
                js.selected,
                js.product_status,
                js.orbit_status,
                js.product_path,
                js.orbit_path,
                s.platform,
                s.start_time,
                s.stop_time,
                s.processing_level,
                s.flight_direction,
                s.relative_orbit,
                s.size_mb
            FROM job_scenes AS js
            JOIN scenes AS s ON s.scene_id = js.scene_id
            WHERE js.job_id = ?
            ORDER BY s.start_time, js.scene_id
            """,
            (job_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_job_events(db_path: Path, job_id: int) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, level, message, created_at FROM job_events WHERE job_id = ? ORDER BY id",
            (job_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def row_to_search_job(row) -> SearchJobRecord:
    return SearchJobRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]) if row["project_id"] is not None else None,
        aoi_id=int(row["aoi_id"]) if row["aoi_id"] is not None else None,
        source_type=str(row["source_type"]),
        source_value=row["source_value"],
        region_adcode=row["region_adcode"],
        region_name=row["region_name"],
        start_time=str(row["start_time"]),
        end_time=str(row["end_time"]),
        processing_level=str(row["processing_level"]),
        beam_mode=row["beam_mode"],
        flight_direction=row["flight_direction"],
        polarization=row["polarization"],
        relative_orbit=int(row["relative_orbit"]) if row["relative_orbit"] is not None else None,
        max_results=int(row["max_results"]),
        status=str(row["status"]),
        result_count=int(row["result_count"]) if row["result_count"] is not None else None,
        data_dir=row["data_dir"],
        orbit_dir=row["orbit_dir"],
        manifest_path=row["manifest_path"],
        error_message=row["error_message"],
        created_at=str(row["created_at"]),
        finished_at=row["finished_at"],
    )


def scene_id_from_product(product) -> str | None:
    from sentinel_orbit_downloader.services.asf_client import scene_name_from_product

    return scene_name_from_product(product)


def platform_from_scene(scene_id: str) -> str | None:
    parts = scene_id.split("_", 1)
    if not parts:
        return None
    return parts[0]


def product_size_mb(props: dict[str, Any]) -> float | None:
    if props.get("sizeMB") is not None:
        return float(props["sizeMB"])
    if props.get("bytes") is not None:
        return float(props["bytes"]) / (1024 * 1024)
    return None


def string_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def job_exists(connection, job_id: int) -> bool:
    row = connection.execute(
        "SELECT 1 FROM search_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    return row is not None


def delete_job_rows(connection, job_id: int) -> None:
    connection.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
    connection.execute("DELETE FROM downloads WHERE job_id = ?", (job_id,))
    connection.execute("DELETE FROM job_scenes WHERE job_id = ?", (job_id,))
    connection.execute("DELETE FROM search_jobs WHERE id = ?", (job_id,))


def prune_orphan_scenes(connection) -> None:
    connection.execute(
        """
        DELETE FROM scenes
        WHERE NOT EXISTS (
            SELECT 1
            FROM job_scenes
            WHERE job_scenes.scene_id = scenes.scene_id
        )
        """
    )
