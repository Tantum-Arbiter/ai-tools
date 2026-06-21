@echo off
REM ── ARBITER Mission Control — Windows Start Script ──────────────
REM First run: creates venv, installs deps, copies .env template.
REM Subsequent runs: activates venv and launches the server.
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo   ===================================================
echo     ARBITER Mission Control — Setup ^& Launch
echo   ===================================================
echo.

REM ── Detect Python ───────────────────────────────────────────────
set "PYTHON="
for %%P in (python3 python) do (
    if not defined PYTHON (
        where %%P >nul 2>&1
        if !errorlevel! equ 0 (
            for /f "tokens=*" %%V in ('%%P -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2^>nul') do (
                for /f "tokens=1,2 delims=." %%A in ("%%V") do (
                    if %%A geq 3 if %%B geq 10 (
                        set "PYTHON=%%P"
                        set "PYVER=%%V"
                    )
                )
            )
        )
    )
)
if not defined PYTHON (
    echo [ERROR] Python 3.10+ is required but not found.
    echo         Download from https://python.org
    echo         Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
echo [OK] Python found: %PYTHON% (%PYVER%)

REM ── Create virtual environment (first run only) ────────────────
if not exist "venv\Scripts\activate.bat" (
    echo [..] Creating virtual environment...
    %PYTHON% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

REM ── Activate venv ──────────────────────────────────────────────
call venv\Scripts\activate.bat
echo [OK] Virtual environment activated

REM ── Install / upgrade dependencies ─────────────────────────────
if not exist "venv\.deps_installed" (
    echo [..] Installing dependencies...
    pip install --upgrade pip -q 2>nul
    pip install -r requirements.txt -q
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo installed > "venv\.deps_installed"
    echo [OK] Dependencies installed
) else (
    REM Re-install if requirements.txt is newer than marker
    for %%R in (requirements.txt) do for %%M in (venv\.deps_installed) do (
        if "%%~tR" gtr "%%~tM" (
            echo [..] requirements.txt changed — updating dependencies...
            pip install -r requirements.txt -q
            echo installed > "venv\.deps_installed"
            echo [OK] Dependencies updated
        ) else (
            echo [OK] Dependencies up to date
        )
    )
)

REM ── Ensure .env exists ─────────────────────────────────────────
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [!!] .env created from .env.example
        echo      Edit it with your API keys before first use.
        echo      Open: %cd%\.env
    ) else (
        echo [!!] No .env file found. Some features may not work.
    )
) else (
    echo [OK] .env file present
)

REM ── Ensure required directories exist ──────────────────────────
if not exist "reports" mkdir reports
if not exist "static\comfyui_output" mkdir "static\comfyui_output"

REM ── Pre-flight checks ─────────────────────────────────────────
echo.
echo -- Pre-flight --
findstr /b "ANTHROPIC_API_KEY=sk-ant-your-key-here" .env >nul 2>&1
if not errorlevel 1 (
    echo [!!] ANTHROPIC_API_KEY not configured — Claude will fall back to Ollama
)
where ollama >nul 2>&1
if not errorlevel 1 (
    echo [OK] Ollama available (local LLM fallback)
) else (
    echo [..] Ollama not installed — get it from https://ollama.com
)

REM ── Launch server ──────────────────────────────────────────────
set "HOST=%ARBITER_HOST%"
set "PORT=%ARBITER_PORT%"
if not defined HOST set "HOST=127.0.0.1"
if not defined PORT set "PORT=8888"

echo.
echo   ===================================================
echo     ARBITER Mission Control
echo     http://%HOST%:%PORT%
echo   ===================================================
echo.

uvicorn server:app --reload --host %HOST% --port %PORT%
pause
