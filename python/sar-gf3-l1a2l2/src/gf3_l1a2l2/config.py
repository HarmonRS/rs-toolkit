from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from gf3_l1a2l2.constants import (
    DEFAULT_BLOCK_SIZE,
    DEFAULT_DST_SRS,
    DEFAULT_X_RES,
    DEFAULT_Y_RES,
)


@dataclass(frozen=True)
class PipelineConfig:
    input_dir: Path
    output_dir: Path
    dem_path: Optional[Path] = None
    x_res: float = DEFAULT_X_RES
    y_res: float = DEFAULT_Y_RES
    dst_srs: str = DEFAULT_DST_SRS
    block_size: int = DEFAULT_BLOCK_SIZE
    workers: int = 1
    skip_decompress: bool = False
    overwrite: bool = False
    flat_output: bool = False
    keep_l1b: bool = True
    fail_fast: bool = False
    log_level: str = "INFO"

    def resolved(self) -> "PipelineConfig":
        dem_path = self.dem_path.resolve() if self.dem_path else None
        return replace(
            self,
            input_dir=self.input_dir.resolve(),
            output_dir=self.output_dir.resolve(),
            dem_path=dem_path,
            workers=max(1, int(self.workers)),
            block_size=max(128, int(self.block_size)),
        )
