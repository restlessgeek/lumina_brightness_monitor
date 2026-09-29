@echo off
title Lumina Display Brightness
cd /d "%~dp0"

REM Check if python is available
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python is not found in PATH! Please ensure Python 3.10+ is installed.
    pause
    exit /b 1
)

REM Run the application using pythonw (no terminal console) or python
echo Starting Lumina Display Brightness...
start "" pythonw app.py
if %errorlevel% neq 0 (
    python app.py
)
