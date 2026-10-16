# GF3 L1A to L2 Pipeline

This repository contains two GF-3 L1A to L2 processing paths:

- **SARscape Go wrapper**: Windows-oriented production wrapper around ENVI/IDL Runtime and SARscape. This is the recommended path when SARscape is available.
- **Python pipeline**: GDAL/Rasterio/NumPy implementation kept as a pure Python package and CLI.

The SARscape wrapper currently has the more complete operational workflow for GF-3 scene import, multilook/filter/geocode processing, batch directory discovery, saved defaults, and progress reporting.

## Repository Layout

```text
dist/windows/                         Prebuilt Windows executable
docs/                                 Operational documentation
src/gf3_l1a2l2/                       Python package
tests/                                Python unit tests and small fixtures
tools/gf3_sarscape_wrapper/           Go wrapper source and embedded SAV asset
tools/gf3_sarscape_wrapper/idl/       IDL/SARscape source scripts
```

Large GF-3 archives, extracted scenes, SARscape outputs, and local runtime files are intentionally not tracked in Git.

## Recommended: SARscape Go Wrapper

Use the prebuilt executable:

```powershell
.\dist\windows\gf3wrapper.exe `
  -input "D:\GF3\L1A_BATCH" `
  -output "E:\GF3\L2_SARscape" `
  -dem "D:\DEM\COPDEM_GLO30_China_4326_DEM" `
  -pol "HH,HV"
```

Supported input forms:

- A single `*.tar.gz` GF-3 L1A package.
- A single `*.meta.xml` scene metadata file.
- A directory containing multiple `*.tar.gz` or `*.meta.xml` scenes.

The wrapper writes one output subdirectory per scene. On successful runs it saves defaults next to the executable in `gf3wrapper.json`, so double-click interactive mode can reuse the previous input/output/DEM/polarization settings.

Batch directory runs continue after per-scene failures. If one archive is truncated, invalid, missing metadata, or fails during SARscape processing, the wrapper prints the failed scene and reason, skips that scene, and continues with the remaining scenes. At the end it prints a batch summary and returns a non-zero exit code when any scene failed.

Before processing each scene, the wrapper checks the scene output directory for completed geocoded products for the requested polarizations. Already completed scenes are skipped, so rerunning the same input/output pair only processes missing or incomplete scenes.

More details: [docs/sarscape_go_wrapper.md](docs/sarscape_go_wrapper.md)

## Python Pipeline

Use an environment that already has working GDAL/OSGeo Python bindings. On Windows, Conda/Miniforge is usually the least fragile route.

```powershell
conda env create -f environment.yml
conda activate gf3-l1a2l2
pip install -e . --no-deps
```

Run:

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

Legacy wrappers remain available:

```powershell
python gf3_L1A_To_L2.py run --input D:\GF3\L1A_BATCH --output E:\GF3\L2_Image --dem .\GMTED2010.jp2
python Decompression.py D:\GF3\L1A_BATCH
```

## Development Checks

Python:

```powershell
python -m pytest
```

Go wrapper:

```powershell
cd .\tools\gf3_sarscape_wrapper
$env:GOTELEMETRY = "off"
go build -o ..\..\dist\windows\gf3wrapper.exe .
```

## Data Policy

Do not commit production GF-3 archives or generated products. Keep large data on NAS/storage and document the path in run notes. Only small sanitized fixtures should be added under `tests/fixtures`.
