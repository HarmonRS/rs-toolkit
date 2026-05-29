# SARscape Go Wrapper

`gf3wrapper.exe` is a Windows command-line wrapper for the SARscape/IDL GF-3 processing workflow. It embeds `gf3_sarscape_cli.sav`, starts `idlrt.exe`, and passes scene metadata, output directory, DEM, and polarization arguments to SARscape.

This path is intended for operational runs where ENVI/IDL Runtime and SARscape are installed and licensed.

## Requirements

- Windows host.
- ENVI/IDL Runtime, default path:
  `C:\Program Files\Harris\ENVI56\IDL88\bin\bin.x86_64\idlrt.exe`
- SARscape available to the IDL Runtime environment.
- DEM file, for example:
  `D:\DEM\COPDEM_GLO30_China_4326_DEM`
- GF-3 L1A input as `*.tar.gz`, `*.meta.xml`, or a directory containing multiple scenes.

The IDL Runtime path can be overridden with `-idlrt` or the `IDLRT_PATH` environment variable.

## Quick Start

Use the prebuilt executable:

```powershell
.\dist\windows\gf3wrapper.exe `
  -input "D:\GF3\L1A_BATCH" `
  -output "E:\GF3\L2_SARscape" `
  -dem "D:\DEM\COPDEM_GLO30_China_4326_DEM" `
  -pol "HH,HV"
```

Double-click mode is also supported. When launched without arguments, the wrapper prompts for input, output, DEM, polarizations, and IDL Runtime path. Press Enter to reuse saved defaults.

## Inputs

The wrapper supports:

- A single GF-3 archive: `GF3_....tar.gz`
- A single extracted scene metadata file: `GF3_....meta.xml`
- A directory containing many archives and/or extracted scenes

Directory mode recursively scans for `*.tar.gz`, `*.tgz`, and `*.meta.xml`. If both archive and metadata exist for the same scene name, the archive is preferred. Internal `.gf3_extract` folders are skipped.

## Outputs

Each scene is processed into its own output directory:

```text
E:\GF3\L2_SARscape\
  GF3_SCENE_NAME\
    .gf3_extract\          Extracted archive, when input was .tar.gz
    *_slc.sml
    *_ml.sml
    *_filt.sml
    *_geo.sml
```

The embedded SAV is materialized under:

```text
<output>\.gf3_runtime\gf3_sarscape_cli.sav
```

## Saved Defaults

After a successful run, the wrapper writes `gf3wrapper.json` next to the executable:

```json
{
  "idlrt_path": "C:\\Program Files\\Harris\\ENVI56\\IDL88\\bin\\bin.x86_64\\idlrt.exe",
  "dem_file": "D:\\DEM\\COPDEM_GLO30_China_4326_DEM",
  "polarizations": "HH,HV",
  "last_input": "D:\\GF3\\L1A_BATCH",
  "last_output": "E:\\GF3\\L2_SARscape",
  "keep_extracted": true
}
```

Command-line flags override saved defaults. If `-input`, `-output`, `-dem`, or `-pol` are omitted, saved values are reused when available.

## Build

From the repository root:

```powershell
cd .\tools\gf3_sarscape_wrapper
$env:GOTELEMETRY = "off"
go build -o ..\..\dist\windows\gf3wrapper.exe .
```

If Go cannot write to the default user cache directory, set local cache paths:

```powershell
$env:GOCACHE = "C:\Temp\go-build-cache"
$env:APPDATA = "C:\Temp\go-appdata"
```

## Source Files

```text
tools/gf3_sarscape_wrapper/main.go
tools/gf3_sarscape_wrapper/assets/gf3_sarscape_cli.sav
tools/gf3_sarscape_wrapper/idl/gf3_sarscape_cli.pro
tools/gf3_sarscape_wrapper/idl/gf3_sarscape_pipeline.pro
```

`assets/gf3_sarscape_cli.sav` is embedded into the Go executable at build time.

## Notes

- Keep production archives and generated products outside Git.
- Keep only small sanitized fixtures in `tests/fixtures`.
- The prebuilt executable in `dist/windows` is a convenience artifact for Windows users. Rebuild it after changing `main.go` or the embedded `.sav`.
