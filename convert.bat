@echo off
title Universal Audio Converter
setlocal
cd /d "%~dp0"

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not found in PATH!
    echo Please install Python 3 and ensure "Add python.exe to PATH" is checked.
    pause
    exit /b 1
)

REM Ensure mutagen is installed in the active Python environment
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

REM A file or folder dropped onto this batch file pre-fills the interactive wizard.
REM Any extra command-line flags are passed straight through (e.g. convert.bat -i "C:\Music" -f flac).
set "FIRST=%~1"
if "%FIRST%"=="" (
    python audio_converter.py
) else if "%FIRST:~0,1%"=="-" (
    python audio_converter.py %*
) else (
    python audio_converter.py "%~1"
)

if errorlevel 1 (
    pause
)
