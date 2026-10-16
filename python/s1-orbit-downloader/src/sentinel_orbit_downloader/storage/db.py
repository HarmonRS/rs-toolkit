from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS regions (
    adcode TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    parent_adcode TEXT,
    province_adcode TEXT,
    province_name TEXT,
    center_lon REAL,
    center_lat REAL,
    centroid_lon REAL,
    centroid_lat REAL,
    min_lon REAL,
    min_lat REAL,
    max_lon REAL,
    max_lat REAL,
    children_num INTEGER,
    tree_id TEXT,
    source_path TEXT,
    geometry_json TEXT NOT NULL,
    wkt TEXT NOT NULL,
    simplified_wkt TEXT NOT NULL,
    simplify_tolerance REAL NOT NULL,
    geometry_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_regions_name ON regions(name);
CREATE INDEX IF NOT EXISTS idx_regions_level ON regions(level);
CREATE INDEX IF NOT EXISTS idx_regions_parent ON regions(parent_adcode);
CREATE INDEX IF NOT EXISTS idx_regions_province ON regions(province_adcode);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    data_root TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aois (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    region_adcode TEXT,
    wkt TEXT NOT NULL,
    bbox_json TEXT,
    geometry_json TEXT,
    simplification_tolerance REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS search_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    aoi_id INTEGER,
    source_type TEXT NOT NULL,
    source_value TEXT,
    region_adcode TEXT,
    region_name TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    processing_level TEXT NOT NULL,
    beam_mode TEXT,
    flight_direction TEXT,
    polarization TEXT,
    relative_orbit INTEGER,
    max_results INTEGER NOT NULL,
    status TEXT NOT NULL,
    result_count INTEGER,
    data_dir TEXT,
    orbit_dir TEXT,
    manifest_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(aoi_id) REFERENCES aois(id)
);

CREATE INDEX IF NOT EXISTS idx_search_jobs_project ON search_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_search_jobs_created ON search_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_search_jobs_region ON search_jobs(region_adcode);

CREATE TABLE IF NOT EXISTS scenes (
    scene_id TEXT PRIMARY KEY,
    platform TEXT,
    start_time TEXT,
    stop_time TEXT,
    processing_level TEXT,
    beam_mode TEXT,
    flight_direction TEXT,
    polarization TEXT,
    relative_orbit INTEGER,
    size_bytes REAL,
    size_mb REAL,
    download_url TEXT,
    geometry_json TEXT,
    properties_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_scenes (
    job_id INTEGER NOT NULL,
    scene_id TEXT NOT NULL,
    selected INTEGER NOT NULL DEFAULT 1,
    product_status TEXT NOT NULL DEFAULT 'pending',
    orbit_status TEXT NOT NULL DEFAULT 'pending',
    product_path TEXT,
    orbit_path TEXT,
    PRIMARY KEY(job_id, scene_id),
    FOREIGN KEY(job_id) REFERENCES search_jobs(id),
    FOREIGN KEY(scene_id) REFERENCES scenes(scene_id)
);

CREATE INDEX IF NOT EXISTS idx_job_scenes_scene ON job_scenes(scene_id);

CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    scene_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    url TEXT,
    path TEXT,
    bytes_total REAL,
    bytes_done REAL,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(job_id) REFERENCES search_jobs(id),
    FOREIGN KEY(scene_id) REFERENCES scenes(scene_id)
);

CREATE INDEX IF NOT EXISTS idx_downloads_job ON downloads(job_id);
CREATE INDEX IF NOT EXISTS idx_downloads_scene ON downloads(scene_id);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(job_id) REFERENCES search_jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def set_setting(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO settings(key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )


def get_setting(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return str(row["value"])
