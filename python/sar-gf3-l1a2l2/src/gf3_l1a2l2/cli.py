from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gf3_l1a2l2.config import PipelineConfig
from gf3_l1a2l2.decompress import extract_compressed_files
from gf3_l1a2l2.discovery import discover_scenes
from gf3_l1a2l2.errors import GF3PipelineError


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 2

    try:
        return args.handler(args)
    except GF3PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gf3-l1a2l2", description="GF3 L1A to L2 pipeline")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="extract and process GF3 L1A products")
    run_parser.add_argument("--input", required=True, type=Path, help="input folder containing archives or scenes")
    run_parser.add_argument("--output", required=True, type=Path, help="output folder")
    run_parser.add_argument("--dem", type=Path, default=None, help="DEM file for RPC orthorectification")
    run_parser.add_argument("--x-res", type=float, default=0.0002, help="output x resolution")
    run_parser.add_argument("--y-res", type=float, default=0.0002, help="output y resolution")
    run_parser.add_argument("--dst-srs", default="EPSG:4326", help="destination spatial reference")
    run_parser.add_argument("--block-size", type=int, default=2048, help="calibration block size in pixels")
    run_parser.add_argument("--workers", type=int, default=1, help="number of scenes to process concurrently")
    run_parser.add_argument("--skip-decompress", action="store_true", help="do not extract archives before processing")
    run_parser.add_argument("--overwrite", action="store_true", help="overwrite existing extraction and output files")
    run_parser.add_argument("--flat-output", action="store_true", help="write all outputs directly to output folder")
    run_parser.add_argument("--fail-fast", action="store_true", help="stop on the first failed scene or polarization")
    run_parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    run_parser.set_defaults(handler=_run)

    decompress_parser = subparsers.add_parser("decompress", help="extract .tar.gz and .zip archives")
    decompress_parser.add_argument("input", type=Path, help="folder containing archives")
    decompress_parser.add_argument("--overwrite", action="store_true", help="overwrite existing extracted folders")
    decompress_parser.set_defaults(handler=_decompress)

    discover_parser = subparsers.add_parser("discover", help="list discovered GF3 scenes")
    discover_parser.add_argument("input", type=Path, help="input folder")
    discover_parser.set_defaults(handler=_discover)

    return parser


def _run(args: argparse.Namespace) -> int:
    from gf3_l1a2l2.pipeline import run_pipeline

    dem_path = args.dem or _default_dem_path()
    config = PipelineConfig(
        input_dir=args.input,
        output_dir=args.output,
        dem_path=dem_path,
        x_res=args.x_res,
        y_res=args.y_res,
        dst_srs=args.dst_srs,
        block_size=args.block_size,
        workers=args.workers,
        skip_decompress=args.skip_decompress,
        overwrite=args.overwrite,
        flat_output=args.flat_output,
        fail_fast=args.fail_fast,
        log_level=args.log_level,
    )
    summary = run_pipeline(config)
    return 1 if summary.failed else 0


def _decompress(args: argparse.Namespace) -> int:
    results = extract_compressed_files(args.input, overwrite=args.overwrite)
    failed = [item for item in results if item.status == "failed"]
    for item in results:
        print(f"{item.status}\t{item.archive}\t{item.output_dir}\t{item.message}")
    return 1 if failed else 0


def _discover(args: argparse.Namespace) -> int:
    scenes = discover_scenes(args.input)
    for scene in scenes:
        polarizations = ",".join(scene.available_polarizations)
        print(f"{scene.root}\tmetadata={scene.metadata_xml.name}\tpol={polarizations}")
    return 0


def _default_dem_path() -> Path | None:
    candidates = [
        Path.cwd() / "GMTED2010.jp2",
        Path(__file__).resolve().parents[2] / "GMTED2010.jp2",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
