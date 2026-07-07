@echo off
title DriveScope
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo ============================================================
  echo   First-time setup - installing DriveScope ^(one time only^)
  echo   Please WAIT until it finishes and your browser opens.
  echo   Do not refresh the browser until you see "DriveScope is
  echo   running" in this window.
  echo ============================================================
  where python >nul 2>nul
  if errorlevel 1 (
    echo.
    echo  ERROR: Python was not found on this PC.
    echo  Install Python 3.9+ from https://www.python.org/downloads/
    echo  IMPORTANT: tick "Add Python to PATH", then run this again.
    echo.
    pause
    exit /b 1
  )
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo  ERROR: dependency install failed. Check internet/proxy and re-run.
    echo.
    pause
    exit /b 1
  )
)

echo Starting DriveScope... (first start can take ~10 seconds)
".venv\Scripts\python.exe" launch.py
echo.
echo DriveScope has stopped.
pause
