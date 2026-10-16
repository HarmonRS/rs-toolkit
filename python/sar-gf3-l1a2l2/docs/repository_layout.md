# Repository Layout

```text
.
|-- dist/
|   `-- windows/
|       `-- gf3wrapper.exe
|-- docs/
|   |-- repository_layout.md
|   `-- sarscape_go_wrapper.md
|-- src/
|   `-- gf3_l1a2l2/
|-- tests/
|   `-- fixtures/
|-- tools/
|   `-- gf3_sarscape_wrapper/
|       |-- assets/
|       |-- idl/
|       |-- go.mod
|       `-- main.go
|-- README.md
|-- environment.yml
`-- pyproject.toml
```

## What Belongs In Git

- Python package source.
- Go wrapper source.
- IDL/SARscape source scripts.
- Small embedded runtime assets needed to build the wrapper.
- Small sanitized tests and fixtures.
- Documentation and reproducible build instructions.
- Small convenience binaries when the team explicitly wants a ready-to-run Windows artifact.

## What Does Not Belong In Git

- Raw GF-3 production archives.
- Extracted scenes.
- SARscape output directories.
- Local wrapper config files such as `gf3wrapper.json`.
- Runtime folders such as `.gf3_extract` and `.gf3_runtime`.
- DEM files and other large environment-specific dependencies.

Use NAS or object storage for production data and record exact paths in run logs or issue notes.
