@echo off
rem ============================================================
rem  Reachy Mini DIY - Exhibition startup (one click)
rem  Runs the voice assistant with auto-restart watchdog.
rem  Double-click this file, or run it from PowerShell.
rem ============================================================

cd /d "%~dp0.."

echo.
echo  [start] Reachy Mini voice assistant (hardware + watchdog)
echo  ---------------------------------------------------------
.venv\Scripts\python.exe -X utf8 scripts\watchdog.py --hardware

echo.
echo  [done] Program stopped.
pause
