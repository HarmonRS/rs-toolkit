from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

from gf3_l1a2l2.errors import DiscoveryError
from gf3_l1a2l2.models import SceneFiles
from gf3_l1a2l2.paths import detect_polarization

SKIP_DIR_NAMES = {".git", ".venv", ".tmp_tests", "__pycache__", ".pytest_cache", "logs"}


def discover_scenes(input_dir: Path | str, logger: Optional[logging.Logger] = None) -> list[SceneFiles]:
    root_dir = Path(input_dir).resolve()
    if not root_dir.is_dir():
        raise DiscoveryError(f"Input directory does not exist: {root_dir}")

    scenes: list[SceneFiles] = []
    for directory in _walk_directories(root_dir):
        try:
            files = [path for path in directory.iterdir() if path.is_file()]
        except OSError as exc:
            if logger:
                logger.warning("Skipping unreadable directory %s: %s", directory, exc)
            continue

        metadata_files = sorted(path for path in files if path.name.lower().endswith(".meta.xml"))
        image_files = sorted(
            path
            for path in files
            if path.suffix.lower() in (".tif", ".tiff") and detect_polarization(path)
        )

        if not metadata_files or not image_files:
            continue

        metadata_xml = metadata_files[0]
        if len(metadata_files) > 1 and logger:
            logger.warning("Multiple metadata files in %s; using %s", directory, metadata_xml.name)

        images = _collect_by_polarization(image_files, logger)
        rpcs = _collect_by_polarization(
            sorted(path for path in files if path.suffix.lower() in (".rpc", ".rpb")),
            logger,
        )

        scenes.append(SceneFiles(root=directory, metadata_xml=metadata_xml, images=images, rpcs=rpcs))

    scenes.sort(key=lambda scene: str(scene.root).lower())
    if logger:
        logger.info("Discovered %s scene(s) under %s", len(scenes), root_dir)
    return scenes


def _walk_directories(root_dir: Path) -> Iterable[Path]:
    stack = [root_dir]
    while stack:
        directory = stack.pop()
        if directory.name in SKIP_DIR_NAMES:
            continue
        yield directory
        try:
            children = list(directory.iterdir())
        except OSError:
            continue
        stack.extend(path for path in children if path.is_dir() and path.name not in SKIP_DIR_NAMES)


def _collect_by_polarization(
    files: Iterable[Path],
    logger: Optional[logging.Logger] = None,
) -> dict[str, Path]:
    collected: dict[str, Path] = {}
    for path in files:
        polarization = detect_polarization(path)
        if not polarization:
            continue
        if polarization in collected:
            if logger:
                logger.warning(
                    "Duplicate %s file in %s; using %s and ignoring %s",
                    polarization,
                    path.parent,
                    collected[polarization].name,
                    path.name,
                )
            continue
        collected[polarization] = path
    return collected
