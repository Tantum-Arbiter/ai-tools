@echo off
REM ============================================================
REM Grow with Freya - Windows PC Setup Script
REM Run this ONCE on your RTX 3080 Windows machine
REM ============================================================

echo.
echo === Grow with Freya Content Pipeline Setup ===
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from python.org
    pause
    exit /b 1
)

REM Create virtual environment
echo [1/6] Creating Python virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

REM Install dependencies
echo [2/6] Installing Python dependencies...
pip install --upgrade pip
pip install -r requirements.txt

REM Install Kokoro TTS (local, free, high quality)
echo [3/6] Installing Kokoro TTS (local voiceover)...
pip install kokoro soundfile
REM Download the voice model on first use (automatic)

REM Check FFmpeg
echo [4/6] Checking FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo WARNING: FFmpeg not found in PATH.
    echo Download from: https://www.gyan.dev/ffmpeg/builds/ (ffmpeg-release-full.7z)
    echo Extract and add to Windows PATH, then re-run this script.
    echo.
    echo Alternatively, use winget:
    echo   winget install Gyan.FFmpeg
    echo.
) else (
    echo FFmpeg found OK.
)

REM Create directories
echo [5/6] Creating data directories...
mkdir data\content\raw 2>nul
mkdir data\content\videos 2>nul
mkdir data\content\images 2>nul
mkdir logs 2>nul
mkdir reports 2>nul

REM Copy env template
echo [6/6] Setting up configuration...
if not exist .env (
    copy .env.example .env
    echo.
    echo IMPORTANT: Edit .env with your API keys before running!
    echo   notepad .env
) else (
    echo .env already exists - skipping copy.
)

echo.
echo === Setup Complete! ===
echo.
echo Next steps:
echo   1. Edit .env with your API keys
echo   2. Install and start ComfyUI: https://github.com/comfyanonymous/ComfyUI
echo   3. Run YouTube auth once:  python scripts/auth/youtube_auth.py
echo   4. Test the pipeline:      python scripts/orchestrator.py
echo   5. Schedule via Task Scheduler (see docs/windows_scheduler.md)
echo.
pause
