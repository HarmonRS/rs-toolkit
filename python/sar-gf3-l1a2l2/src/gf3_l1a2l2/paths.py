from __future__ import annotations

from pathlib import Path
from typing import Optional

from gf3_l1a2l2.constants import POLARIZATIONS


def detect_polarization(path_or_name: Path | str) -> Optional[str]:
    name = Path(path_or_name).name.upper()
    for polarization in POLARIZATIONS:
        if polarization in name:
            return polarization
    return None


def output_name(source: Path, source_level: str, target_level: str) -> str:
    name = source.name
    index = name.lower().find(source_level.lower())
    if index >= 0:
        return name[:index] + target_level + name[index + len(source_level) :]

    stem = source.stem
    suffix = "".join(source.suffixes)
    if suffix and stem.endswith(suffix):
        stem = stem[: -len(suffix)]
    return f"{stem}_{target_level}{source.suffix}"


def scene_output_dir(input_dir: Path, output_dir: Path, scene_dir: Path, flat: bool) -> Path:
    if flat:
        return output_dir

    try:
        relative = scene_dir.relative_to(input_dir)
    except ValueError:
        relative = Path(scene_dir.name)

    if str(relative) in ("", "."):
        relative = Path(scene_dir.name)

    safe_name = "_".join(part for part in relative.parts if part not in ("", "."))
    return output_dir / safe_name
