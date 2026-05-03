# GF3 L1A to L2 Pipeline

This repository contains a Python package and CLI for converting GF3 L1A
products to L2 GeoTIFF outputs.

The heavy work is still handled by GDAL, Rasterio, and NumPy. The package adds
pipeline structure around the original script: explicit configuration, safe path
handling, logging, restart-friendly skipping, per-scene error isolation, and
block-based radiometric calibration.

## Install

Use an environment that already has a working GDAL/OSGeo Python binding. On
Windows, Conda/Miniforge is usually the least fragile route.

```powershell
conda env create -f environment.yml
conda activate gf3-l1a2l2
pip install -e . --no-deps
```

## Run

```powershell
gf3-l1a2l2 run --input D:\GF3\L1A_BATCH --output E:\GF3\L2_Image --dem .\GMTED2010.jp2
```

Common options:

```powershell
gf3-l1a2l2 run `
  --input D:\GF3\L1A_BATCH `
  --output E:\GF3\L2_Image `
  --dem .\GMTED2010.jp2 `
  --workers 1 `
  --x-res 0.0002 `
  --y-res 0.0002 `
  --dst-srs EPSG:4326
```

By default, output files are written under one subdirectory per discovered
scene. Use `--flat-output` to write all outputs directly into the output
directory.

The legacy files are now compatibility wrappers:

```powershell
python gf3_L1A_To_L2.py run --input D:\GF3\L1A_BATCH --output E:\GF3\L2_Image --dem .\GMTED2010.jp2
python Decompression.py D:\GF3\L1A_BATCH
```

## Notes

- The CLI extracts `.tar.gz` and `.zip` products before processing unless
  `--skip-decompress` is used.
- Existing L2 outputs are skipped unless `--overwrite` is used.
- Logs are written to `<output>\logs`.
- Without representative GF3 products, verification is limited to parser unit
  tests and Python syntax/import checks.
