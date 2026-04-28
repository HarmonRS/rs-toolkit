from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from sentinel_orbit_downloader.core.provinces import PROVINCES
from sentinel_orbit_downloader.storage.db import connect, set_setting


@dataclass(frozen=True)
class RegionImportStats:
    source_path: Path
    simplify_tolerance: float
    total_features: int
    imported: int


@dataclass(frozen=True)
class RegionRecord:
    adcode: str
    name: str
    level: str
    parent_adcode: str | None
    parent_name: str | None
    province_adcode: str | None
    province_name: str | None
    center_lon: float | None
    center_lat: float | None
    centroid_lon: float | None
    centroid_lat: float | None
    min_lon: float | None
    min_lat: float | None
    max_lon: float | None
    max_lat: float | None
    children_num: int | None
    tree_id: str | None
    source_path: str | None
    geometry_json: str
    wkt: str
    simplified_wkt: str
    simplify_tolerance: float
    geometry_hash: str

    @property
    def bbox(self) -> tuple[float, float, float, float] | None:
        values = (self.min_lon, self.min_lat, self.max_lon, self.max_lat)
        if any(value is None for value in values):
            return None
        return values  # type: ignore[return-value]

    @property
    def label(self) -> str:
        parts = []
        if self.province_name and self.province_name != self.name:
            parts.append(self.province_name)
        if self.parent_name and self.parent_name not in parts and self.parent_name != self.name:
            parts.append(self.parent_name)
        parts.append(self.name)
        return " / ".join(parts)


def import_regions(
    db_path: Path,
    source_path: Path,
    simplify_tolerance: float = 0.01,
) -> RegionImportStats:
    data = json.loads(source_path.read_text(encoding="utf-8"))
    features = data.get("features") or []
    rows = [feature_to_row(feature, source_path, simplify_tolerance) for feature in features]

    with connect(db_path) as connection:
        connection.execute("DELETE FROM regions")
        connection.executemany(
            """
            INSERT INTO regions (
                adcode, name, level, parent_adcode, province_adcode, province_name,
                center_lon, center_lat, centroid_lon, centroid_lat,
                min_lon, min_lat, max_lon, max_lat, children_num, tree_id,
                source_path, geometry_json, wkt, simplified_wkt, simplify_tolerance, geometry_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        set_setting(connection, "regions.source_path", str(source_path.resolve()))
        set_setting(connection, "regions.simplify_tolerance", str(simplify_tolerance))
        set_setting(connection, "regions.feature_count", str(len(features)))

    return RegionImportStats(
        source_path=source_path,
        simplify_tolerance=simplify_tolerance,
        total_features=len(features),
        imported=len(rows),
    )


def search_regions(
    db_path: Path,
    query: str,
    limit: int = 20,
    level: str | None = None,
) -> list[RegionRecord]:
    sql = """
    SELECT
        r.*,
        parent.name AS parent_name
    FROM regions AS r
    LEFT JOIN regions AS parent ON parent.adcode = r.parent_adcode
    WHERE (
        r.name LIKE :like_query
        OR r.adcode LIKE :like_query
        OR IFNULL(r.province_name, '') LIKE :like_query
    )
    """
    params: dict[str, Any] = {
        "like_query": f"%{query}%",
        "exact_query": query,
        "prefix_query": f"{query}%",
        "limit": limit,
    }
    if level:
        sql += " AND r.level = :level"
        params["level"] = level

    sql += """
    ORDER BY
        CASE
            WHEN r.name = :exact_query THEN 0
            WHEN r.name LIKE :prefix_query THEN 1
            ELSE 2
        END,
        LENGTH(r.name),
        r.level,
        r.adcode
    LIMIT :limit
    """

    with connect(db_path) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [row_to_region(row) for row in rows]


def get_region(db_path: Path, adcode: str) -> RegionRecord | None:
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                r.*,
                parent.name AS parent_name
            FROM regions AS r
            LEFT JOIN regions AS parent ON parent.adcode = r.parent_adcode
            WHERE r.adcode = ?
            """,
            (str(adcode),),
        ).fetchone()
    if row is None:
        return None
    return row_to_region(row)


def region_wkt(db_path: Path, adcode: str, simplified: bool = True) -> str:
    region = get_region(db_path, adcode)
    if region is None:
        raise ValueError(f"region not found: {adcode}")
    return region.simplified_wkt if simplified else region.wkt


def feature_to_row(feature: dict[str, Any], source_path: Path, simplify_tolerance: float) -> tuple[Any, ...]:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry")
    if geometry is None:
        raise ValueError("feature geometry is missing")

    geometry_text = json.dumps(geometry, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    geometry_hash = hashlib.sha256(geometry_text.encode("utf-8")).hexdigest()
    geom = shape(geometry)
    simplified = geom.simplify(simplify_tolerance, preserve_topology=True)
    if simplified.is_empty:
        simplified = geom

    adcode = str(properties.get("adcode"))
    name = str(properties.get("name"))
    level = str(properties.get("level") or "unknown")
    parent_adcode = normalize_adcode((properties.get("parent") or {}).get("adcode"))
    province_adcode = derive_province_adcode(adcode, level, parent_adcode, properties.get("acroutes"))
    province_name = PROVINCES.get(province_adcode) if province_adcode else None

    center = normalize_point(properties.get("center"))
    centroid = normalize_point(properties.get("centroid"))
    min_lon, min_lat, max_lon, max_lat = geom.bounds

    return (
        adcode,
        name,
        level,
        parent_adcode,
        province_adcode,
        province_name,
        center[0] if center else None,
        center[1] if center else None,
        centroid[0] if centroid else None,
        centroid[1] if centroid else None,
        min_lon,
        min_lat,
        max_lon,
        max_lat,
        int(properties["childrenNum"]) if properties.get("childrenNum") is not None else None,
        properties.get("treeID"),
        str(source_path),
        geometry_text,
        geom.wkt,
        simplified.wkt,
        simplify_tolerance,
        geometry_hash,
    )


def derive_province_adcode(
    adcode: str,
    level: str,
    parent_adcode: str | None,
    acroutes: Any,
) -> str | None:
    if level == "province" and adcode in PROVINCES:
        return adcode

    routes = [normalize_adcode(value) for value in acroutes or []]
    for route in routes:
        if route in PROVINCES:
            return route

    if parent_adcode in PROVINCES:
        return parent_adcode

    if adcode.isdigit() and len(adcode) == 6:
        candidate = f"{adcode[:2]}0000"
        if candidate in PROVINCES:
            return candidate
    return None


def normalize_adcode(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def normalize_point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) < 2:
        return None
    return (float(value[0]), float(value[1]))


def row_to_region(row) -> RegionRecord:
    return RegionRecord(
        adcode=str(row["adcode"]),
        name=str(row["name"]),
        level=str(row["level"]),
        parent_adcode=row["parent_adcode"],
        parent_name=row["parent_name"],
        province_adcode=row["province_adcode"],
        province_name=row["province_name"],
        center_lon=row["center_lon"],
        center_lat=row["center_lat"],
        centroid_lon=row["centroid_lon"],
        centroid_lat=row["centroid_lat"],
        min_lon=row["min_lon"],
        min_lat=row["min_lat"],
        max_lon=row["max_lon"],
        max_lat=row["max_lat"],
        children_num=row["children_num"],
        tree_id=row["tree_id"],
        source_path=row["source_path"],
        geometry_json=row["geometry_json"],
        wkt=row["wkt"],
        simplified_wkt=row["simplified_wkt"],
        simplify_tolerance=float(row["simplify_tolerance"]),
        geometry_hash=str(row["geometry_hash"]),
    )
