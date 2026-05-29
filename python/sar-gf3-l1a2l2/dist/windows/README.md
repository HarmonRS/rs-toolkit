# Windows Distribution

`gf3wrapper.exe` is the prebuilt SARscape Go wrapper.

Run from the repository root:

```powershell
.\dist\windows\gf3wrapper.exe `
  -input "D:\GF3\L1A_BATCH" `
  -output "E:\GF3\L2_SARscape" `
  -dem "D:\DEM\COPDEM_GLO30_China_4326_DEM" `
  -pol "HH,HV"
```

The executable requires ENVI/IDL Runtime and SARscape on the target machine.

After successful runs, `gf3wrapper.json` is created in this directory to store defaults. That file is local runtime state and is ignored by Git.
