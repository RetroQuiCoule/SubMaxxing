@echo off
title Submaxxing - TikTok Subtitle Studio Pro
cd /d "%~dp0"

if not exist ".venv" (
    echo [!] Virtual environment not found. Running installer first...
    call install.bat
)

echo ===============================================================================
echo            ⚡ Starting Submaxxing Studio Pro (Local & GPU Powered) ⚡
echo ===============================================================================
echo.

:: Automatically kill any lingering python process on port 5055 to prevent socket collision
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :5055') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: Start the Web UI server (web_ui.py will open the browser once)
.venv\Scripts\python.exe web_ui.py
pause
