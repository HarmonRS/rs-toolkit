from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from gf3_l1a2l2.errors import ProcessingError
from gf3_l1a2l2.paths import output_name
from gf3_l1a2l2.rpc import read_rpc_metadata


def geometric_correction(
    l1b_path: Path | str,
    rpc_path: Path | str,
    output_dir: Path | str,
    *,
    dem_path: Optional[Path],
    x_res: float,
    y_res: float,
    dst_srs: str,
    overwrite: bool = False,
    logger: Optional[logging.Logger] = None,
) -> Path:
    source = Path(l1b_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    l2_path = out_dir / output_name(source, "L1B", "L2")

    if l2_path.exists() and not overwrite:
        if logger:
            logger.info("Skip existing L2: %s", l2_path)
        return l2_path

    if dem_path and not Path(dem_path).is_file():
        raise ProcessingError(f"DEM file does not exist: {dem_path}")

    rpc_metadata = read_rpc_metadata(rpc_path)

    try:
        from osgeo import gdal
    except Exception as exc:
        raise ProcessingError("Cannot import osgeo.gdal. Install GDAL Python bindings.") from exc

    if logger:
        logger.info("Geocorrecting %s -> %s", source, l2_path)

    dataset = gdal.Open(str(source), gdal.GA_Update)
    if dataset is None:
        raise ProcessingError(f"GDAL cannot open L1B image: {source}")

    try:
        dataset.SetMetadata(rpc_metadata, "RPC")
        transformer_options = []
        if dem_path:
            transformer_options.append(f"RPC_DEM={Path(dem_path)}")

        warp_options = gdal.WarpOptions(
            dstSRS=dst_srs,
            xRes=x_res,
            yRes=y_res,
            rpc=True,
            multithread=True,
            transformerOptions=transformer_options,
            creationOptions=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=YES"],
        )
        result = gdal.Warp(str(l2_path), dataset, options=warp_options)
        if result is None:
            raise ProcessingError(f"GDAL Warp failed for {source}")
        result.FlushCache()
        result = None
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError(f"Failed to geocorrect {source}") from exc
    finally:
        dataset = None

    return l2_path
