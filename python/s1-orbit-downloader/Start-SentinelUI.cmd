@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-SentinelUI.ps1"
if errorlevel 1 pause
endlocal
