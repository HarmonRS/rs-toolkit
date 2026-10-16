from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional


@dataclass(frozen=True)
class CalibrationValue:
    qualify_value: float
    calibration_const: float


@dataclass(frozen=True)
class CalibrationMetadata:
    values: Mapping[str, CalibrationValue]

    def for_polarization(self, polarization: str) -> CalibrationValue:
        return self.values[polarization]


@dataclass(frozen=True)
class SceneFiles:
    root: Path
    metadata_xml: Path
    images: Mapping[str, Path]
    rpcs: Mapping[str, Path]

    @property
    def name(self) -> str:
        return self.root.name

    @property
    def available_polarizations(self) -> tuple[str, ...]:
        return tuple(sorted(self.images))


@dataclass(frozen=True)
class TaskResult:
    scene: str
    polarization: str
    status: str
    l1b_path: Optional[Path] = None
    l2_path: Optional[Path] = None
    message: str = ""


@dataclass
class PipelineSummary:
    results: list[TaskResult] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(1 for item in self.results if item.status == "done")

    @property
    def skipped(self) -> int:
        return sum(1 for item in self.results if item.status == "skipped")

    @property
    def failed(self) -> int:
        return sum(1 for item in self.results if item.status == "failed")

    @property
    def total(self) -> int:
        return len(self.results)
