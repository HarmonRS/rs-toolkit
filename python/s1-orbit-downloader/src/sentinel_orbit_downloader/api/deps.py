from __future__ import annotations

from pathlib import Path

from sentinel_orbit_downloader.core.config import configured_db_path


def get_db_path() -> Path:
    return configured_db_path()
