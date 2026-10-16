@echo off
set IDLRT=C:\Program Files\Harris\ENVI56\IDL88\bin\bin.x86_64\idlrt.exe
set SAV=C:\Users\Administrator\Desktop\GF3_Test\GF3_ENVI_IDL\gf3_sarscape_cli.sav
set META=C:\Users\Administrator\Desktop\GF3_Test\GF3_scene_20260513\GF3_SYC_FSI_051370_E124.6_N51.7_20260513_L1A_HHHV_L10007355955.meta.xml
set OUT=C:\Users\Administrator\Desktop\GF3_Test\GF3_cli_test_out_20260513
set DEM=D:\DEM\COPDEM_GLO30_China_4326_DEM

"%IDLRT%" "%SAV%" -args "%META%" "%OUT%" "%DEM%" "HH,HV"
