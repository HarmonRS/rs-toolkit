from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Optional

from gf3_l1a2l2.constants import POLARIZATIONS
from gf3_l1a2l2.errors import MetadataError
from gf3_l1a2l2.models import CalibrationMetadata, CalibrationValue
from gf3_l1a2l2.paths import detect_polarization


QUALIFY_KEYWORDS = ("qualifyvalue", "qualityvalue")
CALIBRATION_KEYWORDS = ("calibrationconst", "calibrationconstant")


def read_calibration_metadata(xml_path: Path | str) -> CalibrationMetadata:
    path = Path(xml_path)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise MetadataError(f"Invalid metadata XML: {path}") from exc
    except OSError as exc:
        raise MetadataError(f"Cannot read metadata XML: {path}") from exc

    qualify_values = _find_values(root, QUALIFY_KEYWORDS) or _legacy_values(root, (17, 13))
    calibration_values = _find_values(root, CALIBRATION_KEYWORDS) or _legacy_values(root, (18, 3))

    if not qualify_values:
        raise MetadataError(f"Cannot find QualifyValue values in {path}")
    if not calibration_values:
        raise MetadataError(f"Cannot find CalibrationConst values in {path}")

    values: dict[str, CalibrationValue] = {}
    for polarization in POLARIZATIONS:
        if polarization not in qualify_values or polarization not in calibration_values:
            continue
        values[polarization] = CalibrationValue(
            qualify_value=qualify_values[polarization],
            calibration_const=calibration_values[polarization],
        )

    if not values:
        raise MetadataError(f"No usable calibration values found in {path}")

    return CalibrationMetadata(values=values)


def _find_values(root: ET.Element, keywords: Iterable[str]) -> Optional[dict[str, float]]:
    lowered = tuple(keyword.lower() for keyword in keywords)
    for element in root.iter():
        name = _local_name(element.tag).lower()
        if not any(keyword in name for keyword in lowered):
            continue

        values = _values_by_child_polarization(element)
        if values:
            return values

        values = _values_by_child_order(element)
        if values:
            return values

        values = _values_from_text(element.text)
        if values:
            return values

    return None


def _legacy_values(root: ET.Element, indexes: tuple[int, int]) -> Optional[dict[str, float]]:
    try:
        node = root
        for index in indexes:
            node = list(node)[index]
        values = [_parse_float(child.text) for child in list(node)[:4]]
    except (IndexError, TypeError, ValueError):
        return None

    if len(values) < 4:
        return None
    return dict(zip(POLARIZATIONS, values))


def _values_by_child_polarization(element: ET.Element) -> Optional[dict[str, float]]:
    values: dict[str, float] = {}
    for child in list(element):
        polarization = _element_polarization(child)
        if not polarization:
            continue
        try:
            values[polarization] = _parse_float(child.text)
        except ValueError:
            continue
    return values if values else None


def _values_by_child_order(element: ET.Element) -> Optional[dict[str, float]]:
    numeric_values: list[float] = []
    for child in list(element):
        try:
            numeric_values.append(_parse_float(child.text))
        except ValueError:
            continue
    if len(numeric_values) < 4:
        return None
    return dict(zip(POLARIZATIONS, numeric_values[:4]))


def _values_from_text(text: Optional[str]) -> Optional[dict[str, float]]:
    if not text:
        return None
    normalized = text.replace(",", " ").replace(";", " ")
    parts = [part for part in normalized.split() if part]
    if len(parts) < 4:
        return None
    try:
        values = [_parse_float(part) for part in parts[:4]]
    except ValueError:
        return None
    return dict(zip(POLARIZATIONS, values))


def _element_polarization(element: ET.Element) -> Optional[str]:
    for value in element.attrib.values():
        polarization = detect_polarization(value)
        if polarization:
            return polarization
    return detect_polarization(_local_name(element.tag))


def _parse_float(text: Optional[str]) -> float:
    if text is None:
        raise ValueError("missing value")
    value = text.strip().strip("=")
    if not value or value.upper() == "NULL":
        return math.nan
    return float(value)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag
