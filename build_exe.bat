@echo off
title Build Lumina Brightness Standalone Executable
cd /d "%~dp0"

echo ========================================================
echo   Building Lumina Display Brightness Standalone (.exe)
echo ========================================================
echo.

where pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo PyInstaller is not installed. Installing pyinstaller...
    python -m pip install pyinstaller
)

echo Packaging app with PyInstaller...
pyinstaller --noconsole --onefile ^
    --name "LuminaBrightness" ^
    --icon "assets\icon.ico" ^
    --add-data "assets;assets" ^
    --collect-all customtkinter ^
    --collect-all pystray ^
    app.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo   BUILD SUCCESSFUL!
    echo   Standalone executable created at:
    echo   %~dp0dist\LuminaBrightness.exe
    echo ========================================================
) else (
    echo.
    echo Build failed. Please inspect the error output above.
)

pause
