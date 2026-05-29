# GF-3 SARscape Go Wrapper

This wrapper embeds `assets/gf3_sarscape_cli.sav` and calls the local ENVI/IDL Runtime:

```text
idlrt.exe gf3_sarscape_cli.sav -args input_meta_xml out_dir dem_file HH,HV
```

It is the operational Windows path for SARscape-based GF-3 processing.

## Build

From this directory:

```powershell
$env:GOTELEMETRY = "off"
go build -o ..\..\dist\windows\gf3wrapper.exe .
```

## Run

Single archive:

```powershell
..\..\dist\windows\gf3wrapper.exe `
  -input "D:\GF3\GF3_SCENE.tar.gz" `
  -output "E:\GF3\L2_SARscape" `
  -dem "D:\DEM\COPDEM_GLO30_China_4326_DEM" `
  -pol "HH,HV"
```

Batch directory:

```powershell
..\..\dist\windows\gf3wrapper.exe `
  -input "D:\GF3\L1A_BATCH" `
  -output "E:\GF3\L2_SARscape"
```

If `gf3wrapper.json` exists next to the executable, omitted `-input`, `-output`, `-dem`, and `-pol` values are loaded from that file.

In batch directory mode, a failed scene does not stop the whole run. Invalid or truncated archives, missing metadata, and SARscape failures are reported with the scene input path and reason, then the wrapper continues with the next scene. A final summary lists succeeded and failed scenes, and the process exits non-zero when any scene failed.

Reruns with the same output directory skip scenes that already have complete `*_geo.sml` outputs and matching data files for the requested polarizations. This lets a repaired archive be placed back into the original input folder without reprocessing scenes that already finished.

## Notes

- The server still needs ENVI, IDL Runtime, and SARscape installed and licensed.
- `.tar.gz` inputs are extracted under each scene output directory in `.gf3_extract`.
- The embedded SAV is extracted to `<output>\.gf3_runtime\gf3_sarscape_cli.sav`.
- More operational details are in `docs/sarscape_go_wrapper.md`.
