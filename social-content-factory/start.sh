#!/usr/bin/env bash
# ── social-content-factory — Universal Start Script ───────────────
# First run: creates venv, installs deps.
# Then: runs the render CLI for the given brand/theme (defaults below).
#
# Usage:
#   ./start.sh                              # personal / weekly-build
#   ./start.sh personal arbiter-voice-shipped
#   ./start.sh personal weekly-build --video --aspect-ratio 9x16
#   FACTORY_BRAND=foo FACTORY_THEME=bar ./start.sh
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

# ── Colours ───────────────────────────────────────────────────────
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
    ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    major="${ver%%.*}"
    minor="${ver##*.}"
    if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
      PYTHON="$cmd"
      break
    fi
  fi
done
[ -n "$PYTHON" ] || die "Python 3.11+ is required but not found. Install from https://python.org"
ok "Python found: $PYTHON ($ver)"

# ── Create virtual environment (first run only) ──────────────────
if [ ! -d "venv" ]; then
  info "Creating virtual environment..."
  "$PYTHON" -m venv venv
  ok "Virtual environment created"
fi

# ── Activate venv ────────────────────────────────────────────────
if [ -f "venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
  # shellcheck disable=SC1091
  source venv/Scripts/activate
else
  die "Cannot find venv activation script. Delete the venv/ folder and re-run."
fi
ok "Virtual environment activated"

# ── Resolve pip command ──────────────────────────────────────────
PIP="pip"
if ! command -v pip >/dev/null 2>&1; then
  PIP="$PYTHON -m pip"
  if ! $PIP --version >/dev/null 2>&1; then
    info "pip not found — bootstrapping..."
    "$PYTHON" -m ensurepip --upgrade 2>/dev/null || die "Cannot find or install pip."
  fi
fi

# ── Install / upgrade dependencies (hash-skipped) ────────────────
MARKER="venv/.deps_installed"
REQS_HASH=""
if command -v md5sum >/dev/null 2>&1; then
  REQS_HASH=$(md5sum requirements.txt | cut -d' ' -f1)
elif command -v md5 >/dev/null 2>&1; then
  REQS_HASH=$(md5 -q requirements.txt)
fi

if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER" 2>/dev/null)" != "$REQS_HASH" ]; then
  info "Installing dependencies (this may take a minute on first run)..."
  $PIP install --upgrade pip --quiet || warn "pip upgrade failed (non-fatal)"
  if $PIP install -r requirements.txt; then
    echo "$REQS_HASH" > "$MARKER"
    ok "Dependencies installed"
  else
    die "Failed to install dependencies. Check the error above."
  fi
else
  ok "Dependencies up to date"
fi

# ── Ensure .env loaded if present (CLI uses python-dotenv) ───────
if [ -f ".env" ]; then
  ok ".env file present"
else
  warn "No .env file — set COMFYUI_BASE_URL and (optionally) OPENROUTER_API_KEY before render"
fi

# ── Resolve brand / theme (positional args win over env vars) ────
BRAND="${1:-${FACTORY_BRAND:-personal}}"
THEME="${2:-${FACTORY_THEME:-weekly-build}}"
# Shift positional args we consumed (if any) so $@ holds extras
if [ $# -ge 2 ]; then shift 2
elif [ $# -ge 1 ]; then shift 1
fi

printf "\n${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}  social-content-factory — render${RESET}\n"
printf "  ${DIM}brand=${BRAND}  theme=${THEME}${RESET}\n"
printf "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

exec "$PYTHON" -m social_content_factory.cli render --brand "$BRAND" --theme "$THEME" "$@"
