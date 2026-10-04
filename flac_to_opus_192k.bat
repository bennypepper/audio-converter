@echo off
title FLAC to Opus Converter
setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not found in PATH!
    pause
    exit /b 1
)

python -c "import mutagen" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing required dependency: mutagen...
    python -m pip install mutagen
    if errorlevel 1 (
        echo [ERROR] Failed to install mutagen automatically.
        pause
        exit /b 1
    )
    echo [INFO] Dependency installed successfully!
    echo.
)

REM Drop a FLAC file or folder onto this file for a one-click 192k conversion.
REM Double-click it (no drop) to open the interactive wizard instead.
if not "%~1"=="" (
    python flac_to_opus.py "%~1"
    pause
) else (
    python flac_to_opus.py
    if errorlevel 1 pause
)
