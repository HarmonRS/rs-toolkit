from __future__ import annotations

import concurrent.futures
import logging
from pathlib import Path
from typing import Iterable

from gf3_l1a2l2.calibration import radiometric_calibrate_l1a_to_l1b
from gf3_l1a2l2.config import PipelineConfig
from gf3_l1a2l2.constants import POLARIZATIONS
from gf3_l1a2l2.decompress import extract_compressed_files
from gf3_l1a2l2.discovery import discover_scenes
from gf3_l1a2l2.errors import GF3PipelineError
from gf3_l1a2l2.geocorrection import geometric_correction
from gf3_l1a2l2.log import configure_logging
from gf3_l1a2l2.metadata import read_calibration_metadata
from gf3_l1a2l2.models import PipelineSummary, SceneFiles, TaskResult
from gf3_l1a2l2.paths import scene_output_dir


def run_pipeline(config: PipelineConfig) -> PipelineSummary:
    config = config.resolved()
    logger = configure_logging(config.output_dir, config.log_level)
    _validate_config(config)

    logger.info("Input: %s", config.input_dir)
    logger.info("Output: %s", config.output_dir)
    if config.dem_path:
        logger.info("DEM: %s", config.dem_path)

    if not config.skip_decompress:
        extract_compressed_files(config.input_dir, overwrite=config.overwrite, logger=logger)

    scenes = discover_scenes(config.input_dir, logger=logger)
    if not scenes:
        logger.warning("No GF3 scenes found under %s", config.input_dir)
        return PipelineSummary()

    summary = PipelineSummary()
    for results in _process_scenes(scenes, config, logger):
        summary.results.extend(results)

    logger.info(
        "Pipeline finished: total=%s done=%s skipped=%s failed=%s",
        summary.total,
        summary.succeeded,
        summary.skipped,
        summary.failed,
    )
    return summary


def _validate_config(config: PipelineConfig) -> None:
    if not config.input_dir.is_dir():
        raise GF3PipelineError(f"Input directory does not exist: {config.input_dir}")
    if config.dem_path and not config.dem_path.is_file():
        raise GF3PipelineError(f"DEM file does not exist: {config.dem_path}")
    if config.x_res <= 0 or config.y_res <= 0:
        raise GF3PipelineError("x_res and y_res must be positive")


def _process_scenes(
    scenes: list[SceneFiles],
    config: PipelineConfig,
    logger: logging.Logger,
) -> Iterable[list[TaskResult]]:
    if config.workers == 1:
        for scene in scenes:
            yield _process_scene(scene, config, logger)
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=config.workers) as executor:
        future_map = {
            executor.submit(_process_scene, scene, config, logger): scene
            for scene in scenes
        }
        for future in concurrent.futures.as_completed(future_map):
            scene = future_map[future]
            try:
                yield future.result()
            except Exception as exc:
                logger.exception("Scene failed: %s", scene.root)
                if config.fail_fast:
                    raise
                yield [
                    TaskResult(
                        scene=scene.name,
                        polarization=polarization,
                        status="failed",
                        message=str(exc),
                    )
                    for polarization in scene.available_polarizations
                ]


def _process_scene(
    scene: SceneFiles,
    config: PipelineConfig,
    logger: logging.Logger,
) -> list[TaskResult]:
    logger.info("Processing scene: %s", scene.root)
    out_dir = scene_output_dir(config.input_dir, config.output_dir, scene.root, config.flat_output)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        metadata = read_calibration_metadata(scene.metadata_xml)
    except Exception as exc:
        logger.exception("Failed to parse metadata for %s", scene.root)
        if config.fail_fast:
            raise
        return [
            TaskResult(scene=scene.name, polarization=pol, status="failed", message=str(exc))
            for pol in scene.available_polarizations
        ]

    results: list[TaskResult] = []
    for polarization in POLARIZATIONS:
        image_path = scene.images.get(polarization)
        if not image_path:
            continue

        rpc_path = scene.rpcs.get(polarization)
        if not rpc_path:
            message = f"Missing RPC/RPB file for {polarization}"
            logger.error("%s in %s", message, scene.root)
            results.append(TaskResult(scene=scene.name, polarization=polarization, status="failed", message=message))
            if config.fail_fast:
                raise GF3PipelineError(message)
            continue

        if polarization not in metadata.values:
            message = f"Missing calibration metadata for {polarization}"
            logger.error("%s in %s", message, scene.metadata_xml)
            results.append(TaskResult(scene=scene.name, polarization=polarization, status="failed", message=message))
            if config.fail_fast:
                raise GF3PipelineError(message)
            continue

        try:
            calibration = metadata.for_polarization(polarization)
            l1b_path = radiometric_calibrate_l1a_to_l1b(
                image_path,
                out_dir,
                calibration,
                block_size=config.block_size,
                overwrite=config.overwrite,
                logger=logger,
            )
            l2_path = geometric_correction(
                l1b_path,
                rpc_path,
                out_dir,
                dem_path=config.dem_path,
                x_res=config.x_res,
                y_res=config.y_res,
                dst_srs=config.dst_srs,
                overwrite=config.overwrite,
                logger=logger,
            )
            results.append(
                TaskResult(
                    scene=scene.name,
                    polarization=polarization,
                    status="done",
                    l1b_path=l1b_path,
                    l2_path=l2_path,
                )
            )
        except Exception as exc:
            logger.exception("Failed %s %s", scene.name, polarization)
            results.append(
                TaskResult(
                    scene=scene.name,
                    polarization=polarization,
                    status="failed",
                    message=str(exc),
                )
            )
            if config.fail_fast:
                raise

    return results
