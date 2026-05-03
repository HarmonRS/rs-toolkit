"""Compatibility wrapper for archive extraction."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from gf3_l1a2l2.decompress import extract_compressed_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract GF3 archives")
    parser.add_argument("input", type=Path, help="folder containing .tar.gz or .zip archives")
    parser.add_argument("--overwrite", action="store_true", help="overwrite existing extracted folders")
    args = parser.parse_args()

    results = extract_compressed_files(args.input, overwrite=args.overwrite)
    failed = [item for item in results if item.status == "failed"]
    for item in results:
        print(f"{item.status}\t{item.archive}\t{item.output_dir}\t{item.message}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
