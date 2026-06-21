#!/usr/bin/env bash
# ── ARBITER Mission Control — Universal Start Script ──────────────
# Works on macOS, Linux, and Windows (Git Bash / WSL / MSYS2).
# First run: creates venv, installs deps, copies .env template.
# Subsequent runs: activates venv and launches the server.
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

# ── Colours (safe for dumb terminals) ─────────────────────────────
if [ -t 1 ]; then
  BOLD="\033[1m" DIM="\033[2m" CYAN="\033[36m" GREEN="\033[32m"
  YELLOW="\033[33m" RED="\033[31m" RESET="\033[0m"
else
  BOLD="" DIM="" CYAN="" GREEN="" YELLOW="" RED="" RESET=""
fi
info()  { printf "${CYAN}▸${RESET} %s\n" "$*"; }
ok()    { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
die()   { printf "${RED}✗${RESET} %s\n" "$*" >&2; exit 1; }

# ── Detect Python ─────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" >/dev/null 2>&1; then
    # Verify it's Python 3.10+
    ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    major="${ver%%.*}"
    minor="${ver##*.}"
    if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
      PYTHON="$cmd"
      break
    fi
  fi
done
[ -n "$PYTHON" ] || die "Python 3.10+ is required but not found. Install from https://python.org"
ok "Python found: $PYTHON ($ver)"

# ── Create virtual environment (first run only) ──────────────────
if [ ! -d "venv" ]; then
  info "Creating virtual environment..."
  "$PYTHON" -m venv venv
  ok "Virtual environment created"
fi

# ── Activate venv (cross-platform) ───────────────────────────────
if [ -f "venv/bin/activate" ]; then
  # macOS / Linux / WSL
  # shellcheck disable=SC1091
  source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
  # Windows Git Bash / MSYS2
  # shellcheck disable=SC1091
  source venv/Scripts/activate
else
  die "Cannot find venv activation script. Delete the venv/ folder and re-run."
fi
ok "Virtual environment activated"

# ── Install / upgrade dependencies ───────────────────────────────
MARKER="venv/.deps_installed"
REQS_HASH=""
if command -v md5sum >/dev/null 2>&1; then
  REQS_HASH=$(md5sum requirements.txt | cut -d' ' -f1)
elif command -v md5 >/dev/null 2>&1; then
  REQS_HASH=$(md5 -q requirements.txt)
fi

if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER" 2>/dev/null)" != "$REQS_HASH" ]; then
  info "Installing dependencies..."
  pip install --upgrade pip -q 2>/dev/null
  pip install -r requirements.txt -q
  echo "$REQS_HASH" > "$MARKER"
  ok "Dependencies installed"
else
  ok "Dependencies up to date"
fi

# ── Ensure .env exists ───────────────────────────────────────────
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    warn ".env created from .env.example — edit it with your API keys before first use"
    warn "  → Open: ${ROOT}/.env"
  else
    warn "No .env file found. The server will start but some features may not work."
  fi
else
  ok ".env file present"
fi

# ── Ensure required directories exist ────────────────────────────
mkdir -p reports static/comfyui_output

# ── Pre-flight checks ────────────────────────────────────────────
printf "\n${BOLD}── Pre-flight ──${RESET}\n"

# Check for Anthropic key (primary LLM)
if grep -q "^ANTHROPIC_API_KEY=sk-ant-your-key-here" .env 2>/dev/null || \
   grep -q "^ANTHROPIC_API_KEY=$" .env 2>/dev/null; then
  warn "ANTHROPIC_API_KEY is not configured — Claude chat will fall back to Ollama"
fi

# Check for Ollama (local fallback)
if command -v ollama >/dev/null 2>&1; then
  ok "Ollama available (local LLM fallback)"
else
  info "Ollama not installed — install from https://ollama.com for free local LLM"
fi

# ── Launch server ─────────────────────────────────────────────────
HOST="${ARBITER_HOST:-127.0.0.1}"
PORT="${ARBITER_PORT:-8888}"

printf "\n${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}  ARBITER Mission Control${RESET}\n"
printf "  ${DIM}http://${HOST}:${PORT}${RESET}\n"
printf "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

exec uvicorn server:app --reload --host "$HOST" --port "$PORT"
