from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DB_PATH = Path(".s1dl/app.db")
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8010


def configured_db_path() -> Path:
    raw = os.getenv("S1DL_DB_PATH")
    if not raw:
        return DEFAULT_DB_PATH
    return Path(raw)


def configured_api_host() -> str:
    return os.getenv("S1DL_API_HOST", DEFAULT_API_HOST)


def configured_api_port() -> int:
    raw = os.getenv("S1DL_API_PORT")
    if not raw:
        return DEFAULT_API_PORT
    return int(raw)
