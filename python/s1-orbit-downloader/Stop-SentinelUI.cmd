@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-SentinelUI.ps1"
if errorlevel 1 pause
endlocal
