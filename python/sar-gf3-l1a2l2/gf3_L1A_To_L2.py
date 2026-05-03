"""Compatibility wrapper for the packaged GF3 L1A to L2 pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from gf3_l1a2l2.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
