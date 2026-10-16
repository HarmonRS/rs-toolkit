from __future__ import annotations

import csv
import getpass
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import asf_search as asf


DEFAULT_FIELDS = (
    "scene",
    "startTime",
    "stopTime",
    "processingLevel",
    "beamModeType",
    "flightDirection",
    "polarization",
    "pathNumber",
    "platform",
    "sizeMB",
)


@dataclass(frozen=True)
class SearchParams:
    aoi_wkt: str
    start: str
    end: str
    processing_level: str = "SLC"
    beam_mode: str | None = "IW"
    flight_direction: str | None = None
    polarization: str | None = None
    relative_orbit: int | None = None
    max_results: int = 50


def query_scenes(params: SearchParams):
    kwargs: dict[str, Any] = {
        "platform": [asf.PLATFORM.SENTINEL1],
        "processingLevel": params.processing_level,
        "intersectsWith": params.aoi_wkt,
        "start": params.start,
        "end": params.end,
        "maxResults": params.max_results,
    }
    if params.beam_mode:
        kwargs["beamMode"] = params.beam_mode
    if params.flight_direction:
        kwargs["flightDirection"] = params.flight_direction.upper()
    if params.polarization:
        kwargs["polarization"] = params.polarization
    if params.relative_orbit:
        kwargs["relativeOrbit"] = params.relative_orbit
    return asf.geo_search(**kwargs)


def resolve_credentials(
    username: str | None = None,
    password: str | None = None,
) -> tuple[str | None, str | None]:
    resolved_username = username or os.getenv("EARTHDATA_USER") or os.getenv("EARTHDATA_USERNAME")
    resolved_password = password or os.getenv("EARTHDATA_PASS") or os.getenv("EARTHDATA_PASSWORD")
    return resolved_username, resolved_password


def credentials_available(
    username: str | None = None,
    password: str | None = None,
) -> bool:
    resolved_username, resolved_password = resolve_credentials(username, password)
    return bool(resolved_username and resolved_password)


def build_session(
    username: str | None = None,
    password: str | None = None,
    ask_password: bool = False,
) -> asf.ASFSession:
    username, password = resolve_credentials(username, password)
    if ask_password:
        password = getpass.getpass("Earthdata password: ")

    if not username or not password:
        raise ValueError(
            "ASF product downloads require NASA Earthdata credentials. "
            "Set EARTHDATA_USER/EARTHDATA_PASS or pass --username/--ask-password."
        )

    return asf.ASFSession().auth_with_creds(username, password)


def product_size_mb(props: dict[str, Any]) -> float | None:
    if props.get("sizeMB") is not None:
        return float(props["sizeMB"])
    if props.get("bytes") is not None:
        return float(props["bytes"]) / (1024 * 1024)
    return None


def scene_name_from_product(product) -> str | None:
    from .orbit_client import normalize_scene_name

    props = getattr(product, "properties", {})
    candidates: Sequence[Any] = (
        props.get("sceneName"),
        props.get("fileID"),
        props.get("fileName"),
        props.get("url"),
    )
    for candidate in candidates:
        if not candidate:
            continue
        scene = normalize_scene_name(str(candidate))
        if scene:
            return scene
    return None


def manifest_row(product) -> dict[str, Any]:
    props = product.properties
    return {
        "scene": scene_name_from_product(product),
        "startTime": props.get("startTime"),
        "stopTime": props.get("stopTime"),
        "processingLevel": props.get("processingLevel"),
        "beamModeType": props.get("beamModeType"),
        "flightDirection": props.get("flightDirection"),
        "polarization": props.get("polarization"),
        "pathNumber": props.get("pathNumber"),
        "platform": props.get("platform"),
        "sizeMB": product_size_mb(props),
    }


def write_manifest(results, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    rows = [manifest_row(product) for product in results]
    if suffix == ".json":
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return
    if suffix not in {"", ".csv"}:
        raise ValueError("manifest path must end with .csv or .json")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEFAULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
