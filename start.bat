@echo off
title Submaxxing - TikTok Subtitle Studio
cd /d "%~dp0"

if not exist ".venv" (
    echo [!] Virtual environment not found. Running installer first...
    call install.bat
)

echo ===============================================================================
echo            ⚡ Starting Submaxxing Studio (Local & GPU Powered) ⚡
echo ===============================================================================
echo.
.venv\Scripts\python.exe web_ui.py
pause
