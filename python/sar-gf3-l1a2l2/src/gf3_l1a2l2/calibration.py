from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
import rasterio
from rasterio.windows import Window

from gf3_l1a2l2.errors import ProcessingError
from gf3_l1a2l2.models import CalibrationValue
from gf3_l1a2l2.paths import output_name


def radiometric_calibrate_l1a_to_l1b(
    image_path: Path | str,
    output_dir: Path | str,
    calibration: CalibrationValue,
    *,
    block_size: int,
    overwrite: bool = False,
    logger: Optional[logging.Logger] = None,
) -> Path:
    source = Path(image_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    l1b_path = out_dir / output_name(source, "L1A", "L1B")

    if l1b_path.exists() and not overwrite:
        if logger:
            logger.info("Skip existing L1B: %s", l1b_path)
        return l1b_path

    if not math.isfinite(calibration.qualify_value):
        raise ProcessingError(f"Invalid QualifyValue for {source.name}: {calibration.qualify_value}")
    if not math.isfinite(calibration.calibration_const):
        raise ProcessingError(
            f"Invalid CalibrationConst for {source.name}: {calibration.calibration_const}"
        )

    if logger:
        logger.info("Calibrating %s -> %s", source, l1b_path)

    try:
        with rasterio.open(source) as src:
            if src.count < 2:
                raise ProcessingError(f"Expected at least 2 bands in L1A image: {source}")

            profile = src.profile.copy()
            profile.update(
                driver="GTiff",
                count=1,
                dtype="float32",
                compress="lzw",
                BIGTIFF="YES",
                tiled=True,
            )

            with rasterio.open(l1b_path, "w", **profile) as dst:
                for window in _iter_windows(src.width, src.height, block_size):
                    real = src.read(1, window=window, out_dtype="float32")
                    imag = src.read(2, window=window, out_dtype="float32")
                    db = _calibrate_window(real, imag, calibration)
                    dst.write(db, 1, window=window)
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError(f"Failed to calibrate {source}") from exc

    return l1b_path


def _calibrate_window(real: np.ndarray, imag: np.ndarray, calibration: CalibrationValue) -> np.ndarray:
    amplitude = np.hypot(real, imag)
    scaled = (amplitude / np.float32(32767.0)) * np.float32(calibration.qualify_value)
    with np.errstate(divide="ignore", invalid="ignore"):
        db = np.float32(20.0) * np.log10(scaled) - np.float32(calibration.calibration_const)
    return db.astype("float32", copy=False)


def _iter_windows(width: int, height: int, block_size: int) -> Iterator[Window]:
    for row_off in range(0, height, block_size):
        window_height = min(block_size, height - row_off)
        for col_off in range(0, width, block_size):
            window_width = min(block_size, width - col_off)
            yield Window(col_off, row_off, window_width, window_height)
