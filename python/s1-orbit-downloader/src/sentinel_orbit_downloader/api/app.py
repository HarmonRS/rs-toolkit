from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sentinel_orbit_downloader.api.routes_downloads import router as downloads_router
from sentinel_orbit_downloader.api.routes_health import router as health_router
from sentinel_orbit_downloader.api.routes_jobs import router as jobs_router
from sentinel_orbit_downloader.api.routes_projects import router as projects_router
from sentinel_orbit_downloader.api.routes_regions import router as regions_router
from sentinel_orbit_downloader.api.routes_search import router as search_router
from sentinel_orbit_downloader.api.routes_settings import router as settings_router
from sentinel_orbit_downloader.core.config import (
    configured_api_host,
    configured_api_port,
    configured_ui_shutdown_token,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sentinel Orbit Downloader API",
        version="0.1.0",
        description="Local API for Sentinel-1 search, orbit matching, and task management.",
    )
    app.state.shutdown_token = configured_ui_shutdown_token()

    web_root = Path(__file__).resolve().parents[1] / "web"
    app.mount("/static", StaticFiles(directory=web_root), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(web_root / "index.html")

    @app.get("/app", include_in_schema=False)
    def app_index() -> FileResponse:
        return FileResponse(web_root / "index.html")

    app.include_router(health_router, prefix="/api")
    app.include_router(regions_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(downloads_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    return app


app = create_app()


def main() -> None:
    uvicorn.run(
        "sentinel_orbit_downloader.api.app:app",
        host=configured_api_host(),
        port=configured_api_port(),
        reload=False,
    )
