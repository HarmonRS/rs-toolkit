from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence


def bbox_to_wkt(value: str) -> str:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must be min_lon,min_lat,max_lon,max_lat")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("--bbox values must be numbers") from exc
    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError("--bbox min values must be smaller than max values")
    return (
        f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},"
        f"{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}))"
    )


def aoi_file_to_wkt(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"AOI file is empty: {path}")
    if text[0] != "{":
        return text

    data = json.loads(text)
    geometry = geojson_geometry(data)
    return geometry_to_wkt(geometry)


def geojson_geometry(data: dict[str, Any]) -> dict[str, Any]:
    kind = data.get("type")
    if kind == "FeatureCollection":
        features = data.get("features") or []
        if not features:
            raise ValueError("GeoJSON FeatureCollection has no features")
        return geojson_geometry(features[0])
    if kind == "Feature":
        geometry = data.get("geometry")
        if not geometry:
            raise ValueError("GeoJSON Feature has no geometry")
        return geometry
    if kind in {"Polygon", "MultiPolygon", "Point", "MultiPoint", "LineString"}:
        return data
    raise ValueError(f"unsupported GeoJSON type: {kind}")


def geometry_to_wkt(geometry: dict[str, Any]) -> str:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Point":
        lon, lat = coordinates
        return f"POINT({lon} {lat})"
    if kind == "MultiPoint":
        return "MULTIPOINT(" + ",".join(f"({lon} {lat})" for lon, lat in coordinates) + ")"
    if kind == "LineString":
        return "LINESTRING(" + coords_to_text(coordinates) + ")"
    if kind == "Polygon":
        return "POLYGON(" + ",".join(f"({coords_to_text(ring)})" for ring in coordinates) + ")"
    if kind == "MultiPolygon":
        polygons = []
        for polygon in coordinates:
            rings = ",".join(f"({coords_to_text(ring)})" for ring in polygon)
            polygons.append(f"({rings})")
        return "MULTIPOLYGON(" + ",".join(polygons) + ")"
    raise ValueError(f"unsupported GeoJSON geometry type: {kind}")


def coords_to_text(coords: Iterable[Sequence[float]]) -> str:
    return ",".join(f"{lon} {lat}" for lon, lat, *_ in coords)
