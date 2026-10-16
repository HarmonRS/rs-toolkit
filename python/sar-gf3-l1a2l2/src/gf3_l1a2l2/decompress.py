from __future__ import annotations

import logging
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover - only used when tqdm is unavailable
    def tqdm(iterable: Iterable, **_: object) -> Iterable:
        return iterable

from gf3_l1a2l2.errors import ProcessingError


@dataclass(frozen=True)
class ExtractionResult:
    archive: Path
    output_dir: Path
    status: str
    message: str = ""


def extract_compressed_files(
    folder_path: Path | str,
    *,
    overwrite: bool = False,
    logger: Optional[logging.Logger] = None,
) -> list[ExtractionResult]:
    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        raise ProcessingError(f"Input folder does not exist: {folder}")

    archives = sorted(
        path
        for path in folder.iterdir()
        if path.is_file()
        and (path.name.lower().endswith(".tar.gz") or path.suffix.lower() == ".zip")
    )

    results: list[ExtractionResult] = []
    if not archives:
        if logger:
            logger.info("No .tar.gz or .zip archives found in %s", folder)
        return results

    for archive in tqdm(archives, desc="Extract archives", unit="file"):
        output_dir = _archive_output_dir(archive)
        try:
            if output_dir.exists():
                if not overwrite:
                    results.append(ExtractionResult(archive, output_dir, "skipped", "output exists"))
                    if logger:
                        logger.info("Skip existing extraction: %s", output_dir)
                    continue
                shutil.rmtree(output_dir)

            output_dir.mkdir(parents=True, exist_ok=True)
            if archive.name.lower().endswith(".tar.gz"):
                _extract_tar_gz(archive, output_dir)
            elif archive.suffix.lower() == ".zip":
                _extract_zip(archive, output_dir)
            else:
                continue

            results.append(ExtractionResult(archive, output_dir, "done"))
            if logger:
                logger.info("Extracted %s -> %s", archive, output_dir)
        except Exception as exc:
            results.append(ExtractionResult(archive, output_dir, "failed", str(exc)))
            if logger:
                logger.exception("Failed to extract %s", archive)

    return results


def _archive_output_dir(archive: Path) -> Path:
    if archive.name.lower().endswith(".tar.gz"):
        return archive.with_name(archive.name[:-7])
    return archive.with_suffix("")


def _extract_tar_gz(archive: Path, output_dir: Path) -> None:
    base = output_dir.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in tqdm(members, desc=f"Extract {archive.name}", leave=False, unit="file"):
            if member.issym() or member.islnk():
                raise ProcessingError(f"Refusing to extract link from archive: {member.name}")
            _ensure_safe_target(base, member.name)
            tar.extract(member, path=base)


def _extract_zip(archive: Path, output_dir: Path) -> None:
    base = output_dir.resolve()
    with zipfile.ZipFile(archive, "r") as zip_ref:
        names = zip_ref.namelist()
        for name in tqdm(names, desc=f"Extract {archive.name}", leave=False, unit="file"):
            _ensure_safe_target(base, name)
            zip_ref.extract(name, base)


def _ensure_safe_target(base: Path, member_name: str) -> None:
    target = (base / member_name).resolve()
    if target == base:
        return
    if base not in target.parents:
        raise ProcessingError(f"Unsafe archive path: {member_name}")
