from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
from typing import Any, Iterable, Sequence
import zipfile

import shapefile
from pyproj import CRS, Transformer
from shapely import make_valid
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.ops import transform as shapely_transform


GEOJSON_SUFFIXES = {".geojson", ".json"}
TEXT_WKT_SUFFIXES = {".wkt", ".txt"}
SHAPEFILE_PART_SUFFIXES = {".shp", ".shx", ".dbf", ".prj", ".cpg"}


@dataclass(frozen=True)
class ParsedAOI:
    name: str
    wkt: str
    source_format: str
    geometry_type: str
    feature_count: int
    bbox: list[float]


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
    suffix = path.suffix.lower()
    if suffix in GEOJSON_SUFFIXES:
        return parse_geojson_bytes(path.name, path.read_bytes()).wkt
    if suffix == ".zip":
        return parse_zip_bytes(path.name, path.read_bytes()).wkt
    if suffix == ".shp":
        return parse_shapefile_paths(path).wkt

    text = decode_text_bytes(path.read_bytes()).strip()
    if not text:
        raise ValueError(f"AOI file is empty: {path}")
    if suffix in TEXT_WKT_SUFFIXES:
        return text
    if text[0] in "{[":
        return parse_geojson_text(path.name, text).wkt
    return text


def parse_uploaded_aoi(files: Sequence[tuple[str, bytes]]) -> ParsedAOI:
    cleaned = [(Path(name).name or name, content) for name, content in files if content]
    if not cleaned:
        raise ValueError("No AOI files were provided")

    suffixes = {Path(name).suffix.lower() for name, _ in cleaned}
    if len(cleaned) == 1:
        name, content = cleaned[0]
        suffix = Path(name).suffix.lower()
        if suffix in GEOJSON_SUFFIXES:
            return parse_geojson_bytes(name, content)
        if suffix == ".zip":
            return parse_zip_bytes(name, content)
        if suffix == ".shp":
            return parse_shapefile_uploads(cleaned)
        if suffix in TEXT_WKT_SUFFIXES:
            return parse_wkt_text(name, content)

    if suffixes & SHAPEFILE_PART_SUFFIXES:
        return parse_shapefile_uploads(cleaned)

    raise ValueError(
        "Unsupported AOI upload. Use .geojson/.json, .zip shapefile, "
        "or shapefile parts (.shp/.shx/.dbf)."
    )


def parse_wkt_text(name: str, content: bytes) -> ParsedAOI:
    text = decode_text_bytes(content).strip()
    if not text:
        raise ValueError(f"AOI file is empty: {name}")
    return ParsedAOI(
        name=Path(name).stem or name,
        wkt=text,
        source_format="wkt",
        geometry_type="WKT",
        feature_count=1,
        bbox=[],
    )


def parse_geojson_bytes(name: str, content: bytes) -> ParsedAOI:
    text = decode_text_bytes(content)
    return parse_geojson_text(name, text)


def parse_geojson_text(name: str, text: str) -> ParsedAOI:
    stripped = text.strip()
    if not stripped:
        raise ValueError(f"AOI file is empty: {name}")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid GeoJSON: {exc}") from exc
    geometry, feature_count = geojson_to_geometry(data)
    return build_parsed_aoi(
        name=Path(name).stem or name,
        source_format="geojson",
        geometry=geometry,
        feature_count=feature_count,
    )


def parse_zip_bytes(name: str, content: bytes) -> ParsedAOI:
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid zip file: {name}") from exc

    with archive:
        file_names = [member for member in archive.namelist() if not member.endswith("/")]
        geojson_members = [member for member in file_names if Path(member).suffix.lower() in GEOJSON_SUFFIXES]
        if geojson_members:
            member = geojson_members[0]
            parsed = parse_geojson_bytes(Path(member).name, archive.read(member))
            return ParsedAOI(
                name=Path(name).stem or parsed.name,
                wkt=parsed.wkt,
                source_format="geojson-zip",
                geometry_type=parsed.geometry_type,
                feature_count=parsed.feature_count,
                bbox=parsed.bbox,
            )

        shape_members = [
            (Path(member).name, archive.read(member))
            for member in file_names
            if Path(member).suffix.lower() in SHAPEFILE_PART_SUFFIXES
        ]
        if shape_members:
            parsed = parse_shapefile_uploads(shape_members)
            return ParsedAOI(
                name=Path(name).stem or parsed.name,
                wkt=parsed.wkt,
                source_format="shapefile-zip",
                geometry_type=parsed.geometry_type,
                feature_count=parsed.feature_count,
                bbox=parsed.bbox,
            )

    raise ValueError("Zip file does not contain GeoJSON or shapefile content")


def parse_shapefile_paths(shp_path: Path) -> ParsedAOI:
    base = shp_path.with_suffix("")
    uploads: list[tuple[str, bytes]] = [(shp_path.name, shp_path.read_bytes())]
    for suffix in (".shx", ".dbf", ".prj", ".cpg"):
        candidate = Path(f"{base}{suffix}")
        if candidate.exists():
            uploads.append((candidate.name, candidate.read_bytes()))
    return parse_shapefile_uploads(uploads)


def parse_shapefile_uploads(files: Sequence[tuple[str, bytes]]) -> ParsedAOI:
    groups: dict[str, dict[str, bytes]] = {}
    display_names: dict[str, str] = {}
    for name, content in files:
        suffix = Path(name).suffix.lower()
        if suffix not in SHAPEFILE_PART_SUFFIXES:
            continue
        stem = Path(name).stem
        key = stem.lower()
        groups.setdefault(key, {})[suffix] = content
        display_names[key] = stem

    shp_groups = [key for key, parts in groups.items() if ".shp" in parts]
    if not shp_groups:
        raise ValueError("Shapefile upload requires at least a .shp file")
    if len(shp_groups) > 1:
        names = ", ".join(display_names[key] for key in shp_groups)
        raise ValueError(f"Multiple shapefiles were uploaded at once: {names}")

    key = shp_groups[0]
    parts = groups[key]
    reader = shapefile.Reader(
        shp=BytesIO(parts[".shp"]),
        shx=BytesIO(parts[".shx"]) if ".shx" in parts else None,
        dbf=BytesIO(parts[".dbf"]) if ".dbf" in parts else None,
    )
    try:
        geometries = [shapely_shape(shape.__geo_interface__) for shape in reader.shapes()]
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            close()

    if not geometries:
        raise ValueError("Shapefile has no geometry records")
    geometry = combine_geometries(geometries)
    geometry = reproject_shapefile_geometry(geometry, parts.get(".prj"))
    return build_parsed_aoi(
        name=display_names[key],
        source_format="shapefile",
        geometry=geometry,
        feature_count=len(geometries),
    )


def geojson_to_geometry(data: dict[str, Any]) -> tuple[BaseGeometry, int]:
    kind = data.get("type")
    if kind == "FeatureCollection":
        features = data.get("features") or []
        geometries = []
        for feature in features:
            geometry = feature.get("geometry") if isinstance(feature, dict) else None
            if geometry:
                geometries.append(shapely_shape(geometry))
        if not geometries:
            raise ValueError("GeoJSON FeatureCollection has no geometry")
        return combine_geometries(geometries), len(geometries)

    if kind == "Feature":
        geometry = data.get("geometry")
        if not geometry:
            raise ValueError("GeoJSON Feature has no geometry")
        return normalize_geometry(shapely_shape(geometry)), 1

    if kind:
        return normalize_geometry(shapely_shape(data)), 1

    raise ValueError("Invalid GeoJSON: missing type")


def combine_geometries(geometries: Iterable[BaseGeometry]) -> BaseGeometry:
    items = [normalize_geometry(geometry) for geometry in geometries if not geometry.is_empty]
    if not items:
        raise ValueError("AOI has no valid geometry")
    geometry = items[0] if len(items) == 1 else unary_union(items)
    return normalize_geometry(geometry)


def normalize_geometry(geometry: BaseGeometry) -> BaseGeometry:
    if geometry.is_empty:
        raise ValueError("AOI geometry is empty")
    if not geometry.is_valid:
        repaired = make_valid(geometry)
        if not repaired.is_empty:
            geometry = repaired
    if geometry.is_empty:
        raise ValueError("AOI geometry is empty")
    return geometry


def reproject_shapefile_geometry(geometry: BaseGeometry, prj_content: bytes | None) -> BaseGeometry:
    if not prj_content:
        validate_lon_lat_bounds(geometry)
        return geometry

    prj_text = decode_text_bytes(prj_content).strip()
    if not prj_text:
        validate_lon_lat_bounds(geometry)
        return geometry

    try:
        source_crs = CRS.from_wkt(prj_text)
    except Exception as exc:
        raise ValueError(f"Unable to read shapefile .prj CRS: {exc}") from exc

    target_crs = CRS.from_epsg(4326)
    if source_crs.equals(target_crs):
        validate_lon_lat_bounds(geometry)
        return geometry

    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    transformed = shapely_transform(transformer.transform, geometry)
    validate_lon_lat_bounds(transformed)
    return normalize_geometry(transformed)


def validate_lon_lat_bounds(geometry: BaseGeometry) -> None:
    min_x, min_y, max_x, max_y = geometry.bounds
    if min_x < -180 or max_x > 180 or min_y < -90 or max_y > 90:
        raise ValueError(
            "AOI coordinates are outside longitude/latitude bounds. "
            "For shapefiles, include a valid .prj file or convert the data to WGS84/EPSG:4326 first."
        )


def build_parsed_aoi(
    *,
    name: str,
    source_format: str,
    geometry: BaseGeometry,
    feature_count: int,
) -> ParsedAOI:
    geometry = normalize_geometry(geometry)
    bounds = list(geometry.bounds) if geometry.bounds else []
    return ParsedAOI(
        name=name,
        wkt=geometry.wkt,
        source_format=source_format,
        geometry_type=geometry.geom_type,
        feature_count=feature_count,
        bbox=[float(value) for value in bounds],
    )


def decode_text_bytes(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1")
