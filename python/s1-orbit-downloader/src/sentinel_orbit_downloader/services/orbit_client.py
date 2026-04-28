from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import s1_orbits
from s1_orbits.exceptions import InvalidSceneError, OrbitNotFoundError

SCENE_RE = re.compile(r"^(S1[A-D]_.+?)(?:\.SAFE|\.zip)?$", re.IGNORECASE)


@dataclass(frozen=True)
class OrbitResult:
    scene: str
    path: Path | None
    error: str | None = None


def normalize_scene_name(value: str) -> str | None:
    name = Path(value).name.strip()
    for suffix in (".SAFE", ".safe", ".ZIP", ".zip"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    match = SCENE_RE.match(name)
    if not match:
        return None
    return match.group(1)


def unique(values: Iterable[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def collect_orbit_scenes(
    scenes: Sequence[str] | None = None,
    scene_file: Path | None = None,
    data_dir: Path | None = None,
) -> list[str]:
    if scenes:
        return unique(filter(None, (normalize_scene_name(scene) for scene in scenes)))

    if scene_file:
        scene_names = []
        for line in scene_file.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            scene_names.append(normalize_scene_name(clean))
        return unique(filter(None, scene_names))

    if not data_dir:
        return []

    found = []
    for path in data_dir.iterdir():
        if not path.name.upper().startswith(("S1A_", "S1B_", "S1C_", "S1D_")):
            continue
        scene = normalize_scene_name(path.name)
        if scene:
            found.append(scene)
    return unique(found)


def scene_names_from_results(results) -> list[str]:
    from .asf_client import scene_name_from_product

    scenes = [scene_name_from_product(product) for product in results]
    return unique(scene for scene in scenes if scene)


def download_orbits(scenes: Sequence[str], orbit_dir: Path) -> list[OrbitResult]:
    orbit_dir.mkdir(parents=True, exist_ok=True)
    results: list[OrbitResult] = []
    for scene in scenes:
        try:
            path = s1_orbits.fetch_for_scene(scene, dir=orbit_dir)
            results.append(OrbitResult(scene=scene, path=path))
        except (InvalidSceneError, OrbitNotFoundError) as exc:
            message = str(exc) or exc.__class__.__name__
            results.append(OrbitResult(scene=scene, path=None, error=message))
    return results
