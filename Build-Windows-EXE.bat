@echo off
title Build DriveScope.exe
cd /d "%~dp0"
echo ============================================================
echo   Building a standalone DriveScope.exe (no Python needed
echo   on the target PC). Run this ONCE on a Windows machine
echo   that has Python installed. Takes a few minutes.
echo ============================================================
where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python not found. Install Python 3.9+ first.
  pause & exit /b 1
)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller DriveScope.spec --noconfirm
echo.
echo ============================================================
echo   Done. Your app is in:  dist\DriveScope\
echo   Double-click  dist\DriveScope\DriveScope.exe  to run it.
echo   You can copy the whole dist\DriveScope folder to any
echo   Windows PC - no Python required there.
echo ============================================================
pause
