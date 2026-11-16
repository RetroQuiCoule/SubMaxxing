@echo off
setlocal enabledelayedexpansion
title Submaxxing - Automated Installer

echo ===============================================================================
echo                ⚡ SUBMAXXING STUDIO - 1-CLICK INSTALLER ⚡
echo       Automated TikTok / Shorts Subtitles Generator (Local & GPU Powered)
echo ===============================================================================
echo.

cd /d "%~dp0"

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Python is not installed or not in PATH!
    echo     Please download and install Python 3.10 - 3.12 from:
    echo     https://www.python.org/downloads/
    echo     (Make sure to check "Add Python to PATH" during installation)
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [*] Detected Python %PY_VER%

:: 2. Create Virtual Environment
if not exist ".venv" (
    echo [*] Creating virtual environment (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [X] Failed to create virtual environment!
        pause
        exit /b 1
    )
    echo [+] Virtual environment created successfully.
) else (
    echo [*] Existing .venv found.
)

:: 3. Upgrade pip & Install requirements
echo [*] Installing dependencies from requirements.txt...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip.exe install -r requirements.txt
if %errorlevel% neq 0 (
    echo [X] Error installing python dependencies!
    pause
    exit /b 1
)
echo [+] Python dependencies installed successfully.

:: 4. Check FFmpeg
echo [*] Checking for FFmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] FFmpeg is not found in system PATH.
    echo [*] Attempting to install FFmpeg via winget...
    winget install --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    if %errorlevel% equ 0 (
        echo [+] FFmpeg installed successfully via winget!
    ) else (
        echo [!] Could not auto-install FFmpeg.
        echo     Please install FFmpeg manually or add it to PATH.
    )
) else (
    echo [+] FFmpeg is already installed and available in PATH.
)

echo.
echo ===============================================================================
echo  🎉 INSTALLATION COMPLETE!
echo  Double-click "start.bat" or run "python web_ui.py" to launch Submaxxing Studio!
echo ===============================================================================
echo.
pause
