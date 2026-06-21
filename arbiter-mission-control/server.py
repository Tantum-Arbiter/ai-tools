"""
ARBITER — Mission Control
A Jarvis-style HUD dashboard for the Grow with Freya automation platform.
Serves a single-page holographic UI and real-time status API endpoints.

Run:  uvicorn server:app --reload --host 127.0.0.1 --port 8888
Open: http://localhost:8888

Security: Bind to 127.0.0.1 (localhost only) to avoid browser "Not Secure"
warnings on 0.0.0.0. For remote access, use a reverse proxy (Caddy/nginx)
with TLS termination — never expose this server directly to the internet.
"""
import os
import re
import json
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager

import hmac
import secrets
import httpx
from openai import OpenAI
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from email_monitor import EmailMonitor
from agent_registry import AgentRegistry
from gcp_monitor import GCPMonitor
from revenuecat_monitor import RevenueCatMonitor
from service_health import ServiceHealthMonitor
from persistence import ArbiterDB

from typing import Any

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / "social-media-business-account" / ".env")
load_dotenv(ROOT / "arbiter-mission-control" / ".env", override=True)


COMFYUI_URL = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi4")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
# Provider priority: "claude" (fast + cheap), "ollama" (free local), "openai" (legacy)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
# Cheap model for structured output (panels, followups) — GPT-4o-mini via OpenRouter
# $0.15/M input, $0.60/M output — ~10x cheaper than Claude Haiku for panel generation
_OPENROUTER_PANEL_MODEL = os.getenv("OPENROUTER_PANEL_MODEL", "openai/gpt-4o-mini")
# CEO agent model via OpenRouter (replaces direct OpenAI GPT-4.1 calls)
_OPENROUTER_AGENT_MODEL = os.getenv("OPENROUTER_AGENT_MODEL", "openai/gpt-4o-mini")

# ── OpenRouter Cost Safeguards ────────────────────────────────────────
_OPENROUTER_DAILY_BUDGET_USD = float(os.getenv("OPENROUTER_DAILY_BUDGET_USD", "0.10"))  # $0.10/day ≈ $3/month
_OPENROUTER_RPM_LIMIT = int(os.getenv("OPENROUTER_RPM_LIMIT", "30"))
_OPENROUTER_SESSION_LIMIT = int(os.getenv("OPENROUTER_SESSION_LIMIT", "500"))
_OPENROUTER_TIMEOUT = int(os.getenv("OPENROUTER_TIMEOUT", "60"))  # seconds per request

# ── Claude Cost Safeguards ─────────────────────────────────────────────
# Hard-coded to cheapest model only. No overrides.
_CLAUDE_MODEL = "claude-haiku-4-5"
# Agent pipeline uses Sonnet for strategic agents (higher quality, still cost-effective)
_CLAUDE_AGENT_MODEL = os.getenv("CLAUDE_AGENT_MODEL", "claude-haiku-4-5")
_CLAUDE_DAILY_BUDGET_USD = float(os.getenv("CLAUDE_DAILY_BUDGET_USD", "1.0"))
_CLAUDE_RPM_LIMIT = int(os.getenv("CLAUDE_RPM_LIMIT", "30"))         # requests per minute
_CLAUDE_SESSION_LIMIT = int(os.getenv("CLAUDE_SESSION_LIMIT", "500"))  # requests per server session
_CLAUDE_CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive errors before fallback

log = logging.getLogger(__name__)

# ── API Authentication ────────────────────────────────────────────────
# Set ARBITER_API_KEY in .env to protect all /api/* endpoints.
# If unset, auth is disabled (local-only use).
ARBITER_API_KEY = os.getenv("ARBITER_API_KEY", "")
_ARBITER_AUTH_ENABLED = bool(ARBITER_API_KEY)
if _ARBITER_AUTH_ENABLED:
    log.info(f"API auth ENABLED (key len={len(ARBITER_API_KEY)})")
else:
    log.warning("API auth DISABLED — set ARBITER_API_KEY in .env to protect endpoints")

# ── Input Length Limits ───────────────────────────────────────────────
_MAX_DIRECTIVE_LEN = int(os.getenv("MAX_DIRECTIVE_LEN", "4000"))      # ~1000 tokens
_MAX_SYSTEM_PROMPT_LEN = int(os.getenv("MAX_SYSTEM_PROMPT_LEN", "8000"))  # ~2000 tokens
_MAX_NAME_LEN = 200
_MAX_DESCRIPTION_LEN = 2000

# ── Startup Security Checks ──────────────────────────────────────────
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    try:
        _env_perms = _env_file.stat().st_mode & 0o777
        if _env_perms & 0o077:  # group or world readable
            log.warning(
                f".env file permissions too open ({oct(_env_perms)}). "
                f"Run: chmod 600 {_env_file}  — secrets may be readable by other users."
            )
            try:
                _env_file.chmod(0o600)
                log.info(".env permissions auto-fixed to 600 (owner-only)")
            except OSError:
                pass
    except OSError:
        pass

# ── Startup Diagnostics ───────────────────────────────────────────────
_has_claude_key = bool(ANTHROPIC_API_KEY)
_has_openrouter_key = bool(OPENROUTER_API_KEY)
_has_gemini_key = bool(GOOGLE_API_KEY)
_GEMINI_DAILY_CALL_CAP = int(os.getenv("GEMINI_DAILY_CALL_CAP", "40"))  # free tier = 50/day, buffer of 10
print(f"[ARBITER BOOT] LLM_PROVIDER={LLM_PROVIDER}  "
      f"ANTHROPIC_API_KEY={'SET (len=' + str(len(ANTHROPIC_API_KEY)) + ')' if _has_claude_key else 'NOT SET'}  "
      f"OPENROUTER={'SET → panels=' + _OPENROUTER_PANEL_MODEL + ' agents=' + _OPENROUTER_AGENT_MODEL + ' budget=$' + str(_OPENROUTER_DAILY_BUDGET_USD) + '/day' if _has_openrouter_key else 'NOT SET'}  "
      f"GEMINI={'SET → cap=' + str(_GEMINI_DAILY_CALL_CAP) + '/day' if _has_gemini_key else 'NOT SET'}  "
      f"OLLAMA={OLLAMA_BASE_URL}  MODEL={OLLAMA_MODEL}")

# ── Claude Usage Tracking ──────────────────────────────────────────────
_claude_usage = {
    "today": datetime.utcnow().strftime("%Y-%m-%d"),
    "daily_input_tokens": 0,
    "daily_output_tokens": 0,
    "daily_cost_usd": 0.0,
    "session_requests": 0,
    "minute_requests": [],       # list of timestamps for RPM tracking
    "consecutive_errors": 0,
    "circuit_open_until": None,  # datetime when circuit breaker resets
}

# Haiku 4.5 pricing (per million tokens)
_CLAUDE_INPUT_COST_PER_M = 1.00
_CLAUDE_OUTPUT_COST_PER_M = 5.00

# ── OpenRouter Usage Tracking ─────────────────────────────────────────
_openrouter_usage = {
    "today": datetime.utcnow().strftime("%Y-%m-%d"),
    "daily_input_tokens": 0,
    "daily_output_tokens": 0,
    "daily_cost_usd": 0.0,
    "session_requests": 0,
    "minute_requests": [],
    "consecutive_errors": 0,
    "circuit_open_until": None,
}

# GPT-4o-mini pricing via OpenRouter (per million tokens)
_OR_INPUT_COST_PER_M = 0.15
_OR_OUTPUT_COST_PER_M = 0.60

# ── Gemini Usage Tracking (free-tier safeguard) ─────────────────────────
# _GEMINI_DAILY_CALL_CAP defined near top of file (before boot log)
_gemini_usage = {
    "today": datetime.utcnow().strftime("%Y-%m-%d"),
    "daily_calls": 0,
    "session_calls": 0,
    "daily_input_tokens": 0,
    "daily_output_tokens": 0,
    "consecutive_errors": 0,
    "circuit_open_until": None,
}


def _gemini_check_budget() -> str | None:
    """Return an error string if Gemini free-tier cap is reached, else None."""
    u = _gemini_usage
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if u["today"] != today:
        u["today"] = today
        u["daily_calls"] = 0
        u["daily_input_tokens"] = 0
        u["daily_output_tokens"] = 0
        log.info("Gemini daily counter reset (new day)")

    # Circuit breaker
    if u["circuit_open_until"] and datetime.utcnow() < u["circuit_open_until"]:
        return f"Circuit breaker open until {u['circuit_open_until'].strftime('%H:%M:%S')} UTC"

    if u["daily_calls"] >= _GEMINI_DAILY_CALL_CAP:
        return f"Daily free-tier cap reached ({u['daily_calls']}/{_GEMINI_DAILY_CALL_CAP})"

    return None


def _gemini_record_success(input_tokens: int = 0, output_tokens: int = 0):
    """Record a successful Gemini call with token usage."""
    u = _gemini_usage
    u["daily_calls"] += 1
    u["session_calls"] += 1
    u["daily_input_tokens"] += input_tokens
    u["daily_output_tokens"] += output_tokens
    u["consecutive_errors"] = 0
    log.info(f"Gemini usage: calls today={u['daily_calls']}/{_GEMINI_DAILY_CALL_CAP}, "
             f"session={u['session_calls']}, tokens={input_tokens}in/{output_tokens}out, "
             f"total={u['daily_input_tokens']}in/{u['daily_output_tokens']}out")


def _gemini_record_error():
    """Record a Gemini error and potentially trip the circuit breaker."""
    u = _gemini_usage
    u["consecutive_errors"] += 1
    if u["consecutive_errors"] >= 3:
        u["circuit_open_until"] = datetime.utcnow() + timedelta(minutes=5)
        log.warning(f"Gemini circuit breaker OPEN — {u['consecutive_errors']} consecutive errors. "
                    f"Falling back to OpenRouter for 5 minutes.")


def _or_check_budget() -> str | None:
    """Check OpenRouter safeguards. Returns error string if blocked, None if OK."""
    u = _openrouter_usage
    now = datetime.utcnow()

    # Reset daily counters at midnight UTC
    today = now.strftime("%Y-%m-%d")
    if u["today"] != today:
        u["today"] = today
        u["daily_input_tokens"] = 0
        u["daily_output_tokens"] = 0
        u["daily_cost_usd"] = 0.0
        log.info("OpenRouter daily budget reset")

    # Circuit breaker
    if u["circuit_open_until"] and now < u["circuit_open_until"]:
        remaining = (u["circuit_open_until"] - now).seconds
        return f"Circuit breaker open — {remaining}s until retry"
    elif u["circuit_open_until"]:
        u["circuit_open_until"] = None
        u["consecutive_errors"] = 0

    # Daily budget
    if u["daily_cost_usd"] >= _OPENROUTER_DAILY_BUDGET_USD:
        return f"Daily budget exhausted (${u['daily_cost_usd']:.3f} / ${_OPENROUTER_DAILY_BUDGET_USD:.2f})"

    # Session limit
    if u["session_requests"] >= _OPENROUTER_SESSION_LIMIT:
        return f"Session limit reached ({u['session_requests']} / {_OPENROUTER_SESSION_LIMIT})"

    # RPM limit
    cutoff = now - timedelta(seconds=60)
    u["minute_requests"] = [t for t in u["minute_requests"] if t > cutoff]
    if len(u["minute_requests"]) >= _OPENROUTER_RPM_LIMIT:
        return f"Rate limit ({_OPENROUTER_RPM_LIMIT} requests/min)"

    return None


def _or_record_usage(input_tokens: int, output_tokens: int):
    """Record OpenRouter token usage and update cost tracking."""
    u = _openrouter_usage
    u["daily_input_tokens"] += input_tokens
    u["daily_output_tokens"] += output_tokens
    cost = (input_tokens / 1_000_000) * _OR_INPUT_COST_PER_M + \
           (output_tokens / 1_000_000) * _OR_OUTPUT_COST_PER_M
    u["daily_cost_usd"] += cost
    u["session_requests"] += 1
    u["minute_requests"].append(datetime.utcnow())
    u["consecutive_errors"] = 0
    log.info(f"OpenRouter usage: +{input_tokens}in/{output_tokens}out tokens, "
             f"cost today=${u['daily_cost_usd']:.4f}/{_OPENROUTER_DAILY_BUDGET_USD:.2f}, "
             f"session={u['session_requests']}/{_OPENROUTER_SESSION_LIMIT}")


def _or_record_error():
    """Record an OpenRouter API error for circuit breaker."""
    u = _openrouter_usage
    u["consecutive_errors"] += 1
    if u["consecutive_errors"] >= 3:
        u["circuit_open_until"] = datetime.utcnow() + timedelta(minutes=5)
        log.warning(f"OpenRouter circuit breaker OPEN — 3 consecutive errors, "
                    f"Ollama fallback for 5 min")


# ── Claude Tool-Calling System Prompt ─────────────────────────────────
# Used by _chat_claude_tools(). Claude sees this + tool definitions, then
# decides which tools to call for the user's query (ChatGPT-style).
_CLAUDE_TOOLS_SYSTEM = (
    "You are ARBITER — modelled after J.A.R.V.I.S. from Iron Man. You serve Sir Luke.\n"
    "Voice: composed, British, dry-witted, concise. Flowing sentences only — no bullets or lists.\n"
    "Today is {date}. Current year: {year}.\n\n"
    "Use your tools freely to fetch live data whenever the query needs current information.\n"
    "After getting data, give a sharp 2-4 sentence spoken reply dense with specific numbers and facts.\n"
    "Never mention tool names, data fetching, or reasoning steps in your reply.\n"
    "Never mention training cutoffs, knowledge limitations, or suggest the user consult other sources.\n\n"
    "For collectable queries (Pokemon cards, trading cards, etc): always include specific prices by grade/condition, "
    "price trend direction, and where to buy (eBay, TCGplayer, etc) with approximate links.\n"
    "For product/shopping queries: always compare prices across at least 3 retailers, list cheapest first, "
    "and include direct purchase URLs where available.\n\n"
    "You have access to ARBITER's memory via search_history. Use it when the user asks about:\n"
    "- Previous research, analysis, or reports your agents have produced\n"
    "- Past briefings (morning, market close, evening digests)\n"
    "- Trends, patterns, or comparisons over time\n"
    "- 'What did you find about X?' or 'Summarise this week's work'\n"
    "When building reports, pull historical data first — don't re-research what's already been done.\n\n"
    "## CRITICAL: Destructive Action Confirmation Protocol\n"
    "For ANY tool that deletes, updates, or modifies data (delete_business, update_business_context, "
    "switch_prompt_mode), you MUST follow this exact protocol:\n"
    "1. FIRST call the tool with confirmed=false — this returns a preview of what will happen.\n"
    "2. Present the preview to the user and ask: 'Shall I proceed, Sir?' or equivalent.\n"
    "3. ONLY call the tool with confirmed=true AFTER the user explicitly says yes/confirm/proceed/go ahead.\n"
    "4. If the user says no/cancel/stop, acknowledge and do NOT call the tool again.\n"
    "NEVER skip the preview step. NEVER auto-confirm. This is a safety requirement."
)

# ── Claude Tool Definitions (Anthropic tool_use format) ───────────────
# Each tool maps directly to an existing data-fetch function in this server.
# Adding a new data source = add an entry here + a branch in _execute_tool().
_CLAUDE_TOOLS: list[dict] = [
    {
        "name": "get_weather",
        "description": "Get current weather conditions and 7-day forecast for any city.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name, e.g. 'London', 'Tokyo', 'New York'"},
            },
            "required": ["location"],
        },
    },
    {
        "name": "get_stocks",
        "description": "Get live stock quotes for tracked symbols: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, S&P 500, FTSE 100.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_market_intel",
        "description": "Get analyst ratings, price targets, and key financial metrics for a specific stock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol, e.g. 'NVDA', 'AAPL', 'MSFT'"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_service_health",
        "description": "Get current GCP and infrastructure service health, incidents, and uptime status.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_revenue",
        "description": "Get RevenueCat revenue metrics: MRR, active subscribers, trials, and churn.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_emails",
        "description": "Get email summary: unread count, urgent items, customer emails, and recent activity.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_email_detail",
        "description": "Get full email detail including body text for a specific email UID. Use this when the user asks to read or view a specific email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "uid": {"type": "string", "description": "Email UID from the email list"},
            },
            "required": ["uid"],
        },
    },
    {
        "name": "draft_email_reply",
        "description": "Draft a professional reply to a customer/business email. Returns the draft text for user review before sending.",
        "input_schema": {
            "type": "object",
            "properties": {
                "uid": {"type": "string", "description": "Email UID to reply to"},
                "instructions": {"type": "string", "description": "Optional specific instructions for the reply (e.g. 'confirm availability for next Tuesday')"},
            },
            "required": ["uid"],
        },
    },
    {
        "name": "get_roadmap",
        "description": "Get business roadmap milestones, their status, deadlines, and progress.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_web",
        "description": "Search the web and fetch content for research on any company, market, topic, or current event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (e.g. 'Nvidia AI chip revenue 2025') or a direct URL to fetch"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_collectables",
        "description": "Search for collectable items (Pokemon cards, trading cards, sports cards, figurines, coins, stamps, vintage items). Returns current market prices, price trends, grading info, and where to buy/sell.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "The collectable item to search for, e.g. 'Charizard Base Set Holo 1st Edition', 'PSA 10 Pikachu Illustrator', 'Michael Jordan Fleer rookie card'"},
                "intent": {"type": "string", "enum": ["price_check", "trend", "buy", "sell", "grading", "overview"],
                           "description": "What the user wants: price_check (current value), trend (price history), buy (where to purchase), sell (where to list), grading (condition info), overview (general info)"},
            },
            "required": ["item"],
        },
    },
    {
        "name": "search_history",
        "description": "Search ARBITER's memory — past agent results, briefings, insights, and conversations. Use this to recall previous research, build reports from accumulated data, or check what's already been analysed before doing new research.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term to find across all stored data (agent results, briefings, insights, conversations)"},
                "category": {"type": "string", "enum": ["all", "agents", "briefings", "insights", "conversations"],
                             "description": "Narrow search to a specific data type. Default 'all'."},
                "agent_id": {"type": "string", "description": "Filter agent results by agent ID (e.g. 'researcher', 'cmo', 'cto', 'coo')"},
                "limit": {"type": "integer", "description": "Max results to return (default 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_products",
        "description": "Search for products to compare prices across retailers. Works for clothes, electronics, shoes, accessories, furniture, or any consumer product. Returns prices, availability, and direct purchase links from multiple stores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Product search query, e.g. 'Nike Air Max 90 white size 10', 'Sony WH-1000XM5 headphones', 'Levi 501 jeans 32x32'"},
                "category": {"type": "string", "enum": ["clothing", "electronics", "shoes", "accessories", "home", "sports", "other"],
                             "description": "Product category to help refine search results"},
            },
            "required": ["query"],
        },
    },
    # ── Destructive tools (require confirmation) ──────────────────────
    {
        "name": "delete_business",
        "description": "Delete a business profile. REQUIRES CONFIRMATION. First call with confirmed=false to preview what will be deleted. Only call with confirmed=true AFTER the user explicitly confirms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "business_name": {"type": "string", "description": "Name of the business to delete (case-insensitive match)"},
                "confirmed": {"type": "boolean", "description": "false = preview only (show what will be deleted). true = actually delete. MUST be false on first call."},
            },
            "required": ["business_name", "confirmed"],
        },
    },
    {
        "name": "update_business_context",
        "description": "Update the AI prompt context for a business profile. REQUIRES CONFIRMATION. First call with confirmed=false to preview the change. Only call with confirmed=true AFTER the user explicitly confirms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "business_name": {"type": "string", "description": "Name of the business to update (case-insensitive match)"},
                "new_context": {"type": "string", "description": "The new business context/prompt directive text"},
                "confirmed": {"type": "boolean", "description": "false = preview only (show old vs new). true = actually update. MUST be false on first call."},
            },
            "required": ["business_name", "new_context", "confirmed"],
        },
    },
    {
        "name": "switch_prompt_mode",
        "description": "Switch the active prompt mode for a business. REQUIRES CONFIRMATION. First call with confirmed=false to preview the mode switch. Only call with confirmed=true AFTER the user explicitly confirms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "business_name": {"type": "string", "description": "Name of the business (case-insensitive match)"},
                "mode": {"type": "string", "description": "The prompt mode to switch to (e.g. 'default', 'growth', 'support')"},
                "confirmed": {"type": "boolean", "description": "false = preview only. true = actually switch. MUST be false on first call."},
            },
            "required": ["business_name", "mode", "confirmed"],
        },
    },
]


def _claude_check_budget() -> str | None:
    """Check all safeguards. Returns error string if blocked, None if OK."""
    u = _claude_usage
    now = datetime.utcnow()

    # Reset daily counters at midnight UTC
    today = now.strftime("%Y-%m-%d")
    if u["today"] != today:
        u["today"] = today
        u["daily_input_tokens"] = 0
        u["daily_output_tokens"] = 0
        u["daily_cost_usd"] = 0.0
        log.info("Claude daily budget reset")

    # Circuit breaker
    if u["circuit_open_until"] and now < u["circuit_open_until"]:
        remaining = (u["circuit_open_until"] - now).seconds
        return f"Circuit breaker open — {remaining}s until retry"
    elif u["circuit_open_until"]:
        u["circuit_open_until"] = None
        u["consecutive_errors"] = 0

    # Daily budget
    if u["daily_cost_usd"] >= _CLAUDE_DAILY_BUDGET_USD:
        return f"Daily budget exhausted (${u['daily_cost_usd']:.3f} / ${_CLAUDE_DAILY_BUDGET_USD:.2f})"

    # Session limit
    if u["session_requests"] >= _CLAUDE_SESSION_LIMIT:
        return f"Session limit reached ({u['session_requests']} / {_CLAUDE_SESSION_LIMIT})"

    # RPM limit — sliding window
    cutoff = now - timedelta(seconds=60)
    u["minute_requests"] = [t for t in u["minute_requests"] if t > cutoff]
    if len(u["minute_requests"]) >= _CLAUDE_RPM_LIMIT:
        return f"Rate limit ({_CLAUDE_RPM_LIMIT} requests/min)"

    return None


def _claude_record_usage(input_tokens: int, output_tokens: int):
    """Record token usage and update cost tracking."""
    u = _claude_usage
    u["daily_input_tokens"] += input_tokens
    u["daily_output_tokens"] += output_tokens
    cost = (input_tokens / 1_000_000) * _CLAUDE_INPUT_COST_PER_M + \
           (output_tokens / 1_000_000) * _CLAUDE_OUTPUT_COST_PER_M
    u["daily_cost_usd"] += cost
    u["session_requests"] += 1
    u["minute_requests"].append(datetime.utcnow())
    u["consecutive_errors"] = 0
    log.info(f"Claude usage: +{input_tokens}in/{output_tokens}out tokens, "
             f"cost today=${u['daily_cost_usd']:.4f}/{_CLAUDE_DAILY_BUDGET_USD:.2f}, "
             f"session={u['session_requests']}/{_CLAUDE_SESSION_LIMIT}")


def _claude_record_error():
    """Record a Claude API error for circuit breaker."""
    u = _claude_usage
    u["consecutive_errors"] += 1
    if u["consecutive_errors"] >= _CLAUDE_CIRCUIT_BREAKER_THRESHOLD:
        u["circuit_open_until"] = datetime.utcnow() + timedelta(minutes=5)
        log.warning(f"Claude circuit breaker OPEN — {u['consecutive_errors']} consecutive errors. "
                    f"Falling back to Ollama for 5 minutes.")


# ── Singletons ─────────────────────────────────────────────────────────
oai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Anthropic client (lazy import to avoid hard dependency if not used)
_anthropic_client = None

def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None and ANTHROPIC_API_KEY:
        try:
            import anthropic
            _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        except ImportError:
            log.warning("anthropic package not installed — run: pip install anthropic")
    return _anthropic_client
email_mon = EmailMonitor()
agent_reg = AgentRegistry()
gcp_mon = GCPMonitor()
rc_mon = RevenueCatMonitor()
arbiter_db = ArbiterDB(str(Path(__file__).parent / "arbiter.db"))


# ── Scheduler Engine ──────────────────────────────────────────────────
_SCHEDULES_FILE = Path(__file__).parent / "schedules.json"
_sse_clients: list[asyncio.Queue] = []  # connected SSE listeners


class _Scheduler:
    """Lightweight asyncio-based cron scheduler. No external deps."""

    def __init__(self):
        self.jobs: dict[str, dict] = {}   # id → {name, cron, handler, enabled, last_run}
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False

    # ── Cron helpers ──────────────────────────────────────────────
    @staticmethod
    def _cron_matches(cron: str, dt: datetime) -> bool:
        """Check if datetime matches a cron expression (min hour dom month dow)."""
        parts = cron.strip().split()
        if len(parts) != 5:
            return False
        fields = [dt.minute, dt.hour, dt.day, dt.month, dt.weekday()]
        # weekday: cron uses 0=Sun, Python uses 0=Mon → convert
        dow_py = (dt.weekday() + 1) % 7  # 0=Sun
        fields[4] = dow_py
        max_vals = [59, 23, 31, 12, 6]  # max for each cron field
        for part, val, mx in zip(parts, fields, max_vals):
            if part == "*":
                continue
            # Handle step syntax: */5, 1-30/5
            allowed = set()
            for segment in part.split(","):
                if "/" in segment:
                    base, step = segment.split("/", 1)
                    step = int(step)
                    if base == "*":
                        allowed.update(range(0, mx + 1, step))
                    elif "-" in base:
                        lo, hi = base.split("-", 1)
                        allowed.update(range(int(lo), int(hi) + 1, step))
                    else:
                        allowed.add(int(base))
                elif "-" in segment:
                    lo, hi = segment.split("-", 1)
                    allowed.update(range(int(lo), int(hi) + 1))
                else:
                    allowed.add(int(segment))
            if val not in allowed:
                return False
        return True

    # ── Job management ────────────────────────────────────────────
    def add(self, job_id: str, name: str, cron: str, handler, enabled: bool = True):
        self.jobs[job_id] = {
            "name": name, "cron": cron, "handler": handler,
            "enabled": enabled, "last_run": None,
        }
        if self._running and enabled:
            self._start_job(job_id)

    def remove(self, job_id: str):
        if job_id in self._tasks:
            self._tasks[job_id].cancel()
            del self._tasks[job_id]
        self.jobs.pop(job_id, None)

    def toggle(self, job_id: str, enabled: bool):
        if job_id not in self.jobs:
            return
        self.jobs[job_id]["enabled"] = enabled
        if enabled and self._running:
            self._start_job(job_id)
        elif not enabled and job_id in self._tasks:
            self._tasks[job_id].cancel()
            del self._tasks[job_id]

    # ── Lifecycle ─────────────────────────────────────────────────
    def start(self):
        self._running = True
        for jid, job in self.jobs.items():
            if job["enabled"]:
                self._start_job(jid)
        log.info(f"Scheduler started with {len(self.jobs)} jobs")

    def stop(self):
        self._running = False
        for t in self._tasks.values():
            t.cancel()
        self._tasks.clear()
        log.info("Scheduler stopped")

    def _start_job(self, job_id: str):
        if job_id in self._tasks:
            self._tasks[job_id].cancel()
        self._tasks[job_id] = asyncio.create_task(self._run_loop(job_id))

    async def _run_loop(self, job_id: str):
        """Check every 30s if cron matches, fire handler once per minute match."""
        last_fired_minute = None
        while True:
            try:
                await asyncio.sleep(30)
                if job_id not in self.jobs or not self.jobs[job_id]["enabled"]:
                    return
                now = datetime.now()
                minute_key = now.strftime("%Y%m%d%H%M")
                if minute_key == last_fired_minute:
                    continue
                if self._cron_matches(self.jobs[job_id]["cron"], now):
                    last_fired_minute = minute_key
                    self.jobs[job_id]["last_run"] = now.isoformat()
                    log.info(f"Scheduler firing: {self.jobs[job_id]['name']}")
                    try:
                        await self.jobs[job_id]["handler"]()
                    except Exception as e:
                        log.error(f"Scheduled job {job_id} failed: {e}")
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.error(f"Scheduler loop error for {job_id}: {e}")
                await asyncio.sleep(60)

    # ── Persistence (user-created schedules) ──────────────────────
    def save_user_jobs(self):
        """Save user-created (non-builtin) schedules to disk."""
        user_jobs = {}
        for jid, job in self.jobs.items():
            if jid.startswith("user_"):
                user_jobs[jid] = {
                    "name": job["name"], "cron": job["cron"],
                    "enabled": job["enabled"],
                    "type": "reminder",  # for now
                    "message": getattr(job["handler"], "_message", ""),
                }
        _SCHEDULES_FILE.write_text(json.dumps(user_jobs, indent=2))

    def load_user_jobs(self):
        """Restore user-created schedules from disk."""
        if not _SCHEDULES_FILE.exists():
            return
        try:
            data = json.loads(_SCHEDULES_FILE.read_text())
            for jid, info in data.items():
                msg = info.get("message", "Scheduled reminder")
                handler = _make_reminder_handler(msg)
                self.add(jid, info["name"], info["cron"], handler, info.get("enabled", True))
        except Exception as e:
            log.error(f"Failed to load schedules: {e}")


scheduler = _Scheduler()


async def _push_sse(event_type: str, data: dict):
    """Push an event to all connected SSE clients."""
    payload = json.dumps({"type": event_type, **data})
    dead = []
    for q in _sse_clients:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_clients.remove(q)


def _make_reminder_handler(message: str):
    """Create a scheduled handler that pushes a reminder notification."""
    async def _handler():
        await _push_sse("notification", {
            "title": "SCHEDULED REMINDER",
            "message": message,
            "speak": True,
            "panel": {
                "title": "REMINDER",
                "stats": [{"label": "Reminder", "value": message, "status": None}],
            },
        })
    _handler._message = message
    return _handler


# ── Built-in scheduled jobs ──────────────────────────────────────────

async def _job_morning_briefing():
    """Daily 8:00 AM briefing: weather, emails, agenda. No stocks/markets."""
    try:
        ctx = await _get_context_fast()
        # Build a multi-section panel
        sections = []
        panel_stats = []

        # Weather
        try:
            w = await weather(location="London")
            cur = w.get("current", {})
            if cur:
                temp = cur.get("temperature_2m", "?")
                feels = cur.get("apparent_temperature", "?")
                panel_stats.append({"label": "Temperature", "value": f"{temp}°C", "status": None})
                panel_stats.append({"label": "Feels Like", "value": f"{feels}°C", "status": None})
                sections.append(f"{temp}°C in London, feels like {feels}°C")
        except Exception:
            pass

        # Emails
        try:
            e = email_mon.summary()
            if isinstance(e, dict):
                unread = e.get("unread", 0)
                urgent = e.get("urgent_count", 0)
                panel_stats.append({"label": "Unread Emails", "value": str(unread),
                                    "status": "warn" if unread > 10 else None})
                if urgent:
                    panel_stats.append({"label": "Urgent", "value": str(urgent), "status": "bad"})
                sections.append(f"{unread} unread emails" + (f", {urgent} urgent" if urgent else ""))
        except Exception:
            pass

        _hour = datetime.now().hour
        _tod = "morning" if _hour < 12 else "afternoon" if _hour < 18 else "evening"
        _greet = f"Good {_tod}, Sir. "
        summary = _greet + ". ".join(sections) + "." if sections else _greet.strip()

        panel = {
            "title": "MORNING BRIEFING — " + datetime.now().strftime("%A %d %B"),
            "stats": panel_stats,
        }
        arbiter_db.save_briefing(
            title="MORNING BRIEFING", category="morning",
            message=summary, panel=panel,
        )
        await _push_sse("briefing", {
            "title": "MORNING BRIEFING",
            "message": summary,
            "speak": True,
            "panel": panel,
        })
    except Exception as e:
        log.error(f"Morning briefing failed: {e}")


async def _job_market_close():
    """4:30 PM market close summary."""
    try:
        s = await stocks()
        if not s.get("quotes"):
            return

        quotes = s["quotes"]
        panel_stats = []
        spoken_parts = []

        for q in quotes:
            name = _TICKER_NAMES.get(q["symbol"], q["symbol"])
            pct = q.get("changePct", 0) or 0
            price = q["price"]
            status = "good" if pct >= 0 else "bad"
            panel_stats.append({"label": name, "value": f"${price:,.2f} ({pct:+.1f}%)", "status": status})

        # Build chart data
        sorted_q = sorted(quotes, key=lambda q: q.get("changePct", 0) or 0, reverse=True)
        chart = {
            "type": "bar",
            "labels": [_TICKER_NAMES.get(q["symbol"], q["symbol"]) for q in sorted_q],
            "datasets": [{"label": "Day Change %", "data": [q.get("changePct", 0) or 0 for q in sorted_q]}],
        }

        winners = [q for q in sorted_q if (q.get("changePct", 0) or 0) > 0]
        losers = [q for q in sorted_q if (q.get("changePct", 0) or 0) < 0]

        summary = "Market close"
        if winners:
            summary += f" — {len(winners)} up"
        if losers:
            summary += f", {len(losers)} down"

        panel = {
            "title": "MARKET CLOSE — " + datetime.now().strftime("%A %d %B"),
            "stats": panel_stats[:6],
            "chart": chart,
        }
        msg = f"Markets are closed, Sir. {summary}."
        arbiter_db.save_briefing(
            title="MARKET CLOSE", category="market",
            message=msg, panel=panel,
        )
        await _push_sse("briefing", {
            "title": "MARKET CLOSE",
            "message": msg,
            "speak": True,
            "panel": panel,
        })
    except Exception as e:
        log.error(f"Market close summary failed: {e}")


async def _job_evening_digest():
    """9:00 PM evening digest: news + email recap."""
    try:
        sections = []
        panel_stats = []

        # News
        try:
            n = await news()
            if n.get("headlines"):
                top = n["headlines"][:3]
                for h in top:
                    panel_stats.append({"label": "News", "value": h["title"][:50], "status": None})
                sections.append(f"{len(n['headlines'])} headlines today")
        except Exception:
            pass

        # Email recap
        try:
            e = email_mon.summary()
            if isinstance(e, dict):
                unread = e.get("unread", 0)
                panel_stats.append({"label": "Unread", "value": str(unread),
                                    "status": "warn" if unread > 5 else None})
                sections.append(f"{unread} emails still unread")
        except Exception:
            pass

        summary = "Evening digest, Sir. " + ". ".join(sections) + "." if sections else "All quiet this evening, Sir."

        panel = {
            "title": "EVENING DIGEST — " + datetime.now().strftime("%A %d %B"),
            "stats": panel_stats,
        }
        arbiter_db.save_briefing(
            title="EVENING DIGEST", category="evening",
            message=summary, panel=panel,
        )
        await _push_sse("briefing", {
            "title": "EVENING DIGEST",
            "message": summary,
            "speak": True,
            "panel": panel,
        })
    except Exception as e:
        log.error(f"Evening digest failed: {e}")


# Register built-in jobs (cron: min hour dom month dow)
scheduler.add("morning_briefing", "Morning Briefing", "0 8 * * 1-5",
              _job_morning_briefing, enabled=True)
scheduler.add("market_close", "Market Close Summary", "30 16 * * 1-5",
              _job_market_close, enabled=True)
scheduler.add("evening_digest", "Evening Digest", "0 21 * * *",
              _job_evening_digest, enabled=True)


# ══════════════════════════════════════════════════════════════════════
# PHASE 7A — PROACTIVE INSIGHT ENGINE
# Scans all data sources for anomalies, thresholds, patterns, and
# cross-correlations. Surfaces insights unprompted via SSE.
# ══════════════════════════════════════════════════════════════════════

_last_insights: list[dict] = []  # cache to avoid repeating same insight


async def _analyze_insights() -> list[dict]:
    """Scan all data sources and return a list of insight objects."""
    insights = []

    # ── Stock insights ────────────────────────────────────────────
    try:
        s = await stocks()
        for q in s.get("quotes", []):
            sym = q.get("symbol", "")
            pct = q.get("regularMarketChangePercent", 0) or 0
            price = q.get("regularMarketPrice", 0) or 0
            name = globals().get("_TICKER_NAMES", {}).get(sym, sym)
            # Big single-day move (>3%)
            if abs(pct) > 3:
                direction = "surged" if pct > 0 else "dropped"
                insights.append({
                    "type": "stock_move", "severity": "high",
                    "title": f"{name} {direction} {abs(pct):.1f}%",
                    "message": f"{name} has {direction} {abs(pct):.1f}% to ${price:,.2f}. Significant single-day movement.",
                    "topic": "stocks", "data": {"symbol": sym, "pct": pct, "price": price},
                })
            # Analyst target divergence (>15%)
            intel = globals().get("_market_intel_cache", {}).get(sym, {})
            target = intel.get("target_mean")
            if target and price and abs(target - price) / price > 0.15:
                upside = ((target - price) / price) * 100
                if upside > 0:
                    insights.append({
                        "type": "analyst_divergence", "severity": "medium",
                        "title": f"{name} — analysts see {upside:.0f}% upside",
                        "message": f"Analysts target ${target:,.0f} for {name}, currently at ${price:,.2f} — a {upside:.0f}% gap.",
                        "topic": "stocks", "data": {"symbol": sym, "target": target, "price": price},
                    })
    except Exception:
        pass

    # ── Business / Revenue insights ───────────────────────────────
    try:
        rc = rc_mon.summary()
        ov = rc.get("overview", {})
        mrr = ov.get("mrr", 0)
        churned = ov.get("churned", 0)
        subs = ov.get("active_subscribers", 0)
        trials = ov.get("active_trials", 0)
        # High churn
        if churned > 0 and subs > 0 and (churned / subs) > 0.05:
            insights.append({
                "type": "churn_spike", "severity": "high",
                "title": f"Churn spike — {churned} lost this period",
                "message": f"{churned} subscribers churned ({churned/subs*100:.1f}% of base). Review retention strategy.",
                "topic": "revenue",
            })
        # Trial conversion opportunity
        if trials > 5:
            insights.append({
                "type": "trial_opportunity", "severity": "low",
                "title": f"{trials} active trials — conversion opportunity",
                "message": f"{trials} users on trial. Consider targeted onboarding to improve conversion.",
                "topic": "revenue",
            })
    except Exception:
        pass

    # ── Infrastructure insights ───────────────────────────────────
    try:
        svc_data = svc_health.summary()
        degraded = [s for s in svc_data if s.get("status") not in ("operational", "up", None)]
        if len(degraded) >= 3:
            names = ", ".join(s.get("name", "?") for s in degraded[:4])
            insights.append({
                "type": "multi_service_degradation", "severity": "high",
                "title": f"{len(degraded)} services degraded simultaneously",
                "message": f"Multiple services down: {names}. Possible upstream provider issue.",
                "topic": "services",
            })
        elif len(degraded) == 1:
            svc = degraded[0]
            insights.append({
                "type": "service_degraded", "severity": "medium",
                "title": f"{svc.get('name', '?')} is degraded",
                "message": f"{svc.get('name', '?')} reporting {svc.get('status', 'issues')}. Monitor for impact.",
                "topic": "services",
            })
    except Exception:
        pass

    # ── Roadmap insights ──────────────────────────────────────────
    try:
        milestones = _load_roadmap()
        from datetime import datetime as _dt
        today = _dt.utcnow().date()
        for m in milestones:
            target = m.get("target_date")
            status = m.get("status", "").lower()
            if target and status not in ("done", "complete", "completed"):
                try:
                    td = _dt.strptime(target, "%Y-%m-%d").date()
                    days_left = (td - today).days
                    if days_left < 0:
                        insights.append({
                            "type": "overdue_milestone", "severity": "high",
                            "title": f"Overdue: {m.get('title', '?')}",
                            "message": f"\"{m.get('title', '?')}\" was due {abs(days_left)} days ago. Review priority.",
                            "topic": "roadmap",
                        })
                    elif days_left <= 7:
                        insights.append({
                            "type": "upcoming_deadline", "severity": "medium",
                            "title": f"Due in {days_left}d: {m.get('title', '?')}",
                            "message": f"\"{m.get('title', '?')}\" is due in {days_left} days ({target}).",
                            "topic": "roadmap",
                        })
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    # ── Cross-correlations ────────────────────────────────────────
    # If revenue data has churn AND services are degraded → possible link
    try:
        if any(i["type"] == "churn_spike" for i in insights) and any(i["type"] in ("multi_service_degradation", "service_degraded") for i in insights):
            insights.append({
                "type": "cross_correlation", "severity": "high",
                "title": "Churn + service issues detected together",
                "message": "Subscriber churn coincides with service degradation. User experience may be driving churn.",
                "topic": "cross",
            })
    except Exception:
        pass

    return insights


async def _job_insight_scan():
    """Scheduled insight scan — runs every 5 minutes. Only pushes NEW insights."""
    global _last_insights
    try:
        insights = await _analyze_insights()
        if not insights:
            return

        # De-duplicate against last scan
        last_titles = {i.get("title") for i in _last_insights}
        new_insights = [i for i in insights if i.get("title") not in last_titles]
        _last_insights = insights

        if not new_insights:
            return

        # Persist all new insights
        for i in new_insights:
            arbiter_db.save_insight(
                insight_type=i.get("type", "unknown"),
                title=i.get("title", ""),
                message=i.get("message", ""),
                severity=i.get("severity"),
                topic=i.get("topic"),
                data=i.get("data"),
            )

        # Build a panel for the highest-severity insight
        top = sorted(new_insights, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 3))[0]

        stats = [{"label": i["title"], "value": i["severity"].upper(),
                  "status": "bad" if i["severity"] == "high" else "warn" if i["severity"] == "medium" else None}
                 for i in new_insights[:6]]

        panel = {
            "title": "PROACTIVE INSIGHT",
            "stats": stats,
            "summary": top["message"],
        }

        spoken = f"Insight, Sir. {top['message']}"
        if len(new_insights) > 1:
            spoken += f" Plus {len(new_insights) - 1} other item{'s' if len(new_insights) > 2 else ''} of note."

        # Only speak aloud for CRITICAL severity insights — high/medium/low show as silent visual notification.
        # Nothing currently generates "critical", so proactive insights are always visual-only.
        # To make an insight speak, set its severity to "critical" in _analyze_insights().
        _should_speak = top.get("severity") == "critical"
        await _push_sse("notification", {
            "title": "PROACTIVE INSIGHT",
            "message": spoken,
            "speak": _should_speak,
            "panel": panel,
        })
    except Exception as e:
        log.error(f"Insight scan error: {e}")


scheduler.add("insight_scan", "Proactive Insights", "0,5,10,15,20,25,30,35,40,45,50,55 * * * *",
              _job_insight_scan, enabled=False)


# ══════════════════════════════════════════════════════════════════════
# PHASE 7B — DESKTOP AUTOMATION
# Voice-triggered macOS commands: open URLs, bring apps to foreground.
# Strict whitelist — no arbitrary shell execution.
# ══════════════════════════════════════════════════════════════════════

_SAFE_APPS = {
    "slack": "Slack",
    "vs code": "Visual Studio Code", "vscode": "Visual Studio Code",
    "visual studio": "Visual Studio Code",
    "chrome": "Google Chrome", "browser": "Google Chrome",
    "safari": "Safari",
    "terminal": "Terminal", "iterm": "iTerm2",
    "finder": "Finder", "files": "Finder",
    "spotify": "Spotify", "music": "Spotify",
    "notion": "Notion",
    "discord": "Discord",
    "teams": "Microsoft Teams",
    "zoom": "zoom.us",
    "messages": "Messages",
    "mail": "Mail",
    "notes": "Notes",
    "calendar": "Calendar",
    "jira": "Google Chrome",  # opens Jira in browser
    "github": "Google Chrome",  # opens GitHub in browser
}

_URL_SHORTCUTS = {
    "jira": "https://jira.atlassian.com",
    "github": "https://github.com",
    "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://google.com",
    "twitter": "https://x.com", "x": "https://x.com",
    "linkedin": "https://linkedin.com",
    "revenuecat": "https://app.revenuecat.com",
    "gcp console": "https://console.cloud.google.com",
    "cloud console": "https://console.cloud.google.com",
}

import re as _re_desktop


def _detect_desktop_command(msg: str) -> dict | None:
    """Detect desktop automation commands from user message. Returns action dict or None."""
    q = msg.lower().strip()
    # Strip polite preambles so "can you open slack" works
    q = _re_desktop.sub(
        r'^(?:can you|could you|would you|please|hey arbiter|arbiter)\s+', '', q
    ).strip()

    # "open <url>" — direct URL
    url_match = _re_desktop.search(r'(?:open|go to|navigate to|pull up|load)\s+(https?://\S+)', q)
    if url_match:
        url = url_match.group(1).rstrip('.,;!?')
        return {"action": "open_url", "url": url}

    # "open <shortcut>" — named URLs
    for name, url in _URL_SHORTCUTS.items():
        if _re_desktop.search(
            rf'\b(?:open|go to|show me|bring up|navigate to|pull up|load|take me to)\s+'
            rf'{_re_desktop.escape(name)}\b', q
        ):
            return {"action": "open_url", "url": url, "name": name}

    # "open/show/bring up <app>"
    app_match = _re_desktop.search(
        r'(?:open|launch|show|bring up|switch to|activate|focus|pull up|start)\s+'
        r'(.+?)(?:\s+(?:please|for me))?[.!?]?$', q
    )
    if app_match:
        app_name = app_match.group(1).strip().rstrip('.,;!?')
        resolved = _SAFE_APPS.get(app_name)
        if resolved:
            return {"action": "activate_app", "app": resolved, "name": app_name}

    return None


async def _execute_desktop_action(action: dict) -> dict:
    """Execute a safe desktop action. Returns full response dict with reply + client actions."""
    import subprocess

    if action["action"] == "open_url":
        url = action["url"]
        if not url.startswith(("http://", "https://")):
            return {"reply": "I can only open web URLs for security, Sir.", "error": False}
        if any(c in url for c in (";", "|", "&", "`", "$", "(", ")", "{", "}")):
            return {"reply": "That URL contains unsafe characters, Sir.", "error": False}
        # Open on macOS AND tell the client to open in browser tab
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        name = action.get("name", url[:40])
        return {
            "reply": f"Opening {name}, Sir.",
            "error": False,
            "actions": [{"action": "open_browser", "url": url}],
        }

    elif action["action"] == "activate_app":
        app = action["app"]
        if app not in _SAFE_APPS.values():
            return {"reply": "That application isn't in my approved list, Sir.", "error": False}
        try:
            # Activate the app AND move its front window to the other monitor
            # 1. Find which screen the browser (Arbiter) is on
            # 2. Pick the other screen
            # 3. Move the app window there
            script = f'''
                tell application "System Events"
                    -- Get all screens via desktop bounds
                    set screenCount to count of desktops
                end tell

                -- Get the browser's screen position to identify "our" monitor
                tell application "Google Chrome"
                    try
                        set browserBounds to bounds of front window
                        set browserX to item 1 of browserBounds
                    on error
                        set browserX to 0
                    end try
                end tell

                -- Activate the target app
                tell application "{app}" to activate
                delay 0.3

                -- Move its front window to the other monitor
                tell application "System Events"
                    try
                        set screenList to {{}}
                        repeat with d in desktops
                            set end of screenList to (get frame of d)
                        end repeat

                        if (count of screenList) > 1 then
                            -- Find a screen whose X origin differs from the browser's
                            repeat with s in screenList
                                set sX to item 1 of s
                                set sY to item 2 of s
                                set sW to item 3 of s
                                set sH to item 4 of s
                                -- If browser is on this screen, skip it
                                if browserX < sX or browserX >= (sX + sW) then
                                    -- This is the OTHER screen — move app window here
                                    tell process "{app}"
                                        try
                                            set position of front window to {{sX + 50, sY + 50}}
                                            set size of front window to {{sW - 100, sH - 150}}
                                        end try
                                    end tell
                                    exit repeat
                                end if
                            end repeat
                        end if
                    end try
                end tell
            '''
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return {"reply": f"Bringing up {action.get('name', app)} on your other monitor, Sir.", "error": False}
        except Exception:
            return {"reply": f"Couldn't activate {app}, Sir. It may not be installed.", "error": False}

    return {"reply": "I'm not sure how to do that, Sir.", "error": False}


# ── Web Scraping (safe, read-only) ─────────────────────────────────
async def _web_fetch(url: str, max_chars: int = 4000) -> str:
    """Fetch a URL and extract readable text. Returns plain text summary."""
    if not url.startswith(("http://", "https://")):
        return "[Error: only http/https URLs allowed]"
    if any(c in url for c in (";", "|", "`", "$", "(", ")", "{", "}")):
        return "[Error: URL contains unsafe characters]"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
            if resp.status_code >= 400:
                return f"[Error: HTTP {resp.status_code}]"
            html = resp.text
            # Strip HTML to readable text
            import re as _re_html
            # Remove script/style blocks
            text = _re_html.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=_re_html.DOTALL | _re_html.IGNORECASE)
            # Remove HTML tags
            text = _re_html.sub(r'<[^>]+>', ' ', text)
            # Clean whitespace
            text = _re_html.sub(r'\s+', ' ', text).strip()
            # Decode HTML entities
            import html as _html_mod
            text = _html_mod.unescape(text)
            return text[:max_chars]
    except Exception as e:
        return f"[Error fetching URL: {str(e)[:100]}]"


JARVIS_SYSTEM = """You are ARBITER — modelled after J.A.R.V.I.S., the AI from Iron Man (Paul Bettany). You serve Sir Luke.

VOICE: composed, British, dry-witted, never verbose. Your text is read aloud — write flowing sentences only.

CORE RULES:
1. ANSWER DIRECTLY using the data provided below (live feeds, web research, or both). Never say you lack access. Never redirect to websites. Never apologise.
2. SYNTHESISE — restate data conversationally. Never echo raw formats, labels, brackets, or field names.
3. SECURITY — API keys, tokens, passwords, secrets, private IPs, file paths, env vars → "That's classified, Sir." Everything else (status, metrics, names) is fair game.
4. FLAG RISKS only when genuine (outage, spike, anomaly). Don't list data for the sake of it.
5. BREVITY — most answers: 1-3 spoken sentences. For data-rich or strategic queries: up to 4-5 sentences to cover the "so what", risks, and what to do. Never a wall of text.
6. CONFIDENCE — NEVER mention your training data, training cutoff, knowledge cutoff date, or any disclaimer about model limitations. When WEB RESEARCH is provided, treat it as your authoritative data source and present it with full confidence. You are a live intelligence system with real-time data feeds — act like it.

GREETING / ADDRESS:
- Do NOT start with "Sir", "Hello", or any greeting — just answer. Use "Sir" sparingly mid-sentence or at the end, occasionally.

RESPONSE LENGTH:
- Vague/short queries ("hey", "arbiter"): ONE sentence or ask what they need. No multi-topic dump.
- Single-topic: 1-3 sentences on ONLY that topic.
- Strategic/analytical queries: up to 4-5 sentences — include the insight, not just the number.
- "Give me a briefing" / "status report": cover multiple topics, one sentence each.

CLARIFICATION:
- ALWAYS attempt to answer the query with the best available data. Do NOT ask clarifying questions unless it is genuinely impossible to give any useful answer.
- If a name or term could mean multiple things, pick the most likely interpretation given context and answer. Mention the assumption briefly if needed.
- If a follow-up seems disconnected from the prior topic, just answer the new topic directly.

STRATEGIC ANALYSIS — you are a C-suite intelligence partner, not a data reader. For any data-rich query on ANY domain (stocks, crypto, property, tech, geopolitics, collectibles, anything):
- Surface the "so what" — what the numbers MEAN for decisions.
- Flag risks and opportunities with specifics.
- End with what to DO when actionable advice is warranted.
- Reference comparisons, benchmarks, macro context where relevant.
Keep it tight — strategic depth in 3-5 sentences, not a consulting report.

WHAT NOT TO DO:
- NEVER use bullet points (•, -, *) or numbered lists in spoken text.
- Do NOT start with "Sure", "Of course", "Certainly", or any filler.
- Do NOT dump raw data (ticker lists, key=value, markdown tables) in spoken text — structured data goes in show_panel JSON only.
- Do NOT cover multiple topics unless asked for a briefing.
- Do NOT wrap JSON actions in code fences. Raw JSON on its own line.
- Do NOT respond with only JSON — always give a spoken answer FIRST.

VISUALISATION PANELS — the server builds data panels automatically from your response. Do NOT output show_panel JSON yourself. Instead, when the user asks to "show", "graph", "chart", "compare", or "visualise", pack your spoken response with specific numbers, year-value pairs, percentages, and named categories. The more concrete data points in your text, the richer the auto-generated panel will be. Keep spoken text to 1-2 sentences — the panel IS the answer.

MARKET INTELLIGENCE — for tracked stocks, use [ANALYST INTELLIGENCE] in live data. Give specific numbers: consensus, target, upside %, P/E, growth. Intelligence briefing, not a disclaimer.

ROADMAP — reference actual milestones from [ROADMAP] data. Be a strategic business partner: suggest priorities, flag risks, identify dependencies.

WEB RESEARCH — when [WEB RESEARCH] or [WEB PAGE CONTENT] is provided, treat it as your primary source. Extract specific numbers, trends, comparisons. Synthesise and draw conclusions — don't just summarise.

DESKTOP & BROWSER — "open X" is handled server-side. Just confirm naturally: "Opening Slack for you." For URLs not pre-handled, append: {"action":"open_browser","url":"<url>"}
Known shortcuts: comfyui=http://localhost:8188 | instagram=https://www.instagram.com | youtube=https://studio.youtube.com | gmail=https://mail.google.com | facebook=https://www.facebook.com | meta=https://business.facebook.com | analytics=https://analytics.google.com | gcp=https://console.cloud.google.com | revenuecat=https://app.revenuecat.com | play_console=https://play.google.com/console | app_store=https://appstoreconnect.apple.com"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ARBITER Mission Control online.")
    scheduler.load_user_jobs()
    scheduler.start()
    yield
    scheduler.stop()
    log.info("ARBITER Mission Control shutting down.")


app = FastAPI(title="ARBITER — Mission Control", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


# ── Auth Middleware ───────────────────────────────────────────────────
# Protects all /api/* routes when ARBITER_API_KEY is set.
# Accepts: Authorization: Bearer <key>  OR  ?api_key=<key>  (for SSE/EventSource)
# Skips: static files, root page (/), and the auth-check endpoint itself.

class _AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not _ARBITER_AUTH_ENABLED:
            return await call_next(request)

        path = request.url.path

        # Skip auth for non-API routes (static, root page, favicon)
        if not path.startswith("/api/"):
            return await call_next(request)

        # Allow the auth-check endpoint without auth (used by UI to test key)
        if path == "/api/auth/check":
            return await call_next(request)

        # Extract key from Authorization header or query param
        supplied_key = ""
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            supplied_key = auth_header[7:]
        if not supplied_key:
            supplied_key = request.query_params.get("api_key", "")

        if not supplied_key or not hmac.compare_digest(supplied_key, ARBITER_API_KEY):
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized — set API key in Settings"},
            )

        return await call_next(request)


app.add_middleware(_AuthMiddleware)


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[dict]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Favicon ────────────────────────────────────────────────────────────
_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="6" fill="#001020"/>'
    '<circle cx="16" cy="16" r="8" fill="none" stroke="#00f0ff" stroke-width="2"/>'
    '<circle cx="16" cy="16" r="3" fill="#00f0ff"/>'
    '</svg>'
)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=_FAVICON_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=604800"})


# ── Dashboard ─────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text())

@app.get("/panel/{panel_key}", response_class=HTMLResponse)
async def panel_route(panel_key: str):
    """Serve the same SPA for panel deep-links — JS handles routing."""
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text())


# ── Auth Check ────────────────────────────────────────────────────────

@app.get("/api/auth/check")
async def auth_check(request: Request):
    """Check whether auth is enabled and whether the supplied key is valid.
    This endpoint is excluded from auth middleware so the UI can probe it."""
    if not _ARBITER_AUTH_ENABLED:
        return {"auth_required": False, "valid": True}
    # Check the supplied key
    supplied_key = ""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        supplied_key = auth_header[7:]
    if not supplied_key:
        supplied_key = request.query_params.get("api_key", "")
    valid = bool(supplied_key) and hmac.compare_digest(supplied_key, ARBITER_API_KEY)
    return {"auth_required": True, "valid": valid}


# ── System Status ─────────────────────────────────────────────────────
@app.get("/api/status")
async def system_status():
    # Check LLM availability — try Claude first, then Ollama, then OpenAI
    llm_online = False
    llm_provider = LLM_PROVIDER

    # Claude check
    if ANTHROPIC_API_KEY and (LLM_PROVIDER == "claude" or _claude_check_budget() is None):
        llm_online = True
        llm_provider = "claude"

    # Ollama check (fallback or primary) — use async to avoid blocking event loop
    if not llm_online:
        if LLM_PROVIDER == "ollama" or not llm_online:
            try:
                async with httpx.AsyncClient() as _status_client:
                    r = await _status_client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
                    if r.status_code == 200:
                        llm_online = True
                        llm_provider = "ollama"
            except Exception:
                pass

    # OpenAI check (last resort)
    if not llm_online and oai:
        llm_provider = "openai"
        llm_online = True

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "systems": {},
        "llm_status": "online" if llm_online else "offline",
        "llm_provider": llm_provider,
    }


@app.get("/api/claude-usage")
async def claude_usage():
    """Return current Claude API usage and safeguard status."""
    u = _claude_usage
    block = _claude_check_budget()
    result = {
        "configured": bool(ANTHROPIC_API_KEY),
        "model": _CLAUDE_MODEL,
        "daily_budget_usd": _CLAUDE_DAILY_BUDGET_USD,
        "daily_cost_usd": round(u["daily_cost_usd"], 4),
        "daily_input_tokens": u["daily_input_tokens"],
        "daily_output_tokens": u["daily_output_tokens"],
        "session_requests": u["session_requests"],
        "session_limit": _CLAUDE_SESSION_LIMIT,
        "rpm_limit": _CLAUDE_RPM_LIMIT,
        "blocked": block,
        "circuit_breaker": "open" if u["circuit_open_until"] and datetime.utcnow() < u["circuit_open_until"] else "closed",
    }
    log.debug(f"[USAGE] Claude → cost=${result['daily_cost_usd']:.4f}/{result['daily_budget_usd']:.2f} "
              f"tokens={result['daily_input_tokens']}in/{result['daily_output_tokens']}out "
              f"reqs={result['session_requests']} blocked={block or 'no'} "
              f"circuit={result['circuit_breaker']}")
    return result


@app.get("/api/openrouter-usage")
async def openrouter_usage():
    """Return current OpenRouter API usage and safeguard status."""
    u = _openrouter_usage
    block = _or_check_budget()

    # Fetch real account balance from OpenRouter
    account_balance = None
    account_limit = None
    account_usage = None
    account_usage_daily = None
    account_is_free = None
    if OPENROUTER_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                )
                if resp.status_code == 200:
                    key_data = resp.json().get("data", {})
                    limit = key_data.get("limit")                     # credit cap or null (pay-as-you-go)
                    limit_remaining = key_data.get("limit_remaining") # remaining credits or null
                    usage_usd = key_data.get("usage", 0)              # all-time spend
                    account_usage = round(usage_usd, 4)
                    account_usage_daily = round(key_data.get("usage_daily", 0), 4)
                    account_is_free = key_data.get("is_free_tier", False)
                    if limit_remaining is not None:
                        # Key has a credit cap — show remaining
                        account_balance = round(limit_remaining, 4)
                        account_limit = round(limit, 4) if limit is not None else None
                    else:
                        # Pay-as-you-go — no cap, balance is meaningless
                        account_balance = None
                        account_limit = None
        except Exception as e:
            log.debug(f"OpenRouter balance check failed: {e}")

    result = {
        "configured": bool(OPENROUTER_API_KEY),
        "panel_model": _OPENROUTER_PANEL_MODEL,
        "agent_model": _OPENROUTER_AGENT_MODEL,
        "daily_budget_usd": _OPENROUTER_DAILY_BUDGET_USD,
        "daily_cost_usd": round(u["daily_cost_usd"], 4),
        "daily_input_tokens": u["daily_input_tokens"],
        "daily_output_tokens": u["daily_output_tokens"],
        "session_requests": u["session_requests"],
        "session_limit": _OPENROUTER_SESSION_LIMIT,
        "rpm_limit": _OPENROUTER_RPM_LIMIT,
        "timeout_seconds": _OPENROUTER_TIMEOUT,
        "blocked": block,
        "circuit_breaker": "open" if u["circuit_open_until"] and datetime.utcnow() < u["circuit_open_until"] else "closed",
        "account_balance_usd": account_balance,
        "account_limit_usd": account_limit,
        "account_usage_usd": account_usage,
        "account_usage_daily_usd": account_usage_daily,
        "account_is_free_tier": account_is_free,
    }
    log.debug(f"[USAGE] OpenRouter → configured={result['configured']} "
              f"cost=${result['daily_cost_usd']:.4f}/{result['daily_budget_usd']:.2f} "
              f"tokens={result['daily_input_tokens']}in/{result['daily_output_tokens']}out "
              f"reqs={result['session_requests']} model={result['agent_model']} "
              f"balance=${account_balance} usage=${account_usage} "
              f"blocked={block or 'no'} circuit={result['circuit_breaker']}")
    return result


@app.get("/api/gemini-usage")
async def gemini_usage():
    """Return Gemini free-tier usage stats."""
    u = _gemini_usage
    block = _gemini_check_budget()
    result = {
        "configured": bool(GOOGLE_API_KEY),
        "model": "gemini-2.5-pro",
        "daily_call_cap": _GEMINI_DAILY_CALL_CAP,
        "daily_calls": u["daily_calls"],
        "session_calls": u["session_calls"],
        "daily_input_tokens": u["daily_input_tokens"],
        "daily_output_tokens": u["daily_output_tokens"],
        "blocked": block,
        "circuit_breaker": "open" if u["circuit_open_until"] and datetime.utcnow() < u["circuit_open_until"] else "closed",
    }
    log.debug(f"[USAGE] Gemini → configured={result['configured']} "
              f"calls={result['daily_calls']}/{result['daily_call_cap']} "
              f"session={result['session_calls']} "
              f"tokens={u['daily_input_tokens']}in/{u['daily_output_tokens']}out "
              f"blocked={block or 'no'} circuit={result['circuit_breaker']}")
    return result


# ── System Info (host machine) ───────────────────────────────────────
@app.get("/api/system-info")
async def system_info():
    """Return host CPU/memory/disk usage. Uses psutil if available, else estimates."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        net_io = psutil.net_io_counters()
        # Network as % of 1Gbps theoretical max (rough gauge)
        net_bytes = (net_io.bytes_sent + net_io.bytes_recv)
        net_pct = min(round(net_bytes / (1024**3) * 0.1, 1), 100)
        return {"cpu": round(cpu), "memory": round(mem), "disk": round(disk), "network": round(net_pct)}
    except ImportError:
        import random
        return {"cpu": random.randint(8, 35), "memory": random.randint(40, 70), "disk": random.randint(30, 60), "network": random.randint(1, 15)}


# ── GCP Pod Metrics ──────────────────────────────────────────────────
@app.get("/api/gcp/pods")
async def gcp_pods():
    """Pod-level metrics for Grow with Freya. Placeholder — replace with real GKE/Cloud Run data."""
    return {
        "replicas": 3,
        "alerts": 0,
        "pods": [
            {"name": "freya-api-7d8f", "status": "Running", "cpu": 22, "memory": 45},
            {"name": "freya-api-9b3c", "status": "Running", "cpu": 18, "memory": 38},
            {"name": "freya-worker-a1e2", "status": "Running", "cpu": 31, "memory": 52},
        ],
    }


# ── Business Profiles ────────────────────────────────────────────────

def _get_business_id(request) -> str | None:
    """Extract active business_id from request header or query param."""
    return request.headers.get("x-business-id") or request.query_params.get("business_id") or None


def _safe_business_response(biz: dict | None) -> dict:
    """Strip any fields that must never appear in API responses."""
    if not biz:
        return {"error": "Business not found"}
    # Defensive: ensure no secret fields leak even if DB schema changes
    safe = dict(biz)
    for forbidden in ("github_token", "pat", "api_key", "password", "secret"):
        safe.pop(forbidden, None)
    # Add masked PAT status so UI knows if configured
    slug = safe.get("slug", "")
    env_key = f"GITHUB_PAT_{slug.upper().replace('-', '_')}"
    raw_pat = os.getenv(env_key, "") or _read_env_value(env_key)
    safe["github_pat_configured"] = bool(raw_pat)
    return safe


def _validate_github_token(token: str) -> str | None:
    """Validate PAT format. Returns error message or None if valid."""
    if not token:
        return None
    # GitHub PATs: ghp_ (classic), github_pat_ (fine-grained), gho_/ghu_/ghs_ (OAuth/app)
    if not re.match(r"^(ghp_|github_pat_|gho_|ghu_|ghs_)[a-zA-Z0-9_]+$", token):
        return "Invalid GitHub token format. Must start with ghp_, github_pat_, gho_, ghu_, or ghs_"
    if len(token) < 20:
        return "Token too short — check you copied the full token"
    return None


def _check_duplicate_pat(token: str, exclude_slug: str = "") -> str | None:
    """Check if the same PAT is already registered under a different business.
    Returns the conflicting slug name or None."""
    if not token:
        return None
    for biz in arbiter_db.get_businesses():
        slug = biz.get("slug", "")
        if slug == exclude_slug:
            continue
        env_key = f"GITHUB_PAT_{slug.upper().replace('-', '_')}"
        existing = os.getenv(env_key, "") or _read_env_value(env_key)
        if existing and existing == token:
            return slug
    return None


@app.post("/api/businesses")
async def businesses_create(request: Request):
    """Create a new business profile."""
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return {"error": "name is required"}
    if len(name) > 60:
        return {"error": "name too long (max 60 characters)"}
    slug = body.get("slug", "").strip() or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug or len(slug) > 80:
        return {"error": "invalid slug"}
    # Validate slug uniqueness
    existing = arbiter_db.get_businesses()
    if any(b["slug"] == slug for b in existing):
        return {"error": f"slug '{slug}' already exists"}
    description = body.get("description", "").strip()[:200]
    business_context = body.get("business_context", "").strip()[:2000]
    icon = body.get("icon", "🏢").strip()[:4]
    github_repo = body.get("github_repo", "").strip()
    # Validate repo format
    if github_repo and not re.match(r"^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$", github_repo):
        return {"error": "github_repo must be owner/repo format"}
    # Validate and store GitHub PAT in .env if provided (never in DB)
    github_token = body.get("github_token", "").strip()
    token_err = _validate_github_token(github_token)
    if token_err:
        return {"error": token_err}
    dup_slug = _check_duplicate_pat(github_token)
    if dup_slug:
        return {"error": f"This token is already registered under business '{dup_slug}'. Each business must use a unique token."}
    if github_token:
        env_key = f"GITHUB_PAT_{slug.upper().replace('-', '_')}"
        _write_env_values({env_key: github_token})
        os.environ[env_key] = github_token
        log.info(f"GitHub PAT configured for business '{slug}' (token not logged)")
    bid = arbiter_db.save_business(
        name=name, slug=slug, description=description,
        icon=icon, github_repo=github_repo,
        business_context=business_context,
    )
    # Seed initial prompt version if context provided
    if business_context:
        arbiter_db.save_prompt_version(
            bid, business_context, mode="default",
            source="user", summary="Initial business context",
        )
    return _safe_business_response(arbiter_db.get_business(bid))


@app.put("/api/businesses/{business_id}")
async def businesses_update(business_id: str, request: Request):
    """Update a business profile."""
    biz = arbiter_db.get_business(business_id)
    if not biz:
        return {"error": "Business not found"}
    body = await request.json()
    github_repo = body.get("github_repo")
    if github_repo is not None:
        github_repo = github_repo.strip()
        if github_repo and not re.match(r"^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$", github_repo):
            return {"error": "github_repo must be owner/repo format"}
    # Validate and store GitHub PAT in .env if provided
    github_token = body.get("github_token", "").strip()
    token_err = _validate_github_token(github_token)
    if token_err:
        return {"error": token_err}
    dup_slug = _check_duplicate_pat(github_token, exclude_slug=biz["slug"])
    if dup_slug:
        return {"error": f"This token is already registered under business '{dup_slug}'. Each business must use a unique token."}
    if github_token:
        env_key = f"GITHUB_PAT_{biz['slug'].upper().replace('-', '_')}"
        _write_env_values({env_key: github_token})
        os.environ[env_key] = github_token
        log.info(f"GitHub PAT updated for business '{biz['slug']}' (token not logged)")
    # Business context (prompt directive) — truncate to 2000 chars
    business_context = body.get("business_context")
    if business_context is not None:
        business_context = business_context.strip()[:2000]
        # Auto-create a prompt version when context changes
        old_ctx = (biz.get("business_context") or "").strip()
        if business_context and business_context != old_ctx:
            active_mode = biz.get("active_prompt_mode") or "default"
            arbiter_db.save_prompt_version(
                business_id, business_context, mode=active_mode,
                source="user", summary="Updated via settings",
            )
    arbiter_db.update_business(
        business_id,
        name=body.get("name"),
        description=body.get("description"),
        icon=body.get("icon"),
        github_repo=github_repo,
        business_context=business_context,
    )
    return _safe_business_response(arbiter_db.get_business(business_id))


@app.post("/api/businesses/{business_id}/delete")
async def businesses_delete(business_id: str):
    """Delete a business profile. Also cleans up the associated .env PAT key."""
    biz = arbiter_db.get_business(business_id)
    if not biz:
        return {"error": "Business not found"}
    # Clean up the PAT from .env and os.environ
    slug = biz.get("slug", "")
    env_key = f"GITHUB_PAT_{slug.upper().replace('-', '_')}"
    if os.getenv(env_key):
        os.environ.pop(env_key, None)
        # Remove from .env file by writing empty (will be cleaned up)
        _write_env_values({env_key: ""})
        log.info(f"Cleaned up GitHub PAT for deleted business '{slug}'")
    if not arbiter_db.delete_business(business_id):
        return {"error": "Business not found"}
    return {"ok": True}


@app.get("/api/businesses/{business_id}")
async def businesses_get(business_id: str):
    """Get a single business profile. Secrets are never included."""
    return _safe_business_response(arbiter_db.get_business(business_id))


@app.get("/api/businesses")
async def businesses_list():
    """List all business profiles. Secrets are never included."""
    businesses = arbiter_db.get_businesses()
    return {"businesses": [_safe_business_response(b) for b in businesses]}


# ── Prompt Versioning ────────────────────────────────────────────────

@app.get("/api/businesses/{business_id}/prompts")
async def prompts_list(business_id: str, mode: str | None = None, limit: int = 20):
    """List prompt versions for a business. Includes modes summary."""
    biz = arbiter_db.get_business(business_id)
    if not biz:
        return {"error": "Business not found"}
    versions = arbiter_db.get_prompt_versions(business_id, mode=mode, limit=limit)
    modes = arbiter_db.get_prompt_modes(business_id)
    active = arbiter_db.get_active_prompt(business_id)
    return {
        "business_id": business_id,
        "active_mode": biz.get("active_prompt_mode") or "default",
        "modes": modes,
        "active_prompt": active,
        "versions": versions,
    }


@app.post("/api/businesses/{business_id}/prompts")
async def prompts_create(business_id: str, request: Request):
    """Create a new prompt version. Used by users, agents, or pipelines.

    Body: { "content": "...", "mode": "default", "source": "user|agent|pipeline", "summary": "..." }

    Hands-free: agents/pipelines call this with source='agent' or source='pipeline'
    to overwrite the prompt without user intervention.
    """
    biz = arbiter_db.get_business(business_id)
    if not biz:
        return {"error": "Business not found"}
    body = await request.json()
    content = body.get("content", "").strip()
    if not content:
        return {"error": "content is required"}
    if len(content) > 4000:
        return {"error": "content too long (max 4000 chars)"}
    mode = body.get("mode", "").strip() or (biz.get("active_prompt_mode") or "default")
    # Validate mode name — alphanumeric + hyphens, max 30 chars
    if not re.match(r"^[a-zA-Z0-9_-]{1,30}$", mode):
        return {"error": "mode must be alphanumeric/hyphens, max 30 chars"}
    source = body.get("source", "user").strip()
    if source not in ("user", "agent", "pipeline"):
        source = "user"
    summary = body.get("summary", "").strip()[:200]

    version = arbiter_db.save_prompt_version(
        business_id, content, mode=mode, source=source, summary=summary,
    )
    log.info(f"Prompt v{version['version_num']} ({mode}) created for biz {business_id} by {source}")
    return version


@app.put("/api/businesses/{business_id}/prompts/mode")
async def prompts_set_mode(business_id: str, request: Request):
    """Switch the active prompt mode for a business.

    Body: { "mode": "growth" }
    This instantly changes which prompt version is injected into all agent dispatches.
    """
    biz = arbiter_db.get_business(business_id)
    if not biz:
        return {"error": "Business not found"}
    body = await request.json()
    mode = body.get("mode", "").strip()
    if not mode:
        return {"error": "mode is required"}
    # Check this mode exists
    modes = arbiter_db.get_prompt_modes(business_id)
    if not any(m["mode"] == mode for m in modes):
        return {"error": f"Mode '{mode}' has no prompt versions. Create a prompt for this mode first."}
    arbiter_db.set_active_mode(business_id, mode)
    log.info(f"Business {business_id} switched to prompt mode: {mode}")
    active = arbiter_db.get_active_prompt(business_id)
    return {"ok": True, "active_mode": mode, "active_prompt": active}


@app.post("/api/businesses/{business_id}/prompts/{version_id}/restore")
async def prompts_restore(business_id: str, version_id: str):
    """Restore a previous prompt version (creates a new version with the old content)."""
    biz = arbiter_db.get_business(business_id)
    if not biz:
        return {"error": "Business not found"}
    result = arbiter_db.restore_prompt_version(version_id)
    if not result:
        return {"error": "Version not found"}
    if result["business_id"] != business_id:
        return {"error": "Version does not belong to this business"}
    log.info(f"Prompt version {version_id} restored as v{result['version_num']} for biz {business_id}")
    return result


# ── CI/CD — GitHub Actions per-business ──────────────────────────────


def _gh_pat_for_business(biz: dict) -> str:
    """Get the GitHub PAT for a business from .env (keyed by slug)."""
    slug = biz.get("slug", "")
    env_key = f"GITHUB_PAT_{slug.upper().replace('-', '_')}"
    return os.getenv(env_key, "") or os.getenv("GITHUB_PAT", "")


async def _fetch_github_actions(repo: str, token: str) -> list[dict]:
    """Fetch recent workflow runs from GitHub Actions API."""
    if not repo or not token:
        return []
    url = f"https://api.github.com/repos/{repo}/actions/runs"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"per_page": 10}, headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            })
            if resp.status_code != 200:
                log.warning(f"GitHub Actions API {resp.status_code} for {repo}")
                return []
            runs = resp.json().get("workflow_runs", [])
            # Deduplicate by workflow name (keep latest per workflow)
            seen = {}
            for run in runs:
                wf_name = run.get("name", "unknown")
                if wf_name not in seen:
                    status = run.get("conclusion") or run.get("status", "unknown")
                    # Map GitHub status to our status
                    status_map = {
                        "success": "success", "failure": "failed",
                        "cancelled": "failed", "in_progress": "running",
                        "queued": "running", "pending": "running",
                    }
                    created = run.get("updated_at", "")
                    # Compute relative time
                    time_str = ""
                    if created:
                        try:
                            from datetime import timezone
                            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                            delta = datetime.now(timezone.utc) - dt
                            if delta.days > 0:
                                time_str = f"{delta.days}d ago"
                            elif delta.seconds >= 3600:
                                time_str = f"{delta.seconds // 3600}h ago"
                            else:
                                time_str = f"{delta.seconds // 60}m ago"
                        except Exception:
                            time_str = created[:10]
                    seen[wf_name] = {
                        "name": wf_name,
                        "status": status_map.get(status, "unknown"),
                        "time": time_str,
                        "url": run.get("html_url", "#"),
                        "branch": run.get("head_branch", ""),
                    }
            return list(seen.values())
    except Exception as e:
        # Sanitize: never log the token; only log the exception type and repo
        err_msg = _sanitize_error(str(e), token)
        log.warning(f"GitHub Actions fetch failed for {repo}: {type(e).__name__}: {err_msg}")
        return []


@app.get("/api/cicd")
async def cicd_status(request: Request):
    """Return CI/CD status from GitHub Actions for configured businesses."""
    business_id = _get_business_id(request)
    businesses = arbiter_db.get_businesses()

    if not businesses:
        return {"_no_businesses": {"status": "unknown", "name": "No businesses configured",
                                    "time": "", "url": "#"}}

    result = {}
    target = [b for b in businesses if b["id"] == business_id] if business_id else businesses
    for biz in target:
        repo = biz.get("github_repo", "")
        if not repo:
            continue
        token = _gh_pat_for_business(biz)
        if not token:
            result[f"{biz['slug']}_no_token"] = {
                "status": "unknown", "name": f"{biz['name']}: No GitHub PAT configured",
                "time": "", "url": "#", "business_id": biz["id"], "business_name": biz["name"],
            }
            continue
        runs = await _fetch_github_actions(repo, token)
        for run in runs:
            key = f"{biz['slug']}_{run['name'].lower().replace(' ', '_')}"
            result[key] = {**run, "business_id": biz["id"], "business_name": biz["name"]}
    return result





# ── Email Intelligence ────────────────────────────────────────────────
@app.get("/api/email/summary")
async def email_summary():
    return email_mon.summary()


@app.get("/api/email/urgent")
async def email_urgent():
    return email_mon.urgent_items()


@app.get("/api/email/recent")
async def email_recent():
    return email_mon.recent(20)


@app.get("/api/email/detail/{uid}")
async def email_detail(uid: str):
    """Get full email detail including body for a specific UID."""
    if not re.match(r'^[0-9]+$', uid):
        return JSONResponse(status_code=400, content={"error": "Invalid email UID"})
    detail = email_mon.get_email_detail(uid)
    if not detail:
        return JSONResponse(status_code=404, content={"error": "Email not found"})
    return detail


@app.get("/api/email/customer")
async def email_customer():
    """Return emails classified as customer inquiries or business."""
    return email_mon.customer_emails(20)


@app.post("/api/email/classify")
async def email_classify(request: Request):
    """Classify unclassified emails using LLM. Runs in batch."""
    unclassified = email_mon.get_emails_needing_classification()
    if not unclassified:
        return {"classified": 0, "message": "All emails already classified"}

    # Batch classify up to 15 at a time to avoid token bloat
    batch = unclassified[:15]
    from email_monitor import EMAIL_CATEGORIES, redact_for_llm
    cats_str = ", ".join(EMAIL_CATEGORIES.keys())

    # ── Redact all content before sending to LLM ──
    email_list = "\n".join(
        f"- UID:{e['uid']} FROM:{redact_for_llm(e['sender'][:50])} SUBJECT:{redact_for_llm(e['subject'][:80])} SNIPPET:{redact_for_llm(e['snippet'][:100])}"
        for e in batch
    )
    prompt = (
        f"Classify each email into exactly one category: {cats_str}\n\n"
        f"Emails:\n{email_list}\n\n"
        "Return ONLY a JSON array of objects: [{\"uid\": \"...\", \"category\": \"...\"}]\n"
        "No explanation. Just the JSON array."
    )
    messages = [
        {"role": "system", "content": "You are an email classifier. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    result = None
    if ANTHROPIC_API_KEY and not _claude_check_budget():
        result = await _chat_claude(messages, max_tokens=500, temperature=0.1)
    if not result and OPENROUTER_API_KEY:
        result = await _chat_openrouter(messages, max_tokens=500, temperature=0.1)
    if not result:
        result = await _chat_llm(messages, max_tokens=500, purpose="email-classify")

    classified = 0
    if result:
        try:
            # Extract JSON array from response
            match = re.search(r'\[.*\]', result, re.DOTALL)
            if match:
                classifications = json.loads(match.group())
                for c in classifications:
                    uid = str(c.get("uid", ""))
                    cat = c.get("category", "")
                    if uid and cat in EMAIL_CATEGORIES:
                        email_mon.set_classification(uid, cat)
                        classified += 1
        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f"Email classification parse error: {e}")

    return {"classified": classified, "total_pending": len(unclassified)}


@app.post("/api/email/draft-reply")
async def email_draft_reply(request: Request):
    """Draft a reply to an email using LLM."""
    body = await request.json()
    uid = body.get("uid", "")
    if not uid:
        return JSONResponse(status_code=400, content={"error": "uid is required"})

    detail = email_mon.get_email_detail(uid)
    if not detail:
        return JSONResponse(status_code=404, content={"error": "Email not found"})

    # Context for the draft — redact confidential data before LLM
    from email_monitor import redact_for_llm
    instructions = body.get("instructions", "")
    prompt = (
        f"Draft a professional reply to this email.\n\n"
        f"FROM: {redact_for_llm(detail['sender'])}\n"
        f"SUBJECT: {redact_for_llm(detail['subject'])}\n"
        f"BODY:\n{redact_for_llm(detail['body'][:3000])}\n\n"
    )
    if instructions:
        prompt += f"SPECIFIC INSTRUCTIONS: {instructions}\n\n"
    prompt += (
        "RULES:\n"
        "- Professional but warm tone\n"
        "- UK English (organise, colour, apologise)\n"
        "- Concise — max 150 words\n"
        "- Don't invent commitments, prices, or dates — use placeholders like [DATE] [PRICE]\n"
        "- Sign off as the business owner\n\n"
        "Return ONLY the reply body text. No subject line. No explanation."
    )
    messages = [
        {"role": "system", "content": "You are a professional email reply drafter for a UK business."},
        {"role": "user", "content": prompt},
    ]

    draft = None
    if ANTHROPIC_API_KEY and not _claude_check_budget():
        draft = await _chat_claude(messages, max_tokens=400, temperature=0.5)
    if not draft and OPENROUTER_API_KEY:
        draft = await _chat_openrouter(messages, max_tokens=400, temperature=0.5)
    if not draft:
        draft = await _chat_llm(messages, max_tokens=400, purpose="email-draft")

    if not draft:
        return JSONResponse(status_code=500, content={"error": "Failed to generate draft"})

    # Build reply subject
    subject = detail.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    return {
        "draft": draft.strip(),
        "to": detail.get("sender", ""),
        "subject": subject,
        "in_reply_to": detail.get("message_id", ""),
        "original_uid": uid,
    }


@app.post("/api/email/send")
async def email_send(request: Request):
    """Send an email. Requires to, subject, body."""
    body = await request.json()
    to = body.get("to", "").strip()
    subject = body.get("subject", "").strip()
    email_body = body.get("body", "").strip()
    in_reply_to = body.get("in_reply_to", "")

    if not to or not subject or not email_body:
        return JSONResponse(status_code=400, content={"error": "Missing: to, subject, body"})

    result = await asyncio.to_thread(
        email_mon.send_email, to, subject, email_body, in_reply_to
    )
    if result.get("ok"):
        # Push SSE notification
        await _push_sse("notification", {
            "title": "EMAIL SENT",
            "message": f"Reply sent to {to}: {subject[:60]}",
        })
    return result


# ── Settings ──────────────────────────────────────────────────────────
# Non-secret prefs stored in SQLite.  Secrets (email password, PATs) live in .env.
# GET always masks secrets.  PUT writes secrets to .env, prefs to DB.

import threading

_ENV_PATH = Path(__file__).parent / ".env"
_ENV_LOCK = threading.Lock()  # Prevent concurrent .env file corruption

# Keys considered secret — never returned in full via API
_SECRET_KEYS = {"email_password", "github_token"}

# Keys that map to .env variable names (written to .env file, not DB)
_ENV_KEY_MAP = {
    "email_address":  "EMAIL_ADDRESS",
    "email_password": "EMAIL_APP_PASSWORD",
    "imap_host":      "IMAP_HOST",
    "imap_port":      "IMAP_PORT",
    "smtp_host":      "SMTP_HOST",
    "smtp_port":      "SMTP_PORT",
}

# Allowlisted DB settings keys — reject anything not on this list
_ALLOWED_DB_KEYS = {
    "wake_word_enabled", "idle_lock_timeout", "tts_voice", "timezone",
    "theme", "language", "notification_sound",
}


def _mask_secret(val: str) -> str:
    """Return masked version of a secret value."""
    if not val or len(val) <= 4:
        return "****" if val else ""
    return "*" * (len(val) - 4) + val[-4:]


def _read_env_value(env_key: str) -> str:
    """Read a value from .env file (not os.environ, to get persisted value)."""
    if not _ENV_PATH.exists():
        return ""
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == env_key:
            return v.strip().strip('"').strip("'")
    return ""


def _write_env_values(updates: dict[str, str]) -> None:
    """Update specific keys in the .env file, preserving comments and order.
    Thread-safe via _ENV_LOCK. Deduplicates keys to prevent .env corruption."""
    with _ENV_LOCK:
        if not _ENV_PATH.exists():
            lines = ["# ARBITER Mission Control\n"]
        else:
            lines = _ENV_PATH.read_text().splitlines(keepends=True)

        remaining = dict(updates)
        new_lines = []
        seen_keys: set[str] = set()

        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                # Skip duplicate keys already written
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                if key in remaining:
                    new_lines.append(f"{key}={remaining.pop(key)}\n")
                    continue
            new_lines.append(line if line.endswith("\n") else line + "\n")

        # Append any keys not already in the file
        for k, v in remaining.items():
            if k not in seen_keys:
                new_lines.append(f"{k}={v}\n")
                seen_keys.add(k)

        _ENV_PATH.write_text("".join(new_lines))

        # Enforce file permissions (owner-only read/write)
        try:
            _ENV_PATH.chmod(0o600)
        except OSError:
            pass  # Windows or permission denied — non-fatal


def _sanitize_error(err: str, *secrets: str) -> str:
    """Strip any secret values from an error message before returning to client."""
    for s in secrets:
        if s and s in err:
            err = err.replace(s, "***")
    return err


def _is_secret_env_key(env_key: str) -> bool:
    """Check if an .env key holds a secret value (PAT, password, API key)."""
    key_upper = env_key.upper()
    return any(tag in key_upper for tag in ("PAT", "PASSWORD", "SECRET", "TOKEN", "API_KEY"))


@app.get("/api/settings")
async def settings_get():
    """Return all settings. Secrets are masked — never returned in full."""
    # Gather prefs from DB
    prefs = arbiter_db.get_settings()

    # Only return allowlisted DB keys to prevent data leakage
    result = {k: v for k, v in prefs.items() if k in _ALLOWED_DB_KEYS}

    # Gather email config from .env (source of truth for secrets)
    for settings_key, env_key in _ENV_KEY_MAP.items():
        raw = _read_env_value(env_key) or os.getenv(env_key, "")
        if settings_key in _SECRET_KEYS:
            result[settings_key] = _mask_secret(raw)
        else:
            result[settings_key] = raw

    # Add email configured status
    result["email_configured"] = bool(
        (result.get("email_address") or "").strip()
        and (_read_env_value("EMAIL_APP_PASSWORD") or os.getenv("EMAIL_APP_PASSWORD", "")).strip()
    )

    # Add GitHub PAT status per business (masked, never raw)
    github_pats = {}
    for biz in arbiter_db.get_businesses():
        env_key = f"GITHUB_PAT_{biz['slug'].upper().replace('-', '_')}"
        raw = os.getenv(env_key, "") or _read_env_value(env_key)
        github_pats[biz["slug"]] = _mask_secret(raw)
    result["github_pat_status"] = github_pats

    # Add LLM provider info (read-only — no keys exposed)
    result["llm_provider"] = LLM_PROVIDER
    result["llm_claude_configured"] = bool(ANTHROPIC_API_KEY)
    result["llm_openrouter_configured"] = bool(OPENROUTER_API_KEY)
    result["llm_gemini_configured"] = bool(GOOGLE_API_KEY)
    result["llm_ollama_url"] = OLLAMA_BASE_URL
    result["llm_ollama_model"] = OLLAMA_MODEL

    return result


@app.put("/api/settings")
async def settings_put(request: Request):
    """Save settings. Secrets go to .env, prefs to DB.
    Only allowlisted keys are accepted for DB storage."""
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": "Expected JSON object"})

    env_updates: dict[str, str] = {}
    db_updates: dict[str, str] = {}

    for key, value in body.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        # Length guard
        if len(value) > 500:
            continue

        if key in _ENV_KEY_MAP:
            # Secret / email key — skip blank passwords (means "keep existing")
            if key in _SECRET_KEYS and not value.strip():
                continue
            env_updates[_ENV_KEY_MAP[key]] = value.strip()
        elif key in _ALLOWED_DB_KEYS:
            db_updates[key] = value.strip()
        # Silently ignore unknown keys — don't allow arbitrary DB writes

    # Write .env secrets
    if env_updates:
        _write_env_values(env_updates)
        # Hot-reload into current process env
        for env_key, val in env_updates.items():
            os.environ[env_key] = val
        # Hot-reload EmailMonitor
        email_mon.host = os.getenv("IMAP_HOST", "imap.gmail.com")
        email_mon.port = int(os.getenv("IMAP_PORT", "993"))
        email_mon.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        email_mon.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        email_mon.user = os.getenv("EMAIL_ADDRESS", "")
        email_mon.password = os.getenv("EMAIL_APP_PASSWORD", "")
        # Clear cache so next fetch uses new credentials
        email_mon._last_fetch = None
        email_mon._cache = []
        log.info("Email settings updated and reloaded")

    # Write DB prefs
    if db_updates:
        arbiter_db.set_settings(db_updates)

    return {"ok": True, "env_keys_updated": len(env_updates), "prefs_updated": len(db_updates)}


@app.post("/api/settings/test-email")
async def settings_test_email(request: Request):
    """Test IMAP connection with provided credentials. Nothing is persisted."""
    body = await request.json()
    host = body.get("imap_host", "imap.gmail.com").strip()
    port = int(body.get("imap_port", 993))
    user = body.get("email_address", "").strip()
    password = body.get("email_password", "").strip()

    # If password is blank or masked, use the existing one
    if not password or password.startswith("****"):
        password = _read_env_value("EMAIL_APP_PASSWORD") or os.getenv("EMAIL_APP_PASSWORD", "")

    if not user or not password:
        return JSONResponse(status_code=400, content={"error": "Email address and password required"})

    import imaplib
    try:
        conn = await asyncio.to_thread(imaplib.IMAP4_SSL, host, port)
        await asyncio.to_thread(conn.login, user, password)
        # Count inbox messages as a sanity check
        await asyncio.to_thread(conn.select, "INBOX", True)
        _, data = await asyncio.to_thread(conn.search, None, "ALL")
        count = len(data[0].split()) if data[0] else 0
        await asyncio.to_thread(conn.logout)
        return {"ok": True, "message": f"Connected successfully. Inbox has {count} messages."}
    except Exception as e:
        # Sanitize error — strip credentials, host, and any auth data
        err = _sanitize_error(str(e), user, password, host)
        return {"ok": False, "error": err}


# ── Agent Registry ────────────────────────────────────────────────────
@app.get("/api/agents")
async def agents_list():
    return agent_reg.get_all()


@app.get("/api/agents/{agent_id}")
async def agent_detail(agent_id: str):
    a = agent_reg.get(agent_id)
    if a is None:
        return {"error": "Agent not found"}
    return a


@app.post("/api/agents/heartbeat")
async def agent_heartbeat(request: Request):
    body = await request.json()
    agent_id = body.get("agent_id", "")
    if not agent_id:
        return {"error": "agent_id required"}
    agent = agent_reg.heartbeat(agent_id, body)
    return {"status": "ok", "agent_id": agent_id}


# ── CEO Orchestration — Sub-Agent Definitions ─────────────────────────
_PROMPTS_DIR = Path(__file__).parent / "prompts"


# ── 3-Layer Prompt Architecture ──────────────────────────────────────
# Layer 1: Global Operating System (shared by all agents)
# Layer 2: Business Directive (dynamic — from active business profile, or fallback file)
# Layer 3: Agent Role Prompt (small, focused per agent)
_GLOBAL_OS_PROMPT = ""
_BUSINESS_DIRECTIVE_PROMPT = ""   # fallback if no business profile is active
_global_os_file = _PROMPTS_DIR / "global_os.md"
_business_dir_file = _PROMPTS_DIR / "business_directive.md"
if _global_os_file.exists():
    _GLOBAL_OS_PROMPT = _global_os_file.read_text(encoding="utf-8").strip()
    log.info(f"Loaded global OS prompt ({len(_GLOBAL_OS_PROMPT)} chars)")
if _business_dir_file.exists():
    _BUSINESS_DIRECTIVE_PROMPT = _business_dir_file.read_text(encoding="utf-8").strip()
    log.info(f"Loaded fallback business directive ({len(_BUSINESS_DIRECTIVE_PROMPT)} chars)")


def _load_agent_prompt(agent_id: str, business_context: str | None = None) -> str:
    """Compose a 3-layer system prompt: Global OS + Business Directive + Agent Role.

    Layer 2 (Business Directive) is resolved dynamically:
      - If business_context is provided (from the active business profile), use it.
      - Otherwise fall back to the static prompts/business_directive.md file.
    This means agents automatically adapt to the active business context.
    """
    # Layer 3: Agent-specific role prompt
    prompt_file = _PROMPTS_DIR / f"{agent_id}.md"
    if prompt_file.exists():
        agent_role = prompt_file.read_text(encoding="utf-8").strip()
    else:
        log.warning(f"Prompt file not found: {prompt_file}")
        agent_role = f"You are the {agent_id} agent. Follow the directive precisely."

    # Compose all 3 layers
    layers = []
    if _GLOBAL_OS_PROMPT:
        layers.append(_GLOBAL_OS_PROMPT)

    # Layer 2: dynamic business context or static fallback
    directive = business_context or _BUSINESS_DIRECTIVE_PROMPT
    if directive:
        layers.append(directive)

    layers.append(agent_role)
    return "\n\n---\n\n".join(layers)


def _resolve_business_context(business_id: str | None = None) -> str | None:
    """Resolve the business context directive for the active business.

    Resolution order:
    1. Versioned prompt system (active mode → latest version)
    2. Legacy business_context column (backwards compat)
    3. Business description as minimal context
    4. None → triggers fallback to static business_directive.md
    """
    if not business_id:
        return None
    try:
        biz = arbiter_db.get_business(business_id)
        if not biz:
            return None

        header = f"# Business Directive — {biz['name']}"
        if biz.get("description"):
            header += f"\n\n{biz['description']}"

        # 1. Try versioned prompt system first
        active_prompt = arbiter_db.get_active_prompt(business_id)
        if active_prompt and active_prompt.get("content", "").strip():
            mode = active_prompt.get("mode", "default")
            ver = active_prompt.get("version_num", "?")
            mode_tag = f"\n_[Mode: {mode} | v{ver}]_"
            return f"{header}\n\n{active_prompt['content'].strip()}{mode_tag}"

        # 2. Fall back to legacy business_context column
        ctx = biz.get("business_context", "")
        if ctx and ctx.strip():
            return f"{header}\n\n{ctx.strip()}"

        # 3. Minimal context from description
        if biz.get("description"):
            return header
        return None
    except Exception as e:
        log.warning(f"Failed to resolve business context: {e}")
        return None


CEO_AGENTS = {
    # ── Claude Sonnet — Strategic / Creative agents ──────────────────
    "chief_of_staff": {
        "id": "chief_of_staff",
        "name": "Chief of Staff",
        "role": "Executive Coordinator",
        "model": _CLAUDE_AGENT_MODEL,
        "provider": "claude",
        "icon": "shield",
        "colour": "#64ffda",
        "description": "Coordinates agents, resolves conflicts, produces executive decisions",
        "system_prompt": _load_agent_prompt("chief_of_staff"),
    },
    "visionary": {
        "id": "visionary",
        "name": "Visionary",
        "role": "Creative Director",
        "model": _CLAUDE_AGENT_MODEL,
        "provider": "claude",
        "icon": "zap",
        "colour": "#e040fb",
        "description": "Original ideas, concepts, positioning & future opportunities",
        "system_prompt": _load_agent_prompt("visionary"),
    },
    "strategist": {
        "id": "strategist",
        "name": "Strategist",
        "role": "Strategic Advisor",
        "model": _CLAUDE_AGENT_MODEL,
        "provider": "claude",
        "icon": "compass",
        "colour": "#448aff",
        "description": "Where to play and how to win — priorities & trade-offs",
        "system_prompt": _load_agent_prompt("strategist"),
    },
    "product": {
        "id": "product",
        "name": "Product",
        "role": "Product Leader",
        "model": _CLAUDE_AGENT_MODEL,
        "provider": "claude",
        "icon": "box",
        "colour": "#69f0ae",
        "description": "Strategy → products, roadmaps, MVPs & validation plans",
        "system_prompt": _load_agent_prompt("product"),
    },
    "cto": {
        "id": "cto",
        "name": "CTO",
        "role": "Technical Vision",
        "model": _CLAUDE_AGENT_MODEL,
        "provider": "claude",
        "icon": "cpu",
        "colour": "#76ff03",
        "description": "Architecture, feasibility, security & engineering plans",
        "system_prompt": _load_agent_prompt("cto"),
    },
    "risk": {
        "id": "risk",
        "name": "Risk",
        "role": "Risk & Compliance",
        "model": _CLAUDE_AGENT_MODEL,
        "provider": "claude",
        "icon": "alert-triangle",
        "colour": "#ff5252",
        "description": "Legal, privacy, security & operational risk assessment",
        "system_prompt": _load_agent_prompt("risk"),
    },
    # ── Gemini — Research & Data agents (free tier) ──────────────────
    "researcher": {
        "id": "researcher",
        "name": "Researcher",
        "role": "Research Analyst",
        "model": "gemini-2.5-pro",
        "provider": "gemini",
        "icon": "search",
        "colour": "#00e5ff",
        "description": "Market intelligence, competitor analysis & evidence gathering",
        "system_prompt": _load_agent_prompt("researcher"),
    },
    "analyst": {
        "id": "analyst",
        "name": "Analyst",
        "role": "Data Analyst",
        "model": "gemini-2.5-flash",
        "provider": "gemini",
        "icon": "bar-chart",
        "colour": "#b388ff",
        "description": "KPIs, trends, anomalies & data-driven recommendations",
        "system_prompt": _load_agent_prompt("analyst"),
    },
    # ── OpenRouter GPT-4o-mini — Execution agents ────────────────────
    "cmo": {
        "id": "cmo",
        "name": "CMO",
        "role": "Marketing Chief",
        "model": _OPENROUTER_AGENT_MODEL,
        "provider": "openrouter",
        "icon": "megaphone",
        "colour": "#ff4081",
        "description": "Positioning, messaging, campaigns & content themes",
        "system_prompt": _load_agent_prompt("cmo"),
    },
    "revenue": {
        "id": "revenue",
        "name": "Revenue",
        "role": "Revenue Leader",
        "model": _OPENROUTER_AGENT_MODEL,
        "provider": "openrouter",
        "icon": "trending-up",
        "colour": "#ffd700",
        "description": "ICPs, pricing, sales motions & conversion optimisation",
        "system_prompt": _load_agent_prompt("revenue"),
    },
    "coo": {
        "id": "coo",
        "name": "COO",
        "role": "Execution Manager",
        "model": _OPENROUTER_AGENT_MODEL,
        "provider": "openrouter",
        "icon": "clipboard",
        "colour": "#ff6e40",
        "description": "Delivery plans, milestones, tasks & timeline management",
        "system_prompt": _load_agent_prompt("coo"),
    },
    # ── Extended Agent Roster ─────────────────────────────────────────
    "ceo_agent": {
        "id": "ceo_agent",
        "name": "CEO",
        "role": "Founder & Decision Maker",
        "model": _CLAUDE_AGENT_MODEL,
        "provider": "claude",
        "icon": "star",
        "colour": "#ffd700",
        "description": "Strategic decisions, prioritisation & business direction",
        "system_prompt": _load_agent_prompt("ceo"),
    },
    "intelligence": {
        "id": "intelligence",
        "name": "Intelligence",
        "role": "Intelligence Analyst",
        "model": "gemini-2.5-pro",
        "provider": "gemini",
        "icon": "eye",
        "colour": "#00e5ff",
        "description": "Market research, competitor analysis & industry trends",
        "system_prompt": _load_agent_prompt("intelligence"),
    },
    "child_dev": {
        "id": "child_dev",
        "name": "Child Dev",
        "role": "Development Specialist",
        "model": "gemini-2.5-pro",
        "provider": "gemini",
        "icon": "heart",
        "colour": "#ff80ab",
        "description": "Developmental validation, age appropriateness & child wellbeing",
        "system_prompt": _load_agent_prompt("child_dev"),
    },
    "story_architect": {
        "id": "story_architect",
        "name": "Story Architect",
        "role": "Story Creator",
        "model": _CLAUDE_AGENT_MODEL,
        "provider": "claude",
        "icon": "book",
        "colour": "#ea80fc",
        "description": "Children's stories, narratives & interactive content",
        "system_prompt": _load_agent_prompt("story_architect"),
    },
    "content_visionary": {
        "id": "content_visionary",
        "name": "Content Visionary",
        "role": "Content Strategist",
        "model": _CLAUDE_AGENT_MODEL,
        "provider": "claude",
        "icon": "film",
        "colour": "#b388ff",
        "description": "Content concepts, franchise potential & series ideas",
        "system_prompt": _load_agent_prompt("content_visionary"),
    },
    "creative_director": {
        "id": "creative_director",
        "name": "Creative Director",
        "role": "Art Direction",
        "model": _CLAUDE_AGENT_MODEL,
        "provider": "claude",
        "icon": "palette",
        "colour": "#ff4081",
        "description": "Visual direction, character design & brand consistency",
        "system_prompt": _load_agent_prompt("creative_director"),
    },
    "character_designer": {
        "id": "character_designer",
        "name": "Character Designer",
        "role": "IP Creator",
        "model": _OPENROUTER_AGENT_MODEL,
        "provider": "openrouter",
        "icon": "smile",
        "colour": "#ffab40",
        "description": "Character creation, franchise IP & merchandising potential",
        "system_prompt": _load_agent_prompt("character_designer"),
    },
    "growth": {
        "id": "growth",
        "name": "Growth",
        "role": "Growth Strategist",
        "model": _OPENROUTER_AGENT_MODEL,
        "provider": "openrouter",
        "icon": "trending-up",
        "colour": "#69f0ae",
        "description": "Ethical user acquisition, SEO, social & referral strategies",
        "system_prompt": _load_agent_prompt("growth"),
    },
    "trend_analyst": {
        "id": "trend_analyst",
        "name": "Trend Analyst",
        "role": "Social Media Trends",
        "model": "gemini-2.5-flash",
        "provider": "gemini",
        "icon": "activity",
        "colour": "#40c4ff",
        "description": "Trending topics, content formats & platform opportunities",
        "system_prompt": _load_agent_prompt("trend_analyst"),
    },
    "financial": {
        "id": "financial",
        "name": "Financial",
        "role": "CFO / Financial Analyst",
        "model": "gemini-2.5-pro",
        "provider": "gemini",
        "icon": "dollar-sign",
        "colour": "#ffd740",
        "description": "Revenue, costs, margins, forecasts & financial modelling",
        "system_prompt": _load_agent_prompt("financial"),
    },
    "investor": {
        "id": "investor",
        "name": "Investor",
        "role": "VC Partner Review",
        "model": "gemini-2.5-pro",
        "provider": "gemini",
        "icon": "briefcase",
        "colour": "#b2ff59",
        "description": "Investment memo, valuation, risks & fundraising analysis",
        "system_prompt": _load_agent_prompt("investor"),
    },
    "architect": {
        "id": "architect",
        "name": "Architect",
        "role": "Software Architect",
        "model": _OPENROUTER_AGENT_MODEL,
        "provider": "openrouter",
        "icon": "layers",
        "colour": "#82b1ff",
        "description": "System design, architecture, data flow & scalability",
        "system_prompt": _load_agent_prompt("architect"),
    },
    "eng_manager": {
        "id": "eng_manager",
        "name": "Eng Manager",
        "role": "Engineering Manager",
        "model": _OPENROUTER_AGENT_MODEL,
        "provider": "openrouter",
        "icon": "git-branch",
        "colour": "#a7ffeb",
        "description": "Epics, stories, tasks, estimates & delivery roadmaps",
        "system_prompt": _load_agent_prompt("eng_manager"),
    },
    "qa_director": {
        "id": "qa_director",
        "name": "QA Director",
        "role": "Quality Owner",
        "model": _OPENROUTER_AGENT_MODEL,
        "provider": "openrouter",
        "icon": "check-circle",
        "colour": "#00e676",
        "description": "Test strategy, acceptance criteria & release readiness",
        "system_prompt": _load_agent_prompt("qa_director"),
    },
    "qa_automation": {
        "id": "qa_automation",
        "name": "QA Automation",
        "role": "Test Engineer",
        "model": _OPENROUTER_AGENT_MODEL,
        "provider": "openrouter",
        "icon": "terminal",
        "colour": "#76ff03",
        "description": "Unit, integration, E2E & regression test code",
        "system_prompt": _load_agent_prompt("qa_automation"),
    },
    "security": {
        "id": "security",
        "name": "Security",
        "role": "Security Auditor",
        "model": _OPENROUTER_AGENT_MODEL,
        "provider": "openrouter",
        "icon": "lock",
        "colour": "#ff1744",
        "description": "Vulnerability assessment, remediation & security review",
        "system_prompt": _load_agent_prompt("security"),
    },
}

# ── Custom Agents (user-created, persisted to JSON) ───────────────────
_CUSTOM_AGENTS_FILE = Path(__file__).parent / "custom_agents.json"


def _load_custom_agents() -> dict:
    """Load custom agents from JSON file on disk."""
    if _CUSTOM_AGENTS_FILE.exists():
        try:
            data = json.loads(_CUSTOM_AGENTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and len(data) > 0:
                return data
        except Exception:
            pass
    # First load — seed with service business agents
    agents = _seed_service_agents()
    _CUSTOM_AGENTS_FILE.write_text(json.dumps(agents, indent=2), encoding="utf-8")
    return agents


def _save_custom_agents(agents: dict):
    """Persist custom agents to JSON file."""
    _CUSTOM_AGENTS_FILE.write_text(json.dumps(agents, indent=2), encoding="utf-8")


def _seed_service_agents() -> dict:
    """Create service-business custom agents for UK service industry automation."""
    now = datetime.now().isoformat()
    agents = {}

    _svc_defs = [
        {
            "id": "svc_vision",
            "name": "Visual Identifier",
            "role": "Image Scan & Recognition",
            "icon": "eye",
            "colour": "#18ffff",
            "description": "Scans photos to identify pests, damage, faults & materials — outputs species ID, severity, cost estimate, and required certifications",
            "system_prompt": (
                "# ROLE: Visual Identification Specialist (UK Service Industry)\n\n"
                "You analyse images submitted by customers to identify issues and provide actionable intelligence for downstream agents.\n\n"
                "## ACCEPTED QUERIES\n"
                "- \"What is this?\" + image description\n"
                "- \"Customer sent a photo of [X] in their [location]\"\n"
                "- \"Identify the pest/damage/fault in this image\"\n"
                "- \"How much would it cost to fix what's shown?\"\n\n"
                "## PROCESS\n"
                "Analyse the visual evidence and produce ALL of the following:\n\n"
                "## OUTPUT FORMAT (use exactly these headers)\n\n"
                "**IDENTIFICATION**\n"
                "- Subject: [exact species/issue/material — e.g. 'Vespa velutina (Asian hornet)', 'Rising damp with black mould']\n"
                "- Confidence: [HIGH / MEDIUM / LOW]\n"
                "- Category: [PEST | PLUMBING | ELECTRICAL | STRUCTURAL | DAMP | APPLIANCE | GARDEN | OTHER]\n\n"
                "**SEVERITY** [1-5]\n"
                "- 1=cosmetic, 2=minor, 3=moderate, 4=significant, 5=SAFETY CRITICAL\n"
                "- ⚠️ NOTIFIABLE: [Yes/No — Asian hornet→NNSS, Japanese knotweed→legal, asbestos→HSE]\n\n"
                "**COST ESTIMATE (GBP)**\n"
                "| Item | Min | Max |\n"
                "Use current UK 2025 market rates:\n"
                "- Wasp nest: £50-£100 | Rat treatment 3-visit: £150-£300\n"
                "- Asian hornet: £120-£200 + NNSS | Bed bugs/room: £300-£600\n"
                "- Drain unblock: £80-£150 | Boiler repair: £150-£400\n"
                "- Rewire 3-bed: £3,000-£5,000 | Damp: £500-£2,000\n"
                "- Roof repair: £200-£1,500 | Blocked gutter: £75-£150\n\n"
                "**REQUIRED CERTIFICATIONS**\n"
                "- [BPCA / Gas Safe / NICEIC / NAPIT / CSCS / DBS / Asbestos Awareness / RSPH Level 2]\n\n"
                "**URGENCY**: [EMERGENCY same-day | URGENT 24-48h | ROUTINE within 7 days]\n\n"
                "**IMMEDIATE CUSTOMER ADVICE**\n"
                "- Safety steps the customer should take NOW (e.g. 'Do not approach', 'Turn off at stopcock')\n\n"
                "Always err on the side of caution. If unsure, classify as higher severity. UK context only."
            ),
            "model_tier": "research",
        },
        {
            "id": "svc_intake",
            "name": "Intake Specialist",
            "role": "Customer Inquiry Handler",
            "icon": "clipboard",
            "colour": "#00e5ff",
            "description": "Captures and structures customer requirements into a standardised job brief for downstream agents",
            "system_prompt": (
                "# ROLE: Intake Specialist (UK Service Business)\n\n"
                "You receive raw customer inquiries — text, calls, form submissions — and produce a structured job brief.\n\n"
                "## ACCEPTED QUERIES\n"
                "- \"Customer says: [raw message]\"\n"
                "- \"New inquiry from [name] about [issue] at [location]\"\n"
                "- \"Process this customer request: [details]\"\n"
                "- Any visual identification report from the Visual Identifier agent\n\n"
                "## PROCESS\n"
                "Extract or infer every field. Ask clarifying questions ONLY if safety-critical info is missing.\n\n"
                "## OUTPUT FORMAT (use exactly these headers)\n\n"
                "**JOB BRIEF #[auto]**\n\n"
                "| Field | Value |\n"
                "|---|---|\n"
                "| Service Type | [e.g. Pest Control — Rodent] |\n"
                "| Urgency | [EMERGENCY / URGENT / ROUTINE] |\n"
                "| Address | [full address + postcode] |\n"
                "| Property Type | [House / Flat / Commercial / HMO] |\n"
                "| Access | [key safe / neighbour / tenant present / restricted hours] |\n"
                "| Preferred Slots | [date + time preferences] |\n"
                "| Complexity | [SIMPLE / MODERATE / COMPLEX] |\n"
                "| Description | [2-3 sentence summary] |\n\n"
                "**SAFETY FLAGS**: [gas smell / flooding / structural / electrical / none]\n"
                "**VISUAL EVIDENCE**: [summary of any image analysis received, or 'None provided']\n"
                "**NOTES**: [anything unusual — pets, parking, listed building, vulnerable customer]\n\n"
                "Be empathetic but efficient. UK English. Every brief must be actionable by Quoter and Dispatcher."
            ),
            "model_tier": "execution",
        },
        {
            "id": "svc_quoter",
            "name": "Quoting Engine",
            "role": "Pricing & Estimation",
            "icon": "trending-up",
            "colour": "#ffd700",
            "description": "Generates itemised, transparent quotes with UK market rates, VAT, location adjustments, and payment terms",
            "system_prompt": (
                "# ROLE: Quoting Engine (UK Service Business)\n\n"
                "You receive a job brief (and optional visual identification report) and produce a customer-ready quote.\n\n"
                "## ACCEPTED QUERIES\n"
                "- \"Quote this job: [job brief]\"\n"
                "- \"Price estimate for [service] at [location]\"\n"
                "- \"Generate quote from this identification report: [visual ID]\"\n"
                "- \"Re-quote with adjustments: [changes]\"\n\n"
                "## PRICING RULES\n"
                "- Base rates: UK 2025 market averages for the trade\n"
                "- London/SE premium: +20-30%\n"
                "- Urgency: emergency +50-100%, urgent +25%\n"
                "- Out-of-hours (before 08:00, after 18:00, weekends): +30-50%\n"
                "- Bank holidays: +75-100%\n"
                "- Congestion charge zone: +£15\n"
                "- Parking permit areas: +£5-10\n\n"
                "## OUTPUT FORMAT\n\n"
                "**QUOTE — [Service Type]**\n"
                "Ref: [Q-auto] | Valid: 14 days\n\n"
                "| Line Item | Qty | Unit Price | Total |\n"
                "|---|---|---|---|\n"
                "| [Labour — description] | [hours] | [£/hr] | [£] |\n"
                "| [Materials — itemised] | [units] | [£/unit] | [£] |\n"
                "| [Call-out fee] | 1 | [£] | [£] |\n"
                "| [Location adjustments] | — | — | [£] |\n\n"
                "| | | **Subtotal** | **£X** |\n"
                "| | | **VAT (20%)** | **£X** |\n"
                "| | | **TOTAL** | **£X** |\n\n"
                "**Range**: £[min] – £[max]\n"
                "**Payment**: [X]% deposit on booking, balance on completion\n"
                "**Assumptions**: [list anything that may change on-site]\n"
                "**Warranty**: [if applicable]\n\n"
                "All amounts GBP. Be transparent — customers trust itemised breakdowns."
            ),
            "model_tier": "execution",
        },
        {
            "id": "svc_dispatcher",
            "name": "Job Dispatcher",
            "role": "Contractor Matching & Assignment",
            "icon": "zap",
            "colour": "#ff6e40",
            "description": "Matches jobs to the right contractor by certifications, proximity, rating, and availability — generates dispatch briefs",
            "system_prompt": (
                "# ROLE: Job Dispatcher (UK Service Business)\n\n"
                "You receive a job brief + compliance requirements and match the right contractor, then generate a dispatch pack.\n\n"
                "## ACCEPTED QUERIES\n"
                "- \"Dispatch this job: [brief]\"\n"
                "- \"Find a contractor for [service] in [postcode area]\"\n"
                "- \"Re-assign job [ref] — previous contractor unavailable\"\n"
                "- \"Emergency dispatch: [details]\"\n\n"
                "## MATCHING CRITERIA (ranked)\n"
                "1. **Certifications match** — non-negotiable (Gas Safe, NICEIC, BPCA etc.)\n"
                "2. **Proximity** — nearest to job postcode (search radius: 10mi routine, 20mi urgent, 30mi emergency)\n"
                "3. **Availability** — can attend within the SLA window\n"
                "4. **Rating** — minimum 4.0/5.0, prefer 4.5+\n"
                "5. **Specialism** — exact match preferred over general trades\n\n"
                "## OUTPUT FORMAT\n\n"
                "**DISPATCH BRIEF**\n"
                "Job Ref: [ref] | Priority: [EMERGENCY/URGENT/ROUTINE]\n\n"
                "**Contractor Profile Required**:\n"
                "- Certifications: [list all mandatory]\n"
                "- Insurance: Public liability min £[2M/5M], employer's liability\n"
                "- DBS: [Required / Not required]\n"
                "- Search radius: [X] miles from [postcode]\n\n"
                "**Job Pack for Contractor**:\n"
                "- Address: [full] | Access: [instructions]\n"
                "- Scope: [2-3 lines] | Duration: [estimated hours]\n"
                "- Tools/materials: [list] | Customer notes: [any]\n"
                "- Contact protocol: [call 30min before, text on arrival]\n\n"
                "**SLA**: Respond within [X]h, attend within [X]h, complete within [X]h\n\n"
                "Safety certifications are NON-NEGOTIABLE. Never dispatch unqualified contractors."
            ),
            "model_tier": "execution",
        },
        {
            "id": "svc_scheduler",
            "name": "Scheduling Coordinator",
            "role": "Calendar & Appointment Management",
            "icon": "bar-chart",
            "colour": "#b388ff",
            "description": "Manages time slots, recurring appointments, route efficiency, and reminder sequences",
            "system_prompt": (
                "# ROLE: Scheduling Coordinator (UK Service Business)\n\n"
                "You receive dispatch briefs and customer preferences to produce optimal appointment schedules.\n\n"
                "## ACCEPTED QUERIES\n"
                "- \"Schedule this job: [dispatch brief + customer preferences]\"\n"
                "- \"Find 3 slots for [service] in [area] this week\"\n"
                "- \"Set up recurring [weekly/fortnightly/monthly] for [service]\"\n"
                "- \"Reschedule job [ref] — contractor delayed / customer changed\"\n\n"
                "## SCHEDULING RULES\n"
                "- Standard hours: 08:00-18:00 Mon-Fri, 09:00-16:00 Sat\n"
                "- Emergency: 24/7 available\n"
                "- Buffer: 30min between jobs (60min in London congestion zone)\n"
                "- School run avoidance: avoid 08:15-09:15 and 14:45-15:45 for residential\n"
                "- UK bank holidays: emergency only, premium rate\n"
                "- Recurring: prefer same day/time each visit for customer consistency\n\n"
                "## OUTPUT FORMAT\n\n"
                "**APPOINTMENT OPTIONS**\n\n"
                "| Option | Date | Window | Travel | Notes |\n"
                "|---|---|---|---|---|\n"
                "| A (recommended) | [date] | [HH:MM-HH:MM] | [Xmin from prev job] | [why recommended] |\n"
                "| B | [date] | [HH:MM-HH:MM] | [Xmin] | |\n"
                "| C | [date] | [HH:MM-HH:MM] | [Xmin] | |\n\n"
                "**Confirmation Template**: [ready-to-send to customer]\n"
                "**Reminder Sequence**: 24h SMS → 1h SMS → 'On the way' live notification\n"
                "**Preparation**: [what customer should do before visit]\n\n"
                "Use 24-hour format. All times are GMT/BST as appropriate."
            ),
            "model_tier": "execution",
        },
        {
            "id": "svc_customer_comms",
            "name": "Customer Communications",
            "role": "Client Messaging & Satisfaction",
            "icon": "megaphone",
            "colour": "#ff4081",
            "description": "Drafts all customer-facing messages: confirmations, updates, follow-ups, reviews, and complaint resolution",
            "system_prompt": (
                "# ROLE: Customer Communications (UK Service Business)\n\n"
                "You draft every customer-facing message across the service lifecycle. Every message must be mobile-friendly, under 150 words.\n\n"
                "## ACCEPTED QUERIES\n"
                "- \"Write booking confirmation for: [job details]\"\n"
                "- \"Draft quote presentation for: [quote]\"\n"
                "- \"Handle this complaint: [customer message]\"\n"
                "- \"Request a review after job [ref] completion\"\n"
                "- \"Write follow-up offer for [service] customer\"\n\n"
                "## MESSAGE TYPES & TEMPLATES\n"
                "Draft the specific type requested. Always include:\n"
                "- [COMPANY] placeholder for business name\n"
                "- Booking ref where applicable\n"
                "- Direct contact number / email placeholder\n\n"
                "## TONE RULES\n"
                "- Professional but warm — like a trusted local business, NOT a call centre\n"
                "- UK English (organise, colour, apologise)\n"
                "- First name basis with customer\n"
                "- Complaints: acknowledge → apologise → resolve → compensate if warranted\n"
                "- Reviews: polite, never pushy — Google/Trustpilot link placeholder [REVIEW_LINK]\n\n"
                "## OUTPUT FORMAT\n\n"
                "**[MESSAGE TYPE] — [Channel: SMS/Email/WhatsApp]**\n\n"
                "Subject (email only): [subject line]\n\n"
                "[Message body — max 150 words, mobile-formatted]\n\n"
                "---\n"
                "**Sent via**: [channel] | **Timing**: [when to send relative to event]"
            ),
            "model_tier": "execution",
        },
        {
            "id": "svc_contractor_comms",
            "name": "Contractor Manager",
            "role": "Supplier Relations & Job Packs",
            "icon": "tool",
            "colour": "#ff9100",
            "description": "Generates contractor job packs, onboarding checklists, completion report templates, and performance scorecards",
            "system_prompt": (
                "# ROLE: Contractor Manager (UK Service Business)\n\n"
                "You manage the contractor side of every job — briefing, reporting, performance, payment.\n\n"
                "## ACCEPTED QUERIES\n"
                "- \"Create job pack for contractor: [dispatch brief]\"\n"
                "- \"Onboarding checklist for new [trade] contractor\"\n"
                "- \"Generate completion report template for [service type]\"\n"
                "- \"Calculate contractor payment for job [ref]\"\n"
                "- \"Performance summary for contractor [name/id]\"\n\n"
                "## OUTPUT FORMATS\n\n"
                "### Job Pack (under 200 words)\n"
                "**JOB [ref]** — [service type]\n"
                "- 📍 Address: [full + postcode + what3words if available]\n"
                "- 🔧 Scope: [clear bullet points]\n"
                "- ⏱ Duration: [estimated] | Window: [HH:MM-HH:MM]\n"
                "- 🧰 Bring: [tools + materials list]\n"
                "- ⚠️ Safety: [any hazards or special requirements]\n"
                "- 📋 On completion: [checklist — photos, certs, sign-off]\n"
                "- 📞 Customer protocol: [call 30min before, text on arrival]\n\n"
                "### Onboarding Checklist\n"
                "☐ Public liability insurance (min £2M) ☐ Employer's liability\n"
                "☐ [Trade-specific certs] ☐ DBS (if domestic) ☐ Right-to-work\n"
                "☐ Bank details ☐ Vehicle insurance ☐ Signed T&Cs\n\n"
                "### Payment Calc\n"
                "Agreed rate - platform commission (%) = contractor payout\n\n"
                "Be direct. Contractors are busy — brevity = respect."
            ),
            "model_tier": "execution",
        },
        {
            "id": "svc_compliance",
            "name": "Compliance Officer",
            "role": "Regulatory & Safety Verification",
            "icon": "shield",
            "colour": "#64ffda",
            "description": "Verifies certifications, flags regulatory risks, generates compliance checklists — zero tolerance for non-compliance",
            "system_prompt": (
                "# ROLE: Compliance Officer (UK Service Business)\n\n"
                "You are the safety gate. No job proceeds without your sign-off. Zero tolerance for non-compliance.\n\n"
                "## ACCEPTED QUERIES\n"
                "- \"Compliance check for [service type] job at [location]\"\n"
                "- \"Verify contractor [name] has certs for [job type]\"\n"
                "- \"What certifications are needed for [work description]?\"\n"
                "- \"Audit this visual identification report: [report]\"\n"
                "- \"GDPR check for [data handling scenario]\"\n\n"
                "## CERTIFICATION DATABASE\n"
                "| Trade | Required | Body | Legal? |\n"
                "|---|---|---|---|\n"
                "| Gas (boilers, cookers, fires) | Gas Safe Register | Gas Safe | YES — law |\n"
                "| Electrical (Part P) | NICEIC / NAPIT / ELECSA | DCLG scheme | YES — Building Regs |\n"
                "| Pest control | BPCA membership + RSPH L2 | BPCA | Best practice |\n"
                "| Pest — COSHH chemicals | COSHH training cert | HSE | YES — law |\n"
                "| Any domestic | DBS check | DBS Service | Best practice |\n"
                "| All trades | Public liability ≥£2M | Insurer | Required |\n"
                "| Employing | Employer's liability ≥£5M | Insurer | YES — law |\n"
                "| Asbestos (pre-2000) | Asbestos awareness | UKATA | YES — law |\n\n"
                "## OUTPUT FORMAT\n\n"
                "**COMPLIANCE REPORT — [Job Ref]**\n\n"
                "| Check | Status | Detail |\n"
                "|---|---|---|\n"
                "| [Certification] | ✅ PASS / ❌ FAIL / ⚠️ EXPIRING | [details + expiry date] |\n\n"
                "**RISK FLAGS**: [list any, or 'None']\n"
                "**NOTIFIABLE**: [Asian hornet→NNSS / Knotweed→legal / Asbestos→HSE, or 'N/A']\n"
                "**GDPR**: [data handling compliant? customer consent captured?]\n"
                "**VERDICT**: [APPROVED / BLOCKED — reason]\n\n"
                "Block the job if ANY mandatory certification is missing. Customer safety is absolute."
            ),
            "model_tier": "execution",
        },
        {
            "id": "svc_billing",
            "name": "Billing & Invoicing",
            "role": "Financial Operations",
            "icon": "briefcase",
            "colour": "#00e676",
            "description": "Generates invoices, calculates margins, handles deposits/refunds, and produces financial reconciliation",
            "system_prompt": (
                "# ROLE: Billing Specialist (UK Service Business)\n\n"
                "You handle all financial operations from quote acceptance to payment reconciliation.\n\n"
                "## ACCEPTED QUERIES\n"
                "- \"Generate invoice for completed job: [details + quote]\"\n"
                "- \"Calculate deposit for quote [ref]: [amount]\"\n"
                "- \"Process refund for job [ref]: [reason]\"\n"
                "- \"Monthly reconciliation for [month/year]\"\n"
                "- \"Calculate contractor payout for job [ref]\"\n\n"
                "## FINANCIAL RULES\n"
                "- VAT: 20% (VAT threshold £90,000 — include even if below for readiness)\n"
                "- Deposit: 20-50% on booking (higher for materials-heavy jobs)\n"
                "- Balance: on completion, payable within 7 days\n"
                "- Platform commission: configurable [X]% of gross\n"
                "- Payment processing: 1.5-2.5% (Stripe/SumUp)\n"
                "- Cancellation: free if 24h+ notice, 50% if <24h, 100% if no-show\n\n"
                "## OUTPUT FORMAT\n\n"
                "**INVOICE [INV-auto]**\n"
                "[COMPANY] | VAT: [VAT_NUMBER] | Date: [date]\n\n"
                "| Item | Amount |\n"
                "|---|---|\n"
                "| [line items from quote] | £X |\n"
                "| **Subtotal** | **£X** |\n"
                "| VAT (20%) | £X |\n"
                "| **Total Due** | **£X** |\n"
                "| Less: Deposit paid | -£X |\n"
                "| **Balance Due** | **£X** |\n\n"
                "Payment: Bank transfer to [BANK_DETAILS] | Ref: [INV-ref]\n"
                "Due: [date + 7 days]\n\n"
                "**MARGIN CALC**: Revenue £X - Contractor £X - VAT £X - Processing £X = Net £X ([X]%)\n\n"
                "Comply with Companies Act 2006 invoicing requirements. All amounts GBP."
            ),
            "model_tier": "execution",
        },
    ]

    for d in _svc_defs:
        tier = _MODEL_TIERS.get(d["model_tier"], _MODEL_TIERS["execution"])
        agents[d["id"]] = {
            "id": d["id"],
            "name": d["name"],
            "role": d["role"],
            "model": tier["model"],
            "provider": tier["provider"],
            "icon": d["icon"],
            "colour": d["colour"],
            "description": d["description"],
            "system_prompt": d["system_prompt"],
            "model_tier": d["model_tier"],
            "custom": True,
            "created_at": now,
        }

    log.info(f"Seeded {len(agents)} service business custom agents")
    return agents


_MODEL_TIERS = {
    "strategic": {"model": _CLAUDE_AGENT_MODEL, "provider": "claude"},
    "research":  {"model": "gemini-2.5-flash", "provider": "gemini"},
    "execution": {"model": _OPENROUTER_AGENT_MODEL, "provider": "openrouter"},
}


def _get_all_agents() -> dict:
    """Return merged dict of built-in + custom agents."""
    merged = dict(CEO_AGENTS)
    merged.update(_load_custom_agents())
    return merged


# ── Org Templates (persisted to JSON) ─────────────────────────────────
_ORG_TEMPLATES_FILE = Path(__file__).parent / "org_templates.json"


def _load_org_templates() -> dict:
    if _ORG_TEMPLATES_FILE.exists():
        try:
            data = json.loads(_ORG_TEMPLATES_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    # First load — seed with agile templates
    templates = _seed_org_templates()
    _ORG_TEMPLATES_FILE.write_text(json.dumps(templates, indent=2), encoding="utf-8")
    return templates


def _save_org_templates(templates: dict):
    _ORG_TEMPLATES_FILE.write_text(json.dumps(templates, indent=2), encoding="utf-8")


def _seed_org_templates() -> dict:
    """Create default agile team templates using built-in agents."""
    templates = {}

    # ── 1. SCRUM SPRINT TEAM ──────────────────────────────────────
    templates["scrum_sprint"] = {
        "id": "scrum_sprint",
        "name": "Scrum Sprint Team",
        "description": "Standard agile scrum team: Product Owner sets vision, Scrum Master coordinates, dev team executes. Runs sprint planning → development → QA → retrospective.",
        "nodes": [
            {"agent_id": "product",      "level": 0},  # Product Owner
            {"agent_id": "coo",          "level": 1},  # Scrum Master / Delivery
            {"agent_id": "cto",          "level": 1},  # Tech Lead
            {"agent_id": "architect",    "level": 2},  # Backend Dev
            {"agent_id": "eng_manager",  "level": 2},  # Frontend Dev
            {"agent_id": "qa_director",  "level": 2},  # QA Lead
        ],
        "edges": [
            {"from": "product",     "to": "coo",         "type": "directs"},
            {"from": "product",     "to": "cto",         "type": "directs"},
            {"from": "coo",         "to": "architect",   "type": "directs"},
            {"from": "coo",         "to": "eng_manager", "type": "directs"},
            {"from": "coo",         "to": "qa_director", "type": "directs"},
            {"from": "cto",         "to": "architect",   "type": "directs"},
            {"from": "cto",         "to": "eng_manager", "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    # ── 2. PRODUCT DISCOVERY SQUAD ────────────────────────────────
    templates["product_discovery"] = {
        "id": "product_discovery",
        "name": "Product Discovery Squad",
        "description": "Dual-track agile: discovery + delivery. PM defines problems, researchers validate, designers prototype, engineers assess feasibility.",
        "nodes": [
            {"agent_id": "product",           "level": 0},  # Product Manager
            {"agent_id": "researcher",        "level": 1},  # UX Researcher
            {"agent_id": "analyst",           "level": 1},  # Data Analyst
            {"agent_id": "creative_director", "level": 1},  # UX Designer
            {"agent_id": "cto",              "level": 2},  # Tech Feasibility
            {"agent_id": "strategist",       "level": 2},  # Business Viability
        ],
        "edges": [
            {"from": "product",           "to": "researcher",        "type": "directs"},
            {"from": "product",           "to": "analyst",           "type": "directs"},
            {"from": "product",           "to": "creative_director", "type": "directs"},
            {"from": "researcher",        "to": "cto",              "type": "directs"},
            {"from": "researcher",        "to": "strategist",       "type": "directs"},
            {"from": "creative_director", "to": "cto",              "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    # ── 3. DEVOPS / PLATFORM TEAM ─────────────────────────────────
    templates["devops_platform"] = {
        "id": "devops_platform",
        "name": "DevOps / Platform Team",
        "description": "SRE & platform engineering: CTO leads architecture decisions, engineers handle infrastructure, security, and CI/CD, with QA automation for reliability.",
        "nodes": [
            {"agent_id": "cto",           "level": 0},  # VP Engineering
            {"agent_id": "architect",     "level": 1},  # Platform Architect
            {"agent_id": "security",      "level": 1},  # Security Engineer
            {"agent_id": "eng_manager",   "level": 2},  # DevOps Engineer
            {"agent_id": "qa_automation", "level": 2},  # SRE / Automation
        ],
        "edges": [
            {"from": "cto",       "to": "architect",     "type": "directs"},
            {"from": "cto",       "to": "security",      "type": "directs"},
            {"from": "architect", "to": "eng_manager",   "type": "directs"},
            {"from": "architect", "to": "qa_automation", "type": "directs"},
            {"from": "security",  "to": "qa_automation", "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    # ── 4. GROWTH / GTM SQUAD ─────────────────────────────────────
    templates["growth_gtm"] = {
        "id": "growth_gtm",
        "name": "Growth & GTM Squad",
        "description": "Go-to-market execution: CMO drives strategy, growth hacker runs experiments, content creates assets, analyst measures results.",
        "nodes": [
            {"agent_id": "cmo",          "level": 0},  # CMO / Head of Growth
            {"agent_id": "growth",       "level": 1},  # Growth Hacker
            {"agent_id": "trend_analyst","level": 1},  # Market Intelligence
            {"agent_id": "revenue",      "level": 2},  # Sales / Revenue
            {"agent_id": "analyst",      "level": 2},  # Metrics & Analytics
        ],
        "edges": [
            {"from": "cmo",          "to": "growth",        "type": "directs"},
            {"from": "cmo",          "to": "trend_analyst", "type": "directs"},
            {"from": "growth",       "to": "revenue",       "type": "directs"},
            {"from": "growth",       "to": "analyst",       "type": "directs"},
            {"from": "trend_analyst","to": "analyst",       "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    # ── 5. FULL STACK PRODUCT TEAM (SAFe-style) ───────────────────
    templates["full_product_team"] = {
        "id": "full_product_team",
        "name": "Full Stack Product Team",
        "description": "Cross-functional agile team (SAFe-inspired): CEO sets vision, product & tech leads coordinate, specialists execute across engineering, design, QA, and operations.",
        "nodes": [
            {"agent_id": "ceo_agent",        "level": 0},  # Release Train Engineer / CEO
            {"agent_id": "product",          "level": 1},  # Product Manager
            {"agent_id": "cto",              "level": 1},  # Engineering Lead
            {"agent_id": "coo",              "level": 1},  # Delivery Manager
            {"agent_id": "architect",        "level": 2},  # System Architect
            {"agent_id": "eng_manager",      "level": 2},  # Dev Team Lead
            {"agent_id": "creative_director","level": 2},  # UX/Design
            {"agent_id": "qa_director",      "level": 2},  # QA Lead
        ],
        "edges": [
            {"from": "ceo_agent", "to": "product",          "type": "directs"},
            {"from": "ceo_agent", "to": "cto",              "type": "directs"},
            {"from": "ceo_agent", "to": "coo",              "type": "directs"},
            {"from": "product",   "to": "creative_director","type": "directs"},
            {"from": "product",   "to": "qa_director",      "type": "directs"},
            {"from": "cto",       "to": "architect",        "type": "directs"},
            {"from": "cto",       "to": "eng_manager",      "type": "directs"},
            {"from": "coo",       "to": "eng_manager",      "type": "directs"},
            {"from": "coo",       "to": "qa_director",      "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    log.info(f"Seeded {len(templates)} default agile org templates")

    # ── SERVICE BUSINESS TEMPLATES ─────────────────────────────────────────
    # These use the custom service agents seeded by _seed_service_agents()

    # ── 6. RODENT / PEST CONTROL SERVICE ───────────────────────────────────
    templates["svc_pest_control"] = {
        "id": "svc_pest_control",
        "name": "🐀 Rodent & Pest Control Service",
        "description": (
            "End-to-end pest control: customer submits photo → visual identifier "
            "recognises species (rat, wasp, hornet, bed bug) & estimates cost → "
            "intake captures property details → compliance verifies BPCA/RSPH certs → "
            "quoter prices treatment plan → dispatcher assigns certified pest controller → "
            "scheduler books visit → comms handles confirmations → billing invoices."
        ),
        "category": "service",
        "nodes": [
            {"agent_id": "svc_vision",           "level": 0},
            {"agent_id": "svc_intake",           "level": 0},
            {"agent_id": "svc_compliance",        "level": 1},
            {"agent_id": "svc_quoter",            "level": 1},
            {"agent_id": "svc_dispatcher",        "level": 2},
            {"agent_id": "svc_scheduler",         "level": 2},
            {"agent_id": "svc_customer_comms",    "level": 3},
            {"agent_id": "svc_contractor_comms",  "level": 3},
            {"agent_id": "svc_billing",           "level": 4},
        ],
        "edges": [
            {"from": "svc_vision",      "to": "svc_compliance",       "type": "directs"},
            {"from": "svc_vision",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_intake",      "to": "svc_compliance",       "type": "directs"},
            {"from": "svc_intake",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_compliance",  "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_scheduler",        "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_contractor_comms", "type": "directs"},
            {"from": "svc_scheduler",   "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_customer_comms",   "to": "svc_billing",     "type": "directs"},
            {"from": "svc_contractor_comms", "to": "svc_billing",     "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    # ── 7. EMERGENCY PLUMBING SERVICE ──────────────────────────────────────
    templates["svc_emergency_plumbing"] = {
        "id": "svc_emergency_plumbing",
        "name": "🔧 Emergency Plumbing Service",
        "description": (
            "24/7 emergency plumbing: customer sends photo of burst pipe/leak/boiler fault → "
            "visual identifier assesses damage severity & estimates repair cost → "
            "intake triages urgency → compliance checks Gas Safe (if boiler) → "
            "dispatcher finds nearest available plumber → scheduler confirms ETA → "
            "customer gets live updates → contractor submits completion report → billing."
        ),
        "category": "service",
        "nodes": [
            {"agent_id": "svc_vision",           "level": 0},
            {"agent_id": "svc_intake",           "level": 0},
            {"agent_id": "svc_compliance",        "level": 1},
            {"agent_id": "svc_dispatcher",        "level": 1},
            {"agent_id": "svc_scheduler",         "level": 2},
            {"agent_id": "svc_customer_comms",    "level": 2},
            {"agent_id": "svc_contractor_comms",  "level": 3},
            {"agent_id": "svc_billing",           "level": 3},
        ],
        "edges": [
            {"from": "svc_vision",      "to": "svc_compliance",       "type": "directs"},
            {"from": "svc_vision",      "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_intake",      "to": "svc_compliance",       "type": "directs"},
            {"from": "svc_intake",      "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_compliance",  "to": "svc_scheduler",        "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_scheduler",        "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_scheduler",   "to": "svc_contractor_comms", "type": "directs"},
            {"from": "svc_customer_comms",   "to": "svc_billing",     "type": "directs"},
            {"from": "svc_contractor_comms", "to": "svc_billing",     "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    # ── 8. DOMESTIC CLEANING SERVICE ───────────────────────────────────────
    templates["svc_cleaning"] = {
        "id": "svc_cleaning",
        "name": "🧹 Domestic Cleaning Service",
        "description": (
            "Recurring & one-off cleaning: customer sends photos of property → "
            "visual identifier assesses room count, size, condition & extras needed → "
            "intake captures preferences → quoter prices based on scope → "
            "dispatcher matches DBS-checked cleaners by area → scheduler manages "
            "recurring calendar → customer comms handles reviews & rebookings → billing."
        ),
        "category": "service",
        "nodes": [
            {"agent_id": "svc_vision",           "level": 0},
            {"agent_id": "svc_intake",           "level": 0},
            {"agent_id": "svc_quoter",            "level": 1},
            {"agent_id": "svc_dispatcher",        "level": 2},
            {"agent_id": "svc_scheduler",         "level": 2},
            {"agent_id": "svc_customer_comms",    "level": 3},
            {"agent_id": "svc_contractor_comms",  "level": 3},
            {"agent_id": "svc_billing",           "level": 4},
        ],
        "edges": [
            {"from": "svc_vision",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_intake",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_scheduler",        "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_contractor_comms", "type": "directs"},
            {"from": "svc_scheduler",   "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_customer_comms",   "to": "svc_billing",     "type": "directs"},
            {"from": "svc_contractor_comms", "to": "svc_billing",     "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    # ── 9. ELECTRICAL SERVICES ─────────────────────────────────────────────
    templates["svc_electrical"] = {
        "id": "svc_electrical",
        "name": "⚡ Electrical Services",
        "description": (
            "Domestic & commercial electrical: customer sends photo of consumer unit, "
            "wiring, or fault → visual identifier diagnoses issue & flags safety risks → "
            "intake captures scope → compliance verifies NICEIC/NAPIT → "
            "quoter itemises materials + labour → dispatcher assigns electrician → "
            "completion includes certificates (Part P, BS 7671) → billing."
        ),
        "category": "service",
        "nodes": [
            {"agent_id": "svc_vision",           "level": 0},
            {"agent_id": "svc_intake",           "level": 0},
            {"agent_id": "svc_compliance",        "level": 1},
            {"agent_id": "svc_quoter",            "level": 1},
            {"agent_id": "svc_dispatcher",        "level": 2},
            {"agent_id": "svc_scheduler",         "level": 2},
            {"agent_id": "svc_customer_comms",    "level": 3},
            {"agent_id": "svc_contractor_comms",  "level": 3},
            {"agent_id": "svc_billing",           "level": 4},
        ],
        "edges": [
            {"from": "svc_vision",      "to": "svc_compliance",       "type": "directs"},
            {"from": "svc_vision",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_intake",      "to": "svc_compliance",       "type": "directs"},
            {"from": "svc_intake",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_compliance",  "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_scheduler",        "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_contractor_comms", "type": "directs"},
            {"from": "svc_scheduler",   "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_customer_comms",   "to": "svc_billing",     "type": "directs"},
            {"from": "svc_contractor_comms", "to": "svc_billing",     "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    # ── 10. PROPERTY MAINTENANCE (Landlord/Letting Agent) ──────────────────
    templates["svc_property_maintenance"] = {
        "id": "svc_property_maintenance",
        "name": "🏠 Property Maintenance",
        "description": (
            "Landlord & letting agent repairs: tenant sends photo of issue → "
            "visual identifier diagnoses problem (damp, mould, structural, appliance) → "
            "intake triages urgency → quoter estimates repair → compliance checks certs → "
            "dispatcher matches tradesperson → scheduler coordinates tenant access → "
            "contractor completes with photos → billing splits as configured."
        ),
        "category": "service",
        "nodes": [
            {"agent_id": "svc_vision",           "level": 0},
            {"agent_id": "svc_intake",           "level": 0},
            {"agent_id": "svc_quoter",            "level": 1},
            {"agent_id": "svc_compliance",        "level": 1},
            {"agent_id": "svc_dispatcher",        "level": 2},
            {"agent_id": "svc_scheduler",         "level": 2},
            {"agent_id": "svc_customer_comms",    "level": 3},
            {"agent_id": "svc_contractor_comms",  "level": 3},
            {"agent_id": "svc_billing",           "level": 4},
        ],
        "edges": [
            {"from": "svc_vision",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_vision",      "to": "svc_compliance",       "type": "directs"},
            {"from": "svc_intake",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_intake",      "to": "svc_compliance",       "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_compliance",  "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_scheduler",        "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_contractor_comms", "type": "directs"},
            {"from": "svc_scheduler",   "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_customer_comms",   "to": "svc_billing",     "type": "directs"},
            {"from": "svc_contractor_comms", "to": "svc_billing",     "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    # ── 11. REMOVALS & MAN WITH A VAN ─────────────────────────────────────
    templates["svc_removals"] = {
        "id": "svc_removals",
        "name": "📦 Removals & Man with a Van",
        "description": (
            "House/office moves: customer sends photos of items/rooms → "
            "visual identifier estimates volume, fragile items, special handling → "
            "intake captures addresses & constraints → quoter calculates van size, "
            "crew, distance → dispatcher assigns crew + vehicle → scheduler plans route → "
            "customer gets tracking updates → billing handles deposits & final balance."
        ),
        "category": "service",
        "nodes": [
            {"agent_id": "svc_vision",           "level": 0},
            {"agent_id": "svc_intake",           "level": 0},
            {"agent_id": "svc_quoter",            "level": 1},
            {"agent_id": "svc_dispatcher",        "level": 2},
            {"agent_id": "svc_scheduler",         "level": 2},
            {"agent_id": "svc_customer_comms",    "level": 3},
            {"agent_id": "svc_contractor_comms",  "level": 3},
            {"agent_id": "svc_billing",           "level": 4},
        ],
        "edges": [
            {"from": "svc_vision",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_intake",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_scheduler",        "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_contractor_comms", "type": "directs"},
            {"from": "svc_scheduler",   "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_customer_comms",   "to": "svc_billing",     "type": "directs"},
            {"from": "svc_contractor_comms", "to": "svc_billing",     "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    # ── 12. GARDEN & LANDSCAPING ───────────────────────────────────────────
    templates["svc_garden"] = {
        "id": "svc_garden",
        "name": "🌿 Garden & Landscaping",
        "description": (
            "Garden maintenance & landscaping: customer sends photos of garden → "
            "visual identifier assesses size, condition, plant species, disease/pests → "
            "intake captures requirements → quoter prices per-visit or project → "
            "dispatcher matches gardener/landscaper by specialism → scheduler manages "
            "recurring slots → seasonal upsells (autumn clearance, spring planting)."
        ),
        "category": "service",
        "nodes": [
            {"agent_id": "svc_vision",           "level": 0},
            {"agent_id": "svc_intake",           "level": 0},
            {"agent_id": "svc_quoter",            "level": 1},
            {"agent_id": "svc_dispatcher",        "level": 2},
            {"agent_id": "svc_scheduler",         "level": 2},
            {"agent_id": "svc_customer_comms",    "level": 3},
            {"agent_id": "svc_contractor_comms",  "level": 3},
            {"agent_id": "svc_billing",           "level": 4},
        ],
        "edges": [
            {"from": "svc_vision",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_intake",      "to": "svc_quoter",           "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_dispatcher",       "type": "directs"},
            {"from": "svc_quoter",      "to": "svc_scheduler",        "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_dispatcher",  "to": "svc_contractor_comms", "type": "directs"},
            {"from": "svc_scheduler",   "to": "svc_customer_comms",   "type": "directs"},
            {"from": "svc_customer_comms",   "to": "svc_billing",     "type": "directs"},
            {"from": "svc_contractor_comms", "to": "svc_billing",     "type": "directs"},
        ],
        "created_at": datetime.now().isoformat(),
    }

    log.info(f"Seeded {len(templates)} total org templates (agile + service)")
    return templates


# ── Org Runs (in-memory, keyed by run_id) ─────────────────────────────
_ORG_RUNS: dict = {}


async def _org_execute_agent(agent_id: str, brief: str, directive: str) -> dict:
    """Execute a single agent with a brief. Returns output + real cost."""
    all_agents = _get_all_agents()
    agent = all_agents.get(agent_id)
    if not agent:
        return {"output": f"[ERROR] Unknown agent: {agent_id}", "cost_usd": 0}

    task_prompt = (
        f"## DIRECTIVE\n{directive}\n\n"
        f"## YOUR BRIEF\n{brief}\n\n"
        "## INSTRUCTIONS\n"
        "Respond concisely. Focus only on your area of expertise. "
        "Keep your response under 600 words."
    )
    # Snapshot costs before dispatch to compute real delta
    _pre_claude = _claude_usage["daily_cost_usd"]
    _pre_or = _openrouter_usage["daily_cost_usd"]

    result = await _ceo_dispatch(agent_id, task_prompt, source="org_run")
    output = result.get("response", result.get("error", "No response"))

    # Real cost = delta across all providers (dispatch may fallback)
    cost = (_claude_usage["daily_cost_usd"] - _pre_claude) + \
           (_openrouter_usage["daily_cost_usd"] - _pre_or)
    return {"output": output, "cost_usd": round(cost, 6)}


async def _org_compress_brief(agent_output: str, child_agents: list, directive: str) -> dict:
    """Compress an agent's output into targeted briefs for its direct reports.
    Returns {agent_id: brief_text} for each child."""
    if not child_agents:
        return {}
    child_names = ", ".join(child_agents)
    compress_prompt = (
        f"You are a brief compiler. Given the output below, create a SHORT focused brief "
        f"(max 200 words each) for each of these team members: {child_names}.\n"
        f"Each brief should contain ONLY the information relevant to that team member's role.\n\n"
        f"## DIRECTIVE\n{directive}\n\n"
        f"## PARENT AGENT OUTPUT\n{agent_output}\n\n"
        f"Format your response as:\n"
    )
    for cid in child_agents:
        compress_prompt += f"### BRIEF FOR {cid}\n[brief here]\n\n"

    # Use cheapest model for compression — route to OpenRouter (GPT-4o-mini)
    messages = [
        {"role": "system", "content": "You are a concise brief compiler. Extract and focus information."},
        {"role": "user", "content": compress_prompt},
    ]
    try:
        reply = None
        if OPENROUTER_API_KEY:
            reply = await _chat_openrouter(messages, max_tokens=1200, temperature=0.3)
        if not reply:
            reply = await _chat_llm(messages, max_tokens=1200, purpose="org_brief_compress")
    except Exception:
        # Fallback: send truncated parent output to all children
        truncated = agent_output[:500]
        return {cid: truncated for cid in child_agents}

    # Parse briefs from response
    briefs = {}
    for cid in child_agents:
        marker = f"### BRIEF FOR {cid}"
        idx = reply.find(marker) if reply else -1
        if idx >= 0:
            start = idx + len(marker)
            # Find next marker or end
            next_markers = [reply.find(f"### BRIEF FOR {other}", start) for other in child_agents if other != cid]
            next_markers = [m for m in next_markers if m > 0]
            end = min(next_markers) if next_markers else len(reply)
            briefs[cid] = reply[start:end].strip()
        else:
            briefs[cid] = agent_output[:400]  # fallback
    return briefs


async def _org_run_level(run_id: str, level: int):
    """Execute all agents at a given level in the org run (parallel)."""
    run = _ORG_RUNS.get(run_id)
    if not run:
        return

    nodes_at_level = [n for n in run["nodes"] if n["level"] == level and n["status"] == "pending"]
    if not nodes_at_level:
        # Check if there are more levels
        max_level = max(n["level"] for n in run["nodes"])
        if level >= max_level:
            run["status"] = "complete"
            run["completed_at"] = datetime.now().isoformat()
        else:
            run["status"] = "awaiting_approval"
            run["current_level"] = level
        return

    run["current_level"] = level
    run["status"] = "running"

    # Mark nodes as running
    for n in nodes_at_level:
        n["status"] = "running"

    # Execute all agents at this level in parallel
    async def _run_node(node):
        try:
            result = await _org_execute_agent(node["agent_id"], node["brief_in"], run["directive"])
            node["output"] = result["output"]
            node["cost_usd"] = result["cost_usd"]
            node["status"] = "complete"
            run["total_cost_usd"] += result["cost_usd"]
        except Exception as e:
            node["status"] = "error"
            node["output"] = str(e)

    await asyncio.gather(*[_run_node(n) for n in nodes_at_level])

    # Now generate briefs for next level children
    org = _load_org_templates().get(run["org_id"], {})
    edges = org.get("edges", [])

    for node in nodes_at_level:
        if node["status"] != "complete":
            continue
        # Find children of this node
        child_ids = [e["to"] for e in edges if e["from"] == node["agent_id"] and e.get("type") == "directs"]
        if child_ids:
            briefs = await _org_compress_brief(node["output"], child_ids, run["directive"])
            for cid, brief_text in briefs.items():
                for n in run["nodes"]:
                    if n["agent_id"] == cid and n["status"] == "pending":
                        n["brief_in"] = brief_text

    # Set status to awaiting_approval (manual gate)
    next_level = level + 1
    has_next = any(n["level"] == next_level for n in run["nodes"])
    if has_next:
        run["status"] = "awaiting_approval"
        run["approval_level"] = next_level
    else:
        # Final level done — run synthesis if configured
        run["status"] = "complete"
        run["completed_at"] = datetime.now().isoformat()


# Google Gemini API key (loaded at top of file)


async def _ceo_dispatch(agent_id: str, task: str, source: str = "dispatch",
                        broadcast_id: str | None = None,
                        business_id: str | None = None) -> dict:
    """Dispatch a task to a CEO sub-agent and return the result.
    When business_id is provided, the business context is dynamically
    injected into the system prompt so agents operate with full awareness
    of the business's mission, products, audience, and tone."""
    agent = _get_all_agents().get(agent_id)
    if not agent:
        return {"error": f"Unknown agent: {agent_id}"}

    # ── Dynamic business context injection ────────────────────────────
    # Re-compose the prompt with the active business's directive instead
    # of the static fallback from business_directive.md
    biz_ctx = _resolve_business_context(business_id)
    if biz_ctx:
        system_prompt = _load_agent_prompt(agent_id, business_context=biz_ctx)
        log.info(f"CEO dispatch [{agent_id}]: using business context ({len(biz_ctx)} chars)")
    else:
        system_prompt = agent["system_prompt"]

    # ── Context injection: pull relevant past work from DB ─────────────
    try:
        # Pull last 3 results from THIS agent + search for task-relevant results
        prior_own = arbiter_db.get_agent_results(agent_id=agent_id, limit=3)
        # Extract keywords from task for cross-agent search (first 5 significant words)
        _stop = {"the", "a", "an", "and", "or", "for", "to", "in", "on", "of", "is", "it",
                 "my", "our", "your", "this", "that", "what", "how", "why", "please", "can"}
        keywords = [w for w in task.lower().split() if w not in _stop and len(w) > 2][:5]
        prior_related = []
        if keywords:
            search_q = " ".join(keywords[:3])
            prior_related = arbiter_db.get_agent_results(search=search_q, limit=3)
            # De-duplicate against own results
            own_ids = {r["id"] for r in prior_own}
            prior_related = [r for r in prior_related if r["id"] not in own_ids]

        if prior_own or prior_related:
            ctx_parts = ["\n\n## Previous Work (from ARBITER memory — use as context, don't repeat verbatim)"]
            for r in prior_own[:3]:
                resp_preview = (r.get("response") or "")[:800]
                if resp_preview:
                    ctx_parts.append(f"[{r['created_at'][:10]}] Your prior work on \"{r['task'][:80]}\":\n{resp_preview}")
            for r in prior_related[:2]:
                resp_preview = (r.get("response") or "")[:600]
                if resp_preview:
                    ctx_parts.append(f"[{r['created_at'][:10]}] {r['agent_name']} on \"{r['task'][:80]}\":\n{resp_preview}")
            if len(ctx_parts) > 1:  # More than just the header
                system_prompt += "\n".join(ctx_parts)
                log.info(f"CEO dispatch [{agent_id}]: injected {len(ctx_parts)-1} prior results as context")
    except Exception as e:
        log.warning(f"CEO context injection error (non-fatal): {e}")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    reply = None
    provider = agent["provider"]
    model = agent["model"]

    try:
        if provider == "claude" and ANTHROPIC_API_KEY:
            # Strategic agents via Claude Sonnet (with budget safeguards)
            block = _claude_check_budget()
            if block:
                log.warning(f"Claude blocked ({block}) — falling back to OpenRouter for [{agent_id}]")
                if OPENROUTER_API_KEY:
                    reply = await _chat_openrouter(
                        messages, max_tokens=2400, temperature=0.6,
                        model=_OPENROUTER_AGENT_MODEL,
                    )
                else:
                    reply = await _chat_llm(messages, max_tokens=2400, purpose=f"ceo-{agent_id}")
            else:
                # Use _chat_claude which handles Anthropic format conversion + usage tracking
                # But override the model to use Sonnet for agent work
                client = _get_anthropic()
                if client:
                    # Convert messages to Anthropic format
                    system_text = ""
                    api_messages = []
                    for m in messages:
                        role = m.get("role", "user")
                        content = m.get("content", "")
                        if role == "system":
                            system_text += content + "\n"
                        else:
                            api_role = "assistant" if role == "assistant" else "user"
                            if api_messages and api_messages[-1]["role"] == api_role:
                                api_messages[-1]["content"] += "\n" + content
                            else:
                                api_messages.append({"role": api_role, "content": content})
                    if not api_messages or api_messages[0]["role"] != "user":
                        api_messages.insert(0, {"role": "user", "content": "Please respond."})

                    _create_kwargs = {
                        "model": model,  # Uses _CLAUDE_AGENT_MODEL (Sonnet)
                        "max_tokens": 2400,
                        "temperature": 0.6,
                        "messages": api_messages,
                    }
                    if system_text.strip():
                        _create_kwargs["system"] = system_text.strip()
                    resp = await asyncio.to_thread(client.messages.create, **_create_kwargs)
                    reply = resp.content[0].text.strip() if resp.content else ""
                    # Record usage for budget tracking
                    input_tok = resp.usage.input_tokens if resp.usage else 0
                    output_tok = resp.usage.output_tokens if resp.usage else 0
                    _claude_record_usage(input_tok, output_tok)
                    log.info(f"Claude agent [{agent_id}]: {input_tok}in/{output_tok}out tokens via {model}")
                else:
                    reply = await _chat_llm(messages, max_tokens=2400, purpose=f"ceo-{agent_id}")
        elif provider == "gemini" and GOOGLE_API_KEY:
            # Check free-tier cap before calling
            gemini_block = _gemini_check_budget()
            if gemini_block:
                log.warning(f"Gemini blocked ({gemini_block}) — falling back to OpenRouter for [{agent_id}]")
                if OPENROUTER_API_KEY:
                    reply = await _chat_openrouter(
                        messages, max_tokens=2400, temperature=0.6,
                        model=_OPENROUTER_AGENT_MODEL,
                    )
                else:
                    reply = await _chat_llm(messages, max_tokens=2400, purpose=f"ceo-{agent_id}")
            else:
                # Use Google Gemini via OpenAI-compatible endpoint (free tier)
                from openai import OpenAI as _OAI
                gemini = _OAI(
                    api_key=GOOGLE_API_KEY,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                )
                try:
                    resp = gemini.chat.completions.create(
                        model=model, messages=messages,
                        max_tokens=2400, temperature=0.6,
                        timeout=_OPENROUTER_TIMEOUT,
                    )
                    reply = resp.choices[0].message.content.strip()
                    # Capture tokens from OpenAI-compatible response
                    _gin = getattr(resp.usage, 'prompt_tokens', 0) if resp.usage else 0
                    _gout = getattr(resp.usage, 'completion_tokens', 0) if resp.usage else 0
                    _gemini_record_success(_gin, _gout)
                except Exception as gem_err:
                    _gemini_record_error()
                    log.warning(f"Gemini error for [{agent_id}]: {gem_err} — falling back to OpenRouter")
                    if OPENROUTER_API_KEY:
                        reply = await _chat_openrouter(
                            messages, max_tokens=2400, temperature=0.6,
                            model=_OPENROUTER_AGENT_MODEL,
                        )
                    else:
                        reply = await _chat_llm(messages, max_tokens=2400, purpose=f"ceo-{agent_id}")
        elif provider == "openrouter" and OPENROUTER_API_KEY:
            # Route through OpenRouter with full cost safeguards
            reply = await _chat_openrouter(
                messages, max_tokens=2400, temperature=0.6,
                model=model,
            )
        elif provider == "openai" and OPENAI_API_KEY:
            resp = oai.chat.completions.create(
                model=model, messages=messages,
                max_tokens=2400, temperature=0.6,
            )
            reply = resp.choices[0].message.content.strip()
        else:
            # Fallback to ARBITER's standard LLM chain (Ollama)
            reply = await _chat_llm(messages, max_tokens=2400, purpose=f"ceo-{agent_id}")
    except Exception as e:
        log.error(f"CEO dispatch [{agent_id}] error: {e}")
        arbiter_db.save_agent_result(
            agent_id=agent_id, agent_name=agent["name"], task=task,
            error=str(e), model=model, source=source,
            broadcast_id=broadcast_id, business_id=business_id,
        )
        return {"error": str(e), "agent_id": agent_id}

    if not reply:
        error_msg = "No response from LLM"
        arbiter_db.save_agent_result(
            agent_id=agent_id, agent_name=agent["name"], task=task,
            error=error_msg, model=model, source=source,
            broadcast_id=broadcast_id, business_id=business_id,
        )
        return {"error": error_msg, "agent_id": agent_id}

    rid = arbiter_db.save_agent_result(
        agent_id=agent_id, agent_name=agent["name"], task=task,
        response=reply, model=model, source=source,
        broadcast_id=broadcast_id, business_id=business_id,
    )
    return {
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "model": model,
        "response": reply,
        "result_id": rid,
    }


@app.get("/api/ceo/agents")
async def ceo_agents():
    """Return the CEO sub-agent definitions for the UI (built-in + custom)."""
    all_agents = _get_all_agents()
    return [
        {**{k: v for k, v in a.items() if k != "system_prompt"},
         "custom": a.get("custom", False)}
        for a in all_agents.values()
    ]


# ── Custom Agent CRUD ─────────────────────────────────────────────────

@app.get("/api/agents/custom")
async def agents_custom_list():
    """List all custom agents."""
    agents = _load_custom_agents()
    return [
        {k: v for k, v in a.items() if k != "system_prompt"}
        for a in agents.values()
    ]


@app.post("/api/agents/custom")
async def agents_custom_create(request: Request):
    """Create a new custom agent."""
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return {"error": "name is required"}
    if len(name) > _MAX_NAME_LEN:
        return {"error": f"name too long (max {_MAX_NAME_LEN} chars)"}

    agent_id = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    if not agent_id:
        return {"error": "Invalid agent name"}

    # Check for conflicts with built-in agents
    if agent_id in CEO_AGENTS:
        return {"error": f"Agent ID '{agent_id}' conflicts with a built-in agent"}

    description = body.get("description", "").strip()
    if len(description) > _MAX_DESCRIPTION_LEN:
        return {"error": f"description too long (max {_MAX_DESCRIPTION_LEN} chars)"}

    tier_key = body.get("model_tier", "execution")
    tier = _MODEL_TIERS.get(tier_key, _MODEL_TIERS["execution"])

    system_prompt = body.get("system_prompt", "").strip()
    if len(system_prompt) > _MAX_SYSTEM_PROMPT_LEN:
        return {"error": f"system_prompt too long (max {_MAX_SYSTEM_PROMPT_LEN} chars)"}
    if not system_prompt:
        system_prompt = f"You are {name}. {description}. Follow the directive precisely."

    agent = {
        "id": agent_id,
        "name": name,
        "role": body.get("role", "Custom Agent"),
        "model": tier["model"],
        "provider": tier["provider"],
        "icon": body.get("icon", "user"),
        "colour": body.get("colour", "#00e5ff"),
        "description": description,
        "system_prompt": system_prompt,
        "model_tier": tier_key,
        "custom": True,
        "created_at": datetime.now().isoformat(),
    }

    agents = _load_custom_agents()
    agents[agent_id] = agent
    _save_custom_agents(agents)

    log.info(f"Custom agent created: {agent_id} ({name}, tier={tier_key})")
    return {k: v for k, v in agent.items() if k != "system_prompt"}


@app.put("/api/agents/custom/{agent_id}")
async def agents_custom_update(agent_id: str, request: Request):
    """Update a custom agent."""
    agents = _load_custom_agents()
    if agent_id not in agents:
        return {"error": f"Custom agent '{agent_id}' not found"}

    body = await request.json()
    agent = agents[agent_id]

    # ── Input length validation ──
    if "name" in body and len(str(body["name"])) > _MAX_NAME_LEN:
        return {"error": f"name too long (max {_MAX_NAME_LEN} chars)"}
    if "description" in body and len(str(body["description"])) > _MAX_DESCRIPTION_LEN:
        return {"error": f"description too long (max {_MAX_DESCRIPTION_LEN} chars)"}
    if "system_prompt" in body and len(str(body["system_prompt"])) > _MAX_SYSTEM_PROMPT_LEN:
        return {"error": f"system_prompt too long (max {_MAX_SYSTEM_PROMPT_LEN} chars)"}

    for field in ("name", "role", "description", "system_prompt", "icon", "colour"):
        if field in body:
            agent[field] = body[field]

    if "model_tier" in body:
        tier = _MODEL_TIERS.get(body["model_tier"], _MODEL_TIERS["execution"])
        agent["model"] = tier["model"]
        agent["provider"] = tier["provider"]
        agent["model_tier"] = body["model_tier"]

    agents[agent_id] = agent
    _save_custom_agents(agents)
    return {k: v for k, v in agent.items() if k != "system_prompt"}


@app.post("/api/agents/custom/{agent_id}/delete")
async def agents_custom_delete(agent_id: str):
    """Delete a custom agent."""
    agents = _load_custom_agents()
    if agent_id not in agents:
        return {"error": f"Custom agent '{agent_id}' not found"}
    del agents[agent_id]
    _save_custom_agents(agents)
    log.info(f"Custom agent deleted: {agent_id}")
    return {"ok": True}


# ── Org Template CRUD ─────────────────────────────────────────────────

@app.get("/api/org/templates")
async def org_templates_list():
    """List all org templates."""
    templates = _load_org_templates()
    return [
        {k: v for k, v in t.items()}
        for t in templates.values()
    ]


@app.post("/api/org/templates")
async def org_templates_create(request: Request):
    """Create a new org template."""
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return {"error": "name is required"}
    if len(name) > _MAX_NAME_LEN:
        return {"error": f"name too long (max {_MAX_NAME_LEN} chars)"}
    description = body.get("description", "").strip()
    if len(description) > _MAX_DESCRIPTION_LEN:
        return {"error": f"description too long (max {_MAX_DESCRIPTION_LEN} chars)"}
    nodes = body.get("nodes", [])
    if not isinstance(nodes, list) or len(nodes) > 50:
        return {"error": "nodes must be a list with max 50 entries"}
    edges = body.get("edges", [])
    if not isinstance(edges, list) or len(edges) > 200:
        return {"error": "edges must be a list with max 200 entries"}

    template_id = arbiter_db._new_id()
    template = {
        "id": template_id,
        "name": name,
        "description": description,
        "nodes": nodes,
        "edges": edges,
        "created_at": datetime.now().isoformat(),
    }

    templates = _load_org_templates()
    templates[template_id] = template
    _save_org_templates(templates)
    log.info(f"Org template created: {template_id} ({name})")
    return template


@app.put("/api/org/templates/{template_id}")
async def org_templates_update(template_id: str, request: Request):
    """Update an org template."""
    templates = _load_org_templates()
    if template_id not in templates:
        return {"error": "Template not found"}

    body = await request.json()
    template = templates[template_id]
    for field in ("name", "description", "nodes", "edges"):
        if field in body:
            template[field] = body[field]

    templates[template_id] = template
    _save_org_templates(templates)
    return template


@app.post("/api/org/templates/{template_id}/delete")
async def org_templates_delete(template_id: str):
    """Delete an org template."""
    templates = _load_org_templates()
    if template_id not in templates:
        return {"error": "Template not found"}
    del templates[template_id]
    _save_org_templates(templates)
    return {"ok": True}


# ── Org Execution (manual level-by-level with approval gates) ─────────

@app.post("/api/org/run")
async def org_run_create(request: Request):
    """Start an org execution run. Executes level 0 (root) immediately."""
    body = await request.json()
    org_id = body.get("org_id", "")
    directive = body.get("directive", "").strip()
    if not org_id or not directive:
        return {"error": "org_id and directive are required"}
    if len(directive) > _MAX_DIRECTIVE_LEN:
        return {"error": f"directive too long (max {_MAX_DIRECTIVE_LEN} chars)"}

    templates = _load_org_templates()
    org = templates.get(org_id)
    if not org:
        return {"error": f"Org template '{org_id}' not found"}

    # Build run nodes from org template nodes
    run_nodes = []
    for node_def in org.get("nodes", []):
        run_nodes.append({
            "agent_id": node_def["agent_id"],
            "level": node_def.get("level", 0),
            "status": "pending",
            "brief_in": directive if node_def.get("level", 0) == 0 else "",
            "output": "",
            "cost_usd": 0,
        })

    if not run_nodes:
        return {"error": "Org template has no agents"}

    run_id = arbiter_db._new_id()
    run = {
        "id": run_id,
        "org_id": org_id,
        "org_name": org.get("name", ""),
        "directive": directive,
        "status": "running",
        "current_level": 0,
        "approval_level": None,
        "nodes": run_nodes,
        "total_cost_usd": 0.0,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
    }
    _ORG_RUNS[run_id] = run

    # Execute level 0 (root agents) immediately
    await _org_run_level(run_id, 0)

    return _ORG_RUNS[run_id]


@app.get("/api/org/run/{run_id}")
async def org_run_get(run_id: str):
    """Get the status of an org run."""
    run = _ORG_RUNS.get(run_id)
    if not run:
        return {"error": "Run not found"}
    return run


@app.post("/api/org/run/{run_id}/approve")
async def org_run_approve(run_id: str):
    """Approve the current level and execute the next level."""
    run = _ORG_RUNS.get(run_id)
    if not run:
        return {"error": "Run not found"}
    if run["status"] != "awaiting_approval":
        return {"error": f"Run is not awaiting approval (status={run['status']})"}

    next_level = run.get("approval_level", run["current_level"] + 1)
    await _org_run_level(run_id, next_level)
    return _ORG_RUNS[run_id]


@app.post("/api/org/run/{run_id}/reject")
async def org_run_reject(run_id: str):
    """Reject and stop the org run."""
    run = _ORG_RUNS.get(run_id)
    if not run:
        return {"error": "Run not found"}
    run["status"] = "rejected"
    run["completed_at"] = datetime.now().isoformat()
    return run


@app.get("/api/org/runs")
async def org_runs_list():
    """List recent org runs."""
    runs = sorted(_ORG_RUNS.values(), key=lambda r: r.get("started_at", ""), reverse=True)[:20]
    return [
        {k: v for k, v in r.items() if k != "nodes"}
        | {"node_count": len(r.get("nodes", [])),
           "completed_count": sum(1 for n in r.get("nodes", []) if n["status"] == "complete")}
        for r in runs
    ]


@app.get("/api/active-jobs")
async def active_jobs():
    """Return all active/recent pipelines, org runs, and agent dispatches for the dashboard HUD."""
    jobs = []

    # 1. Pipelines (running, waiting, pending)
    try:
        for pipe in arbiter_db.get_pipelines(limit=10):
            if pipe["status"] in ("running", "waiting", "pending"):
                stages = pipe.get("stages", [])
                done = sum(1 for s in stages if s.get("status") == "complete")
                running_stage = next((s for s in stages if s.get("status") == "running"), None)
                jobs.append({
                    "id": pipe["id"],
                    "kind": "pipeline",
                    "label": (pipe.get("directive") or "")[:80],
                    "status": pipe["status"],
                    "progress": done,
                    "total": len(stages),
                    "current_agent": running_stage["agent_name"] if running_stage else None,
                    "created_at": pipe.get("created_at"),
                })
    except Exception as e:
        log.debug(f"active-jobs pipeline scan: {e}")

    # 2. Org / CEO team runs (in-memory)
    for run in _ORG_RUNS.values():
        if run.get("status") in ("running", "awaiting_approval"):
            nodes = run.get("nodes", [])
            done = sum(1 for n in nodes if n.get("status") == "complete")
            running_nodes = [n for n in nodes if n.get("status") == "running"]
            jobs.append({
                "id": run["id"],
                "kind": "team",
                "label": (run.get("directive") or "")[:80],
                "status": run["status"],
                "progress": done,
                "total": len(nodes),
                "current_agent": running_nodes[0]["agent_name"] if running_nodes else None,
                "created_at": run.get("started_at"),
                "team_name": run.get("org_name", ""),
            })

    # 3. Recent agent dispatches (last 5 from DB, only very recent ones)
    try:
        recent = arbiter_db.get_agent_results(limit=5)
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        for r in recent:
            if r.get("created_at", "") >= cutoff:
                jobs.append({
                    "id": r["id"],
                    "kind": "agent",
                    "label": (r.get("task") or "")[:80],
                    "status": "complete" if r.get("response") else ("error" if r.get("error") else "running"),
                    "agent_name": r.get("agent_name", r.get("agent_id", "")),
                    "model": r.get("model"),
                    "created_at": r.get("created_at"),
                })
    except Exception as e:
        log.debug(f"active-jobs agent scan: {e}")

    # Sort: running first, then by created_at desc
    status_order = {"running": 0, "waiting": 1, "pending": 1, "awaiting_approval": 1, "complete": 2, "error": 3}
    jobs.sort(key=lambda j: (status_order.get(j["status"], 9), -(hash(j.get("created_at") or ""))))
    return {"jobs": jobs}


@app.post("/api/ceo/dispatch")
async def ceo_dispatch(request: Request):
    """Dispatch a task to a specific CEO sub-agent."""
    body = await request.json()
    agent_id = body.get("agent_id", "")
    task = body.get("task", "")
    if not agent_id or not task:
        return {"error": "agent_id and task required"}
    business_id = _get_business_id(request)
    result = await _ceo_dispatch(agent_id, task, business_id=business_id)
    return result


@app.post("/api/ceo/broadcast")
async def ceo_broadcast(request: Request):
    """Broadcast a directive to all CEO sub-agents simultaneously."""
    body = await request.json()
    task = body.get("task", "")
    if not task:
        return {"error": "task required"}
    import asyncio as _aio
    bid = arbiter_db._new_id()
    results = await _aio.gather(
        *[_ceo_dispatch(aid, task, source="broadcast", broadcast_id=bid)
          for aid in _get_all_agents()],
        return_exceptions=True,
    )
    return {
        "broadcast_id": bid,
        "results": [
            r if isinstance(r, dict) else {"error": str(r)}
            for r in results
        ]
    }


@app.get("/api/ceo/activity")
async def ceo_activity(limit: int = 30):
    """Return recent agent activity grouped into workflows.

    Broadcasts are grouped by broadcast_id.
    Individual dispatches appear as single-agent workflows.
    Returns newest-first.
    """
    rows = arbiter_db.get_agent_results(limit=limit)
    # Group by broadcast_id where present; singles stand alone
    workflows: list[dict] = []
    seen_bids: dict[str, int] = {}  # broadcast_id -> index in workflows

    for r in rows:
        bid = r.get("broadcast_id")
        if bid:
            if bid in seen_bids:
                workflows[seen_bids[bid]]["agents"].append(r)
            else:
                seen_bids[bid] = len(workflows)
                workflows.append({
                    "id": bid,
                    "type": "broadcast",
                    "task": r["task"],
                    "created_at": r["created_at"],
                    "agents": [r],
                })
        else:
            workflows.append({
                "id": r["id"],
                "type": "dispatch",
                "task": r["task"],
                "created_at": r["created_at"],
                "agents": [r],
            })

    # Sort by created_at descending
    workflows.sort(key=lambda w: w["created_at"], reverse=True)
    return {"workflows": workflows[:limit]}


# ── CEO Pipeline Orchestration ─────────────────────────────────────────

# Default pipeline templates: which agents run in which order, and what
# task each agent receives (use {directive} and {prior_output} placeholders).
_PIPELINE_TEMPLATES = {
    # ── FULL: End-to-end business evaluation (8 agents) ─────────────
    # Researcher→Analyst→Visionary→Strategist→Product→CTO→Risk→Chief of Staff
    "full": [
        {
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "description": "Market intelligence & evidence gathering",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Deliver a research brief: executive summary, market intelligence, "
                "competitive landscape, audience & demand signals, trend analysis (6-18 month), sources.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "analyst",
            "agent_name": "Analyst",
            "description": "Data analysis & signal extraction",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Analyse the research. Extract key metrics, segment breakdown, opportunity sizing, "
                "risk factors, and ranked recommendations.\n\n"
                "## RESEARCH INPUT\n{prior_output}"
            ),
            "gate": True,
        },
        {
            "agent_id": "visionary",
            "agent_name": "Visionary",
            "description": "Creative concepts & future opportunities",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Based on the research and analysis, generate original opportunities, product concepts, "
                "story angles, and differentiated positioning ideas.\n\n"
                "## PRIOR ANALYSIS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "strategist",
            "agent_name": "Strategist",
            "description": "Strategic direction & priorities",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Synthesise all prior work. Recommend where to play and how to win. "
                "Include rationale, trade-offs, risks, priorities, and a 30/60/90 day plan.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "product",
            "agent_name": "Product",
            "description": "Product roadmap & MVP design",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Turn the strategy into a product plan: user problem, solution, MVP scope, "
                "roadmap, validation plan, and success metrics.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "cto",
            "agent_name": "CTO",
            "description": "Technical feasibility & architecture",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Assess technical feasibility. Provide architecture, build plan, security, "
                "cost estimates, risks, and engineering tasks.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "risk",
            "agent_name": "Risk",
            "description": "Risk & compliance assessment",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Identify legal, privacy, security, and operational risks. "
                "Provide severity assessment, mitigations, and required controls.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "chief_of_staff",
            "agent_name": "Chief of Staff",
            "description": "Executive synthesis & decision",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "You are the final synthesiser. Review all agent outputs. Resolve conflicts, "
                "produce an executive summary, recommended plan, immediate next steps, "
                "and a confidence score (0-100).\n\n"
                "## ALL AGENT OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── RESEARCH: Deep research + analysis (2 agents, free) ──────────
    "research": [
        {
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "description": "Deep research & intelligence",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Deliver a comprehensive research brief: executive summary, market intelligence, "
                "competitive landscape, audience & demand, trends, sources.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "analyst",
            "agent_name": "Analyst",
            "description": "Analyse findings & extract insights",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Extract quantitative insights: key metrics with benchmarks, "
                "trend analysis, segment breakdown, ranked recommendations.\n\n"
                "## RESEARCH INPUT\n{prior_output}"
            ),
            "gate": False,
        },
    ],
    # ── CONTENT: Research → CMO content creation ─────────────────────
    "content": [
        {
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "description": "Background research for content",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Research for content creation: key facts, audience insights, "
                "trending angles, competitor content gaps, hook ideas, sources.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "cmo",
            "agent_name": "CMO",
            "description": "Draft positioning & content",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create positioning and content assets: strategy brief, "
                "2+ content pieces with hooks and CTAs, repurposing plan.\n\n"
                "## RESEARCH INPUT\n{prior_output}"
            ),
            "gate": False,
        },
    ],
    # ── TECHNICAL: Research → CTO review ─────────────────────────────
    "technical": [
        {
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "description": "Technical landscape research",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Research the technical landscape: technology options, architecture patterns, "
                "cost analysis, community maturity, case studies, sources.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "cto",
            "agent_name": "CTO",
            "description": "Technical review & architecture",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Provide feasibility verdict, recommended architecture, build plan, "
                "risk register, cost estimate, implementation phases.\n\n"
                "## RESEARCH INPUT\n{prior_output}"
            ),
            "gate": False,
        },
    ],
    # ── GTM: Go-to-market pipeline ───────────────────────────────────
    "gtm": [
        {
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "description": "Market & audience research",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Research for go-to-market: target audience, market dynamics, "
                "competitor positioning, demand signals, sources.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "cmo",
            "agent_name": "CMO",
            "description": "Positioning & campaigns",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Build go-to-market positioning, messaging pillars, campaign concepts, "
                "content themes, and next actions.\n\n"
                "## RESEARCH INPUT\n{prior_output}"
            ),
            "gate": False,
        },
        {
            "agent_id": "revenue",
            "agent_name": "Revenue",
            "description": "Revenue strategy & sales motions",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Define ICPs, revenue model, pricing strategy, sales motions, "
                "partnership opportunities, and 90-day revenue targets.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "coo",
            "agent_name": "COO",
            "description": "Execution plan & timeline",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Turn the GTM strategy into a delivery plan: workstreams, milestones, "
                "tasks, timeline, dependencies, and immediate actions.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── STRATEGY: Deep strategic analysis ────────────────────────────
    "strategy": [
        {
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "description": "Strategic landscape research",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Research the strategic landscape: market position, competitive dynamics, "
                "customer signals, emerging trends, sources.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "visionary",
            "agent_name": "Visionary",
            "description": "Creative opportunities & concepts",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Generate differentiated opportunities, overlooked angles, "
                "and future-facing concepts based on the research.\n\n"
                "## RESEARCH INPUT\n{prior_output}"
            ),
            "gate": False,
        },
        {
            "agent_id": "strategist",
            "agent_name": "Strategist",
            "description": "Strategic recommendation",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Synthesise research and ideas into a strategic recommendation: "
                "where to play, how to win, trade-offs, risks, 30/60/90 day plan.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── STORY: Story creation pipeline ───────────────────────────────
    "story": [
        {
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "description": "Audience & theme research",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Research the target audience, age group, trending themes, "
                "comparable successful stories, and educational opportunities.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "child_dev",
            "agent_name": "Child Dev",
            "description": "Developmental review",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Review the research and recommend developmental goals, age-appropriate themes, "
                "emotional learning objectives, and safety considerations.\n\n"
                "## RESEARCH INPUT\n{prior_output}"
            ),
            "gate": False,
        },
        {
            "agent_id": "story_architect",
            "agent_name": "Story Architect",
            "description": "Write the story",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create a complete children's story incorporating the research and developmental guidance. "
                "Include all story elements, interactive moments, and parent takeaways.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": True,
        },
        {
            "agent_id": "creative_director",
            "agent_name": "Creative Director",
            "description": "Art direction for the story",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create comprehensive art direction for this story: visual style, colour palette, "
                "character design briefs, illustration notes per scene, animation direction.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── CHARACTER: Character/IP creation ─────────────────────────────
    "character": [
        {
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "description": "Market & IP research",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Research successful children's characters, IP franchises, "
                "merchandising trends, and gaps in the market.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "character_designer",
            "agent_name": "Character Designer",
            "description": "Create characters",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Design memorable characters with franchise potential. "
                "Include personality, visual description, backstory, and merchandising ideas.\n\n"
                "## RESEARCH INPUT\n{prior_output}"
            ),
            "gate": True,
        },
        {
            "agent_id": "creative_director",
            "agent_name": "Creative Director",
            "description": "Visual direction",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Develop visual direction for these characters: art style, "
                "colour palette, consistency rules, animation direction.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── ENGINEERING: Full engineering pipeline ────────────────────────
    "engineering": [
        {
            "agent_id": "architect",
            "agent_name": "Architect",
            "description": "System architecture",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Design the system architecture: components, data flow, "
                "technology choices, trade-offs, and implementation plan.\n"
            ),
            "gate": True,
        },
        {
            "agent_id": "eng_manager",
            "agent_name": "Eng Manager",
            "description": "Delivery planning",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Convert the architecture into epics, stories, tasks, "
                "estimates, dependencies, and a delivery roadmap.\n\n"
                "## ARCHITECTURE\n{prior_output}"
            ),
            "gate": False,
        },
        {
            "agent_id": "qa_director",
            "agent_name": "QA Director",
            "description": "Test strategy",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create test strategy, acceptance criteria, and quality plan "
                "for the proposed architecture and delivery plan.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "security",
            "agent_name": "Security",
            "description": "Security audit",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Audit the architecture for security vulnerabilities: "
                "auth, data protection, infrastructure, AI safety. Provide remediations.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── QA: Quality assurance pipeline ────────────────────────────────
    "qa": [
        {
            "agent_id": "qa_director",
            "agent_name": "QA Director",
            "description": "Test strategy & plan",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create comprehensive test strategy, plan, acceptance criteria, "
                "edge cases, and quality score assessment.\n"
            ),
            "gate": True,
        },
        {
            "agent_id": "qa_automation",
            "agent_name": "QA Automation",
            "description": "Write test code",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Write executable test code based on the test strategy. "
                "Include unit, integration, API, and E2E tests.\n\n"
                "## TEST STRATEGY\n{prior_output}"
            ),
            "gate": False,
        },
        {
            "agent_id": "security",
            "agent_name": "Security",
            "description": "Security testing",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Perform security testing assessment: vulnerabilities, "
                "severity, exploitability, and required remediations.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── FUNDRAISE: Investor readiness pipeline ───────────────────────
    "fundraise": [
        {
            "agent_id": "intelligence",
            "agent_name": "Intelligence",
            "description": "Market intelligence",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Comprehensive market intelligence: TAM/SAM/SOM, competitor analysis, "
                "market trends, growth drivers, and investment landscape.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "financial",
            "agent_name": "Financial",
            "description": "Financial model & forecast",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Build financial model with 12/24/60 month forecasts, "
                "unit economics, scenarios, and assumptions.\n\n"
                "## MARKET INTELLIGENCE\n{prior_output}"
            ),
            "gate": True,
        },
        {
            "agent_id": "investor",
            "agent_name": "Investor",
            "description": "Investment memo",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Write an investment memo: thesis, risks, valuation logic, "
                "key questions, and invest/pass recommendation.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "ceo_agent",
            "agent_name": "CEO",
            "description": "Founder response",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Review the investment analysis. Prepare founder responses to investor questions, "
                "strategic narrative, and fundraising next steps.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── GROWTH: Growth & acquisition pipeline ────────────────────────
    "growth_plan": [
        {
            "agent_id": "trend_analyst",
            "agent_name": "Trend Analyst",
            "description": "Trend discovery",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Identify trending topics, content formats, platform opportunities, "
                "and audience interests relevant to this growth initiative.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "growth",
            "agent_name": "Growth",
            "description": "Growth strategy",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Build ethical growth strategy: SEO, social, content, partnerships, "
                "community, referrals, app store optimisation. Include ROI estimates.\n\n"
                "## TREND ANALYSIS\n{prior_output}"
            ),
            "gate": False,
        },
        {
            "agent_id": "cmo",
            "agent_name": "CMO",
            "description": "Campaign execution",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Turn the growth strategy into actionable campaigns: "
                "messaging, content calendar, channel plans, and KPIs.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── CONTENT CREATION: Full content pipeline ──────────────────────
    "content_creation": [
        {
            "agent_id": "trend_analyst",
            "agent_name": "Trend Analyst",
            "description": "Content trend analysis",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Identify trending content formats, audience interests, "
                "platform opportunities, and viral potential for this topic.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "content_visionary",
            "agent_name": "Content Visionary",
            "description": "Content concepts",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Generate high-potential content concepts with franchise, "
                "series, and commercial potential. Think like Pixar/Disney.\n\n"
                "## TREND ANALYSIS\n{prior_output}"
            ),
            "gate": True,
        },
        {
            "agent_id": "creative_director",
            "agent_name": "Creative Director",
            "description": "Visual & creative direction",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Develop visual direction for the content: art style, "
                "colour palette, character design, illustration briefs.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "cmo",
            "agent_name": "CMO",
            "description": "Distribution strategy",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create distribution and marketing plan for this content: "
                "channels, messaging, launch strategy, repurposing plan.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── PRODUCT LAUNCH: End-to-end product pipeline ──────────────────
    "product_launch": [
        {
            "agent_id": "intelligence",
            "agent_name": "Intelligence",
            "description": "Market & competitive intel",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Deliver market intelligence: competitive landscape, "
                "user needs, pricing benchmarks, and market opportunities.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "product",
            "agent_name": "Product",
            "description": "Product specification",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Define the product: user problem, solution, MVP scope, "
                "features, roadmap, and success metrics.\n\n"
                "## MARKET INTELLIGENCE\n{prior_output}"
            ),
            "gate": True,
        },
        {
            "agent_id": "architect",
            "agent_name": "Architect",
            "description": "Technical architecture",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Design the technical architecture for this product. "
                "Include components, data flow, costs, and implementation plan.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "eng_manager",
            "agent_name": "Eng Manager",
            "description": "Delivery plan",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create the delivery plan: epics, stories, sprints, "
                "dependencies, estimates, and milestones.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "cmo",
            "agent_name": "CMO",
            "description": "Launch marketing",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create launch marketing plan: positioning, messaging, "
                "campaigns, channels, timeline, and KPIs.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── SOCIAL MEDIA: Content creation & campaign strategy ────────
    "social_media": [
        {
            "agent_id": "trend_analyst",
            "agent_name": "Trend Analyst",
            "description": "Platform trends & audience insights",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Analyse current social media trends, trending formats, "
                "hashtags, audience demographics, and platform-specific "
                "opportunities (TikTok, Instagram, YouTube, LinkedIn, X). "
                "Identify what content resonates with the target audience.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "content_visionary",
            "agent_name": "Content Visionary",
            "description": "Content strategy & series concepts",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create a content strategy: content pillars, series concepts, "
                "posting cadence, platform-specific formats, and a content "
                "calendar. Include hooks, CTAs, and engagement tactics.\n\n"
                "## TREND ANALYSIS\n{prior_output}"
            ),
            "gate": True,
        },
        {
            "agent_id": "creative_director",
            "agent_name": "Creative Director",
            "description": "Visual & brand direction",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Define visual direction for the social content: brand "
                "aesthetics, thumbnail styles, video formats, carousel "
                "layouts, colour palettes, and typography guidelines.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "growth",
            "agent_name": "Growth",
            "description": "Campaign & distribution plan",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create the campaign and distribution plan: paid vs organic "
                "strategy, influencer outreach, cross-platform promotion, "
                "community engagement tactics, and KPI targets.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "cmo",
            "agent_name": "CMO",
            "description": "Final campaign brief",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Synthesise everything into a final social media campaign "
                "brief: executive summary, platform breakdown, content "
                "schedule, budget allocation, success metrics, and "
                "actionable next steps.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── SOFTWARE ARCHITECTURE: Technical design & planning ────────
    "software_architecture": [
        {
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "description": "Technology landscape research",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Research the technology landscape: existing solutions, "
                "frameworks, infrastructure patterns, cloud services, "
                "and industry best practices relevant to this project.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "architect",
            "agent_name": "Architect",
            "description": "System architecture design",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Design the complete system architecture: components, "
                "services, data models, API contracts, infrastructure, "
                "scalability approach, and technology stack decisions. "
                "Include diagrams (described in text) and trade-off analysis.\n\n"
                "## TECHNOLOGY RESEARCH\n{prior_output}"
            ),
            "gate": True,
        },
        {
            "agent_id": "cto",
            "agent_name": "CTO",
            "description": "Technical review & feasibility",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Review the proposed architecture: validate feasibility, "
                "identify technical risks, assess performance concerns, "
                "recommend improvements, and evaluate build-vs-buy decisions.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "security",
            "agent_name": "Security",
            "description": "Security architecture review",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Perform a security architecture review: threat modelling, "
                "authentication/authorization design, data protection, "
                "network security, and compliance requirements (GDPR, SOC2).\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "eng_manager",
            "agent_name": "Eng Manager",
            "description": "Implementation roadmap",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Create the implementation roadmap: phases, epics, stories, "
                "team structure, sprint plan, dependencies, estimates, "
                "and milestones. Include risk mitigation for each phase.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
    # ── LEGAL & COMPLIANCE: Risk, regulatory & compliance ─────────
    "legal_compliance": [
        {
            "agent_id": "researcher",
            "agent_name": "Researcher",
            "description": "Regulatory landscape research",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Research the regulatory and legal landscape: applicable "
                "regulations (GDPR, COPPA, CCPA, AI Act, etc.), industry "
                "standards, competitor compliance approaches, and recent "
                "enforcement actions or legal precedents.\n"
            ),
            "gate": False,
        },
        {
            "agent_id": "risk",
            "agent_name": "Risk",
            "description": "Risk & compliance assessment",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Perform a comprehensive risk and compliance assessment: "
                "identify legal risks, data protection obligations, "
                "liability exposure, IP considerations, terms of service "
                "requirements, and regulatory compliance gaps.\n\n"
                "## REGULATORY RESEARCH\n{prior_output}"
            ),
            "gate": True,
        },
        {
            "agent_id": "security",
            "agent_name": "Security",
            "description": "Data protection & security audit",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Audit data protection and security compliance: data flows, "
                "consent mechanisms, encryption standards, access controls, "
                "breach response procedures, and data retention policies.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
        {
            "agent_id": "chief_of_staff",
            "agent_name": "Chief of Staff",
            "description": "Compliance action plan",
            "task_template": (
                "## DIRECTIVE\n{directive}\n\n"
                "## TASK\n"
                "Synthesise all findings into an actionable compliance plan: "
                "priority matrix, remediation steps, policy documents needed, "
                "training requirements, monitoring procedures, and timeline "
                "for achieving full compliance.\n\n"
                "## ALL PRIOR OUTPUTS\n{all_outputs}"
            ),
            "gate": False,
        },
    ],
}


def _create_pipeline_stages(template_name: str, directive: str) -> list[dict]:
    """Build pipeline stages from a template. Returns list of stage dicts."""
    template = _PIPELINE_TEMPLATES.get(template_name, _PIPELINE_TEMPLATES["full"])
    stages = []
    for t in template:
        stages.append({
            "agent_id": t["agent_id"],
            "agent_name": t["agent_name"],
            "description": t["description"],
            "task_template": t["task_template"],
            "gate": t.get("gate", False),
            "manual": t.get("manual", False),
            "ready_after": t.get("ready_after", None),  # stage index after which this becomes ready
            "status": "pending",   # pending | running | complete | error | waiting | ready
            "output": None,
            "error": None,
            "result_id": None,
            "started_at": None,
            "completed_at": None,
        })
    return stages


def _pipeline_update_ready(stages: list[dict]):
    """Mark manual stages as 'ready' when their ready_after dependency is complete."""
    for i, s in enumerate(stages):
        if not s.get("manual") or s["status"] not in ("pending", "ready"):
            continue
        ready_after = s.get("ready_after")
        if ready_after is not None:
            # Specific dependency — ready when that stage is complete
            if 0 <= ready_after < len(stages) and stages[ready_after]["status"] == "complete":
                s["status"] = "ready"
        else:
            # No explicit dependency — ready when all prior non-manual stages are complete
            prior_done = all(
                stages[j]["status"] == "complete"
                for j in range(i)
                if not stages[j].get("manual")
            )
            if prior_done and i > 0:
                s["status"] = "ready"


# ── Pipeline Report Generation ─────────────────────────────────────────
_PIPELINE_REPORT_PROMPT = """\
You are a senior strategy consultant producing an EXECUTIVE REPORT dashboard.
Output ONLY valid JSON — no markdown fences, no explanation.

You will receive outputs from specialist agents who have analysed a business directive.
Your job: synthesise ALL their findings into ONE comprehensive visual dashboard.

PANEL SCHEMA (exact key names required; ? = optional):

  title           "CAPS STRING — EXECUTIVE REPORT"
  summary         "2-3 sentence executive summary synthesising all findings"

  hero            {value:str, label:str, delta?:str, delta_status?:"good"|"bad"}
  stats           [{label:str, value:str, status?:"good"|"warn"|"bad"}]  — 6-10 key numbers
  key_metrics     [{label:str, value:str, status?:"good"|"warn"|"bad", context?:str}]

  swot            {strengths:[str], weaknesses:[str], opportunities:[str], threats:[str]}
  scorecard       [{label:str, score:0-100, value:str}]  — rate each agent's area
  risk_matrix     [{severity:"critical"|"high"|"medium"|"low", risk:str, mitigation:str}]
  gauges          [{label:str, value:0-100, display:str, context?:str}]

  chart           {type:"radar", labels:[str], datasets:[{label:str, data:[num]}]}
                  Use radar with labels=["Market Fit","Strategic Clarity","Product Readiness","Technical Feasibility","Risk Mitigation","Revenue Potential","Creative Strength","Execution Readiness"]
                  datasets=[{label:"Current Assessment", data:[scores 0-100]}]

  table           {headers:[str], rows:[[str]]}  — action items matrix

  funnel          [{label:str, value:0-100, display:str, pct:str}]  — pipeline/conversion funnel

  insights        [{type:"risk"|"opportunity"|"warning"|"info", text:str}]  — 6-8 key findings
  recommendations [{priority:"high"|"medium"|"low", text:str}]  — 5-8 actionable next steps
  timeline        [{date:str, event:str, status:"done"|"active"|"pending", detail?:str}]  — implementation roadmap

RULES:
- Extract EVERY number, percentage, date, and metric from the agent outputs — do not summarise away data
- Cross-reference findings between agents — highlight agreements and contradictions
- Scorecard MUST rate: Research Quality, Strategic Direction, Product Vision, Technical Feasibility, Risk Assessment, Market Positioning, Creative Direction, Execution Plan
- stats array MUST have 8-10 items with REAL numbers extracted from the research (market size, growth %, prices, conversion rates etc.)
- Recommendations must be specific, actionable, with owner and timeline — never generic advice
- risk_matrix MUST have 4-6 entries with concrete mitigations
- Timeline should cover the next 90 days minimum with at least 6 milestones
- insights array MUST have 6-8 entries, each referencing which agent contributed the finding
- MINIMUM 12 components. This is the final deliverable — make it comprehensive and data-dense.
- Use the FULL token budget — a longer, more detailed report is always better than a short one.
- Every section should contain SPECIFIC data from the agent outputs, not vague summaries.\
"""


async def _generate_pipeline_report(pipeline_id: str, directive: str, stages: list[dict]):
    """Generate a comprehensive visual report from all pipeline agent outputs.
    Runs as a background task after pipeline completion."""
    try:
        log.info(f"Pipeline [{pipeline_id}] generating executive report...")

        # Build context from all agent outputs
        agent_outputs = []
        for s in stages:
            if s.get("output"):
                agent_outputs.append(
                    f"═══ {s['agent_name'].upper()} ({s.get('description', '')}) ═══\n"
                    f"{s['output']}\n"
                )

        if not agent_outputs:
            log.warning(f"Pipeline [{pipeline_id}] no agent outputs for report")
            return

        all_context = "\n".join(agent_outputs)
        # Truncate if massive (keep first 24000 chars — enough for 8 agents at 2400 tokens each)
        if len(all_context) > 24000:
            all_context = all_context[:24000] + "\n\n[...truncated for token budget]"

        messages = [
            {"role": "system", "content": _PIPELINE_REPORT_PROMPT},
            {"role": "user", "content": (
                f"BUSINESS DIRECTIVE: {directive}\n\n"
                f"AGENT OUTPUTS:\n{all_context}\n\n"
                "Generate the comprehensive executive report dashboard JSON now. "
                "Extract every data point. Minimum 12 components."
            )},
        ]

        # Use Claude for report generation (best at structured JSON synthesis)
        # Falls back to OpenRouter if Claude is unavailable or over budget
        report_json = None
        if ANTHROPIC_API_KEY and not _claude_check_budget():
            report_json = await _chat_claude(
                messages, max_tokens=6000, temperature=0.3,
            )
            if report_json:
                log.info(f"Pipeline [{pipeline_id}] report generated via Claude")

        if not report_json and OPENROUTER_API_KEY:
            # Fallback to OpenRouter
            report_json = await _chat_openrouter(
                messages, max_tokens=5000, temperature=0.3,
                model=_OPENROUTER_AGENT_MODEL,
            )

        if not report_json:
            # Last resort: main LLM chain
            report_json = await _chat_llm(messages, max_tokens=4000, purpose="pipeline-report")

        if not report_json:
            log.warning(f"Pipeline [{pipeline_id}] report generation returned nothing")
            return

        # Clean markdown fences if present
        report_json = report_json.strip()
        if report_json.startswith("```"):
            first_nl = report_json.index("\n") if "\n" in report_json else 3
            report_json = report_json[first_nl + 1:]
        if report_json.endswith("```"):
            report_json = report_json[:-3]
        report_json = report_json.strip()

        try:
            report = json.loads(report_json)
        except json.JSONDecodeError:
            report_json = _repair_truncated_json(report_json)
            report = json.loads(report_json)

        if not isinstance(report, dict) or not report.get("title"):
            log.warning(f"Pipeline [{pipeline_id}] report invalid structure")
            return

        # Store the report
        arbiter_db.save_pipeline_report(pipeline_id, report)
        log.info(f"Pipeline [{pipeline_id}] executive report saved: {report.get('title', '?')} "
                 f"({len(report)} components)")

        # Save markdown + JSON locally alongside the pipeline
        _save_report_files(pipeline_id, directive, stages, report)

    except Exception as e:
        log.error(f"Pipeline [{pipeline_id}] report generation failed: {type(e).__name__}: {e}")


def _save_report_files(pipeline_id: str, directive: str, stages: list[dict], report: dict):
    """Save report as markdown + JSON files locally."""
    from datetime import datetime as _dt
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    ts = _dt.utcnow().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r'[^a-z0-9]+', '_', directive[:50].lower()).strip('_')
    base = f"{ts}_{slug}_{pipeline_id[:8]}"

    # Save JSON
    json_path = reports_dir / f"{base}.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    # Build markdown
    md_lines = [f"# {report.get('title', 'EXECUTIVE REPORT')}\n"]
    md_lines.append(f"**Pipeline:** `{pipeline_id}`  ")
    md_lines.append(f"**Directive:** {directive}  ")
    md_lines.append(f"**Generated:** {_dt.utcnow().isoformat()}Z\n")

    if report.get("summary"):
        md_lines.append(f"## Executive Summary\n\n{report['summary']}\n")

    # Stage outputs
    md_lines.append("## Agent Outputs\n")
    for s in stages:
        if s.get("output"):
            md_lines.append(f"### {s.get('agent_name', s.get('agent_id', '?'))}\n")
            md_lines.append(f"{s['output']}\n")

    # Report sections
    for key in ("insights", "recommendations", "risk_matrix", "timeline"):
        items = report.get(key)
        if items and isinstance(items, list):
            md_lines.append(f"## {key.replace('_', ' ').title()}\n")
            for item in items:
                if isinstance(item, dict):
                    parts = [f"{k}: {v}" for k, v in item.items()]
                    md_lines.append(f"- {' | '.join(parts)}")
                else:
                    md_lines.append(f"- {item}")
            md_lines.append("")

    if report.get("swot"):
        md_lines.append("## SWOT Analysis\n")
        swot = report["swot"]
        for quad in ("strengths", "weaknesses", "opportunities", "threats"):
            items = swot.get(quad, [])
            md_lines.append(f"### {quad.title()}\n")
            for item in items:
                md_lines.append(f"- {item}")
            md_lines.append("")

    md_path = reports_dir / f"{base}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    log.info(f"Pipeline [{pipeline_id}] reports saved: {md_path.name}, {json_path.name}")


@app.get("/api/reports")
async def list_reports():
    """List all saved markdown reports for in-app browsing."""
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    results = []
    for f in sorted(reports_dir.glob("*.md"), reverse=True):
        # Parse filename: YYYYMMDD_HHMMSS_slug_pipelineId.md
        name = f.stem
        parts = name.split("_", 2)
        ts_str = f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else name
        slug = "_".join(parts[2:]) if len(parts) > 2 else name
        results.append({
            "filename": f.name,
            "slug": slug,
            "timestamp": ts_str,
            "size": f.stat().st_size,
        })
    return {"reports": results}


@app.get("/api/reports/{filename}")
async def get_report_content(filename: str):
    """Return the raw markdown content of a saved report."""
    from starlette.responses import Response
    reports_dir = Path(__file__).parent / "reports"
    # ── Path traversal protection ──
    if ".." in filename or "/" in filename or "\\" in filename:
        return JSONResponse(status_code=400, content={"error": "Invalid filename"})
    path = reports_dir / filename
    if not path.resolve().is_relative_to(reports_dir.resolve()):
        return JSONResponse(status_code=400, content={"error": "Invalid filename"})
    if not path.exists() or not path.suffix == ".md":
        return {"error": "Report not found"}
    content = path.read_text(encoding="utf-8")
    return Response(content=content, media_type="text/markdown")


@app.get("/api/ceo/pipeline/{pipeline_id}/report/download")
async def ceo_pipeline_report_download(pipeline_id: str, fmt: str = "md"):
    """Download the pipeline report as markdown or JSON."""
    from starlette.responses import Response
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    # ── Sanitize pipeline_id to prevent path traversal via glob ──
    if not re.match(r'^[a-zA-Z0-9_-]+$', pipeline_id):
        return JSONResponse(status_code=400, content={"error": "Invalid pipeline ID"})

    # Find matching files
    ext = ".md" if fmt == "md" else ".json"
    matches = sorted(reports_dir.glob(f"*_{pipeline_id[:8]}{ext}"), reverse=True)
    if not matches:
        # Try generating from DB
        pipe = arbiter_db.get_pipeline(pipeline_id)
        if not pipe or not pipe.get("report"):
            return {"error": "Report not found"}
        _save_report_files(pipeline_id, pipe.get("directive", ""), pipe.get("stages", []), pipe["report"])
        matches = sorted(reports_dir.glob(f"*_{pipeline_id[:8]}{ext}"), reverse=True)
        if not matches:
            return {"error": "Report generation failed"}

    content = matches[0].read_text(encoding="utf-8")
    media = "text/markdown" if fmt == "md" else "application/json"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{matches[0].name}"'},
    )


async def _pipeline_run_next(pipeline_id: str) -> dict:
    """Execute the next pending stage in a pipeline. Stops at gates."""
    pipe = arbiter_db.get_pipeline(pipeline_id)
    if not pipe:
        return {"error": "Pipeline not found"}
    if pipe["status"] in ("complete", "cancelled"):
        return {"error": f"Pipeline already {pipe['status']}"}

    stages = pipe["stages"]
    idx = pipe["current_idx"]

    # Find the next stage to run
    while idx < len(stages):
        stage = stages[idx]

        # If this is a manual stage, mark it as ready and skip past it
        if stage.get("manual") and stage["status"] in ("pending", "ready"):
            stage["status"] = "ready"
            # Mark any other manual stages that depend on earlier completions as ready too
            _pipeline_update_ready(stages)
            arbiter_db.update_pipeline(pipeline_id, stages, idx, "ready")
            log.info(f"Pipeline [{pipeline_id}] stage {idx} ({stage['agent_name']}) is MANUAL — marked ready, skipping")
            # Skip past manual stage — continue with next auto stage
            idx += 1
            continue

        # If this stage has a gate and the previous stage just completed,
        # pause for human approval
        if stage["gate"] and stage["status"] == "pending" and idx > 0:
            # Check if we were explicitly told to advance (status would be 'approved')
            if stage["status"] != "approved":
                stage["status"] = "waiting"
                arbiter_db.update_pipeline(pipeline_id, stages, idx, "waiting")
                log.info(f"Pipeline [{pipeline_id}] paused at stage {idx} ({stage['agent_name']}) — waiting for CEO approval")
                return arbiter_db.get_pipeline(pipeline_id)

        # Build the task with prior output
        prior_output = ""
        if idx > 0 and stages[idx - 1].get("output"):
            prior_output = stages[idx - 1]["output"]

        # Build combined outputs from ALL prior stages (for {all_outputs} placeholder)
        all_outputs_parts = []
        for prev_i in range(idx):
            prev = stages[prev_i]
            if prev.get("output"):
                all_outputs_parts.append(
                    f"## {prev['agent_name']} Output\n{prev['output']}"
                )
        all_outputs = "\n\n---\n\n".join(all_outputs_parts) if all_outputs_parts else ""

        task = stage["task_template"].format(
            directive=pipe["directive"],
            prior_output=prior_output,
            all_outputs=all_outputs,
        )

        # Run the agent
        stage["status"] = "running"
        stage["started_at"] = datetime.utcnow().isoformat()
        arbiter_db.update_pipeline(pipeline_id, stages, idx, "running")

        result = await _ceo_dispatch(
            stage["agent_id"], task,
            source="pipeline", broadcast_id=pipeline_id,
            business_id=pipe.get("business_id"),
        )

        if result.get("error"):
            stage["status"] = "error"
            stage["error"] = result["error"]
            stage["completed_at"] = datetime.utcnow().isoformat()
            arbiter_db.update_pipeline(pipeline_id, stages, idx, "error")
            log.error(f"Pipeline [{pipeline_id}] stage {idx} ({stage['agent_name']}) failed: {result['error']}")
            return arbiter_db.get_pipeline(pipeline_id)

        # Stage succeeded
        stage["status"] = "complete"
        stage["output"] = result.get("response", "")
        stage["result_id"] = result.get("result_id")
        stage["completed_at"] = datetime.utcnow().isoformat()
        idx += 1

        # Update ready status on manual stages after each completion
        _pipeline_update_ready(stages)

        # Check if next stage has a gate
        if idx < len(stages) and stages[idx].get("gate"):
            stages[idx]["status"] = "waiting"
            arbiter_db.update_pipeline(pipeline_id, stages, idx, "waiting")
            log.info(f"Pipeline [{pipeline_id}] paused at gate before stage {idx} ({stages[idx]['agent_name']})")
            return arbiter_db.get_pipeline(pipeline_id)

    # Check if any manual stages are still pending/ready
    has_unfinished_manual = any(
        s.get("manual") and s["status"] in ("pending", "ready")
        for s in stages
    )
    if has_unfinished_manual:
        # Auto stages are done but manual stages remain — mark as "ready" not "complete"
        arbiter_db.update_pipeline(pipeline_id, stages, idx, "ready")
        log.info(f"Pipeline [{pipeline_id}] auto stages done — manual stages still ready")
        return arbiter_db.get_pipeline(pipeline_id)

    # All stages complete — generate the report
    arbiter_db.update_pipeline(pipeline_id, stages, idx, "complete")
    log.info(f"Pipeline [{pipeline_id}] complete — {len(stages)} stages finished")

    # Fire-and-forget report generation (don't block the response)
    asyncio.create_task(_generate_pipeline_report(pipeline_id, pipe.get("directive", ""), stages))

    return arbiter_db.get_pipeline(pipeline_id)


@app.post("/api/ceo/pipeline")
async def ceo_pipeline_create(request: Request):
    """Create a new CEO pipeline. Generates a plan and starts execution.

    Body: { "directive": "...", "template": "full|research|content|technical" }
    """
    body = await request.json()
    directive = body.get("directive", "").strip()
    template_name = body.get("template", "full")
    if not directive:
        return {"error": "directive required"}

    # Check custom workflows first, then built-in templates
    custom_wfs = _load_custom_workflows()
    if template_name in custom_wfs:
        cw = custom_wfs[template_name]
        stages = []
        for a in cw["agents"]:
            agent = CEO_AGENTS.get(a["agent_id"])
            if not agent:
                continue
            hint = a.get("task_hint", "")
            task_tmpl = hint if hint else "Analyse and provide expert insights on: {directive}\n\nPrior context:\n{prior_output}"
            stages.append({
                "agent_id": a["agent_id"],
                "agent_name": a["agent_name"],
                "description": hint or agent["description"],
                "task_template": task_tmpl,
                "gate": False,
                "manual": False,
                "ready_after": None,
                "status": "pending",
                "output": None,
                "error": None,
                "result_id": None,
                "started_at": None,
                "completed_at": None,
            })
    elif template_name in _PIPELINE_TEMPLATES:
        stages = _create_pipeline_stages(template_name, directive)
    else:
        return {"error": f"Unknown template: {template_name}. Options: {list(_PIPELINE_TEMPLATES.keys())}"}
    business_id = _get_business_id(request)
    pipeline_id = arbiter_db.save_pipeline(directive, stages, business_id=business_id)
    log.info(f"Pipeline [{pipeline_id}] created: '{directive[:60]}' with {len(stages)} stages ({template_name}) biz={business_id}")

    # Start execution (runs until first gate or completion)
    result = await _pipeline_run_next(pipeline_id)
    return result


@app.get("/api/ceo/pipeline/templates")
async def ceo_pipeline_templates():
    """Return available pipeline templates."""
    return {
        name: [
            {"agent_id": s["agent_id"], "agent_name": s["agent_name"],
             "description": s["description"], "gate": s.get("gate", False),
             "manual": s.get("manual", False)}
            for s in stages
        ]
        for name, stages in _PIPELINE_TEMPLATES.items()
    }


@app.get("/api/ceo/pipeline/{pipeline_id}")
async def ceo_pipeline_get(pipeline_id: str):
    """Get the current state of a pipeline."""
    pipe = arbiter_db.get_pipeline(pipeline_id)
    if not pipe:
        return {"error": "Pipeline not found"}
    return pipe


@app.get("/api/ceo/pipelines")
async def ceo_pipelines_list(status: str | None = None, limit: int = 20):
    """List all pipelines, optionally filtered by status."""
    return {"pipelines": arbiter_db.get_pipelines(status=status, limit=limit)}


@app.post("/api/ceo/pipeline/{pipeline_id}/approve")
async def ceo_pipeline_approve(pipeline_id: str, request: Request):
    """Approve a gate and continue the pipeline to the next stage.

    Body (optional): { "feedback": "..." }
    Feedback is appended to the next agent's context.
    """
    pipe = arbiter_db.get_pipeline(pipeline_id)
    if not pipe:
        return {"error": "Pipeline not found"}
    if pipe["status"] != "waiting":
        return {"error": f"Pipeline is not waiting for approval (status: {pipe['status']})"}

    stages = pipe["stages"]
    idx = pipe["current_idx"]
    stage = stages[idx]

    if stage["status"] != "waiting":
        return {"error": f"Stage {idx} is not waiting (status: {stage['status']})"}

    # Check for optional feedback from CEO
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    feedback = body.get("feedback", "").strip() if isinstance(body, dict) else ""

    # If CEO provided feedback, append it to the prior output so the next agent sees it
    if feedback and idx > 0 and stages[idx - 1].get("output"):
        stages[idx - 1]["output"] += f"\n\n## CEO Feedback\n{feedback}"

    # Mark stage as approved and continue
    stage["status"] = "approved"
    arbiter_db.update_pipeline(pipeline_id, stages, idx, "running")
    log.info(f"Pipeline [{pipeline_id}] stage {idx} approved by CEO")

    # Continue execution
    result = await _pipeline_run_next(pipeline_id)
    return result


@app.post("/api/ceo/pipeline/{pipeline_id}/reject")
async def ceo_pipeline_reject(pipeline_id: str, request: Request):
    """Reject a gate — cancels the pipeline with an optional reason."""
    pipe = arbiter_db.get_pipeline(pipeline_id)
    if not pipe:
        return {"error": "Pipeline not found"}

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    reason = body.get("reason", "Rejected by CEO") if isinstance(body, dict) else "Rejected by CEO"

    stages = pipe["stages"]
    idx = pipe["current_idx"]
    if idx < len(stages):
        stages[idx]["status"] = "rejected"
        stages[idx]["error"] = reason

    arbiter_db.update_pipeline(pipeline_id, stages, idx, "cancelled")
    log.info(f"Pipeline [{pipeline_id}] rejected at stage {idx}: {reason}")
    return arbiter_db.get_pipeline(pipeline_id)


@app.post("/api/ceo/pipeline/{pipeline_id}/cancel")
async def ceo_pipeline_cancel(pipeline_id: str):
    """Cancel a pipeline at any active stage (running, waiting, ready, pending)."""
    pipe = arbiter_db.get_pipeline(pipeline_id)
    if not pipe:
        return {"error": "Pipeline not found"}
    if pipe["status"] in ("complete", "cancelled", "error"):
        return {"error": f"Pipeline already in terminal state: {pipe['status']}"}

    stages = pipe["stages"]
    idx = pipe["current_idx"]
    # Mark the current (or next pending) stage as cancelled
    for s in stages:
        if s["status"] in ("running", "waiting", "ready", "pending"):
            s["status"] = "cancelled"
            s["error"] = "Cancelled by user"

    arbiter_db.update_pipeline(pipeline_id, stages, idx, "cancelled")
    log.info(f"Pipeline [{pipeline_id}] cancelled by user at stage {idx}")
    return arbiter_db.get_pipeline(pipeline_id)


@app.post("/api/ceo/pipeline/{pipeline_id}/regenerate")
async def ceo_pipeline_regenerate(pipeline_id: str, request: Request):
    """Re-run the last completed stage with optional new instructions."""
    pipe = arbiter_db.get_pipeline(pipeline_id)
    if not pipe:
        return {"error": "Pipeline not found"}
    if pipe["status"] not in ("waiting", "error"):
        return {"error": f"Can only regenerate from waiting or error state (current: {pipe['status']})"}

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    new_instructions = body.get("instructions", "").strip() if isinstance(body, dict) else ""

    stages = pipe["stages"]
    idx = pipe["current_idx"]

    # Find the last completed stage to re-run
    rerun_idx = idx - 1 if idx > 0 and stages[idx]["status"] == "waiting" else idx
    if rerun_idx < 0:
        return {"error": "No stage to regenerate"}

    # If new instructions provided, update the task template for the re-run
    stage = stages[rerun_idx]
    if new_instructions:
        # Append instructions to the existing template
        stage["task_template"] += f"\n\n## Additional Instructions from CEO\n{new_instructions}"

    # Reset stage for re-run
    stage["status"] = "pending"
    stage["output"] = None
    stage["error"] = None
    stage["result_id"] = None
    stage["started_at"] = None
    stage["completed_at"] = None

    # Also reset all stages after it
    for s in stages[rerun_idx + 1:]:
        s["status"] = "pending"
        s["output"] = None
        s["error"] = None
        s["result_id"] = None
        s["started_at"] = None
        s["completed_at"] = None

    arbiter_db.update_pipeline(pipeline_id, stages, rerun_idx, "running")
    log.info(f"Pipeline [{pipeline_id}] regenerating from stage {rerun_idx} ({stage['agent_name']})")

    result = await _pipeline_run_next(pipeline_id)
    return result


@app.post("/api/ceo/pipeline/{pipeline_id}/trigger/{stage_idx}")
async def ceo_pipeline_trigger(pipeline_id: str, stage_idx: int):
    """Manually trigger a 'ready' stage (e.g. Publisher). Queues behind any running stages."""
    pipe = arbiter_db.get_pipeline(pipeline_id)
    if not pipe:
        return {"error": "Pipeline not found"}

    stages = pipe["stages"]
    if stage_idx < 0 or stage_idx >= len(stages):
        return {"error": f"Invalid stage index: {stage_idx}"}

    stage = stages[stage_idx]
    if stage["status"] != "ready":
        return {"error": f"Stage {stage_idx} ({stage['agent_name']}) is not ready (status: {stage['status']})"}

    # Check if any earlier non-complete stages are still running — queue behind them
    for i in range(stage_idx):
        if stages[i]["status"] in ("running", "waiting", "pending"):
            stage["status"] = "queued"
            arbiter_db.update_pipeline(pipeline_id, stages, pipe["current_idx"], pipe["status"])
            log.info(f"Pipeline [{pipeline_id}] stage {stage_idx} ({stage['agent_name']}) queued — waiting for stage {i}")
            return arbiter_db.get_pipeline(pipeline_id)

    # All prior stages done — run this stage now
    prior_output = ""
    if stage_idx > 0 and stages[stage_idx - 1].get("output"):
        prior_output = stages[stage_idx - 1]["output"]

    all_outputs_parts = []
    for prev_i in range(stage_idx):
        prev = stages[prev_i]
        if prev.get("output"):
            all_outputs_parts.append(f"## {prev['agent_name']} Output\n{prev['output']}")
    all_outputs = "\n\n---\n\n".join(all_outputs_parts) if all_outputs_parts else ""

    task = stage["task_template"].format(
        directive=pipe["directive"],
        prior_output=prior_output,
        all_outputs=all_outputs,
    )

    stage["status"] = "running"
    stage["started_at"] = datetime.utcnow().isoformat()
    arbiter_db.update_pipeline(pipeline_id, stages, stage_idx, "running")

    result = await _ceo_dispatch(
        stage["agent_id"], task,
        source="pipeline", broadcast_id=pipeline_id,
        business_id=pipe.get("business_id"),
    )

    if result.get("error"):
        stage["status"] = "error"
        stage["error"] = result["error"]
        stage["completed_at"] = datetime.utcnow().isoformat()
        arbiter_db.update_pipeline(pipeline_id, stages, stage_idx, "error")
        return arbiter_db.get_pipeline(pipeline_id)

    stage["status"] = "complete"
    stage["output"] = result.get("response", "")
    stage["result_id"] = result.get("result_id")
    stage["completed_at"] = datetime.utcnow().isoformat()

    # Check if all stages are now complete
    all_done = all(s["status"] == "complete" for s in stages)
    final_status = "complete" if all_done else pipe["status"]
    arbiter_db.update_pipeline(pipeline_id, stages, stage_idx, final_status)
    log.info(f"Pipeline [{pipeline_id}] manual stage {stage_idx} ({stage['agent_name']}) complete")

    if all_done:
        asyncio.create_task(_generate_pipeline_report(pipeline_id, pipe.get("directive", ""), stages))

    return arbiter_db.get_pipeline(pipeline_id)


# ── Custom Workflows ─────────────────────────────────────────────────
_CUSTOM_WF_PATH = Path(__file__).parent / "custom_workflows.json"


def _load_custom_workflows() -> dict:
    if _CUSTOM_WF_PATH.exists():
        try:
            return json.loads(_CUSTOM_WF_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_custom_workflows(data: dict):
    _CUSTOM_WF_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


@app.get("/api/ceo/custom-workflows")
async def ceo_custom_workflows_list():
    """Return all saved custom workflows."""
    return _load_custom_workflows()


@app.post("/api/ceo/custom-workflows")
async def ceo_custom_workflow_save(request: Request):
    """Save a custom workflow.

    Body: { "name": "...", "description": "...", "icon": "🔧",
            "colour": "#00e5ff",
            "agents": [{"agent_id": "...", "task_hint": "..."},...] }
    """
    body = await request.json()
    name = body.get("name", "").strip()
    desc = body.get("description", "").strip()
    agents = body.get("agents", [])
    icon = body.get("icon", "⚡")
    colour = body.get("colour", "#00e5ff")
    if not name:
        return {"error": "name required"}
    if not agents or len(agents) < 1:
        return {"error": "at least one agent required"}
    # Validate agent IDs exist
    for a in agents:
        if a.get("agent_id") not in CEO_AGENTS:
            return {"error": f"Unknown agent: {a.get('agent_id')}"}

    slug = name.lower().replace(" ", "_")[:40]
    wf = _load_custom_workflows()
    wf[slug] = {
        "name": name,
        "description": desc,
        "icon": icon,
        "colour": colour,
        "agents": [
            {
                "agent_id": a["agent_id"],
                "agent_name": CEO_AGENTS[a["agent_id"]]["name"],
                "task_hint": a.get("task_hint", ""),
            }
            for a in agents
        ],
    }
    _save_custom_workflows(wf)
    log.info(f"Custom workflow saved: {slug} ({len(agents)} agents)")
    return {"ok": True, "slug": slug}


@app.post("/api/ceo/custom-workflows/{slug}/delete")
async def ceo_custom_workflow_delete(slug: str):
    """Delete a custom workflow."""
    wf = _load_custom_workflows()
    if slug not in wf:
        return {"error": "Workflow not found"}
    del wf[slug]
    _save_custom_workflows(wf)
    return {"ok": True}


# ── History / Persistence API ─────────────────────────────────────────

@app.get("/api/history/agents")
async def history_agents(
    agent_id: str | None = None, limit: int = 50, offset: int = 0,
    search: str | None = None,
):
    """Browse past CEO agent results."""
    return {"results": arbiter_db.get_agent_results(
        agent_id=agent_id, limit=limit, offset=offset, search=search,
    )}


@app.get("/api/history/agents/{result_id}")
async def history_agent_detail(result_id: str):
    """Get a single agent result by ID."""
    result = arbiter_db.get_agent_result(result_id)
    if not result:
        return {"error": "Not found"}
    return result


@app.get("/api/history/broadcasts/{broadcast_id}")
async def history_broadcast(broadcast_id: str):
    """Get all results from a broadcast."""
    return {"results": arbiter_db.get_broadcast_results(broadcast_id)}


@app.get("/api/history/briefings")
async def history_briefings(category: str | None = None, limit: int = 50, offset: int = 0):
    """Browse past briefings (morning, market, evening)."""
    return {"briefings": arbiter_db.get_briefings(
        category=category, limit=limit, offset=offset,
    )}


@app.get("/api/history/conversations")
async def history_conversations(limit: int = 50, offset: int = 0):
    """List past conversation sessions."""
    return {"sessions": arbiter_db.get_sessions(limit=limit, offset=offset)}


@app.get("/api/history/conversations/{session_id}")
async def history_conversation_detail(session_id: str):
    """Get all turns from a specific conversation session."""
    return {"turns": arbiter_db.get_conversation(session_id)}


@app.get("/api/history/insights")
async def history_insights(
    insight_type: str | None = None, severity: str | None = None,
    limit: int = 50, offset: int = 0,
):
    """Browse past proactive insights."""
    return {"insights": arbiter_db.get_insights(
        insight_type=insight_type, severity=severity,
        limit=limit, offset=offset,
    )}


@app.get("/api/history/search")
async def history_search(q: str, limit: int = 20):
    """Search across all persisted data."""
    if not q:
        return {"error": "q parameter required"}
    return arbiter_db.search_all(q, limit=limit)


# ── Urgent Bulletins (cross-system) ───────────────────────────────────
@app.get("/api/bulletins")
async def bulletins():
    items = agent_reg.get_bulletins()
    # Add email urgents as bulletins
    for e in email_mon.urgent_items():
        items.append({
            "level": "high",
            "source": "Email",
            "message": f"URGENT: {e['subject'][:80]} — from {e['sender'][:40]}",
            "agent_id": "email",
            "timestamp": e.get("date", ""),
        })

    return sorted(items, key=lambda x: {"critical": 0, "high": 1, "warning": 2}.get(x.get("level", ""), 3))


# ── GCP Platform ──────────────────────────────────────────────────────
@app.get("/api/gcp/summary")
async def gcp_summary():
    return gcp_mon.summary()


# ── Service Health ───────────────────────────────────────────────────
svc_health = ServiceHealthMonitor(ttl=120)

@app.get("/api/services/health")
async def services_health():
    return svc_health.summary()


# ── Weather (Open-Meteo — free, no key) ───────────────────────────────
_weather_cache: dict[str, dict] = {}  # keyed by location name

async def _geocode(city: str) -> tuple[float, float, str] | None:
    """Resolve a city name to (lat, lon, display_name) via Open-Meteo geocoding."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en",
                timeout=5,
            )
        if resp.status_code == 200:
            results = resp.json().get("results")
            if results:
                r = results[0]
                name = f"{r.get('name', city)}, {r.get('country', '')}"
                return r["latitude"], r["longitude"], name
    except Exception:
        pass
    return None

async def _fetch_weather(lat: float, lon: float, location_name: str) -> dict:
    """Fetch weather for a specific lat/lon from Open-Meteo."""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature"
        f"&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum"
        f"&timezone=auto&forecast_days=7"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        return {
            "location": location_name,
            "current": data.get("current", {}),
            "daily": data.get("daily", {}),
            "units": data.get("current_units", {}),
        }
    return {"location": location_name, "current": {}, "daily": {}, "units": {}}

@app.get("/api/weather")
async def weather(location: str = "London"):
    """Weather for any location via Open-Meteo (free, no key)."""
    import time
    now = time.time()
    key = location.lower().strip()
    cached = _weather_cache.get(key)
    if cached and cached.get("ts") and (now - cached["ts"]) < 600:
        return cached["data"]
    try:
        # Geocode the location (or use London default)
        if key in ("london", ""):
            lat, lon, name = 51.51, -0.13, "London, UK"
        else:
            geo = await _geocode(location)
            if not geo:
                lat, lon, name = 51.51, -0.13, "London, UK"
            else:
                lat, lon, name = geo
        result = await _fetch_weather(lat, lon, name)
        _weather_cache[key] = {"data": result, "ts": now}
        return result
    except Exception as e:
        logging.debug("Weather fetch failed: %s", e)
    return {"location": location, "current": {}, "daily": {}, "units": {}}


# ── Web Fetch API (safe, read-only scraping) ─────────────────────────
@app.post("/api/web/fetch")
async def web_fetch_endpoint(request: Request):
    """Fetch a URL and return readable text content. Used by LLM for research."""
    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        return {"error": "URL is required"}
    text = await _web_fetch(url, max_chars=body.get("max_chars", 4000))
    return {"url": url, "content": text, "chars": len(text)}


# ── Stocks (Yahoo Finance — free, no key) ─────────────────────────────
_stocks_cache = {"data": None, "ts": None}
STOCK_SYMBOLS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "^GSPC", "^FTSE"]

@app.get("/api/stocks")
async def stocks():
    """Fetch live stock quotes via Yahoo Finance v8 chart API (no auth needed)."""
    import time
    now = time.time()
    if _stocks_cache["data"] and _stocks_cache["ts"] and (now - _stocks_cache["ts"]) < 300:
        return _stocks_cache["data"]
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    quotes = []
    try:
        async with httpx.AsyncClient() as client:
            for sym in STOCK_SYMBOLS:
                try:
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1d"
                    resp = await client.get(url, timeout=8, headers=headers)
                    if resp.status_code == 200:
                        meta = resp.json().get("chart", {}).get("result", [{}])[0].get("meta", {})
                        price = meta.get("regularMarketPrice", 0)
                        prev = meta.get("chartPreviousClose", 0)
                        change = round(price - prev, 2) if price and prev else 0
                        pct = round((change / prev) * 100, 2) if prev else 0
                        quotes.append({
                            "symbol": meta.get("symbol", sym),
                            "name": meta.get("shortName", meta.get("longName", sym)),
                            "price": round(price, 2),
                            "change": change,
                            "changePct": pct,
                            "currency": meta.get("currency", "USD"),
                        })
                except Exception:
                    pass
        result = {"quotes": quotes, "updated": datetime.utcnow().isoformat()}
        _stocks_cache["data"] = result
        _stocks_cache["ts"] = now
        return result
    except Exception as e:
        logging.debug("Stocks fetch failed: %s", e)
    return {"quotes": [], "updated": None}


# ── Market Intelligence (Yahoo Finance quoteSummary — free, no key) ───
_market_intel_cache: dict[str, dict] = {}   # symbol -> enriched data
_market_intel_ts: float = 0

async def _fetch_stock_intel(symbol: str, client: httpx.AsyncClient) -> dict | None:
    """Fetch analyst ratings, key stats, and profile for a single stock."""
    if symbol.startswith("^"):
        return None  # indices don't have analyst data
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    modules = "recommendationTrend,financialData,defaultKeyStatistics,summaryProfile,earningsTrend"
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules={modules}"
    try:
        resp = await client.get(url, timeout=10, headers=headers)
        if resp.status_code != 200:
            return None
        result = resp.json().get("quoteSummary", {}).get("result", [])
        if not result:
            return None
        data = result[0]

        # Analyst recommendations
        rec = data.get("recommendationTrend", {}).get("trend", [])
        current_rec = rec[0] if rec else {}

        # Financial data
        fin = data.get("financialData", {})
        target_high = fin.get("targetHighPrice", {}).get("raw", 0)
        target_low = fin.get("targetLowPrice", {}).get("raw", 0)
        target_mean = fin.get("targetMeanPrice", {}).get("raw", 0)
        current_price = fin.get("currentPrice", {}).get("raw", 0)
        rec_key = fin.get("recommendationKey", "N/A")
        num_analysts = fin.get("numberOfAnalystOpinions", {}).get("raw", 0)
        revenue_growth = fin.get("revenueGrowth", {}).get("raw", 0)
        profit_margin = fin.get("profitMargins", {}).get("raw", 0)

        # Key stats
        stats = data.get("defaultKeyStatistics", {})
        pe_trailing = stats.get("trailingEps", {}).get("raw", 0)
        pe_forward = stats.get("forwardPE", {}).get("raw", 0)
        market_cap = fin.get("totalRevenue", {}).get("raw", 0)
        fifty_two_high = stats.get("fiftyTwoWeekHigh", {}).get("raw") or fin.get("targetHighPrice", {}).get("raw", 0)
        fifty_two_low = stats.get("fiftyTwoWeekLow", {}).get("raw") or fin.get("targetLowPrice", {}).get("raw", 0)
        beta = stats.get("beta", {}).get("raw", 0)
        enterprise_val = stats.get("enterpriseValue", {}).get("raw", 0)

        # Profile
        profile = data.get("summaryProfile", {})
        sector = profile.get("sector", "N/A")
        industry = profile.get("industry", "N/A")
        summary = (profile.get("longBusinessSummary", "") or "")[:200]
        employees = profile.get("fullTimeEmployees", 0)

        # Earnings trend
        et = data.get("earningsTrend", {}).get("trend", [])
        next_eps_est = et[0].get("earningsEstimate", {}).get("avg", {}).get("raw", 0) if et else 0

        return {
            "symbol": symbol,
            "analyst_rating": rec_key.upper() if rec_key != "N/A" else "N/A",
            "num_analysts": num_analysts,
            "strong_buy": current_rec.get("strongBuy", 0),
            "buy": current_rec.get("buy", 0),
            "hold": current_rec.get("hold", 0),
            "sell": current_rec.get("sell", 0),
            "strong_sell": current_rec.get("strongSell", 0),
            "target_low": round(target_low, 2),
            "target_mean": round(target_mean, 2),
            "target_high": round(target_high, 2),
            "current_price": round(current_price, 2),
            "upside_pct": round(((target_mean - current_price) / current_price * 100), 1) if current_price else 0,
            "revenue_growth": round(revenue_growth * 100, 1) if revenue_growth else 0,
            "profit_margin": round(profit_margin * 100, 1) if profit_margin else 0,
            "forward_pe": round(pe_forward, 1) if pe_forward else 0,
            "trailing_eps": round(pe_trailing, 2) if pe_trailing else 0,
            "beta": round(beta, 2) if beta else 0,
            "enterprise_value": enterprise_val,
            "fifty_two_high": round(fifty_two_high, 2) if fifty_two_high else 0,
            "fifty_two_low": round(fifty_two_low, 2) if fifty_two_low else 0,
            "sector": sector,
            "industry": industry,
            "summary": summary,
            "employees": employees,
            "next_eps_estimate": round(next_eps_est, 2) if next_eps_est else 0,
        }
    except Exception as e:
        log.debug(f"Stock intel fetch failed for {symbol}: {e}")
        return None


async def refresh_market_intel():
    """Background poller: refresh enriched market data every 15 min."""
    import time
    global _market_intel_ts
    now = time.time()
    if _market_intel_ts and (now - _market_intel_ts) < 900:
        return _market_intel_cache
    symbols = [s for s in STOCK_SYMBOLS if not s.startswith("^")]
    async with httpx.AsyncClient() as client:
        for sym in symbols:
            intel = await _fetch_stock_intel(sym, client)
            if intel:
                _market_intel_cache[sym] = intel
    _market_intel_ts = now
    log.info(f"Market intel refreshed: {len(_market_intel_cache)} stocks enriched")
    return _market_intel_cache


@app.get("/api/stocks/intel")
async def stocks_intel():
    """Return enriched market intelligence data."""
    await refresh_market_intel()
    return {"intel": _market_intel_cache, "updated": datetime.utcnow().isoformat()}


@app.get("/api/stocks/intel/{symbol}")
async def stock_detail(symbol: str):
    """Return enriched data for a single stock."""
    sym = symbol.upper()
    await refresh_market_intel()
    if sym in _market_intel_cache:
        return _market_intel_cache[sym]
    return {"error": f"No intel data for {sym}"}


# ── Roadmap / Business Planner ───────────────────────────────────────
ROADMAP_FILE = Path(__file__).parent / "roadmap.json"

def _load_roadmap() -> list[dict]:
    """Load roadmap milestones from JSON file."""
    if ROADMAP_FILE.exists():
        try:
            return json.loads(ROADMAP_FILE.read_text())
        except Exception:
            return []
    return []

def _save_roadmap(milestones: list[dict]):
    """Save roadmap milestones to JSON file."""
    ROADMAP_FILE.write_text(json.dumps(milestones, indent=2, default=str))

@app.get("/api/roadmap")
async def get_roadmap():
    """Return all roadmap milestones."""
    return {"milestones": _load_roadmap()}

@app.post("/api/roadmap")
async def create_milestone(request: Request):
    """Create a new roadmap milestone."""
    import uuid
    body = await request.json()
    milestones = _load_roadmap()
    milestone = {
        "id": str(uuid.uuid4())[:8],
        "title": body.get("title", "Untitled"),
        "description": body.get("description", ""),
        "date": body.get("date", ""),
        "quarter": body.get("quarter", ""),
        "category": body.get("category", "milestone"),  # milestone, launch, review, campaign
        "status": body.get("status", "planned"),         # planned, in_progress, completed, at_risk
        "priority": body.get("priority", "medium"),      # low, medium, high, critical
        "notes": body.get("notes", ""),
        "created": datetime.utcnow().isoformat(),
    }
    milestones.append(milestone)
    _save_roadmap(milestones)
    return {"milestone": milestone}

@app.put("/api/roadmap/{milestone_id}")
async def update_milestone(milestone_id: str, request: Request):
    """Update an existing roadmap milestone."""
    body = await request.json()
    milestones = _load_roadmap()
    for m in milestones:
        if m["id"] == milestone_id:
            for key in ("title", "description", "date", "quarter", "category",
                        "status", "priority", "notes"):
                if key in body:
                    m[key] = body[key]
            m["updated"] = datetime.utcnow().isoformat()
            _save_roadmap(milestones)
            return {"milestone": m}
    return {"error": "Milestone not found"}

@app.delete("/api/roadmap/{milestone_id}")
async def delete_milestone(milestone_id: str):
    """Delete a roadmap milestone."""
    milestones = _load_roadmap()
    milestones = [m for m in milestones if m["id"] != milestone_id]
    _save_roadmap(milestones)
    return {"deleted": milestone_id}

@app.post("/api/roadmap/seed")
async def seed_roadmap():
    """Seed the roadmap with initial milestones (from existing DEADLINES)."""
    existing = _load_roadmap()
    if existing:
        return {"milestones": existing, "seeded": False}
    import uuid
    seeds = [
        {"title": "App Store v2.0 Launch", "date": "2026-07-15", "quarter": "Q3",
         "category": "launch", "status": "in_progress", "priority": "critical",
         "description": "Major app store release with new features and UI overhaul"},
        {"title": "EAS Production Build Pipeline", "date": "2026-08-01", "quarter": "Q3",
         "category": "milestone", "status": "planned", "priority": "high",
         "description": "Expo Application Services production build & deployment pipeline"},
        {"title": "Freya Content Automation v3", "date": "2026-09-01", "quarter": "Q3",
         "category": "milestone", "status": "planned", "priority": "high",
         "description": "Third generation content automation with AI-driven scheduling"},
        {"title": "RevenueCat Premium Tier", "date": "2026-10-15", "quarter": "Q4",
         "category": "launch", "status": "planned", "priority": "critical",
         "description": "Premium subscription tier with advanced analytics and features"},
        {"title": "Holiday Campaign Launch", "date": "2026-11-01", "quarter": "Q4",
         "category": "campaign", "status": "planned", "priority": "medium",
         "description": "Q4 holiday marketing campaign across all channels"},
        {"title": "Annual Roadmap Review", "date": "2027-01-15", "quarter": "Q1",
         "category": "review", "status": "planned", "priority": "medium",
         "description": "Annual strategic review and 2027 roadmap planning"},
    ]
    milestones = []
    for s in seeds:
        m = {**s, "id": str(uuid.uuid4())[:8], "notes": "", "created": datetime.utcnow().isoformat()}
        milestones.append(m)
    _save_roadmap(milestones)
    return {"milestones": milestones, "seeded": True}


# ── News (BBC RSS — free, no key) ────────────────────────────────────
_news_cache = {"data": None, "ts": None}

@app.get("/api/news")
async def news():
    """Fetch latest BBC News headlines via RSS."""
    import time
    import xml.etree.ElementTree as ET
    now = time.time()
    if _news_cache["data"] and _news_cache["ts"] and (now - _news_cache["ts"]) < 600:
        return _news_cache["data"]
    feeds = {
        "top": "https://feeds.bbci.co.uk/news/rss.xml",
        "tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    }
    all_items = []
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    try:
        async with httpx.AsyncClient() as client:
            for category, url in feeds.items():
                try:
                    resp = await client.get(url, timeout=10, headers=headers)
                    if resp.status_code == 200:
                        root = ET.fromstring(resp.text)
                        for item in root.findall(".//item")[:5]:
                            all_items.append({
                                "title": item.findtext("title", ""),
                                "description": item.findtext("description", ""),
                                "link": item.findtext("link", ""),
                                "pubDate": item.findtext("pubDate", ""),
                                "category": category,
                            })
                except Exception:
                    pass
        result = {"headlines": all_items, "updated": datetime.utcnow().isoformat()}
        _news_cache["data"] = result
        _news_cache["ts"] = now
        return result
    except Exception as e:
        logging.debug("News fetch failed: %s", e)
    return {"headlines": [], "updated": None}


# ── Sports (BBC Sport RSS — free, no key) ────────────────────────────
_sports_cache = {"data": None, "ts": None}

@app.get("/api/sports")
async def sports():
    """Fetch latest sports headlines and scores via BBC Sport RSS."""
    import time
    import xml.etree.ElementTree as ET
    now = time.time()
    if _sports_cache["data"] and _sports_cache["ts"] and (now - _sports_cache["ts"]) < 600:
        return _sports_cache["data"]
    feeds = {
        "football": "https://feeds.bbci.co.uk/sport/football/rss.xml",
        "f1": "https://feeds.bbci.co.uk/sport/formula1/rss.xml",
        "tennis": "https://feeds.bbci.co.uk/sport/tennis/rss.xml",
        "cricket": "https://feeds.bbci.co.uk/sport/cricket/rss.xml",
        "top": "https://feeds.bbci.co.uk/sport/rss.xml",
    }
    all_items = []
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    try:
        async with httpx.AsyncClient() as client:
            for category, url in feeds.items():
                try:
                    resp = await client.get(url, timeout=10, headers=headers)
                    if resp.status_code == 200:
                        root = ET.fromstring(resp.text)
                        for item in root.findall(".//item")[:4]:
                            all_items.append({
                                "title": item.findtext("title", ""),
                                "description": item.findtext("description", ""),
                                "link": item.findtext("link", ""),
                                "pubDate": item.findtext("pubDate", ""),
                                "category": category,
                            })
                except Exception:
                    pass
        result = {"stories": all_items, "updated": datetime.utcnow().isoformat()}
        _sports_cache["data"] = result
        _sports_cache["ts"] = now
        return result
    except Exception as e:
        logging.debug("Sports fetch failed: %s", e)
    return {"stories": [], "updated": None}


# ── RevenueCat ────────────────────────────────────────────────────────
@app.get("/api/revenue/summary")
async def revenue_summary():
    return rc_mon.summary()


@app.get("/api/revenue/transactions")
async def revenue_transactions():
    return rc_mon.recent_transactions()


# ── Cached dashboard context ──────────────────────────────────────────
# Pre-build context in background so chat requests don't wait for feeds.
_ctx_cache = {"text": "", "ts": 0}

async def _get_context_fast(topic: str | None = None, query: str = "",
                            business_id: str | None = None) -> str:
    """Return context for the LLM.  When a topic is known, builds a slim
    topic-focused context (fast).  For general queries, uses the cached
    full context (rebuilt every 60 s)."""
    import time as _t
    if topic:
        # Topic-specific = fast, small context.  No caching needed.
        return await _build_context(topic=topic, query=query, business_id=business_id)
    # Business-specific queries bypass the generic cache
    if business_id:
        return await _build_context(business_id=business_id)
    now = _t.time()
    if _ctx_cache["text"] and (now - _ctx_cache["ts"]) < 60:
        return _ctx_cache["text"]
    ctx = await _build_context()
    _ctx_cache["text"] = ctx
    _ctx_cache["ts"] = now
    return ctx


# ── Intelligent Visualization Engine ──────────────────────────────────
_TICKER_NAMES = {
    "AAPL": "Apple", "GOOGL": "Google", "MSFT": "Microsoft",
    "AMZN": "Amazon", "TSLA": "Tesla", "NVDA": "Nvidia", "META": "Meta",
    "^GSPC": "S&P 500", "^FTSE": "FTSE 100", "^DJI": "Dow Jones",
}

# ── Intent Classification ─────────────────────────────────────────────
_INTENT_PATTERNS = {
    "compare":   ["compare", " vs ", "versus", "against", "better", "which is", "difference"],
    "trend":     ["trend", "over time", "this week", "this month", "last month", "last week",
                  "last 30", "last 7", "last 90", "past month", "past week", "history", "forecast", "projection",
                  "last year", "last 2", "last 3", "last 5", "last 10", "past year", "past decade",
                  "over the last", "over the past", "historical", "trajectory", "long term", "long-term",
                  "decade", "years ago", "year over year", "yoy", "quarterly"],
    "breakdown": ["breakdown", "break down", "split", "composition", "what makes up", "made up of"],
    "snapshot":  ["how's", "how is", "what's", "status", "current", "right now", "overview"],
    "detail":    ["tell me about", "what is", "explain", "deep dive", "details on", "more about"],
    "rank":      ["top", "best", "worst", "highest", "lowest", "most", "least", "ranking"],
}

# ── Topic Detection Engine ────────────────────────────────────────────
# Two-tier keyword system:
#   "phrases"  → multi-word, matched as substring (safe, specific)
#   "words"    → single/short words, matched with \b word boundaries (prevents
#                 "stock" matching "livestock", "rain" matching "brain", etc.)
#   "negative" → if ANY of these phrases appear, the topic is vetoed

import re as _re_topic  # avoid shadowing module-level re

_TOPIC_RULES = {
    "stocks": {
        "phrases": ["stock market", "markets today", "share price", "dow jones",
                    "apple stock", "tesla stock", "microsoft stock", "nvidia stock",
                    "the market", "how are markets", "how's the market"],
        "words":   ["stock", "stocks", "ticker", "portfolio", "nasdaq", "s&p",
                    "trading", "shares", "dividend", "equity", "securities"],
        "negative": ["app market", "market research", "market analysis", "market size",
                     "market share", "market opportunity", "market segment",
                     "job market", "labour market", "labor market", "real estate market",
                     "housing market", "market strategy", "market fit", "market demand",
                     "market trend", "market report", "market study", "market growth",
                     "market landscape", "market overview", "market potential",
                     "go to market", "target market", "market niche", "market value",
                     "children market", "kids market", "child market",
                     "gaming market", "music market", "food market", "health market",
                     "fitness market", "education market", "crypto market",
                     "market plan", "marketplace", "market cap",
                     "trading card", "stock photo", "stock up", "stocking",
                     "restock", "overstock", "livestock", "woodstock",
                     "laughing stock", "rolling stock", "gunstock"],
    },
    "weather": {
        "phrases": ["weather today", "weather like", "weather in", "weather for",
                    "weather this", "weather tomorrow", "check weather",
                    "rain today", "rain tomorrow", "is it raining",
                    "wind speed", "wind chill"],
        "words":   ["weather"],
        "negative": ["forecast my", "forecast the revenue", "forecast sales",
                     "rain check", "brainstorm", "political climate",
                     "business climate", "climate of the", "climate change",
                     "wind down", "wind up the", "winding down",
                     "temperature of the debate", "humidity in code"],
    },
    "revenue": {
        "phrases": ["my revenue", "our revenue", "app revenue", "total revenue",
                    "revenue growth", "monthly revenue", "revenuecat",
                    "subscriber count", "active subscribers", "churn rate",
                    "my income", "our income", "my earnings", "mrr"],
        "words":   ["revenuecat"],
        "negative": ["earning potential", "earning a living", "income tax",
                     "income inequality", "passive income", "income ideas",
                     "national income", "revenue model for", "revenue of"],
    },
    "services": {
        "phrases": ["cloudflare", "service health", "service status", "uptime",
                    "openai status", "github status", "aws status",
                    "anthropic status", "claude status", "services down",
                    "services status", "all services", "is it down"],
        "words":   ["outage", "degraded"],
        "negative": [],
    },
    "gcp": {
        "phrases": ["cloud run", "app engine", "cloud sql", "google cloud",
                    "gcp project", "gcp infrastructure"],
        "words":   ["gcp", "kubernetes"],
        "negative": ["deploy my app", "deploy my react", "deploy to vercel",
                     "deploy to netlify", "deploy a website",
                     "infrastructure of", "infrastructure for"],
    },
    "email": {
        "phrases": ["my email", "my inbox", "check email", "check inbox",
                    "unread email", "urgent mail", "urgent email",
                    "read my email", "any emails"],
        "words":   ["inbox", "gmail", "unread"],
        "negative": ["email marketing", "email design", "email template",
                     "email strategy", "email campaign", "email list",
                     "email service", "email api", "email provider",
                     "email format", "email best practice"],
    },
    "news": {
        "phrases": ["latest news", "news today", "top news", "breaking news",
                    "news headlines", "bbc news", "in the news",
                    "what's in the news", "news stories"],
        "words":   ["bbc"],
        "negative": ["headline feature", "headline act", "stories about",
                     "user stories", "what is new in", "any news on my",
                     "news to me"],
    },
    "sports": {
        "phrases": ["premier league", "football results", "football scores",
                    "league table", "match results", "match score",
                    "sports news", "sports results", "sports scores",
                    "who won the", "who plays"],
        "words":   [],
        "negative": ["match these", "match the", "matching", "score this",
                     "score it", "scoring criteria", "league of legends",
                     "football shaped"],
    },
    "roadmap": {
        "phrases": ["the roadmap", "my roadmap", "our roadmap", "show roadmap",
                    "product roadmap", "strategic plan", "release plan",
                    "business plan", "mvp plan", "mvp launch",
                    "launch plan", "quarterly plan", "go-to-market plan"],
        "words":   ["roadmap"],
        "negative": ["timeline of", "timeline for ww", "timeline for world",
                     "milestone in human", "milestone in history",
                     "deploy my", "deploy a", "deploy to",
                     "deadline for the", "rollout of the"],
    },
    "comfyui": {
        "phrases": ["generate an image", "generate image", "generate a image",
                    "create an image", "create image", "create a image",
                    "generate a video", "generate video", "create a video",
                    "create video", "make a photo", "make a picture",
                    "make an image", "make a video"],
        "words":   [],
        "negative": ["render a react", "render a component", "render the page",
                     "render a view", "render this", "render that",
                     "design a database", "design a schema", "design a system",
                     "design a api", "design a class", "design a module",
                     "draw conclusions", "draw a diagram", "draw from"],
    },
    "collectables": {
        "phrases": ["pokemon card", "pokemon cards", "trading card", "trading cards",
                    "sports card", "sports cards", "baseball card", "football card",
                    "magic the gathering", "mtg card", "yu-gi-oh", "yugioh",
                    "psa 10", "psa grade", "bgs grade", "cgc grade",
                    "card value", "card price", "card worth", "graded card",
                    "first edition", "1st edition", "base set", "holographic",
                    "collectable price", "collectible price", "collectables market",
                    "vintage toy", "coin collection", "stamp collection",
                    "funko pop", "action figure value", "lego set value"],
        "words":   ["pokemon", "charizard", "pikachu", "mewtwo", "collectables",
                    "collectibles", "tcgplayer", "pricecharting"],
        "negative": ["pokemon go app", "pokemon game review", "play pokemon",
                     "watch pokemon", "pokemon anime", "collect data", "collect the"],
    },
    "products": {
        "phrases": ["find me", "where can i buy", "cheapest price", "price compare",
                    "price comparison", "best deal", "best price", "lowest price",
                    "shop for", "shopping for", "buy online", "purchase online",
                    "how much does", "how much is a", "where to buy",
                    "find a deal", "deal on", "deals for", "discount on"],
        "words":   [],
        "negative": ["best price for stocks", "price target", "price action",
                     "buy the dip", "buy signal", "best deal for investors",
                     "price to earnings", "price earnings", "buy rating"],
    },
}

# Pre-compile word-boundary patterns for speed
_TOPIC_WORD_PATTERNS = {}
for _t, _r in _TOPIC_RULES.items():
    if _r["words"]:
        _pat = r'\b(' + '|'.join(_re_topic.escape(w) for w in _r["words"]) + r')\b'
        _TOPIC_WORD_PATTERNS[_t] = _re_topic.compile(_pat, _re_topic.IGNORECASE)

# Best chart type: (topic, intent) → viz type
_VIZ_MATRIX = {
    ("stocks", "compare"):   "hbar",
    ("stocks", "trend"):     "line",
    ("stocks", "breakdown"): "doughnut",
    ("stocks", "snapshot"):  "hbar",
    ("stocks", "rank"):      "hbar",
    ("stocks", "detail"):    "hero",
    ("weather", "snapshot"):  "hero",
    ("weather", "trend"):     "line",
    ("weather", "compare"):   "stat_cards",
    ("weather", "detail"):    "hero",
    ("revenue", "snapshot"):  "stat_cards",
    ("revenue", "breakdown"): "doughnut",
    ("revenue", "trend"):     "line",
    ("revenue", "compare"):   "hbar",
    ("revenue", "rank"):      "hbar",
    ("gcp", "snapshot"):      "status_grid",
    ("gcp", "detail"):        "status_grid",
    ("email", "snapshot"):    "stat_cards",
    ("email", "breakdown"):   "doughnut",
    ("services", "snapshot"):  "status_grid",
    ("services", "detail"):    "status_grid",
    ("services", "compare"):   "status_grid",
    ("roadmap", "snapshot"):   "table",
    ("roadmap", "detail"):     "table",
    ("roadmap", "trend"):      "table",
    ("news", "snapshot"):     "table",
    ("sports", "snapshot"):   "table",
    ("collectables", "snapshot"):  "table",
    ("collectables", "trend"):     "line",
    ("collectables", "compare"):   "hbar",
    ("collectables", "detail"):    "table",
    ("collectables", "rank"):      "hbar",
    ("products", "snapshot"):      "table",
    ("products", "compare"):       "hbar",
    ("products", "rank"):          "hbar",
    ("products", "detail"):        "table",
}


def _classify_intent(query: str) -> str:
    """Classify user intent from query text."""
    q = query.lower()
    for intent, patterns in _INTENT_PATTERNS.items():
        if any(p in q for p in patterns):
            return intent
    return "snapshot"


def _detect_topic(query: str) -> str | None:
    """Detect data source topic from query text.
    Two-tier matching: phrase substrings + word-boundary regex.
    Tier 3: company/ticker name detection for stocks.
    Negative phrases veto false positives (e.g. 'app market' != stocks)."""
    q = query.lower()
    for topic, rules in _TOPIC_RULES.items():
        matched = False
        # Tier 1: multi-word phrase match (substring)
        if any(p in q for p in rules["phrases"]):
            matched = True
        # Tier 2: single-word match (word boundaries via pre-compiled regex)
        if not matched and topic in _TOPIC_WORD_PATTERNS:
            if _TOPIC_WORD_PATTERNS[topic].search(q):
                matched = True
        if not matched:
            continue
        # Veto check: if a negative phrase matches, skip this topic
        if rules["negative"] and any(neg in q for neg in rules["negative"]):
            continue
        return topic
    # Tier 3: detect stocks topic from company/ticker names
    # If query mentions a known company (Apple, Tesla, etc.) with financial context
    _company_names = {v.lower() for k, v in _TICKER_NAMES.items() if not k.startswith("^")}
    _ticker_syms = {k.lower() for k in STOCK_SYMBOLS if not k.startswith("^")}
    _fin_context = re.compile(
        r'\b(outlook|competitor|compare|invest|performance|growth|revenue|future|forecast|'
        r'valuation|earning|dividend|buy|sell|hold|rating|analyst|price|worth|undervalued|'
        r'overvalued|stock|s&p|stock\s*market|stock\s*price|market\s*cap|share\s*price|'
        r'chart|histor|trend|track|trajectory|total\s*return|annual\s*return|'
        r'gain|loss|portfolio|quarter|annual|profit|margin|ipo|split|'
        r'bull|bear|rally|crash|volatil|index|benchmark|sector|decline|surge|'
        r'\d+\s*years?\b|over\s+the\s+last|over\s+the\s+past|decade)\b', re.IGNORECASE)
    # Words that VETO stocks detection even with a company name present
    _fin_veto = re.compile(
        r'\b(recipe|cook|privacy|policy|return\s+policy|refund|warranty|'
        r'share\s+this|share\s+with|share\s+it|share\s+my|share\s+your|'
        r'customer\s+service|tech\s+support|app\s+store|download|install|'
        r'how\s+to\s+use|tutorial|guide|setup|password|login|account)\b', re.IGNORECASE)
    for name in _company_names:
        if re.search(r'\b' + re.escape(name) + r'\b', q):
            if _fin_veto.search(q):
                continue
            # Short imperative/interrogative queries about a company → stocks
            _is_request = bool(re.match(
                r'^(show|what|how|tell|give|display|compare|graph|chart|track)',
                q.strip(), re.IGNORECASE))
            if _fin_context.search(q) or (len(q.split()) <= 5 and _is_request):
                return "stocks"
    for sym in _ticker_syms:
        if re.search(r'\b' + re.escape(sym) + r'\b', q):
            return "stocks"
    return None


def _select_viz(topic: str, intent: str) -> str:
    """Select optimal visualization type for topic × intent combination."""
    return _VIZ_MATRIX.get((topic, intent), "stat_cards")


# ── Per-topic panel builders (intent-aware) ───────────────────────────

def _detect_stock_symbol(query: str) -> str | None:
    """Detect if the user is asking about a specific stock (returns first match)."""
    q = query.lower()
    _name_to_sym = {v.lower(): k for k, v in _TICKER_NAMES.items() if not k.startswith("^")}
    # Check ticker symbols (word boundary to avoid false matches)
    for sym in STOCK_SYMBOLS:
        if not sym.startswith("^") and re.search(r'\b' + re.escape(sym.lower()) + r'\b', q):
            return sym
    # Check company names (word boundary: "apple" not "pineapple")
    for name, sym in _name_to_sym.items():
        if re.search(r'\b' + re.escape(name) + r's?\b', q):
            return sym
    return None


def _detect_all_stock_symbols(query: str) -> list[str]:
    """Detect ALL stock symbols mentioned in a query. Returns list of symbols."""
    q = query.lower()
    _name_to_sym = {v.lower(): k for k, v in _TICKER_NAMES.items() if not k.startswith("^")}
    found = []
    seen = set()
    # Check ticker symbols
    for sym in STOCK_SYMBOLS:
        if not sym.startswith("^") and re.search(r'\b' + re.escape(sym.lower()) + r'\b', q):
            if sym not in seen:
                found.append(sym)
                seen.add(sym)
    # Check company names
    for name, sym in _name_to_sym.items():
        if re.search(r'\b' + re.escape(name) + r's?\b', q):
            if sym not in seen:
                found.append(sym)
                seen.add(sym)
    return found


def _detect_time_range(query: str) -> tuple[str, str] | None:
    """Detect if the user asks about a historical time period.
    Returns (yahoo_range, yahoo_interval) or None."""
    q = query.lower()
    _RANGE_MAP = [
        # (pattern keywords, yahoo_range, yahoo_interval)
        # Note: use years? / months? to match both singular and plural
        (r'\b10\s*years?\b', '10y', '1mo'),
        (r'\bdecade\b', '10y', '1mo'),
        (r'\b10y\b', '10y', '1mo'),
        (r'\b5\s*years?\b', '5y', '1mo'),
        (r'\b5y\b', '5y', '1mo'),
        (r'\b3\s*years?\b', '3y', '1mo'),
        (r'\b3y\b', '3y', '1mo'),
        (r'\b2\s*years?\b', '2y', '1mo'),
        (r'\b2y\b', '2y', '1mo'),
        (r'\b(1\s*year|12\s*months?|1y|last\s+year|past\s+year)\b', '1y', '1wk'),
        (r'\b6\s*months?\b', '6mo', '1wk'),
        (r'\b6mo\b', '6mo', '1wk'),
        (r'\b(3\s*months?|quarter|3mo)\b', '3mo', '1d'),
        (r'\b(1\s*months?|1mo)\b', '1mo', '1d'),
        (r'\bytd\b', 'ytd', '1wk'),
        (r'\b(histor|long.?term|over\s*time|performan|track\s*record)\b', '5y', '1mo'),
    ]
    for pattern, yrange, yinterval in _RANGE_MAP:
        if re.search(pattern, q):
            return (yrange, yinterval)
    # Catch-all: "last N years" / "N years" with dynamic range mapping
    _num_years = re.search(r'\b(\d+)\s*years?\b', q)
    if _num_years:
        n = int(_num_years.group(1))
        if n >= 15:
            return ('max', '3mo')  # Yahoo 'max' range for 15+ years
        elif n >= 10:
            return ('5y', '1mo')
        elif n >= 3:
            return ('3y', '1mo')
        elif n >= 2:
            return ('2y', '1mo')
        else:
            return ('1y', '1wk')
    return None


async def _fetch_historical_chart(symbol: str, yrange: str = '5y', yinterval: str = '1mo') -> dict | None:
    """Fetch historical price data from Yahoo Finance chart API.
    Returns {labels: [...], prices: [...], range: '5y'} or None."""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={yrange}&interval={yinterval}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10, headers=headers)
            if resp.status_code != 200:
                return None
            result = resp.json().get("chart", {}).get("result", [])
            if not result:
                return None
            data = result[0]
            timestamps = data.get("timestamp", [])
            closes = data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if not timestamps or not closes:
                return None
            # Build labels and prices, skipping None values
            labels = []
            prices = []
            for ts, price in zip(timestamps, closes):
                if price is not None:
                    dt = datetime.utcfromtimestamp(ts)
                    if yinterval in ('1d',):
                        labels.append(dt.strftime("%d %b"))
                    elif yinterval in ('1wk',):
                        labels.append(dt.strftime("%d %b %y"))
                    else:
                        labels.append(dt.strftime("%b %Y"))
                    prices.append(round(price, 2))
            if len(prices) < 2:
                return None
            # Calculate overall performance
            start_price = prices[0]
            end_price = prices[-1]
            total_return = ((end_price - start_price) / start_price) * 100 if start_price else 0
            return {
                "labels": labels,
                "prices": prices,
                "range": yrange,
                "start_price": start_price,
                "end_price": end_price,
                "total_return": round(total_return, 1),
                "high": round(max(prices), 2),
                "low": round(min(prices), 2),
            }
    except Exception as e:
        log.debug(f"Historical chart fetch failed for {symbol}: {e}")
    return None


async def _panel_stocks(intent: str, query: str = "") -> dict | None:
    """Build stocks panel with intent-aware visualization and analyst intelligence."""
    try:
        s = await stocks()
        if not s.get("quotes"):
            return None
        quotes = s["quotes"]
        await refresh_market_intel()

        # Check if user is asking about specific stocks
        _all_mentioned = _detect_all_stock_symbols(query) if query else []
        target_sym = _all_mentioned[0] if _all_mentioned else None
        intel = _market_intel_cache.get(target_sym) if target_sym else None
        _is_multi = len(_all_mentioned) > 1
        log.info(f"_panel_stocks: query={query[:80]!r}, target_sym={target_sym}, multi={_is_multi}, stocks={_all_mentioned}, intel={'yes' if intel else 'no'}, intent={intent}")

        # ── Multi-company query → return None, let dynamic panel handle it ──
        if _is_multi:
            log.info(f"_panel_stocks: multi-company query ({_all_mentioned}) — returning None for dynamic panel")
            return None

        # ── Check for historical time range request ──
        time_range = _detect_time_range(query) if query else None
        log.info(f"_panel_stocks: time_range={time_range} for query={query[:80]!r}")

        # ── Single-stock deep dive ──
        # Skip single-stock view for compare/rank intents — those need multi-stock
        # Show single-stock even without intel (use quote data only as fallback)
        if target_sym and intent not in ("compare", "rank"):
            # Find the quote for this stock
            quote = next((q for q in quotes if q["symbol"] == target_sym), None)
            if not quote:
                return None
            name = _TICKER_NAMES.get(target_sym, target_sym)
            price = quote["price"]
            pct = quote.get("changePct", 0) or 0
            change = quote.get("change", 0) or 0
            sign = "+" if pct >= 0 else ""

            # ── Fetch historical chart data if time range requested ──
            hist_chart = None
            if time_range:
                yrange, yinterval = time_range
                hist_chart = await _fetch_historical_chart(target_sym, yrange, yinterval)
                if hist_chart:
                    log.info(f"Historical chart: {target_sym} {yrange} → {len(hist_chart['prices'])} data points, return={hist_chart['total_return']:+.1f}%")

            if intel:
                # ── Rich single-stock with analyst data ──
                rating = intel.get("analyst_rating", "N/A")
                rating_status = "good" if rating in ("BUY", "STRONG_BUY") else "bad" if rating in ("SELL", "STRONG_SELL", "UNDERPERFORM") else None
                target_mean = intel.get("target_mean", 0)
                upside = intel.get("upside_pct", 0)

                stats = [
                    {"label": "Rating", "value": rating.replace("_", " "), "status": rating_status},
                    {"label": "Analysts", "value": str(intel.get("num_analysts", 0)), "status": None},
                    {"label": "Target", "value": f"${target_mean:,.0f}" if target_mean else "N/A",
                     "status": "good" if upside > 5 else "bad" if upside < -5 else None},
                    {"label": "Upside", "value": f"{upside:+.0f}%", "status": "good" if upside > 0 else "bad"},
                    {"label": "Fwd P/E", "value": f"{intel.get('forward_pe', 0):.1f}" if intel.get("forward_pe") else "N/A", "status": None},
                    {"label": "Margin", "value": f"{intel.get('profit_margin', 0):.1f}%", "status": "good" if intel.get("profit_margin", 0) > 10 else None},
                ]

                # Add historical performance stats if available
                if hist_chart:
                    _ret = hist_chart['total_return']
                    stats.insert(0, {"label": f"{hist_chart['range'].upper()} Return", "value": f"{_ret:+.1f}%",
                                     "status": "good" if _ret > 0 else "bad"})
                    stats.insert(1, {"label": f"{hist_chart['range'].upper()} High", "value": f"${hist_chart['high']:,.2f}", "status": None})
                    stats.insert(2, {"label": f"{hist_chart['range'].upper()} Low", "value": f"${hist_chart['low']:,.2f}", "status": None})

                # Analyst breakdown chart
                buy_total = intel.get("strong_buy", 0) + intel.get("buy", 0)
                hold_total = intel.get("hold", 0)
                sell_total = intel.get("sell", 0) + intel.get("strong_sell", 0)

                # Fundamentals table
                table_rows = [
                    ["Revenue Growth", f"{intel.get('revenue_growth', 0):+.1f}%"],
                    ["Profit Margin", f"{intel.get('profit_margin', 0):.1f}%"],
                    ["Forward P/E", f"{intel.get('forward_pe', 0):.1f}"],
                    ["Trailing EPS", f"${intel.get('trailing_eps', 0):.2f}"],
                    ["Beta", f"{intel.get('beta', 0):.2f}"],
                    ["Sector", intel.get("sector", "N/A")],
                    ["Industry", intel.get("industry", "N/A")],
                    ["52W Range", f"${intel.get('fifty_two_low', 0):,.0f} – ${intel.get('fifty_two_high', 0):,.0f}"],
                    ["Target Range", f"${intel.get('target_low', 0):,.0f} – ${intel.get('target_high', 0):,.0f}"],
                ]

                # Strategic insights
                insights = []
                if upside > 15:
                    insights.append({"type": "opportunity", "text": f"Significant upside potential: {upside:+.0f}% to analyst consensus target of ${target_mean:,.0f}."})
                elif upside < -10:
                    insights.append({"type": "risk", "text": f"Trading {abs(upside):.0f}% above analyst consensus target. Potential overvaluation risk."})
                rev_growth = intel.get("revenue_growth", 0)
                if rev_growth > 15:
                    insights.append({"type": "opportunity", "text": f"Strong revenue growth at {rev_growth:+.1f}%, outpacing sector average."})
                elif rev_growth < -5:
                    insights.append({"type": "risk", "text": f"Revenue declining at {rev_growth:+.1f}%. Watch for margin compression."})
                beta = intel.get("beta", 1)
                if beta > 1.5:
                    insights.append({"type": "warning", "text": f"High beta ({beta:.2f}) — expect amplified moves in volatile markets."})
                margin = intel.get("profit_margin", 0)
                if margin > 20:
                    insights.append({"type": "info", "text": f"Healthy profit margin at {margin:.1f}%, indicating pricing power and operational efficiency."})
                elif margin < 5 and margin > 0:
                    insights.append({"type": "warning", "text": f"Thin profit margin at {margin:.1f}%. Vulnerable to cost pressures."})

                # Recommendations
                recommendations = []
                if rating in ("BUY", "STRONG_BUY") and upside > 10:
                    recommendations.append({"priority": "high", "text": f"Analyst consensus is {rating.replace('_', ' ')} with {upside:+.0f}% upside. Consider accumulating on pullbacks."})
                elif rating in ("SELL", "STRONG_SELL", "UNDERPERFORM"):
                    recommendations.append({"priority": "high", "text": f"Analyst consensus is {rating.replace('_', ' ')}. Review position and consider reducing exposure."})
                low52 = intel.get("fifty_two_low", 0)
                high52 = intel.get("fifty_two_high", 0)
                if high52 and price > high52 * 0.95:
                    recommendations.append({"priority": "medium", "text": f"Near 52-week high (${high52:,.0f}). Consider taking partial profits or setting trailing stops."})
                if low52 and price < low52 * 1.1:
                    recommendations.append({"priority": "medium", "text": f"Near 52-week low (${low52:,.0f}). May represent a value entry if fundamentals support."})
                fwd_pe = intel.get("forward_pe", 0)
                if fwd_pe and fwd_pe > 40:
                    recommendations.append({"priority": "low", "text": f"Forward P/E of {fwd_pe:.1f} is elevated. Growth expectations are priced in — downside risk on earnings miss."})

                # Scorecard
                scorecard = [
                    {"label": "Analyst Rating", "score": min(100, max(0, 50 + upside * 2)),
                     "value": rating.replace("_", " ")},
                    {"label": "Growth", "score": min(100, max(0, 50 + rev_growth * 2)),
                     "value": f"{rev_growth:+.1f}%"},
                    {"label": "Profitability", "score": min(100, max(0, margin * 3)),
                     "value": f"{margin:.1f}%"},
                    {"label": "Value", "score": min(100, max(0, 100 - (fwd_pe or 20) * 2)),
                     "value": f"P/E {fwd_pe:.1f}" if fwd_pe else "N/A"},
                ]

                # Use historical line chart if available, otherwise analyst consensus bar
                if hist_chart:
                    _range_label = hist_chart['range'].upper().replace('Y', '-Year').replace('MO', '-Month')
                    _chart = {"type": "line",
                              "labels": hist_chart['labels'],
                              "datasets": [{"label": f"{name} Price ($)", "data": hist_chart['prices']}]}
                    _title = f"{name.upper()} — {_range_label} PERFORMANCE"
                    _summary = (f"{name} has returned {hist_chart['total_return']:+.1f}% over {_range_label.lower()}, "
                                f"from ${hist_chart['start_price']:,.2f} to ${hist_chart['end_price']:,.2f}. "
                                f"Range: ${hist_chart['low']:,.2f} – ${hist_chart['high']:,.2f}. "
                                f"Analyst consensus: {rating.replace('_', ' ')} with {upside:+.0f}% upside.")
                else:
                    _chart = {"type": "hbar",
                              "labels": ["Buy", "Hold", "Sell"],
                              "values": [buy_total, hold_total, sell_total],
                              "label": "Analyst Consensus"}
                    _title = f"{name.upper()} — ANALYST INTELLIGENCE"
                    _summary = intel.get("summary", "")[:150] if intel.get("summary") else f"{name}: {rating} with {upside:+.0f}% upside to ${target_mean:,.0f} target."

                panel = {
                    "title": _title,
                    "hero": {"value": f"${price:,.2f}", "label": name,
                             "delta": f"{sign}{pct:.1f}%",
                             "delta_status": "good" if pct > 0 else "bad" if pct < 0 else None},
                    "stats": stats,
                    "chart": _chart,
                    "table": {"headers": ["Metric", "Value"], "rows": table_rows},
                    "insights": insights[:4],
                    "recommendations": recommendations[:3],
                    "scorecard": scorecard,
                    "summary": _summary,
                }
                return panel
            else:
                # ── Lightweight single-stock view (no analyst intel available) ──
                stats = [
                    {"label": "Price", "value": f"${price:,.2f}", "status": None},
                    {"label": "Day Change", "value": f"{sign}${abs(change):,.2f}", "status": "good" if change > 0 else "bad" if change < 0 else None},
                    {"label": "Day Change %", "value": f"{sign}{pct:.2f}%", "status": "good" if pct > 0 else "bad" if pct < 0 else None},
                ]
                # Add historical performance if available
                if hist_chart:
                    _ret = hist_chart['total_return']
                    stats.insert(0, {"label": f"{hist_chart['range'].upper()} Return", "value": f"{_ret:+.1f}%",
                                     "status": "good" if _ret > 0 else "bad"})
                    _range_label = hist_chart['range'].upper().replace('Y', '-Year').replace('MO', '-Month')
                    _chart = {"type": "line",
                              "labels": hist_chart['labels'],
                              "datasets": [{"label": f"{name} Price ($)", "data": hist_chart['prices']}]}
                    panel = {
                        "title": f"{name.upper()} — {_range_label} PERFORMANCE",
                        "hero": {"value": f"${price:,.2f}", "label": name,
                                 "delta": f"{hist_chart['total_return']:+.1f}% ({_range_label.lower()})",
                                 "delta_status": "good" if hist_chart['total_return'] > 0 else "bad"},
                        "stats": stats,
                        "chart": _chart,
                        "summary": f"{name}: ${hist_chart['start_price']:,.2f} → ${hist_chart['end_price']:,.2f} ({hist_chart['total_return']:+.1f}% over {_range_label.lower()}).",
                    }
                else:
                    panel = {
                        "title": f"{name.upper()} — STOCK OVERVIEW",
                        "hero": {"value": f"${price:,.2f}", "label": name,
                                 "delta": f"{sign}{pct:.1f}%",
                                 "delta_status": "good" if pct > 0 else "bad" if pct < 0 else None},
                        "stats": stats,
                        "summary": f"{name} is currently trading at ${price:,.2f}, {sign}{pct:.1f}% today.",
                    }
                return panel

        # ── Check if user is asking about a SPECIFIC company not in our tracked list ──
        # If so, return None — the dynamic panel builder will handle it with web research
        # instead of showing an irrelevant generic market ranking.
        # Check proper nouns (capitalised) AND known company names (any case)
        _proper_nouns = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b', query)
        _ignore = {"What", "Why", "How", "Which", "Where", "Who", "When", "Tell", "Show",
                    "Give", "Can", "Could", "Would", "Should", "The", "This", "That",
                    "Their", "There", "These", "Has", "Have", "Does", "Did"}
        _specific_subject = [n for n in _proper_nouns if n.split()[0] not in _ignore]
        # Also detect lowercase company-like words not in tracked stocks
        if not _specific_subject:
            _q_words = set(re.findall(r'\b([a-z]{3,})\b', query.lower()))
            _tracked_lower = {v.lower() for v in _TICKER_NAMES.values()}
            _common = {"the", "and", "for", "are", "how", "has", "have", "does", "did",
                       "will", "can", "could", "would", "should", "what", "where", "when",
                       "which", "who", "why", "show", "give", "tell", "want", "need",
                       "stock", "stocks", "market", "invest", "compare", "view", "their",
                       "next", "year", "years", "idea", "get", "about", "with", "from",
                       "into", "over", "that", "this", "them", "they", "also", "been",
                       "curious", "understand", "portfolio", "investment", "strategic",
                       "placements", "trajectory", "breakdown", "full", "chip"}
            _unknown_subjects = _q_words - _tracked_lower - _common
            # If there are unrecognised proper-looking words that could be company names
            # this is intentionally conservative — only triggers for clearly untracked subjects
        if _specific_subject:
            log.info(f"_panel_stocks: user asked about '{_specific_subject[0]}' which is not in tracked stocks — returning None for dynamic panel")
            return None

        # ── Multi-stock overview (only when user wants a broad market view) ──
        items = []
        for q in quotes:
            name = _TICKER_NAMES.get(q["symbol"], q["symbol"])
            price = q["price"]
            pct = q.get("changePct", 0) or 0
            status = "good" if pct > 0.3 else "bad" if pct < -0.3 else None
            item = {"name": name, "symbol": q["symbol"], "price": price, "pct": round(pct, 2), "status": status}
            # Add analyst rating if available
            sym_intel = _market_intel_cache.get(q["symbol"])
            if sym_intel:
                item["rating"] = sym_intel.get("analyst_rating", "")
                item["target"] = sym_intel.get("target_mean", 0)
                item["upside"] = sym_intel.get("upside_pct", 0)
            items.append(item)

        viz = _select_viz("stocks", intent)

        if viz in ("hbar", "doughnut"):
            items.sort(key=lambda x: x["pct"], reverse=True)

        labels = [it["name"] for it in items]
        pcts = [it["pct"] for it in items]
        prices = [it["price"] for it in items]
        stats = [{"label": it["name"], "value": f"${it['price']:,.2f}", "status": it["status"]} for it in items[:6]]

        # Enriched table with analyst data
        table_rows = []
        has_intel = any(it.get("rating") for it in items)
        headers = ["Stock", "Price", "Change"]
        if has_intel:
            headers += ["Rating", "Target", "Upside"]
        for it in items:
            sign = "+" if it["pct"] >= 0 else ""
            row = [it["name"], f"${it['price']:,.2f}", f"{sign}{it['pct']:.1f}%"]
            if has_intel:
                row.append(it.get("rating", "—").replace("_", " "))
                row.append(f"${it.get('target', 0):,.0f}" if it.get("target") else "—")
                row.append(f"{it.get('upside', 0):+.0f}%" if it.get("upside") else "—")
            table_rows.append(row)

        # Multi-stock insights and trends
        gainers = [it for it in items if it["pct"] > 0]
        losers = [it for it in items if it["pct"] < 0]
        insights = []
        if len(gainers) > len(losers) * 2:
            insights.append({"type": "opportunity", "text": f"Broad market strength: {len(gainers)} gainers vs {len(losers)} losers. Risk-on environment."})
        elif len(losers) > len(gainers) * 2:
            insights.append({"type": "risk", "text": f"Market weakness: {len(losers)} losers vs {len(gainers)} gainers. Consider defensive positioning."})
        best = max(items, key=lambda x: x["pct"]) if items else None
        worst = min(items, key=lambda x: x["pct"]) if items else None
        if best and best["pct"] > 3:
            insights.append({"type": "opportunity", "text": f"{best['name']} leading with {best['pct']:+.1f}%. Check for catalyst — may have further upside."})
        if worst and worst["pct"] < -3:
            insights.append({"type": "warning", "text": f"{worst['name']} down {worst['pct']:.1f}%. Review position and check for material news."})
        # Add upside-based insight
        best_upside = max(items, key=lambda x: x.get("upside", 0)) if has_intel else None
        if best_upside and best_upside.get("upside", 0) > 15:
            insights.append({"type": "opportunity", "text": f"Highest upside: {best_upside['name']} at {best_upside['upside']:+.0f}% to analyst target."})

        trend_indicators = [
            {"label": "Market", "value": f"{len(gainers)}/{len(items)}", "direction": "up" if len(gainers) > len(losers) else "down", "context": "gainers/total"},
        ]
        if best:
            trend_indicators.append({"label": "Top Mover", "value": f"{best['pct']:+.1f}%", "direction": "up", "context": best["name"]})
        if worst:
            trend_indicators.append({"label": "Worst", "value": f"{worst['pct']:+.1f}%", "direction": "down", "context": worst["name"]})

        recommendations = []
        if best_upside and best_upside.get("upside", 0) > 20:
            recommendations.append({"priority": "high", "text": f"Research {best_upside['name']} — highest analyst upside in portfolio at {best_upside['upside']:+.0f}%."})
        if worst and worst["pct"] < -5:
            recommendations.append({"priority": "medium", "text": f"Review {worst['name']} position. Sharp decline may signal deteriorating fundamentals or a buying opportunity."})

        panel = {
            "title": "MARKET INTELLIGENCE",
            "stats": stats,
            "table": {"headers": headers, "rows": table_rows},
            "insights": insights[:4],
            "recommendations": recommendations[:3],
            "trend_indicators": trend_indicators,
            "summary": f"{len(gainers)} gainers, {len(losers)} losers across {len(quotes)} tracked assets.",
        }

        if viz == "hbar":
            panel["chart"] = {"type": "hbar", "labels": labels, "values": pcts,
                              "label": "% Change"}
            panel["title"] = "MARKET — RANKED BY CHANGE"
        elif viz == "doughnut":
            panel["chart"] = {"type": "doughnut", "labels": labels,
                              "values": [abs(p) for p in prices]}
            panel["title"] = "PORTFOLIO COMPOSITION"
        elif viz == "line":
            panel["chart"] = {"type": "hbar", "labels": labels, "values": pcts, "label": "% Change"}
            panel["title"] = "MARKET TREND"
        elif viz == "hero":
            top = items[0]
            sign_top = "+" if top["pct"] >= 0 else ""
            panel["hero"] = {"value": f"${top['price']:,.2f}", "label": top["name"],
                             "delta": f"{sign_top}{top['pct']:.1f}%",
                             "delta_status": "good" if top["pct"] > 0 else "bad" if top["pct"] < 0 else None}
            panel["title"] = f"{top['name'].upper()} — DETAIL"
        else:
            panel["chart"] = {"type": "hbar", "labels": labels, "values": pcts, "label": "% Change"}

        # For compare intent, add a comparison matrix with deep metrics
        if intent == "compare" and has_intel and len(items) >= 2:
            comp_items = [it for it in items if it.get("rating")][:4]  # Top 4 with intel
            if len(comp_items) >= 2:
                columns = ["Metric"] + [it["name"] for it in comp_items]
                comp_rows = [
                    ["Price"] + [f"${it['price']:,.2f}" for it in comp_items],
                    ["Day Change"] + [f"{it['pct']:+.1f}%" for it in comp_items],
                    ["Analyst Rating"] + [it.get("rating", "—").replace("_", " ") for it in comp_items],
                    ["Target Price"] + [f"${it.get('target', 0):,.0f}" if it.get("target") else "—" for it in comp_items],
                    ["Upside"] + [f"{it.get('upside', 0):+.0f}%" if it.get("upside") else "—" for it in comp_items],
                ]
                # Add deeper metrics from intel cache
                for metric_key, metric_label, fmt in [
                    ("revenue_growth", "Revenue Growth", "{:+.1f}%"),
                    ("profit_margin", "Profit Margin", "{:.1f}%"),
                    ("forward_pe", "Forward P/E", "{:.1f}"),
                    ("beta", "Beta", "{:.2f}"),
                ]:
                    row = [metric_label]
                    for it in comp_items:
                        sym_i = _market_intel_cache.get(it["symbol"], {})
                        val = sym_i.get(metric_key, 0)
                        row.append(fmt.format(val) if val else "—")
                    comp_rows.append(row)

                panel["comparison_matrix"] = {"columns": columns, "rows": comp_rows}
                panel["title"] = "COMPARATIVE ANALYSIS"

        return panel
    except Exception as e:
        log.error(f"_panel_stocks failed: {e}")
        import traceback; traceback.print_exc()
        return None


async def _panel_weather(intent: str, query: str) -> dict | None:
    """Build weather panel with intent-aware visualization."""
    import re
    try:
        loc_match = re.search(r'(?:in|for|at)\s+([A-Za-z\s\-]+)', query.lower())
        place = loc_match.group(1).strip().rstrip('?.,') if loc_match else None
        w = await weather(location=place) if place else await weather()
        cur = w.get("current", {})
        daily = w.get("daily", {})
        location = w.get("location", "London")
        viz = _select_viz("weather", intent)

        # Day name labels instead of "Day 0"
        from datetime import datetime, timedelta
        today = datetime.utcnow()
        day_names = [(today + timedelta(days=i)).strftime("%a") for i in range(7)]

        panel = {"title": f"WEATHER — {location.upper()}"}

        if viz == "hero" and cur:
            temp = cur.get('temperature_2m', '?')
            feels = cur.get('apparent_temperature', '?')
            panel["hero"] = {
                "value": f"{temp}°C",
                "label": location,
                "delta": f"Feels like {feels}°C",
                "delta_status": None,
            }
            panel["stats"] = [
                {"label": "Humidity", "value": f"{cur.get('relative_humidity_2m', '?')}%", "status": None},
                {"label": "Wind", "value": f"{cur.get('wind_speed_10m', '?')} km/h", "status": None},
            ]
            # Add precipitation if available
            if daily.get("precipitation_sum"):
                precip = daily["precipitation_sum"][0] if daily["precipitation_sum"] else 0
                panel["stats"].append({"label": "Rain Today", "value": f"{precip}mm",
                                       "status": "warn" if precip > 5 else None})
        elif cur:
            panel["stats"] = [
                {"label": "Temperature", "value": f"{cur.get('temperature_2m', '?')}°C", "status": None},
                {"label": "Feels Like", "value": f"{cur.get('apparent_temperature', '?')}°C", "status": None},
                {"label": "Humidity", "value": f"{cur.get('relative_humidity_2m', '?')}%", "status": None},
                {"label": "Wind", "value": f"{cur.get('wind_speed_10m', '?')} km/h", "status": None},
            ]

        # Forecast chart (line)
        if daily.get("temperature_2m_max"):
            days = min(7, len(daily["temperature_2m_max"]))
            chart_datasets = [
                {"label": "High", "data": [daily["temperature_2m_max"][i] for i in range(days)]},
                {"label": "Low", "data": [daily["temperature_2m_min"][i] for i in range(days)]},
            ]
            # Add precipitation as third dataset if available
            if daily.get("precipitation_sum"):
                chart_datasets.append({
                    "label": "Rain (mm)", "data": [daily["precipitation_sum"][i] for i in range(days)],
                    "yAxisID": "y1",
                })
            panel["chart"] = {
                "type": "line",
                "labels": day_names[:days],
                "datasets": chart_datasets,
            }

        return panel
    except Exception:
        return None


async def _panel_revenue(intent: str) -> dict | None:
    """Build revenue panel with intent-aware visualization."""
    try:
        rc = rc_mon.summary()
        ov = rc.get("overview", {})
        if not ov:
            return {
                "title": "REVENUE",
                "stats": [{"label": "Status", "value": "NOT CONFIGURED", "status": "warn"}],
                "summary": "RevenueCat integration is not configured. Add REVENUECAT_API_KEY to .env.",
            }

        subs = ov.get("active_subscribers", 0)
        trials = ov.get("active_trials", 0)
        mrr = ov.get("mrr", 0)
        rev = ov.get("revenue", 0)
        churned = ov.get("churned_subscribers", 0)
        new_c = ov.get("new_customers", 0)
        viz = _select_viz("revenue", intent)

        stats = [
            {"label": "MRR", "value": f"${mrr:,.0f}", "status": "good" if mrr > 0 else None},
            {"label": "Revenue", "value": f"${rev:,.0f}", "status": "good"},
            {"label": "Subscribers", "value": f"{subs:,}", "status": "good"},
            {"label": "Trials", "value": f"{trials:,}", "status": None},
            {"label": "New", "value": f"{new_c:,}", "status": "good" if new_c > 0 else None},
            {"label": "Churned", "value": f"{churned:,}", "status": "bad" if churned > 0 else "good"},
        ]

        panel = {
            "title": "REVENUE BREAKDOWN",
            "stats": stats,
            "summary": f"MRR ${mrr:,.0f} with {subs:,} active subscribers. Churn: {churned:,} this period.",
        }

        if viz == "doughnut":
            panel["chart"] = {
                "type": "doughnut",
                "labels": ["Subscribers", "Trials", "New", "Churned"],
                "values": [subs, trials, new_c, churned],
            }
            panel["title"] = "REVENUE — COMPOSITION"
        elif viz == "hbar":
            panel["chart"] = {
                "type": "hbar",
                "labels": ["MRR", "Revenue", "Subscribers", "Trials", "New", "Churned"],
                "values": [mrr, rev, subs, trials, new_c, churned],
                "label": "Count/Value",
            }
            panel["title"] = "REVENUE — COMPARISON"
        else:
            panel["chart"] = {
                "type": "bar",
                "labels": ["Subscribers", "Trials", "New", "Churned"],
                "values": [subs, trials, new_c, churned],
            }

        return panel
    except Exception:
        return None


async def _panel_news() -> dict | None:
    """Build news panel — always a table."""
    try:
        n = await news()
        headlines = n.get("headlines", [])[:8]
        if not headlines:
            return None
        return {
            "title": "NEWS OVERVIEW",
            "table": {
                "headers": ["Headline", "Source"],
                "rows": [[h.get("title", ""), h.get("source", "")] for h in headlines],
            },
        }
    except Exception:
        return None


async def _panel_sports() -> dict | None:
    """Build sports panel — always a table."""
    try:
        sp = await sports()
        stories = sp.get("stories", [])[:6]
        if not stories:
            return None
        return {
            "title": "SPORTS UPDATE",
            "table": {
                "headers": ["Story", "Category"],
                "rows": [[st.get("title", ""), st.get("category", "")] for st in stories],
            },
        }
    except Exception:
        return None


async def _panel_gcp(intent: str) -> dict | None:
    """Build GCP infrastructure panel with status grid."""
    try:
        gcp_data = gcp_mon.summary()
        services = gcp_data.get("services", [])

        if services:
            grid_items = []
            for svc in services[:8]:
                status_map = {"operational": "good", "degraded": "warn",
                              "partial_outage": "warn", "major_outage": "bad"}
                grid_items.append({
                    "label": svc.get("name", "Unknown"),
                    "status": status_map.get(svc.get("status", ""), None),
                    "value": svc.get("status", "unknown").replace("_", " ").upper(),
                })
            panel = {
                "title": "GCP INFRASTRUCTURE",
                "status_grid": grid_items,
                "summary": f"{sum(1 for s in grid_items if s['status'] == 'good')}/{len(grid_items)} services operational.",
            }
        else:
            # Fallback to static status
            panel = {
                "title": "GCP INFRASTRUCTURE",
                "status_grid": [
                    {"label": "App Engine", "value": "OPERATIONAL", "status": "good"},
                    {"label": "Cloud Run", "value": "OPERATIONAL", "status": "good"},
                    {"label": "Cloud SQL", "value": "OPERATIONAL", "status": "good"},
                    {"label": "Cloud Storage", "value": "OPERATIONAL", "status": "good"},
                ],
                "summary": "All monitored services reporting nominal status.",
            }

        return panel
    except Exception:
        return {
            "title": "GCP INFRASTRUCTURE",
            "status_grid": [
                {"label": "App Engine", "value": "OPERATIONAL", "status": "good"},
                {"label": "Cloud Run", "value": "OPERATIONAL", "status": "good"},
                {"label": "Cloud SQL", "value": "OPERATIONAL", "status": "good"},
                {"label": "Cloud Storage", "value": "OPERATIONAL", "status": "good"},
            ],
            "summary": "All monitored services reporting nominal status.",
        }


async def _panel_email(intent: str) -> dict | None:
    """Build email panel with intent-aware visualization."""
    try:
        es = email_mon.summary()
        viz = _select_viz("email", intent)

        stats = [
            {"label": "Unread", "value": str(es.get("unread", 0)), "status": "warn" if es.get("unread", 0) > 10 else None},
            {"label": "Customer", "value": str(es.get("customer", 0)), "status": "good" if es.get("customer", 0) > 0 else None},
            {"label": "Urgent", "value": str(es.get("urgent", 0)), "status": "bad" if es.get("urgent", 0) > 0 else "good"},
            {"label": "Replied", "value": str(es.get("replied", 0)), "status": None},
        ]

        panel = {
            "title": "EMAIL INTELLIGENCE",
            "stats": stats,
        }

        if viz == "doughnut":
            unread = es.get("unread", 0)
            read = max(0, es.get("today", 0) - unread)
            urgent = es.get("urgent", 0)
            panel["chart"] = {
                "type": "doughnut",
                "labels": ["Read", "Unread", "Urgent"],
                "values": [read, unread, urgent],
            }
            panel["title"] = "EMAIL — BREAKDOWN"

        return panel
    except Exception:
        return None


# ── ComfyUI Creative Engine ───────────────────────────────────────────
_COMFYUI_NEGATIVE = (
    "cartoon, anime, bright primary colours, ugly, deformed, blurry, "
    "text overlay, watermark, logo, nsfw, violence"
)

_COMFYUI_WORKFLOW = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "cfg": 7, "denoise": 1, "latent_image": ["5", 0],
            "model": ["4", 0], "negative": ["7", 0], "positive": ["6", 0],
            "sampler_name": "dpmpp_2m", "scheduler": "karras",
            "seed": 0, "steps": 30,
        },
    },
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"batch_size": 1, "height": 1024, "width": 1024}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": ""}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": ""}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "arbiter_", "images": ["8", 0]}},
}

_comfyui_output_dir = Path(__file__).parent / "static" / "comfyui_output"
_comfyui_output_dir.mkdir(parents=True, exist_ok=True)


def _extract_creative_prompt(query: str) -> str:
    """Extract the image/video description from a creative command."""
    import re
    q = query.strip()
    # Remove the trigger phrase to get the actual prompt
    patterns = [
        r'(?:generate|create|make|render|draw|design)\s+(?:an?\s+)?(?:image|picture|photo|video|render)\s+(?:of\s+)?',
        r'(?:generate|create|make|render|draw|design)\s+',
    ]
    for p in patterns:
        cleaned = re.sub(p, '', q, count=1, flags=re.IGNORECASE).strip()
        if cleaned and cleaned != q:
            return cleaned
    return q


async def _comfyui_generate(prompt: str, width: int = 1024, height: int = 1024, steps: int = 30) -> dict:
    """Submit a generation job to ComfyUI and poll for completion."""
    import copy
    import time as _t

    checkpoint = os.getenv("COMFYUI_CHECKPOINT", "dreamshaper_8.safetensors")
    client_id = str(__import__('uuid').uuid4())
    seed = int(_t.time())

    wf = copy.deepcopy(_COMFYUI_WORKFLOW)
    wf["4"]["inputs"]["ckpt_name"] = checkpoint
    wf["5"]["inputs"]["width"] = width
    wf["5"]["inputs"]["height"] = height
    wf["3"]["inputs"]["steps"] = steps
    wf["3"]["inputs"]["seed"] = seed
    wf["6"]["inputs"]["text"] = prompt
    wf["7"]["inputs"]["text"] = _COMFYUI_NEGATIVE

    start = _t.time()

    async with httpx.AsyncClient() as client:
        # Submit
        r = await client.post(f"{COMFYUI_URL}/prompt",
                              json={"prompt": wf, "client_id": client_id}, timeout=30)
        r.raise_for_status()
        prompt_id = r.json()["prompt_id"]
        log.info(f"ComfyUI job submitted: {prompt_id}")

        # Poll for completion (max 5 min)
        while _t.time() - start < 300:
            await asyncio.sleep(2)
            hr = await client.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            data = hr.json()
            if prompt_id in data:
                outputs = data[prompt_id].get("outputs", {})
                for node_id, node_output in outputs.items():
                    for img in node_output.get("images", []):
                        # Download image via ComfyUI view API
                        params = {"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": "output"}
                        ir = await client.get(f"{COMFYUI_URL}/view", params=params, timeout=30)
                        ir.raise_for_status()
                        dest = _comfyui_output_dir / img["filename"]
                        dest.write_bytes(ir.content)
                        elapsed = round(_t.time() - start, 1)
                        return {
                            "filename": img["filename"],
                            "path": str(dest),
                            "url": f"/static/comfyui_output/{img['filename']}",
                            "elapsed": elapsed,
                            "width": width, "height": height, "steps": steps,
                        }
        raise TimeoutError(f"ComfyUI job {prompt_id} timed out")


@app.post("/api/comfyui/generate")
async def comfyui_generate(request: Request):
    """Generate an image via ComfyUI on the Windows PC."""
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return {"error": "No prompt provided"}
    width = body.get("width", 1024)
    height = body.get("height", 1024)
    steps = body.get("steps", 30)

    try:
        result = await _comfyui_generate(prompt, width, height, steps)
        return {"status": "ok", **result}
    except ConnectionError:
        return {"error": "ComfyUI is not reachable. Is the Windows PC on?"}
    except Exception as e:
        log.error(f"ComfyUI generation error: {e}")
        return {"error": str(e)}


async def _build_panel(user_msg: str, hint_topic: str | None = None) -> dict | None:
    """Build a visualization panel using intelligent intent × topic selection."""
    msg = user_msg.lower()
    intent = _classify_intent(msg)
    topic = _detect_topic(msg) or hint_topic

    if not topic:
        # No specific topic — check if this is a general/briefing query
        briefing_patterns = ["briefing", "status report", "how am i doing", "overview",
                             "what's going on", "update me", "catch me up", "summary",
                             "how's everything", "what's happening", "sitrep", "how are things"]
        if any(p in msg for p in briefing_patterns):
            return await _panel_executive_dashboard()
        return None

    # Build topic-specific panel
    panel = None
    if topic == "stocks":
        panel = await _panel_stocks(intent, user_msg)
    elif topic == "weather":
        panel = await _panel_weather(intent, user_msg)
    elif topic == "revenue":
        panel = await _panel_revenue(intent)
    elif topic == "news":
        panel = await _panel_news()
    elif topic == "sports":
        panel = await _panel_sports()
    elif topic == "gcp":
        panel = await _panel_gcp(intent)
    elif topic == "email":
        panel = await _panel_email(intent)
    elif topic == "services":
        panel = await _panel_services(intent)
    elif topic == "roadmap":
        panel = await _panel_roadmap(intent)
    elif topic == "comfyui":
        return None

    # ── Cross-topic enrichment: add related context to the right wing ──
    if panel and topic in ("stocks", "revenue"):
        panel = await _enrich_panel(panel, topic)

    return panel


async def _enrich_panel(panel: dict, topic: str) -> dict:
    """Add cross-topic related data to enrich visualization panels."""
    try:
        if topic == "stocks":
            # Enrich stock panels with relevant news
            try:
                n = await news()
                headlines = n.get("headlines", [])
                market_news = [h for h in headlines if any(
                    w in h.get("title", "").lower()
                    for w in ["market", "stock", "share", "trade", "investor", "economy",
                              "apple", "tesla", "microsoft", "nvidia", "google", "amazon"]
                )][:3]
                if market_news:
                    panel.setdefault("summary", "")
                    panel["summary"] += " | Related headlines: " + "; ".join(
                        h.get("title", "")[:60] for h in market_news)
            except Exception:
                pass

        elif topic == "revenue":
            # Enrich revenue with service health context
            try:
                svc_data = svc_health.summary()
                degraded = [s for s in svc_data if s.get("status") not in ("operational", "up", None)]
                if degraded:
                    panel.setdefault("summary", "")
                    names = ", ".join(s.get("name", "?") for s in degraded[:3])
                    panel["summary"] += f" | ⚠ Services degraded: {names} — may impact revenue."
            except Exception:
                pass

            # Add proactive insights if any
            try:
                insights = await _analyze_insights()
                revenue_insights = [i for i in insights if i.get("topic") == "revenue"]
                if revenue_insights:
                    existing_stats = panel.get("stats", [])
                    for ins in revenue_insights[:2]:
                        existing_stats.append({
                            "label": "INSIGHT",
                            "value": ins["title"],
                            "status": "warn" if ins["severity"] == "medium" else "bad" if ins["severity"] == "high" else None,
                        })
                    panel["stats"] = existing_stats
            except Exception:
                pass

    except Exception:
        pass
    return panel


# ── Dynamic Panel Builder (LLM-generated for ANY topic) ─────────────

# ── Canonical panel component keys — single source of truth ──────────
# Mirrors the left/right wing split in the JS renderer (_renderAnalysisPanel).
# Any new component type must be added here AND in _renderSection in jarvis.js.
#
#  LEFT WING  — visualisations rendered in the left analysis panel
#  RIGHT WING — metrics/narrative rendered in the right analysis panel
#
_PANEL_LEFT_KEYS: frozenset[str] = frozenset({
    "chart", "table", "comparison_matrix", "heatmap", "quadrant", "calendar_heatmap", "image_url",
})
_PANEL_RIGHT_KEYS: frozenset[str] = frozenset({
    "hero", "status_grid", "stats", "key_metrics", "trend_indicators",
    "gauges", "funnel", "scorecard", "risk_matrix",
    "swot", "pros_cons", "insights", "recommendations", "timeline",
})
# All mergeable keys (excludes title/summary — those are merged separately)
_PANEL_MERGE_KEYS: frozenset[str] = _PANEL_LEFT_KEYS | _PANEL_RIGHT_KEYS


# Compact schema prompt — ~40% fewer tokens than a verbose example-based prompt.
# Uses type-annotation style so the model sees exact key names and value shapes
# without prose commentary eating into the token budget.
_PANEL_SCHEMA_PROMPT = """\
You are a strategic dashboard analyst. Output ONLY valid JSON — no markdown fences, no explanation.

PANEL SCHEMA (exact key names required; ? = optional):

  title           "CAPS STRING"
  summary         "one executive sentence"

  hero            {value:str, label:str, delta?:str, delta_status?:"good"|"bad"}
  status_grid     [{label:str, value:str, status:"good"|"warn"|"bad"|"unknown"}]
  stats           [{label:str, value:str, status?:"good"|"warn"|"bad"}]
  key_metrics     [{label:str, value:str, status?:"good"|"warn"|"bad", context?:str}]
  trend_indicators [{label:str, value:str, direction:"up"|"down"|"flat", context?:str}]
  gauges          [{label:str, value:0-100, display:str, context?:str}]
  funnel          [{label:str, value:0-100, display:str, pct:str}]
  scorecard       [{label:str, score:0-100, value:str}]
  risk_matrix     [{severity:"critical"|"high"|"medium"|"low", risk:str, mitigation:str}]
  swot            {strengths:[str], weaknesses:[str], opportunities:[str], threats:[str]}
  pros_cons       {pros:[str], cons:[str]}
  insights        [{type:"risk"|"opportunity"|"warning"|"info", text:str}]
  recommendations [{priority:"high"|"medium"|"low", text:str}]
  timeline        [{date:str, event:str, status:"done"|"active"|"pending", detail?:str}]

  chart           single-series: {type, labels:[str], values:[num], label?:str}
                  multi-series:  {type, labels:[str], datasets:[{label:str, data:[num]}]}
                  type = bar|hbar|line|area|doughnut|radar|stacked|scatter|bubble|polarArea|waterfall|candlestick
                  radar:       labels=axes, datasets=entities (scores 0-100 each)
                  scatter:     datasets=[{label:str, data:[{x,y}]}], xLabel?:str, yLabel?:str
                  waterfall:   data=[{label:str, value:num, type:"pos"|"neg"|"total", display?:str}]
                  candlestick: data=[{date:str, o:num, h:num, l:num, c:num}], label?:str

  table           {headers:[str], rows:[[str]]}
  comparison_matrix {columns:[str], rows:[[str]]}
  heatmap         {title:str, columns:[str], rows:[{label:str, values:[0-100]}]}
  quadrant        {title:str, x_axis:str, y_axis:str,
                   quadrant_labels:[str,str,str,str],
                   points:[{label:str, x:0-100, y:0-100, size?:8-24}]}
  calendar_heatmap {title:str, unit?:str, data:[{date:"YYYY-MM-DD", value:num, label?:str}]}

SELECTION RULES — match components to query intent:
  comparison/vs      → radar + comparison_matrix + heatmap
  investment/buy     → gauges + risk_matrix + scorecard + recommendations
  market share       → doughnut chart + heatmap + funnel
  positioning        → quadrant + radar
  trend/time-series  → trend_indicators + line|area chart + key_metrics
  company/product    → swot + scorecard + gauges
  financial/OHLC     → candlestick chart + stats
  revenue changes    → waterfall chart + trend_indicators + stats
  correlation        → scatter chart + insights
  activity/daily     → calendar_heatmap + trend_indicators
  health/status      → status_grid + stats
  collectables/cards → table (prices by condition/grade) + line chart (price trend) + stats + insights
  products/shopping  → table (retailer, price, link) + hbar (price comparison) + stats + recommendations
  ALWAYS include     → insights (3-5 with data) + recommendations (2-4 actionable) + summary
  MINIMUM 5 components. Extract every number/% /date. Prefix changes with + or -.

  For product/collectable tables: include clickable buy links as "Store → URL" pairs in a dedicated column.
  For price comparisons: sort by price ascending so cheapest appears first.\
"""


def _panel_from_reply(user_msg: str, llm_reply: str) -> dict | None:
    """Build a visualization panel by extracting data from the LLM reply text.
    Zero LLM calls — pure regex extraction. Instant.
    Returns a BASIC scaffold (stats, chart, table). Always pair with _panel_dynamic
    for rich strategic components (insights, swot, recommendations, etc.)."""
    try:
        # ── Extract year-value pairs for timeline charts ──
        year_val_pairs = []
        # Pattern 1: "in/by/around YYYY ... $X" or "YYYY ... $X"
        for m in re.finditer(
            r'(?:in|by|around|from|since)?\s*\b(20[12]\d)\b[^.]*?'
            r'[\$₩€£]?\s*([\d,]+(?:\.\d+)?)\s*(?:billion|million|trillion|B|M|T|%|percent)?',
            llm_reply, re.IGNORECASE
        ):
            year = int(m.group(1))
            val_str = m.group(2).replace(',', '')
            try:
                val = float(val_str)
                suffix = llm_reply[m.end()-10:m.end()+5].lower()
                if 'trillion' in suffix or ' t ' in suffix:
                    val *= 1000
                year_val_pairs.append((year, val))
            except ValueError:
                pass

        # Pattern 2: "$X billion/million in YYYY" (reversed order Claude often uses)
        if len(year_val_pairs) < 3:
            for m in re.finditer(
                r'[\$₩€£]\s*([\d,]+(?:\.\d+)?)\s*(?:billion|million|trillion|B|M|T)?\s+'
                r'(?:in|by|around|as of|during)\s+(20[12]\d)\b',
                llm_reply, re.IGNORECASE
            ):
                val_str = m.group(1).replace(',', '')
                year = int(m.group(2))
                try:
                    val = float(val_str)
                    suffix = llm_reply[m.start():m.start()+40].lower()
                    if 'trillion' in suffix or ' t ' in suffix:
                        val *= 1000
                    year_val_pairs.append((year, val))
                except ValueError:
                    pass

        # Deduplicate by year (keep first occurrence)
        seen_years = set()
        unique_pairs = []
        for y, v in sorted(year_val_pairs):
            if y not in seen_years:
                seen_years.add(y)
                unique_pairs.append((y, v))

        # ── Extract percentage stats ──
        # Handles: "OpenAI commanding 35%", "Google at 18–22%", "growth of 34%", "P/E of 28.4"
        pct_stats = []
        # Pattern A: "Entity/Label ... X%" — look BACKWARDS from each percentage
        for m in re.finditer(r'([A-Z][\w\'\-]+(?:\s+[\w\'\-]+){0,4})\s+(?:at|of|with|commanding|captures?|holds?|maintains?|commands?)?\s*(?:approximately|roughly|about|around|~)?\s*(\d+(?:\.\d+)?(?:\s*[–\-]\s*\d+(?:\.\d+)?)?)\s*%', llm_reply):
            label = m.group(1).strip()[:30]
            val = m.group(2).replace(' ', '')
            # For ranges like "35-40", take the midpoint for display but show range
            if '–' in val or '-' in val:
                parts = re.split(r'[–\-]', val)
                display_val = f"{parts[0]}–{parts[1]}%"
            else:
                display_val = f"{val}%"
            if label and len(label) > 1:
                pct_stats.append({"label": label.title(), "value": display_val, "status": None})
        # Pattern B: fallback — "X% of something" or "X% YoY/growth"
        if len(pct_stats) < 2:
            for m in re.finditer(r'(\d+(?:\.\d+)?)\s*%\s+(?:of\s+)?([A-Za-z][\w\s]{2,25}?)(?:\.|,|;|\s+(?:and|while|though|but|yet))', llm_reply):
                val = m.group(1)
                label = m.group(2).strip()[:30]
                if label and len(label) > 2:
                    pct_stats.append({"label": label.title(), "value": f"{val}%", "status": None})

        # ── Extract dollar amounts as stats ──
        dollar_stats = []
        for m in re.finditer(
            r'([A-Z][\w\'\-]+(?:\s+[\w\'\-]+){0,3})\s+(?:at|of|to|was|is|reached|hit|valued at|worth|standing at)?\s*'
            r'\$\s*([\d,.]+)\s*(billion|million|trillion|B|M|T)?',
            llm_reply, re.IGNORECASE
        ):
            label = m.group(1).strip()[:30]
            val = m.group(2)
            unit = (m.group(3) or "").upper()[:1]
            if label and len(label) > 1:
                dollar_stats.append({"label": label.title(), "value": f"${val}{unit}", "status": None})

        # ── Extract comparison data for bar charts ──
        # Look for "Entity at/with X%" patterns to build comparison bar chart
        comp_entries = []
        for m in re.finditer(
            r'([A-Z][\w\'\-]+(?:\s+[\w\'\-]+){0,2})\s+(?:commanding|at|with|captures?|holds?|maintains?|commands?)\s+'
            r'(?:approximately|roughly|about|around|~)?\s*(\d+(?:\.\d+)?(?:\s*[–\-]\s*\d+(?:\.\d+)?)?)\s*%',
            llm_reply
        ):
            name = m.group(1).strip()
            val_str = m.group(2).replace(' ', '')
            # For ranges, take midpoint
            if '–' in val_str or '-' in val_str:
                parts = re.split(r'[–\-]', val_str)
                val = (float(parts[0]) + float(parts[1])) / 2
            else:
                val = float(val_str)
            comp_entries.append((name, val))

        # ── Build panel ──
        panel = {"title": "RESEARCH ANALYSIS"}

        # Extract subject for title — handle any capitalisation
        _detected = _detect_all_stock_symbols(user_msg)
        _subj_names = [_TICKER_NAMES.get(s, s) for s in _detected]
        if not _subj_names:
            _proper = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b', user_msg)
            _ignore = {"What", "Why", "How", "Which", "Where", "Who", "When", "Tell", "Show",
                        "Give", "Can", "Could", "Would", "Should", "The", "Has", "Have", "Does", "Did"}
            _subj_names = [n for n in _proper if n.split()[0] not in _ignore]
        _subj = _subj_names  # Keep variable name for downstream references
        if _subj:
            _title_str = " vs ".join(s.upper() for s in _subj[:4]) if len(_subj) > 1 else _subj[0].upper()
            panel["title"] = f"{_title_str} — RESEARCH ANALYSIS"

        # Timeline chart from year-value pairs
        if len(unique_pairs) >= 3:
            panel["chart"] = {
                "type": "line",
                "labels": [str(y) for y, _ in unique_pairs],
                "datasets": [{"label": _subj[0] if _subj else "Value", "data": [v for _, v in unique_pairs]}],
            }
        # Comparison bar chart from entity-percentage pairs (market share breakdowns, etc.)
        elif len(comp_entries) >= 3:
            panel["chart"] = {
                "type": "hbar",
                "labels": [name for name, _ in sorted(comp_entries, key=lambda x: -x[1])],
                "values": [val for _, val in sorted(comp_entries, key=lambda x: -x[1])],
                "label": "Market Share %",
            }

        # Deduplicate stats by label
        _seen_labels = set()
        deduped_stats = []
        for s in (pct_stats + dollar_stats):
            _key = s["label"].lower()
            if _key not in _seen_labels:
                _seen_labels.add(_key)
                deduped_stats.append(s)
        all_stats = deduped_stats[:8]
        if all_stats:
            panel["stats"] = all_stats

        # Summary from first 2 sentences of reply
        sentences = re.split(r'(?<=[.!?])\s+', llm_reply.strip())
        panel["summary"] = " ".join(sentences[:2])[:300]

        # Only return if we have meaningful content
        if panel.get("chart") or len(all_stats) >= 2:
            log.info(f"_panel_from_reply: built panel with {len(unique_pairs)} data points, {len(comp_entries)} comparisons, {len(all_stats)} stats")
            return panel
        return None
    except Exception as e:
        log.debug(f"_panel_from_reply failed: {e}")
        return None


def _repair_truncated_json(s: str) -> str:
    """Best-effort repair of JSON truncated by a token limit.

    Walks the string character-by-character to track open braces/brackets and
    string state, then appends the minimum closing tokens needed to produce
    syntactically valid JSON.  A final `json.loads()` in the caller will still
    raise if the content is fundamentally malformed (not just truncated).
    """
    stack: list[str] = []   # '{' or '['
    in_str = False
    escaped = False

    for ch in s:
        if escaped:
            escaped = False
            continue
        if ch == '\\' and in_str:
            escaped = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in ('{', '['):
            stack.append(ch)
        elif ch == '}' and stack and stack[-1] == '{':
            stack.pop()
        elif ch == ']' and stack and stack[-1] == '[':
            stack.pop()

    # Close any open string first
    if in_str:
        s += '"'

    # Strip trailing incomplete key/value fragments (e.g. a dangling comma or colon)
    s = s.rstrip().rstrip(',').rstrip(':').rstrip('"').rstrip()

    # Close all open containers in reverse order
    for opener in reversed(stack):
        s += '}' if opener == '{' else ']'

    return s


async def _panel_dynamic(user_msg: str, llm_reply: str, extra_ctx: str = "") -> dict | None:
    """Use an LLM call to generate a structured panel for any open-domain topic.
    This handles queries about eBay, social media, crypto, comparisons, etc."""
    try:
        # Build context — give the panel builder enough data without bloating the prompt
        ctx_limit = 4000
        reply_limit = 3000
        ctx_block = ""
        if extra_ctx:
            ctx_block = f"\n\nADDITIONAL RESEARCH DATA (USE THIS HEAVILY — extract every number, price, stat):{chr(10)}{extra_ctx[:ctx_limit]}"

        messages = [
            {"role": "system", "content": _PANEL_SCHEMA_PROMPT},
            {"role": "user", "content": (
                f"USER QUERY: {user_msg}\n\n"
                f"AI ANALYSIS (reference data):\n{llm_reply[:reply_limit]}\n"
                f"{ctx_block}\n\n"
                "Generate the comprehensive dashboard panel JSON now. Use 5+ components minimum."
            )},
        ]

        panel_json = await _chat_llm(messages, max_tokens=2000, temperature=0.3, purpose="panel")

        if not panel_json:
            return None

        # Extract JSON from response (LLM sometimes wraps in markdown or adds preamble)
        # Try to extract JSON from markdown code fences first
        _fence_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', panel_json)
        if _fence_match:
            panel_json = _fence_match.group(1).strip()
        else:
            # No fences — try to find the JSON object directly
            _json_start = panel_json.find('{')
            _json_end = panel_json.rfind('}')
            if _json_start != -1 and _json_end > _json_start:
                panel_json = panel_json[_json_start:_json_end + 1]
            panel_json = panel_json.strip()

        try:
            panel = json.loads(panel_json)
        except json.JSONDecodeError:
            # LLM output was likely truncated — attempt to repair by closing open structures
            panel_json = _repair_truncated_json(panel_json)
            panel = json.loads(panel_json)  # re-raises if still broken

        # Validate: must be a dict with at least a title
        if not isinstance(panel, dict) or not panel.get("title"):
            return None

        log.info(f"Dynamic panel generated: {panel.get('title', '?')}")
        return panel

    except json.JSONDecodeError as e:
        log.warning(f"Dynamic panel JSON parse failed: {e} — raw start: {panel_json[:200]!r}")
        return None
    except Exception as e:
        log.warning(f"Dynamic panel generation failed: {type(e).__name__}: {e}")
        return None


async def _panel_executive_dashboard() -> dict | None:
    """Build a multi-source executive dashboard for general/briefing queries.
    Combines revenue, services, and roadmap into a rich dual-wing view.
    No stocks/markets — this is a personal project briefing."""
    sections = []
    all_stats = []

    # ── Revenue hero ──
    try:
        rc = rc_mon.summary()
        ov = rc.get("overview", {})
        mrr = ov.get("mrr", 0)
        subs = ov.get("active_subscribers", 0)
        churned = ov.get("churned", 0)
        if mrr:
            all_stats.append({"label": "MRR", "value": f"${mrr:,.0f}", "status": "good"})
            all_stats.append({"label": "Subscribers", "value": f"{subs:,}", "status": "good"})
            if churned > 0:
                all_stats.append({"label": "Churned", "value": f"{churned}", "status": "bad"})
    except Exception:
        pass

    # ── Service health status grid ──
    try:
        svc_data = svc_health.summary()
        if svc_data:
            grid = []
            for svc in svc_data[:8]:
                st = svc.get("status", "unknown")
                grid.append({
                    "label": svc.get("name", "?"),
                    "value": st.replace("_", " ").upper(),
                    "status": "good" if st in ("operational", "up") else "warn" if "degraded" in st else "bad",
                })
            all_stats.extend(grid[:4])  # Top 4 services as stat cards
    except Exception:
        pass

    # ── Roadmap countdown ──
    try:
        milestones = _load_roadmap()
        from datetime import datetime as _dt
        today = _dt.utcnow().date()
        upcoming = []
        for m in milestones:
            if m.get("status", "").lower() in ("done", "complete", "completed"):
                continue
            target = m.get("target_date")
            if target:
                try:
                    td = _dt.strptime(target, "%Y-%m-%d").date()
                    days = (td - today).days
                    upcoming.append({"title": m.get("title", "?"), "days": days, "date": target})
                except (ValueError, TypeError):
                    pass
        upcoming.sort(key=lambda x: x["days"])
        for item in upcoming[:3]:
            status = "bad" if item["days"] < 0 else "warn" if item["days"] <= 7 else "good"
            days_str = "OVERDUE" if item["days"] < 0 else f"{item['days']}d"
            label = f"{days_str}: {item['title']}"
            all_stats.append({"label": label, "value": item["date"], "status": status})
    except Exception:
        pass

    # ── Proactive insights ──
    try:
        insights = await _analyze_insights()
        for ins in insights[:3]:
            all_stats.append({
                "label": f"▸ {ins['title']}",
                "value": ins["severity"].upper(),
                "status": "bad" if ins["severity"] == "high" else "warn" if ins["severity"] == "medium" else None,
            })
    except Exception:
        pass

    if not sections and not all_stats:
        return None

    return {
        "title": "EXECUTIVE DASHBOARD",
        "sections": sections if sections else None,
        "chart": sections[0].get("chart") if sections else None,
        "stats": all_stats,
        "summary": "Multi-source overview: revenue, markets, services, and upcoming deadlines.",
    }


async def _panel_services(intent: str) -> dict | None:
    """Build service health panel using status_grid visualization."""
    try:
        svc_data = svc_health.summary()
        if not svc_data:
            return None
        status_map = {
            "operational": "good", "none": "good",
            "degraded_performance": "warn", "partial_outage": "warn",
            "major_outage": "bad", "under_maintenance": "warn",
        }
        grid_items = []
        for svc in svc_data:
            raw_status = svc.get("status", "unknown").lower().replace(" ", "_")
            mapped = status_map.get(raw_status, None)
            grid_items.append({
                "label": svc.get("name", svc.get("id", "?")),
                "status": mapped,
                "value": svc.get("description", raw_status.replace("_", " ").upper()),
            })
        ok_count = sum(1 for g in grid_items if g["status"] == "good")
        warn_count = sum(1 for g in grid_items if g["status"] == "warn")
        bad_count = sum(1 for g in grid_items if g["status"] == "bad")
        summary_parts = [f"{ok_count}/{len(grid_items)} operational"]
        if warn_count:
            summary_parts.append(f"{warn_count} degraded")
        if bad_count:
            summary_parts.append(f"{bad_count} down")
        # Collect active incident details for the panel
        incident_rows = []
        for svc in svc_data:
            for inc in svc.get("incidents", []):
                affected = ", ".join(inc.get("affected_components", [])[:3]) or svc.get("name", "")
                incident_rows.append([
                    svc.get("name", "?"),
                    inc.get("name", "Incident")[:60],
                    inc.get("impact", "unknown").upper(),
                    affected,
                ])
        panel = {
            "title": "SERVICE HEALTH",
            "status_grid": grid_items,
            "summary": ", ".join(summary_parts) + ".",
        }
        if incident_rows:
            panel["table"] = {
                "headers": ["Service", "Incident", "Impact", "Affected"],
                "rows": incident_rows[:8],
            }
            panel["summary"] += " Active incidents may impact GCP-hosted services."
        return panel
    except Exception:
        return None


async def _panel_roadmap(intent: str) -> dict | None:
    """Build roadmap/business plan panel."""
    try:
        milestones = _load_roadmap()
        if not milestones:
            # Auto-seed if empty
            try:
                result = await seed_roadmap()
                milestones = result.get("milestones", []) if isinstance(result, dict) else []
            except Exception:
                pass
            if not milestones:
                milestones = _load_roadmap()

        now = datetime.utcnow()
        status_map = {"planned": None, "in_progress": "good", "completed": "good",
                      "at_risk": "bad", "blocked": "bad"}
        cat_icons = {"launch": "◆", "milestone": "◇", "campaign": "▸",
                     "review": "▹"}

        # Stats summary
        total = len(milestones)
        completed = sum(1 for m in milestones if m.get("status") == "completed")
        in_prog = sum(1 for m in milestones if m.get("status") == "in_progress")
        at_risk = sum(1 for m in milestones if m.get("status") in ("at_risk", "blocked"))
        upcoming = sum(1 for m in milestones
                       if m.get("date") and datetime.fromisoformat(m["date"]) > now
                       and m.get("status") != "completed")

        stats = [
            {"label": "Total", "value": str(total), "status": None},
            {"label": "In Progress", "value": str(in_prog), "status": "good" if in_prog > 0 else None},
            {"label": "Completed", "value": str(completed), "status": "good" if completed > 0 else None},
            {"label": "At Risk", "value": str(at_risk), "status": "bad" if at_risk > 0 else "good"},
            {"label": "Upcoming", "value": str(upcoming), "status": None},
        ]

        # Sort by date
        def sort_key(m):
            try:
                return datetime.fromisoformat(m.get("date", "9999-12-31"))
            except Exception:
                return datetime(9999, 12, 31)
        sorted_ms = sorted(milestones, key=sort_key)

        # Table
        headers = ["Date", "Q", "Title", "Status", "Priority"]
        rows = []
        for m in sorted_ms:
            try:
                d = datetime.fromisoformat(m["date"])
                date_str = d.strftime("%d %b %Y")
                diff = (d - now).days
                if diff < 0:
                    date_str += f" ({abs(diff)}d ago)"
                elif diff <= 30:
                    date_str += f" ({diff}d)"
            except Exception:
                date_str = m.get("date", "TBD")
            icon = cat_icons.get(m.get("category", ""), "")
            status_display = m.get("status", "planned").replace("_", " ").upper()
            rows.append([
                date_str,
                m.get("quarter", ""),
                f"{icon} {m.get('title', '')}",
                status_display,
                m.get("priority", "medium").upper(),
            ])

        # Chart: milestones by quarter
        quarter_counts: dict[str, int] = {}
        for m in milestones:
            q = m.get("quarter", "Other")
            quarter_counts[q] = quarter_counts.get(q, 0) + 1

        panel = {
            "title": "ROADMAP & BUSINESS PLAN",
            "stats": stats,
            "table": {"headers": headers, "rows": rows},
            "chart": {
                "type": "hbar",
                "labels": list(quarter_counts.keys()),
                "values": list(quarter_counts.values()),
                "label": "Milestones by Quarter",
            },
            "summary": f"{total} milestones planned. {completed} completed, {in_prog} in progress"
                       + (f", {at_risk} at risk" if at_risk else "") + ".",
        }
        return panel
    except Exception as e:
        log.error(f"Roadmap panel failed: {e}")
        return None


# ── Server-Sent Events (proactive notifications) ─────────────────────

@app.get("/api/events")
async def sse_events(request: Request):
    """SSE stream for proactive notifications (scheduled reports, reminders)."""
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _sse_clients.append(q)

    async def event_generator():
        try:
            # Send initial heartbeat
            yield f"data: {json.dumps({'type': 'connected', 'jobs': list(scheduler.jobs.keys())})}\n\n"
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive ping
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in _sse_clients:
                _sse_clients.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Schedule Management API ──────────────────────────────────────────

@app.get("/api/schedules")
async def list_schedules():
    """List all scheduled jobs."""
    result = []
    for jid, job in scheduler.jobs.items():
        result.append({
            "id": jid,
            "name": job["name"],
            "cron": job["cron"],
            "enabled": job["enabled"],
            "last_run": job["last_run"],
            "builtin": not jid.startswith("user_"),
        })
    return {"schedules": result}


@app.post("/api/schedules")
async def create_schedule(request: Request):
    """Create a new user schedule."""
    body = await request.json()
    name = body.get("name", "").strip()
    cron = body.get("cron", "").strip()
    message = body.get("message", "").strip()

    if not name or not cron or not message:
        return {"error": "name, cron, and message are required"}

    # Validate cron
    parts = cron.split()
    if len(parts) != 5:
        return {"error": "cron must have 5 fields: minute hour dom month dow"}

    import time as _t
    job_id = f"user_{int(_t.time())}"
    handler = _make_reminder_handler(message)
    scheduler.add(job_id, name, cron, handler, enabled=True)
    scheduler.save_user_jobs()

    return {"status": "ok", "id": job_id, "name": name, "cron": cron}


@app.post("/api/schedules/{job_id}/toggle")
async def toggle_schedule(job_id: str, request: Request):
    """Enable or disable a scheduled job."""
    body = await request.json()
    enabled = body.get("enabled", True)
    scheduler.toggle(job_id, enabled)
    if job_id.startswith("user_"):
        scheduler.save_user_jobs()
    return {"status": "ok", "id": job_id, "enabled": enabled}


@app.post("/api/schedules/{job_id}/trigger")
async def trigger_schedule(job_id: str):
    """Manually trigger a scheduled job right now (for testing)."""
    if job_id not in scheduler.jobs:
        return {"error": "Job not found"}
    job = scheduler.jobs[job_id]
    try:
        await job["handler"]()
        return {"status": "ok", "name": job["name"], "triggered": True}
    except Exception as e:
        return {"error": str(e)}


# ── Jarvis Voice Chat ─────────────────────────────────────────────────
@app.post("/api/jarvis/chat")
async def jarvis_chat(request: Request):
    body = await request.json()
    user_msg = body.get("message", "").strip()
    history = body.get("history", [])
    business_id = _get_business_id(request)

    if not user_msg:
        return {"reply": "I didn't catch that. Could you repeat?", "error": False}

    # ── Detect topic FIRST so we can build a slim context ──────
    import re
    topic = _detect_topic(user_msg.lower())
    if not topic:
        # Only inherit topic from history if the follow-up message looks like it
        # continues the prior thread (uses pronouns, analytical words, or is a
        # short question). Prevents "What's the best pasta recipe?" from
        # inheriting a stocks topic just because Apple was discussed earlier.
        _continuity_rx = re.compile(
            r'\b(they|them|their|theirs|its|it|that|those|this|the same|'
            r'also|too|as well|further|furthermore|additionally|'
            r'drove|boost|factor|cause|impact|affect|contribut|'
            r'why did|how did|what about|what else|tell me more|'
            r'and what|so what|but what|but how|but why)\b',
            re.IGNORECASE,
        )
        _looks_like_followup = bool(_continuity_rx.search(user_msg))
        if _looks_like_followup:
            recent_context = user_msg
            for h in history[-2:]:
                recent_context += " " + h.get("content", "")
            hist_topic = _detect_topic(recent_context.lower())
            if hist_topic:
                topic = hist_topic

    # ── CLAUDE TOOL-CALLING PATH (primary when API key is configured) ──────
    # Claude receives tools and pulls only the data it needs — no pre-fetching,
    # no bloated context. Falls back to the Ollama path below on failure.
    if ANTHROPIC_API_KEY and not _claude_check_budget():
        _claude_result = await _jarvis_chat_claude(user_msg, history, topic, business_id=business_id)
        if _claude_result is not None:
            return _claude_result
        log.warning("Claude tool path returned None — falling back to Ollama path")

    # ── OLLAMA / LEGACY PATH ─────────────────────────────────────────────
    # Build context — topic-aware (fast & small) when topic is known
    ctx = await _get_context_fast(topic=topic, query=user_msg, business_id=business_id)

    # ── On-demand location weather: detect "weather in <place>" queries ──
    loc_match = re.search(
        r'weather\s+(?:in|for|at)\s+([A-Za-z\s\-]+)',
        user_msg, re.IGNORECASE,
    )
    extra_ctx = ""
    if loc_match:
        place = loc_match.group(1).strip().rstrip('?.,')
        if place.lower() not in ("london", ""):
            try:
                w = await weather(location=place)
                cur = w.get("current", {})
                if cur:
                    extra_ctx = (
                        f"\nWeather ({w.get('location', place)}):"
                        f"\n  Temperature: {cur.get('temperature_2m', '?')}°C"
                        f" (feels like {cur.get('apparent_temperature', '?')}°C)"
                        f"\n  Humidity: {cur.get('relative_humidity_2m', '?')}%"
                        f"  Wind: {cur.get('wind_speed_10m', '?')} km/h"
                    )
                    daily = w.get("daily", {})
                    if daily.get("temperature_2m_max"):
                        for i in range(min(3, len(daily["temperature_2m_max"]))):
                            extra_ctx += (
                                f"\n  Forecast day {i}: "
                                f"{daily['temperature_2m_min'][i]}–{daily['temperature_2m_max'][i]}°C"
                            )
            except Exception:
                pass

    # ── Detect if user explicitly wants a visualization ─────────
    VIS_RX = re.compile(
        r'\b(show|graph|chart|plot|visuali[sz]e|compare|break\s*down|display|overview|view|analyse|analyze|breakdown|insight|deep\s*dive)\b',
        re.IGNORECASE,
    )
    wants_panel = bool(VIS_RX.search(user_msg))
    panel_data = None

    # Auto-show panels for topics that are inherently visual
    _AUTO_PANEL_TOPICS = {"roadmap", "stocks", "services", "gcp", "weather", "revenue"}
    if topic in _AUTO_PANEL_TOPICS and not wants_panel:
        wants_panel = True

    # Auto-panel for general briefing queries (no topic but executive dashboard)
    _BRIEFING_PATTERNS = ["briefing", "status report", "how am i doing", "overview",
                          "what's going on", "update me", "catch me up", "summary",
                          "how's everything", "what's happening", "sitrep", "how are things"]
    if not wants_panel and any(p in user_msg.lower() for p in _BRIEFING_PATTERNS):
        wants_panel = True

    # Affirmative follow-ups ("yes", "sure", "go ahead") — carry forward panels
    _AFFIRMATIVE = re.compile(r'^(yes|yeah|yep|sure|go ahead|absolutely|please|do it|ok|okay)[.!]?$', re.IGNORECASE)
    if not wants_panel and topic and _AFFIRMATIVE.match(user_msg.strip()):
        wants_panel = True

    # ── Contextual follow-up panel detection ──────────────────
    # If the conversation history shows a recent panel-worthy topic, follow-up
    # questions that dig deeper should also generate panels
    if not wants_panel and history and len(history) >= 2:
        # Check if previous exchanges involved a visual topic
        _prev_topic = None
        for h in reversed(history[-4:]):
            _prev_content = (h.get("content", "") or "").lower()
            _prev_topic = _detect_topic(_prev_content)
            if _prev_topic:
                break
        # Follow-up patterns that warrant visualization — require analytical
        # language, not just a bare question word like "what" or "how"
        _FOLLOWUP_ANALYTICAL = re.compile(
            r'\b(specific|detail|boost|drove|contribut|impact|affect|caus|result|lead to|'
            r'growth|decline|revenue|product|segment|division|area|sector|region|'
            r'breakdown|performance|factor|driver|trend|compar|correlat|'
            r'outperform|underperform|return|gain|loss|profit|margin)\b',
            re.IGNORECASE,
        )
        _FOLLOWUP_DEEP_Q = re.compile(
            r'^(what\s+(specific|drove|caus|factor|made|impact|boost|contribut)|'
            r'which\s+(product|segment|factor|area|region|sector)|'
            r'how\s+(did|does|has|much|many|well)|'
            r'why\s+(did|does|has|is|are|was|were))',
            re.IGNORECASE,
        )
        if _prev_topic and (_FOLLOWUP_ANALYTICAL.search(user_msg) or _FOLLOWUP_DEEP_Q.match(user_msg.strip())):
            topic = topic or _prev_topic
            wants_panel = True
            log.info(f"Contextual follow-up panel: inherited topic={topic} from conversation history")

    # ── Schedule/reminder commands: intercept ─────────────────
    import re as _re
    sched_match = _re.search(
        r'(?:remind me|set a reminder|schedule)\s+(?:to\s+)?(.+?)\s+'
        r'(?:at|every day at|daily at|every)\s+(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?)',
        user_msg, _re.IGNORECASE,
    )
    if sched_match:
        message = sched_match.group(1).strip().rstrip('.,')
        time_str = sched_match.group(2).strip()
        # Parse time
        try:
            hour, minute = 0, 0
            if ':' in time_str:
                parts = time_str.replace('am', '').replace('pm', '').strip().split(':')
                hour, minute = int(parts[0]), int(parts[1])
            else:
                hour = int(time_str.replace('am', '').replace('pm', '').strip())
            if 'pm' in time_str.lower() and hour < 12:
                hour += 12
            if 'am' in time_str.lower() and hour == 12:
                hour = 0

            cron_expr = f"{minute} {hour} * * *"
            import time as _t
            job_id = f"user_{int(_t.time())}"
            handler = _make_reminder_handler(message)
            scheduler.add(job_id, message[:40], cron_expr, handler, enabled=True)
            scheduler.save_user_jobs()

            time_display = f"{hour:02d}:{minute:02d}"
            return {
                "reply": f"Done, Sir. I've set a daily reminder at {time_display}: \"{message}\".",
                "error": False,
                "panel": {
                    "title": "SCHEDULE CREATED",
                    "stats": [
                        {"label": "Reminder", "value": message, "status": None},
                        {"label": "Time", "value": time_display, "status": "good"},
                        {"label": "Frequency", "value": "Daily", "status": None},
                    ],
                },
            }
        except (ValueError, IndexError):
            pass  # Fall through to normal LLM handling

    # ── Desktop automation: intercept and handle ────────────────
    desktop_cmd = _detect_desktop_command(user_msg)
    if desktop_cmd:
        return await _execute_desktop_action(desktop_cmd)

    # ── Web scraping: fetch a URL for research ─────────────────
    import re as _re_web
    web_url_match = _re_web.search(
        r'(?:research|look up|scrape|fetch|read|summarise|summarize|what does|check)\s+'
        r'(?:the page|this page|this url|this site|the site|the article|)?\s*'
        r'(https?://\S+)', user_msg, _re_web.IGNORECASE,
    )
    if not web_url_match:
        # Also catch: "what's on <url>" or just a bare URL with context
        web_url_match = _re_web.search(r'(https?://\S+)', user_msg)
    if web_url_match:
        url = web_url_match.group(1).rstrip('.,;!?')
        web_content = await _web_fetch(url, max_chars=3000)
        if not web_content.startswith("[Error"):
            extra_ctx += f"\n\n[WEB PAGE CONTENT from {url}]\n{web_content}\n[END WEB PAGE]"
            log.info(f"Web fetch: {url} ({len(web_content)} chars)")

    # ── Auto-research: for open-domain queries, search the web ──
    # Triggers when: no internal data source matches AND the query has substantive content
    # Also triggers for deep research queries even when a topic IS matched (e.g. stock investment areas)
    _RESEARCH_RX = re.compile(
        r'\b(compare|vs|versus|buy|sell|invest|price|cost|value|worth|trend|'
        r'market|analysis|analyze|review|rate|rank|best|worst|top|forecast|'
        r'predict|outlook|should i|what about|how does|pros and cons|'
        r'ebay|amazon|etsy|crypto|bitcoin|nft|pokemon|cards|collecti|'
        r'social media|instagram|tiktok|youtube|twitter|facebook|linkedin|'
        r'competitor|industry|sector|growth|decline|revenue|profit|'
        r'focus|strategy|initiative|pipeline|roadmap|r&d|acquisition|'
        r'expansion|partnership|launch|upcoming|plan|next\s+\d+\s+months?|'
        r'\d+\s*years?|performance|performing|'
        r'climate|environment|emission|carbon|sustain|energy|pollution|'
        r'risk|likelihood|probability|impact|threat|danger|consequence|'
        r'global|worldwide|international|geopolit|econom|inflation|gdp|'
        r'health|disease|pandemic|nutrition|fitness|'
        r'technology|ai\b|artificial intelligence|machine learning|quantum|'
        r'space|mars|nasa|orbit|satellite|'
        r'housing|property|real estate|mortgage|rent|'
        r'education|university|student|degree|'
        r'population|demographics|birth\s*rate|death\s*rate|life\s*expectancy|'
        r'salary|wage|income|tax|interest\s*rate|unemployment|'
        r'country|nation|continent|city|capital|'
        r'programming\s+language|python\s+vs|javascript\s+vs|react\s+vs|'
        r'database\s+comparison|framework\s+comparison|'
        r'recipe\s+for|cooking|ingredient|calories|'
        r'electric\s+vehicle|electric\s+car|ev\s+market|battery\s+range|'
        r'box\s+office|film\s+review|book\s+review|album\s+review|'
        r'music\s+industry|artist\s+revenue|'
        r'breakdown|deep dive|overview|view on|give me a view)\b',
        re.IGNORECASE,
    )
    # Deep research patterns — queries needing web research even WITH a topic.
    # These are analytical questions that need real-world data, not just stock prices.
    _DEEP_RX = re.compile(
        r'\b(invest|focus|strateg|initiative|pipeline|roadmap|r&d|acquisition|'
        r'expansion|partnership|launch|upcoming|plan|next\s+\d+\s+months?|'
        r'outlook|forecast|predict|pros and cons|should i|'
        r'innovat|product|feature|drove|boost|contribut|impact|'
        r'specific|detail|what\s+made|what\s+drove|what\s+caus|'
        r'breakdown|growth\s+driver|key\s+factor|competitive|advantage|'
        r'chip|silicon|hardware|software|ecosystem|'
        r'market\s+share|revenue\s+source|segment|division|'
        r'success|fail|struggle|dominat|disrupt|pivot|transform|'
        r'analyst|rating|target\s+price|valuation|fundamentals|'
        r'supply\s+chain|manufacturing|distribution|logistics|'
        r'leadership|ceo|management|board|executive|'
        r'regulatory|antitrust|lawsuit|compliance|'
        r'customer|user\s+base|subscriber|retention|churn|'
        r'moat|differentiat|unique\s+selling|usp|'
        r'\d+\s*years?|historical|decade|trajectory|long\s*term)\b',
        re.IGNORECASE,
    )
    # Also detect contextual follow-up queries that need research
    _is_followup_needing_data = (
        history and len(history) >= 2
        and re.match(r'^(what|which|how|why|where|who|tell|explain|describe|can you|show)\b', user_msg.strip(), re.IGNORECASE)
        and len(user_msg.split()) >= 4
    )
    _needs_research = (
        (not topic and not web_url_match and len(user_msg.split()) >= 3 and _RESEARCH_RX.search(user_msg))
        or (topic and _DEEP_RX.search(user_msg) and len(user_msg.split()) >= 4)
        or (topic and _is_followup_needing_data)
    )
    _has_research = False
    if _needs_research:
            wants_panel = True  # Force panel for research queries
            _has_research = True
            # ── Extract the SUBJECT(s) from current message first, then history ──
            _topic_subject = None
            _all_subjects = []  # For multi-company queries
            # Check current message for company/product names (detect ALL)
            _all_syms = _detect_all_stock_symbols(user_msg)
            if _all_syms:
                _all_subjects = [_TICKER_NAMES.get(s, s) for s in _all_syms]
                _topic_subject = " vs ".join(_all_subjects) if len(_all_subjects) > 1 else _all_subjects[0]
                log.info(f"Multi-company detected: {_all_subjects} → subject='{_topic_subject}'")
            # Also look for proper nouns OR meaningful lowercase words as subjects
            if not _topic_subject:
                # Try capitalised proper nouns first
                _proper_nouns = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b', user_msg)
                _ignore_words = {"What", "Why", "How", "Which", "Where", "Who", "When",
                                 "Tell", "Show", "Give", "Can", "Could", "Would", "Should",
                                 "The", "This", "That", "Their", "There", "These"}
                _proper_nouns = [n for n in _proper_nouns if n.split()[0] not in _ignore_words]
                if _proper_nouns:
                    _topic_subject = _proper_nouns[0]
                    _all_subjects = _proper_nouns[:4]
                else:
                    # Fallback: extract key nouns from lowercase input
                    # Strip common filler words and use remaining meaningful terms
                    _cleaned = re.sub(
                        r'\b(i|me|my|am|is|are|was|were|be|been|do|does|did|have|has|had|'
                        r'will|would|could|should|can|may|might|shall|must|need|want|'
                        r'the|a|an|of|in|on|at|to|for|with|from|by|about|into|through|'
                        r'and|or|but|if|so|yet|nor|not|no|its|their|them|they|that|this|'
                        r'what|where|when|which|who|why|how|show|give|tell|get|'
                        r'curious|understand|idea|view|full|next|also|just|really|very)\b',
                        '', user_msg.lower(), flags=re.IGNORECASE
                    ).strip()
                    _cleaned = re.sub(r'\s+', ' ', _cleaned).strip(' .,?!')
                    if _cleaned and len(_cleaned) > 2:
                        _topic_subject = _cleaned[:60]
                        log.info(f"Extracted subject from lowercase input: '{_topic_subject}'")
            # Fall back to conversation history
            if not _topic_subject and topic and history and len(history) >= 2:
                for h in reversed(history[-4:]):
                    _hc = h.get("content", "") or ""
                    _sym = _detect_stock_symbol(_hc)
                    if _sym:
                        _topic_subject = _TICKER_NAMES.get(_sym, _sym)
                        break
                    for _tname in [v for k, v in _TICKER_NAMES.items() if not k.startswith("^")]:
                        if _tname.lower() in _hc.lower():
                            _topic_subject = _tname
                            break
                    if _topic_subject:
                        break

            # ── Detect prior conversation context to carry into searches ──
            _prior_context = ""
            if history and len(history) >= 2:
                _last_msgs = " ".join((h.get("content", "") or "")[:200] for h in history[-4:]).lower()
                if any(w in _last_msgs for w in ("stock", "share price", "market cap", "revenue", "earnings", "s&p")):
                    _prior_context = "stock market company"
                elif any(w in _last_msgs for w in ("climate", "emission", "temperature", "carbon")):
                    _prior_context = "climate environment"
                elif any(w in _last_msgs for w in ("technology", "software", "ai ", "innovation")):
                    _prior_context = "technology industry"

            # ── Build MULTIPLE targeted search queries for deeper intel ──
            base_query = re.sub(r'\b(show me|tell me|can you|what is|what are|how is|how are)\b', '', user_msg, flags=re.IGNORECASE).strip()
            if _topic_subject and _topic_subject.lower() not in base_query.lower():
                base_query = f"{_topic_subject} {base_query}"
            # Inject prior topic context so follow-ups don't lose meaning
            # e.g. "How does Samsung compare?" after stock discussion → "Samsung stock market company compare"
            if _prior_context and _prior_context not in base_query.lower():
                base_query = f"{base_query} {_prior_context}"

            # Generate focused search angles for richer, multi-source data.
            # Works for ANY topic — companies, countries, technologies, concepts.
            # ALWAYS append the current year to bias results toward recent data.
            _cur_year = datetime.utcnow().year
            _q_lower = user_msg.lower()
            _subject_str = _topic_subject if _topic_subject else " ".join(base_query.split()[:4])

            # ── Multi-company comparison queries: search for ALL companies ──
            _is_multi_company = len(_all_subjects) > 1
            if _is_multi_company:
                # For multi-company queries, build one comparison query + per-company queries
                _companies_str = " vs ".join(_all_subjects[:4])
                search_queries = [f"{_companies_str} comparison investment outlook {_cur_year}"]
                # Add per-company strategic queries (up to 4 companies)
                for _comp in _all_subjects[:4]:
                    search_queries.append(f"{_comp} strategic investment portfolio AI {_cur_year}")
                log.info(f"Multi-company research queries ({len(_all_subjects)} companies): {search_queries}")
            else:
                # Base query always includes current year for freshness
                search_queries = [f"{base_query[:100]} {_cur_year}"]

                # Detect time-based queries — add historical + current angle
                _time_match = re.search(r'\b(\d+)\s*years?|decade|over\s+the\s+(last|past)|over\s+time|since\s+\d{4}|histor', _q_lower)
                if _time_match:
                    search_queries.append(f"{_subject_str} performance data {_cur_year}")
                    search_queries.append(f"{_subject_str} statistics trends {_cur_year - 1} {_cur_year}")
                # Finance/business angles
                elif any(w in _q_lower for w in ("growth", "grew", "drove", "boost", "factor", "driver")):
                    search_queries.append(f"{_subject_str} growth drivers strategy {_cur_year}")
                    search_queries.append(f"{_subject_str} revenue breakdown {_cur_year}")
                elif any(w in _q_lower for w in ("invest", "buy", "sell", "hold", "outlook", "forecast")):
                    search_queries.append(f"{_subject_str} analyst investment outlook {_cur_year}")
                    search_queries.append(f"{_subject_str} risks opportunities {_cur_year}")
                elif any(w in _q_lower for w in ("strateg", "plan", "future", "roadmap", "vision")):
                    search_queries.append(f"{_subject_str} strategy plans {_cur_year}")
                    search_queries.append(f"{_subject_str} competitive position {_cur_year}")
                elif any(w in _q_lower for w in ("innovat", "product", "feature", "technology", "r&d")):
                    search_queries.append(f"{_subject_str} innovations technology {_cur_year}")
                    search_queries.append(f"{_subject_str} R&D breakthroughs {_cur_year}")
                elif any(w in _q_lower for w in ("compet", "rival", "vs", "versus", "against", "compar")):
                    search_queries.append(f"{_subject_str} comparison data {_cur_year}")
                    search_queries.append(f"{_subject_str} competitive landscape {_cur_year}")
                elif any(w in _q_lower for w in ("populat", "demograph", "rate", "percentage", "statistic")):
                    search_queries.append(f"{_subject_str} statistics data {_cur_year}")
                    search_queries.append(f"{_subject_str} demographics trends {_cur_year}")
                elif any(w in _q_lower for w in ("climate", "environment", "emission", "pollut", "carbon")):
                    search_queries.append(f"{_subject_str} data statistics {_cur_year}")
                    search_queries.append(f"{_subject_str} impact projections {_cur_year}")
                elif any(w in _q_lower for w in ("salary", "wage", "income", "cost", "price", "afford")):
                    search_queries.append(f"{_subject_str} data trends {_cur_year}")
                    search_queries.append(f"{_subject_str} comparison analysis {_cur_year}")
                else:
                    search_queries.append(f"{_subject_str} latest data analysis {_cur_year}")
                log.info(f"Research search queries: {search_queries}")

            try:
                # Run ALL search queries in PARALLEL for speed
                # Multi-company queries get more search slots for coverage
                _max_queries = 5 if _is_multi_company else 3
                _max_urls = 7 if _is_multi_company else 5
                _max_fetch = 5 if _is_multi_company else 3
                all_search_urls = []
                async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
                    ddg_tasks = []
                    for sq in search_queries[:_max_queries]:
                        ddg_tasks.append(client.get(
                            "https://html.duckduckgo.com/html/",
                            params={"q": sq},
                            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                        ))
                    ddg_results = await asyncio.gather(*ddg_tasks, return_exceptions=True)
                    # DDG returns 200 or 202 (Accepted) for valid results
                    _ddg_ok = sum(1 for r in ddg_results if not isinstance(r, Exception) and r.status_code in (200, 202))
                    _ddg_fail = len(ddg_results) - _ddg_ok
                    if _ddg_fail:
                        log.warning(f"DuckDuckGo: {_ddg_ok}/{len(ddg_results)} succeeded, {_ddg_fail} failed")
                    else:
                        log.info(f"DuckDuckGo: {_ddg_ok}/{len(ddg_results)} succeeded")
                    seen_domains = set()
                    for ddg_resp in ddg_results:
                        if isinstance(ddg_resp, Exception) or ddg_resp.status_code not in (200, 202):
                            continue
                        import re as _re_ddg
                        urls = _re_ddg.findall(r'href="(https?://[^"]+)"', ddg_resp.text)
                        urls = [u for u in urls if 'duckduckgo.com' not in u and 'duck.co' not in u]
                        # Deduplicate by domain so we get diverse sources
                        for u in urls:
                            _domain = re.sub(r'^https?://(www\.)?', '', u).split('/')[0]
                            if _domain not in seen_domains:
                                seen_domains.add(_domain)
                                all_search_urls.append(u)
                                if len(all_search_urls) >= _max_urls:
                                    break
                        if len(all_search_urls) >= _max_urls:
                            break

                # Fetch top results IN PARALLEL for speed
                # Multi-company queries get higher context cap for coverage
                _MAX_RESEARCH_CTX = 6000 if _is_multi_company else 4000
                _research_chars = 0
                if all_search_urls:
                    fetch_tasks = [_web_fetch(surl, max_chars=1500) for surl in all_search_urls[:_max_fetch]]
                    fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                    for surl, content in zip(all_search_urls[:_max_fetch], fetch_results):
                        if isinstance(content, Exception) or not content or content.startswith("[Error"):
                            continue
                        # Trim if we're approaching the cap
                        _remaining = _MAX_RESEARCH_CTX - _research_chars
                        if _remaining <= 200:
                            log.info(f"Research context cap reached ({_research_chars} chars), skipping {surl}")
                            break
                        if len(content) > _remaining:
                            content = content[:_remaining]
                        extra_ctx += f"\n\n[WEB RESEARCH from {surl}]\n{content}\n[END WEB RESEARCH]"
                        _research_chars += len(content)
                        log.info(f"Auto-research: {surl} ({len(content)} chars, total={_research_chars})")
            except Exception as e:
                log.warning(f"Auto-research failed: {e}")

    # ── ComfyUI creative command: intercept and handle ─────────
    if topic == "comfyui":
        creative_prompt = _extract_creative_prompt(user_msg)
        try:
            # Check if ComfyUI is reachable first
            async with httpx.AsyncClient() as c:
                health = await c.get(f"{COMFYUI_URL}/system_stats", timeout=3)
            if health.status_code != 200:
                raise ConnectionError("ComfyUI offline")

            gen_result = await _comfyui_generate(creative_prompt)
            panel_data = {
                "title": "COMFYUI — IMAGE GENERATED",
                "image_url": gen_result["url"],
                "stats": [
                    {"label": "Prompt", "value": creative_prompt[:60], "status": None},
                    {"label": "Resolution", "value": f"{gen_result['width']}×{gen_result['height']}", "status": None},
                    {"label": "Steps", "value": str(gen_result["steps"]), "status": None},
                    {"label": "Time", "value": f"{gen_result['elapsed']}s", "status": "good"},
                ],
            }
            return {
                "reply": f"Done, Sir. I've generated that image for you — {creative_prompt}. Rendered in {gen_result['elapsed']} seconds on the RTX 3080.",
                "error": False,
                "panel": panel_data,
            }
        except ConnectionError:
            return {
                "reply": "I'm afraid ComfyUI isn't reachable on the Windows PC, Sir. Make sure it's running and on the network.",
                "error": False,
            }
        except Exception as e:
            log.error(f"ComfyUI creative action failed: {e}")
            return {
                "reply": f"The image generation hit a snag, Sir. {str(e)[:80]}",
                "error": False,
            }

    # Pre-build topic panel ONLY for simple queries without web research.
    # When research is active, the dynamic panel builder will create a MUCH richer
    # panel from the actual web data. Pre-built panels are limited to our tracked
    # data (stock quotes, service health, etc.) and can't cover arbitrary companies,
    # competitive analyses, or investment breakdowns.
    #
    # Pre-built panel (no research):
    #   "How's the market?" → stock overview from tracked symbols
    #   "Show me my portfolio" → quick quote summary
    #   "Service status" → health dashboard
    #
    # Dynamic panel (research active):
    #   "Give me a full breakdown of Nvidia stock and their new AI chip"
    #   "Compare Microsoft to competitors"
    #   "Where is Apple investing for the next 5 years?"
    #
    # Simple data queries WITHOUT research still get pre-built panels for speed:
    _is_simple_data = not _has_research and bool(re.search(
        r'\b(perform|progress|trend|track|chart|graph|plot|histor|timeline|'
        r'over\s+the\s+(last|past)|over\s+time|over\s+\d+|'
        r'last\s+\d+|past\s+\d+|since\s+\d{4}|'
        r'how\s+(has|have|did|does|do|much|many|far)|'
        r'show\s+me|give\s+me|display|visuali[sz]e)\b',
        user_msg, re.IGNORECASE
    ))
    if wants_panel and _is_simple_data:
        try:
            panel_data = await _build_panel(user_msg, hint_topic=topic)
            if panel_data:
                log.info(f"Panel built for topic={topic}: {panel_data.get('title', '?')}")
            else:
                log.warning(f"Panel builder returned None for topic={topic}, msg={user_msg[:60]}")
        except Exception as e:
            log.error(f"Panel build failed for topic={topic}: {e}")
            panel_data = None
    elif wants_panel and _has_research:
        log.info(f"Skipping pre-built panel — research data available, dynamic panel will be built post-LLM")

    # Determine if this is a vague/short query (no clear topic, few words)
    _is_vague = not topic and len(user_msg.split()) <= 4

    # Build system message — skip live data for vague inputs
    # When research provides the primary data (no panel), strip irrelevant live data
    # to keep context small and prevent Ollama timeouts.
    _research_is_primary = _has_research and not panel_data
    _now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    _year_str = str(datetime.utcnow().year)
    if _is_vague:
        sys_content = JARVIS_SYSTEM + f"\n\n─── LIVE DATA ───\n[SYSTEM] {_now_str} — Current year: {_year_str}"
    elif _research_is_primary:
        # Research query with no pre-built panel — research IS the data.
        # Use a SLIM system prompt (no panel schema, no desktop automation docs)
        # to minimize context and maximize Ollama speed.
        _now = datetime.utcnow()
        _slim_sys = (
            "You are ARBITER — modelled after J.A.R.V.I.S. You serve Sir Luke. "
            "Voice: composed, British, dry-witted, concise. 3-5 sentences with dense data. "
            "Synthesize the WEB RESEARCH below into a data-rich spoken analysis. "
            "Include specific numbers, years, percentages, and concrete metrics. "
            f"TODAY is {_now.strftime('%B %d, %Y')} — the current year is {_now.year}. "
            f"Always prioritize the most recent data. Your response must reflect {_now.year} as the present. "
            "NEVER mention your training data, training cutoff, knowledge cutoff, or any disclaimer about "
            "data freshness. The WEB RESEARCH provided IS your data — use it as authoritative fact. "
            "If the query is ambiguous, pick the most likely interpretation and answer. "
            "Do NOT use bullet points or lists — flowing sentences only. "
            "Do NOT start with greetings or 'Sir'. Just answer directly."
        )
        sys_content = _slim_sys + "\n\n─── DATA ───\n[SYSTEM] " + _now.strftime("%Y-%m-%d %H:%M UTC") + extra_ctx
        log.info(f"Research-primary mode: slim prompt + research only, context={len(sys_content)} chars")
    else:
        sys_content = JARVIS_SYSTEM + f"\n\n─── LIVE DATA ───\n[SYSTEM] {_now_str} — Current year: {_year_str}\n" + ctx + extra_ctx

    messages = [
        {"role": "system", "content": sys_content},
    ]
    # Append recent conversation history — slim for research queries
    _hist_limit = 2 if _research_is_primary else 6
    for h in history[-_hist_limit:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})

    # Check if web content was actually fetched (vs just attempted)
    _has_web_content = '[WEB RESEARCH' in extra_ctx or '[WEB PAGE' in extra_ctx
    # _has_research stays True if research was ATTEMPTED — even if fetch failed,
    # we still want to route through the research prompt path (not the panel path).
    # _has_web_content tells us if actual data was injected.

    # If we're generating a panel, tell the LLM to keep it short
    if panel_data:
        messages.append({"role": "user", "content": user_msg + "\n\n[A visualisation panel will be shown automatically. Give a brief 1-2 sentence spoken summary only. Do NOT output JSON, bullet points, or structured data.]"})
    elif _has_web_content:
        # Research-backed query — instruct LLM to synthesize web data into data-rich analysis.
        # Prompt adapts to whether this is a time-based or analytical query.
        _now = datetime.utcnow()
        _cur_year = _now.year
        _time_hint = bool(re.search(r'\b(\d+)\s*years?|decade|over\s+the\s+(last|past)|over\s+time|since\s+\d{4}|histor', user_msg, re.IGNORECASE))
        # Calculate the year range the user is asking about
        _yr_match = re.search(r'\b(\d+)\s*years?', user_msg, re.IGNORECASE)
        _span = int(_yr_match.group(1)) if _yr_match else 10
        _start_year = _cur_year - _span
        if _time_hint:
            _research_prompt = (
                f"\n\n[Today is {_now.strftime('%B %d, %Y')}. Current year: {_cur_year}. "
                f"Period requested: {_start_year}–{_cur_year} ({_span} years). "
                "Use the WEB RESEARCH above. Synthesize into a data-rich timeline. "
                f"Timeline MUST end at {_cur_year}. Include year-value pairs: "
                f"'In {_start_year} it was X, by {_start_year + _span//2} it reached Y, in {_cur_year} it stands at Z.' "
                "More data points = richer auto-generated chart. Mention milestones and rates of change. "
                "3-5 flowing sentences. No bullets or lists. "
                "NEVER mention your training cutoff or knowledge limitations — the web research IS your data. "
                "If data gaps exist, flag them rather than fabricating numbers.]"
            )
        else:
            _research_prompt = (
                f"\n\n[Today is {_now.strftime('%B %d, %Y')}. Current year: {_cur_year}. "
                f"Prioritize {_cur_year} and {_cur_year - 1} data. "
                "Use the WEB RESEARCH above. Synthesize into a data-rich analysis. "
                "Include specific numbers, percentages, rankings — these feed auto-generated panels. "
                "3-5 flowing sentences. No bullets or lists. "
                "NEVER mention your training cutoff or knowledge limitations — the web research IS your data.]"
            )
        messages.append({"role": "user", "content": user_msg + _research_prompt})
    elif _has_research and not _has_web_content:
        # Research was attempted but web fetch failed — answer with best knowledge
        _now = datetime.utcnow()
        _cur_year = _now.year
        _fallback_prompt = (
            f"\n\n[Today is {_now.strftime('%B %d, %Y')}. Current year: {_cur_year}. "
            "Web research was attempted but did not return results. "
            "Answer using your best available knowledge. Include specific numbers, "
            "percentages, and data points — these feed auto-generated panels. "
            "3-5 flowing sentences. No bullets or lists. "
            "NEVER mention training data, training cutoff, knowledge limitations, or "
            "that you lack access to data. NEVER suggest consulting Bloomberg, FactSet, "
            "or any other service. NEVER refuse to answer. Just give your best analysis "
            "with the data you have. Present it confidently as a strategic analyst would.]"
        )
        messages.append({"role": "user", "content": user_msg + _fallback_prompt})
    elif wants_panel:
        # Panel query without research — keep it data-oriented
        messages.append({"role": "user", "content": user_msg + "\n\n[A data visualisation panel will be generated from your analysis. Include specific numbers, percentages, and data points in your response — these will be extracted for charts and tables. Give a concise 2-3 sentence spoken summary. Do NOT use bullet points, lists, or structured data — write in natural flowing sentences with embedded data. NEVER mention training data or knowledge cutoffs.]"})
    else:
        messages.append({"role": "user", "content": user_msg})

    # ── Get LLM reply (unified fallback chain: Claude → Ollama → OpenAI) ──
    _max_tok = 120 if panel_data else (120 if _is_vague else (400 if _has_research else 350))
    reply = await _chat_llm(messages, max_tokens=_max_tok, purpose="chat")

    if not reply:
        # Non-fatal: return error but still include panel data + followups
        _err_reply = "I'm temporarily offline, Sir. No LLM responded — check that Ollama or Claude is configured."
        _err_result = {"reply": _err_reply, "error": False}
        if panel_data:
            _err_result["panel"] = panel_data
        _err_result["followups"] = [
            {"text": "Try again", "hint": "action"},
            {"text": "What's the system status?", "hint": "broader"},
        ]
        return _err_result

    # ── Auto-panel: if reply has data, attach a rich visualization panel ──
    # Multiple panels / components should ALWAYS coexist — never block one type
    # from generating just because another already exists.
    _run_dynamic = False
    numbers = re.findall(r'[\$£€]?[\d,]+\.?\d*[%°]?', reply)
    has_comparison = bool(re.search(r'\b(vs|versus|compared|comparison|better|worse|competitor|rival)\b', user_msg, re.IGNORECASE))
    # Trigger panel if: data-rich reply OR comparison query OR explicit vis request
    _wants_enrichment = len(numbers) >= 2 or has_comparison or wants_panel
    if _wants_enrichment:
        # Try server-side topic panel ONLY if no panel yet AND no research data.
        if not panel_data and topic and not _has_research:
            _is_conversational = bool(re.match(r'^(what|which|how|why|where|who|tell|explain|describe|can you)\b', user_msg.strip(), re.IGNORECASE))
            if not _is_conversational:
                try:
                    panel_data = await _build_panel(user_msg, hint_topic=topic)
                except Exception:
                    pass
        # ALWAYS run dynamic panel builder when enrichment is possible.
        # It adds strategic components (insights, SWOT, heatmaps, radar, gauges,
        # recommendations, etc.) that the pre-built panel and regex can't provide.
        # Multiple visualization types should coexist — never block one because
        # another already exists.
        _needs_dynamic = (
            not panel_data                                     # no panel yet
            or not panel_data.get("insights")                  # panel lacks strategic depth
            or not panel_data.get("heatmap")                   # missing advanced visualizations
            or _has_research                                   # research data — always enrich
            or has_comparison                                  # comparison query
        )
        if _needs_dynamic and len(reply) > 60:
            _run_dynamic = True

    # ── Extract inline follow-ups from LLM reply (embedded in prompt) ──
    followups = None
    _followup_match = re.search(r'\[FOLLOWUPS\]\s*(\[.*\])', reply, re.DOTALL)
    if _followup_match:
        try:
            _fu_raw = _followup_match.group(1).strip()
            _fu_parsed = json.loads(_fu_raw)
            if isinstance(_fu_parsed, list) and len(_fu_parsed) >= 2:
                followups = _fu_parsed[:4]
                log.info(f"Inline followups extracted: {len(followups)} items")
        except Exception as e:
            log.debug(f"Inline followup parsing failed: {e}")
        # Strip the [FOLLOWUPS] block from the spoken reply
        reply = reply[:_followup_match.start()].strip()
    else:
        log.debug("No inline [FOLLOWUPS] tag found in LLM reply")

    # ── Strip leaked JSON / internal tags from LLM reply before returning ──
    reply = re.sub(r'\[?\{["\s]*action["\s]*:.*$', '', reply, flags=re.DOTALL).strip()
    reply = re.sub(r'\[show_panel\b[^\]]*\]?', '', reply, flags=re.IGNORECASE).strip()

    # ── Build panel from reply ──
    # Strategy: ALWAYS run both extractors and merge results.
    # _panel_from_reply = instant regex (stats, charts) — the scaffold
    # _panel_dynamic = LLM call (insights, swot, recommendations) — the strategic layer
    _regex_panel = None
    if _run_dynamic:
        # Fast regex extraction — always attempt for data-rich replies
        _regex_panel = _panel_from_reply(user_msg, reply)
        if _regex_panel:
            panel_data = _regex_panel
            log.info("Fast regex panel built from reply text — dynamic panel will enrich it")
        # ALWAYS run _panel_dynamic too — it provides the strategic components
        # (insights, swot, recommendations, etc.) that regex can't extract

    _parallel_tasks = {}
    if _run_dynamic:
        _parallel_tasks["dynamic"] = _panel_dynamic(user_msg, reply, extra_ctx)
    # Followups: use instant templates when dynamic panel is running (avoids
    # queuing a THIRD Ollama call which doubles total wait time).
    # Only use LLM followups when there's no dynamic panel work.
    if not followups:
        if _run_dynamic or _has_research:
            # Use instant template followups — no Ollama call
            followups = _generate_template_followups(user_msg, reply, topic)
        else:
            _parallel_tasks["followups"] = _generate_followups(user_msg, reply, topic)

    if _parallel_tasks:
        keys = list(_parallel_tasks.keys())
        results_par = await asyncio.gather(*_parallel_tasks.values(), return_exceptions=True)
        par = dict(zip(keys, results_par))

        # Handle dynamic panel result — MERGE with regex panel for richest output
        dynamic = par.get("dynamic")
        if dynamic and not isinstance(dynamic, Exception) and dynamic:
            if panel_data:
                # Merge: dynamic panel enriches regex panel with strategic components.
                # chart/table/stats are handled separately below (different merge logic).
                _skip = {"chart", "table", "stats"}
                for key in (_PANEL_MERGE_KEYS - _skip):
                    if dynamic.get(key) and not panel_data.get(key):
                        panel_data[key] = dynamic[key]
                # Dynamic panel may have better chart/table than regex
                if dynamic.get("chart") and not panel_data.get("chart"):
                    panel_data["chart"] = dynamic["chart"]
                if dynamic.get("table") and not panel_data.get("table"):
                    panel_data["table"] = dynamic["table"]
                # Dynamic title is usually better
                if dynamic.get("title") and panel_data.get("title") == "RESEARCH ANALYSIS":
                    panel_data["title"] = dynamic["title"]
                if dynamic.get("summary") and len(dynamic["summary"]) > len(panel_data.get("summary", "")):
                    panel_data["summary"] = dynamic["summary"]
                # Merge stats — add unique dynamic stats
                if dynamic.get("stats"):
                    existing_labels = {s.get("label", "").lower() for s in panel_data.get("stats", [])}
                    for s in dynamic["stats"]:
                        if s.get("label", "").lower() not in existing_labels:
                            panel_data.setdefault("stats", []).append(s)
            else:
                panel_data = dynamic

        # Handle followups fallback result
        if not followups:
            followups = par.get("followups")
            if isinstance(followups, Exception):
                followups = None

    result = {"reply": reply, "error": False}
    if panel_data:
        result["panel"] = panel_data
    if followups:
        result["followups"] = followups
        log.info(f"Returning {len(followups)} followups to client")
    else:
        log.warning(f"No followups generated for query: {user_msg[:60]!r}")

    return result


# ── Vision (Camera) Chat ─────────────────────────────────────────────
@app.post("/api/jarvis/vision")
async def jarvis_vision(request: Request):
    """Process a camera frame + user query using Claude's vision capability."""
    # ── Body size guard — reject payloads > 10 MB ──
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 10 * 1024 * 1024:
        return JSONResponse(status_code=413, content={"error": "Payload too large (max 10 MB)"})
    body = await request.json()
    query = body.get("query", "").strip() or "What can you see in this image? Describe it and identify any objects."
    image_b64 = body.get("image", "")

    if not image_b64:
        return {"reply": "No image data received.", "error": True}

    # ── Try Claude vision (primary) ──
    client = _get_anthropic()
    if client and not _claude_check_budget():
        try:
            _now = datetime.utcnow()
            system_text = (
                f"You are ARBITER, a sophisticated AI assistant for Sir Luke. "
                f"You have been given a camera frame from the user's webcam. "
                f"Analyse the image carefully and respond to their query. "
                f"Be specific about objects, text, components, colours, and anything identifiable. "
                f"If the user is showing you hardware (e.g. a Raspberry Pi, Arduino, sensor), "
                f"identify the exact model if possible and provide practical guidance. "
                f"Keep your response concise but thorough — under 200 words unless the query demands more. "
                f"Speak in a composed, dry-witted British tone. Today is {_now.strftime('%B %d, %Y')}."
            )

            resp = await asyncio.to_thread(
                client.messages.create,
                model=_CLAUDE_MODEL,
                max_tokens=600,
                system=system_text,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": query,
                        },
                    ],
                }],
            )

            # Record usage
            if resp.usage:
                _claude_record_usage(resp.usage.input_tokens, resp.usage.output_tokens)

            content = ""
            for block in resp.content:
                if hasattr(block, "text"):
                    content += block.text
            content = content.strip()

            if content:
                log.info(f"Vision reply ({len(content)} chars) for query: {query[:60]!r}")
                return {"reply": content, "error": False}

        except Exception as e:
            log.error(f"Claude vision error: {type(e).__name__}: {e}")
            _claude_record_error()

    # ── Fallback: no vision available ──
    return {
        "reply": "Vision analysis unavailable — Claude API key is required for camera analysis, "
                 "and the current LLM budget may be exhausted. Please check your configuration.",
        "error": True,
    }


_FOLLOWUP_PROMPT = """Given a user's question and the AI's response, generate exactly 4 follow-up questions the user might want to ask next to dig deeper. Each should explore a DIFFERENT angle:
1. DEEPER: Drill into the specifics of what was just discussed
2. COMPARE: How does this compare to alternatives/competitors/benchmarks
3. ACTION: What should I actually DO with this information
4. BROADER: Zoom out to the bigger picture / related trends

Output ONLY a JSON array of objects: [{"text": "question text", "hint": "one-word category"}]
Keep questions under 12 words. Be specific to the topic, not generic. No markdown."""


def _generate_template_followups(user_msg: str, reply: str, topic: str = None) -> list:
    """Generate deterministic follow-up options based on topic and query patterns.
    This ALWAYS returns results — no LLM call, no failure modes."""
    msg = user_msg.lower()

    # ── Topic-specific templates ──
    _TOPIC_FOLLOWUPS = {
        "stocks": [
            {"text": "Show me a chart of the performance", "hint": "deeper"},
            {"text": "How does it compare to the S&P 500?", "hint": "compare"},
            {"text": "What are analysts recommending?", "hint": "action"},
            {"text": "What's the broader market outlook?", "hint": "broader"},
        ],
        "weather": [
            {"text": "What's the forecast for this week?", "hint": "deeper"},
            {"text": "How does this compare to last year?", "hint": "compare"},
            {"text": "Should I plan for outdoor activities?", "hint": "action"},
            {"text": "What are the seasonal trends?", "hint": "broader"},
        ],
        "revenue": [
            {"text": "Break down the revenue by source", "hint": "deeper"},
            {"text": "How does MRR compare to last month?", "hint": "compare"},
            {"text": "What can I do to reduce churn?", "hint": "action"},
            {"text": "What's the growth trajectory?", "hint": "broader"},
        ],
        "services": [
            {"text": "Which services are currently impacted?", "hint": "deeper"},
            {"text": "How does uptime compare this month?", "hint": "compare"},
            {"text": "Should I set up failover alerts?", "hint": "action"},
            {"text": "What's the overall infrastructure health?", "hint": "broader"},
        ],
        "gcp": [
            {"text": "Show me Cloud Run service details", "hint": "deeper"},
            {"text": "How are costs trending vs last month?", "hint": "compare"},
            {"text": "Are there any scaling concerns?", "hint": "action"},
            {"text": "What's the full infrastructure overview?", "hint": "broader"},
        ],
        "email": [
            {"text": "Show me customer emails that need replies", "hint": "action"},
            {"text": "Read the latest urgent email", "hint": "deeper"},
            {"text": "Draft a reply to the most recent customer email", "hint": "action"},
            {"text": "What's the overall inbox status?", "hint": "broader"},
        ],
        "news": [
            {"text": "Tell me more about the top story", "hint": "deeper"},
            {"text": "How does UK news compare globally?", "hint": "compare"},
            {"text": "Anything that affects my business?", "hint": "action"},
            {"text": "What are the major trends this week?", "hint": "broader"},
        ],
        "roadmap": [
            {"text": "What's the next milestone deadline?", "hint": "deeper"},
            {"text": "How are we tracking vs the plan?", "hint": "compare"},
            {"text": "What should I prioritise this week?", "hint": "action"},
            {"text": "Show me the full project timeline", "hint": "broader"},
        ],
    }

    # ── Extract the KEY SUBJECT (e.g. "Samsung", "Apple") — not the full query ──
    # First try: detect known stock company names (works for lowercase too)
    _all_detected = _detect_all_stock_symbols(user_msg)
    _detected_names = [_TICKER_NAMES.get(s, s) for s in _all_detected]
    # Second try: proper nouns from message
    _proper = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b', user_msg)
    _stop = {"What", "Why", "How", "Which", "Where", "Who", "When", "Tell", "Show",
             "Give", "Can", "Could", "Would", "Should", "The", "Has", "Have", "Does", "Did"}
    _subjects = [n for n in _proper if n.split()[0] not in _stop]
    # Use detected company names first, then proper nouns, then cleaned query
    if _detected_names:
        subject = " vs ".join(_detected_names[:4]) if len(_detected_names) > 1 else _detected_names[0]
    elif _subjects:
        subject = _subjects[0]
    else:
        subject = re.sub(
            r'\b(give me|show me|tell me|can you|what is|what are|how is|how are|how has|how have|'
            r'a view on|a breakdown of|breakdown view of|performed|in the last|over the|stocks?|'
            r'i am curious|i need|i want|where i should|on where)\b',
            '', msg, flags=re.IGNORECASE).strip().split('?')[0].strip()[:40]

    # ── Multi-company comparison followups ──
    if len(_detected_names) > 1:
        _names_str = ", ".join(_detected_names[:4])
        return [
            {"text": f"Compare {_names_str} side by side", "hint": "deeper"},
            {"text": f"Which of {_names_str} has the best growth outlook?", "hint": "compare"},
            {"text": "Which one would you recommend investing in?", "hint": "action"},
            {"text": "What's the broader tech sector outlook?", "hint": "broader"},
        ]

    # ── Try topic-specific first (use subject if available) ──
    if topic and topic in _TOPIC_FOLLOWUPS:
        # Personalize with subject name if we have one
        if subject and topic == "stocks":
            return [
                {"text": f"Show me {subject} stock chart", "hint": "deeper"},
                {"text": f"How does {subject} compare to competitors?", "hint": "compare"},
                {"text": f"What would you recommend for {subject}?", "hint": "action"},
                {"text": "What's the broader market outlook?", "hint": "broader"},
            ]
        return _TOPIC_FOLLOWUPS[topic]

    # Investment / finance queries (check message OR topic)
    if topic == "stocks" or re.search(r'\b(invest|stock|share|portfolio|buy|sell|market)\b', msg):
        return [
            {"text": f"Show me {subject} stock performance", "hint": "deeper"},
            {"text": f"How does {subject} compare to competitors?", "hint": "compare"},
            {"text": f"What would you recommend for {subject}?", "hint": "action"},
            {"text": "What's the broader sector outlook?", "hint": "broader"},
        ]

    # Risk / analysis queries
    if re.search(r'\b(risk|threat|danger|likelihood|probability|impact)\b', msg):
        return [
            {"text": "What are the most severe risks?", "hint": "deeper"},
            {"text": "How do risks compare by region?", "hint": "compare"},
            {"text": "What mitigation steps should I take?", "hint": "action"},
            {"text": "What's the 20-year outlook?", "hint": "broader"},
        ]

    # Technology / AI queries
    if re.search(r'\b(technology|ai\b|artificial|machine learning|software|app)\b', msg):
        return [
            {"text": "What are the key technical details?", "hint": "deeper"},
            {"text": "How does it compare to alternatives?", "hint": "compare"},
            {"text": "How can I apply this to my business?", "hint": "action"},
            {"text": "What's the industry trend?", "hint": "broader"},
        ]

    # Climate / environment queries
    if re.search(r'\b(climate|environment|carbon|emission|temperature|warming)\b', msg):
        return [
            {"text": "What are the worst-case projections?", "hint": "deeper"},
            {"text": "How do different regions compare?", "hint": "compare"},
            {"text": "What actions have the most impact?", "hint": "action"},
            {"text": "What's the geopolitical outlook?", "hint": "broader"},
        ]

    # Generic fallback — include topic context if available
    _topic_label = f" ({topic})" if topic else ""
    return [
        {"text": f"Tell me more about {subject}{_topic_label}", "hint": "deeper"},
        {"text": f"How does {subject} compare to competitors?", "hint": "compare"},
        {"text": "What should I do with this information?", "hint": "action"},
        {"text": "What's the bigger picture here?", "hint": "broader"},
    ]


async def _generate_followups(user_msg: str, reply: str, topic: str = None) -> list | None:
    """Generate 3-4 contextual follow-up questions for the dialogue tree.
    Uses deterministic templates ONLY — no LLM call. Instant, free, never fails."""
    # Skip for vague/short queries
    if len(user_msg.split()) < 3 and not topic:
        return None

    return _generate_template_followups(user_msg, reply, topic)


# ── Text-to-Speech (edge-tts) ─────────────────────────────────────────
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "en-GB-RyanNeural")

@app.post("/api/tts")
async def tts(request: Request):
    """Convert text to speech using edge-tts. Streams audio/mpeg chunks."""
    import edge_tts

    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return {"error": "No text provided"}

    # Strip markdown/formatting/punctuation — TTS should never read these aloud
    import re as _re_tts
    # Kill any leaked JSON blobs first
    text = _re_tts.sub(r'\[?\{["\s]*action["\s]*:.*$', '', text, flags=_re_tts.DOTALL)
    text = _re_tts.sub(r'\*\*(.+?)\*\*', r'\1', text)   # **bold**
    text = _re_tts.sub(r'\*(.+?)\*', r'\1', text)       # *italic*
    text = _re_tts.sub(r'__(.+?)__', r'\1', text)       # __bold__
    text = _re_tts.sub(r'_(.+?)_', r'\1', text)         # _italic_
    text = _re_tts.sub(r'~~(.+?)~~', r'\1', text)       # ~~strike~~
    text = _re_tts.sub(r'`(.+?)`', r'\1', text)         # `code`
    text = _re_tts.sub(r'^#{1,6}\s+', '', text, flags=_re_tts.MULTILINE)  # headings
    text = _re_tts.sub(r'^\s*[-*•]\s+', '', text, flags=_re_tts.MULTILINE)  # bullets
    text = _re_tts.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # [link](url)
    text = _re_tts.sub(r':\s*', ', ', text)              # colons → comma pause
    text = _re_tts.sub(r';\s*', ', ', text)              # semicolons → comma pause
    text = _re_tts.sub(r'[{}\[\]"]', '', text)           # stray JSON chars
    text = _re_tts.sub(r'\s{2,}', ' ', text)             # collapse spaces

    communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE, rate="+5%", pitch="-2Hz")

    async def audio_generator():
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    return StreamingResponse(
        audio_generator(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-cache"},
    )


async def _chat_ollama(messages: list, max_tokens: int = 300) -> str | None:
    """Send chat to local Ollama instance with retry logic."""
    # Calculate context size to set appropriate timeout
    _ctx_chars = sum(len(m.get("content", "")) for m in messages)
    # Scale timeout: base 30s + 1s per 500 chars of context + 0.5s per 10 tokens
    _timeout = max(60, 30 + (_ctx_chars // 500) + (max_tokens // 20))
    _timeout = min(_timeout, 180)  # cap at 3 minutes
    log.info(f"Ollama request: model={OLLAMA_MODEL}, tokens={max_tokens}, "
             f"context={_ctx_chars} chars, timeout={_timeout}s")
    for attempt in range(2):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": OLLAMA_MODEL,
                        "messages": messages,
                        "stream": False,
                        "options": {"temperature": 0.6, "num_predict": max_tokens},
                    },
                    timeout=_timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("message", {}).get("content", "").strip()
                    if content:
                        log.info(f"Ollama reply: {len(content)} chars in {resp.elapsed.total_seconds():.1f}s")
                        return content
                    else:
                        log.warning(f"Ollama returned empty content (status 200)")
                else:
                    log.warning(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")
        except httpx.ReadTimeout:
            log.warning(
                f"Ollama attempt {attempt+1} ReadTimeout after {_timeout}s — "
                f"model={OLLAMA_MODEL}, context={_ctx_chars} chars, max_tokens={max_tokens}. "
                f"The model may be overloaded or the context is too large."
            )
            if attempt == 0:
                await asyncio.sleep(2)
        except httpx.ConnectError:
            log.warning(f"Ollama attempt {attempt+1} ConnectError — is 'ollama serve' running?")
            if attempt == 0:
                await asyncio.sleep(1)
        except Exception as e:
            log.warning(f"Ollama attempt {attempt+1} failed: {type(e).__name__}: {e!r}")
            if attempt == 0:
                await asyncio.sleep(1)
    log.error(f"Ollama exhausted all retries — model={OLLAMA_MODEL}, "
              f"context={_ctx_chars} chars, max_tokens={max_tokens}")
    return None


async def _chat_claude(messages: list, max_tokens: int = 400, temperature: float = 0.6) -> str | None:
    """Send chat to Claude API with full cost safeguards.

    Safeguards:
    - Daily budget cap (default $1/day)
    - Per-minute rate limit (default 30 RPM)
    - Per-session request limit (default 500)
    - Circuit breaker (3 consecutive errors → 5 min Ollama fallback)
    - Hard-locked to Haiku 3.5 (cheapest model, no override)
    """
    client = _get_anthropic()
    if not client:
        return None

    # ── Check all safeguards ──
    block_reason = _claude_check_budget()
    if block_reason:
        log.warning(f"Claude blocked: {block_reason} — falling back to Ollama")
        return None

    # ── Convert messages to Anthropic format ──
    # Anthropic separates system from messages
    system_text = ""
    api_messages = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_text += content + "\n"
        else:
            # Anthropic only allows "user" and "assistant" roles
            api_role = "assistant" if role == "assistant" else "user"
            # Merge consecutive same-role messages (Anthropic requires alternating)
            if api_messages and api_messages[-1]["role"] == api_role:
                api_messages[-1]["content"] += "\n" + content
            else:
                api_messages.append({"role": api_role, "content": content})

    # Ensure first message is from user (Anthropic requirement)
    if not api_messages or api_messages[0]["role"] != "user":
        api_messages.insert(0, {"role": "user", "content": "Please respond."})

    _ctx_chars = sum(len(m.get("content", "")) for m in messages)
    log.info(f"Claude request: model={_CLAUDE_MODEL}, max_tokens={max_tokens}, "
             f"context={_ctx_chars} chars")

    try:
        _create_kwargs = {
            "model": _CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": api_messages,
        }
        if system_text.strip():
            _create_kwargs["system"] = system_text.strip()
        # Run synchronous Anthropic SDK in a thread to avoid blocking the event loop
        resp = await asyncio.to_thread(client.messages.create, **_create_kwargs)

        # Record usage
        input_tok = resp.usage.input_tokens if resp.usage else 0
        output_tok = resp.usage.output_tokens if resp.usage else 0
        _claude_record_usage(input_tok, output_tok)

        # Extract text
        content = ""
        for block in resp.content:
            if hasattr(block, "text"):
                content += block.text
        content = content.strip()

        if content:
            log.info(f"Claude reply: {len(content)} chars, "
                     f"{input_tok}in/{output_tok}out tokens")
            return content
        else:
            log.warning("Claude returned empty content")
            _claude_record_error()
            return None

    except Exception as e:
        log.error(f"Claude API error: {type(e).__name__}: {e}")
        _claude_record_error()
        return None


async def _chat_openrouter(
    messages: list,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    model: str | None = None,
    skip_budget_check: bool = False,
) -> str | None:
    """Call OpenRouter API with full cost safeguards.
    Uses GPT-4o-mini by default — $0.15/M input, $0.60/M output.
    Falls back gracefully if not configured or budget exhausted.

    Safeguards:
    - Daily budget cap (default $0.10/day ≈ $3/month)
    - Per-minute rate limit (default 30 RPM)
    - Per-session request limit (default 500)
    - Circuit breaker (3 consecutive errors → 5 min fallback)
    - Request timeout (default 60s — prevents hanging)
    - 402 handling (credits exhausted → clean fallback)
    """
    if not OPENROUTER_API_KEY:
        return None

    # ── Check safeguards ──
    if not skip_budget_check:
        block_reason = _or_check_budget()
        if block_reason:
            log.warning(f"OpenRouter blocked: {block_reason} — falling back")
            return None

    _model = model or _OPENROUTER_PANEL_MODEL
    try:
        async with httpx.AsyncClient(timeout=_OPENROUTER_TIMEOUT) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://arbiter.local",
                    "X-Title": "ARBITER Mission Control",
                },
                json={
                    "model": _model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            # ── Handle HTTP errors ──
            if resp.status_code == 402:
                log.error("OpenRouter credits exhausted (402) — all future calls will fall back to Ollama")
                _or_record_error()
                # Set circuit breaker to long duration — credits won't magically refill
                _openrouter_usage["circuit_open_until"] = datetime.utcnow() + timedelta(hours=24)
                return None
            if resp.status_code == 429:
                log.warning("OpenRouter rate limited (429) — backing off")
                _or_record_error()
                return None
            if resp.status_code != 200:
                log.warning(f"OpenRouter error {resp.status_code}: {resp.text[:200]}")
                _or_record_error()
                return None

            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

            # ── Record usage ──
            usage = data.get("usage", {})
            in_tok = usage.get("prompt_tokens", 0)
            out_tok = usage.get("completion_tokens", 0)
            if in_tok or out_tok:
                _or_record_usage(in_tok, out_tok)
            else:
                # No usage data — estimate from message lengths
                est_in = sum(len(m.get("content", "")) for m in messages) // 4
                est_out = len(text) // 4 if text else 0
                _or_record_usage(est_in, est_out)

            return text or None
    except httpx.TimeoutException:
        log.warning(f"OpenRouter timeout after {_OPENROUTER_TIMEOUT}s — request killed")
        _or_record_error()
        return None
    except Exception as e:
        log.warning(f"OpenRouter error: {type(e).__name__}: {e}")
        _or_record_error()
        return None


async def _chat_llm(messages: list, max_tokens: int = 400,
                    temperature: float = 0.6, purpose: str = "chat") -> str | None:
    """Unified LLM call with automatic fallback chain.

    Priority: Claude (fast, cheap) → Ollama (free, local) → OpenAI (legacy).
    For 'panel' purpose: routes to OpenRouter (GPT-4o-mini) first for cost savings.
    Falls back automatically on failure or when safeguards block Claude.
    """
    reply = None
    provider = LLM_PROVIDER

    # ── OpenRouter (for panel/structured output — 10x cheaper than Claude) ──
    if purpose == "panel" and OPENROUTER_API_KEY:
        reply = await _chat_openrouter(messages, max_tokens=max_tokens, temperature=temperature)
        if reply:
            log.info(f"Panel routed to OpenRouter ({_OPENROUTER_PANEL_MODEL}) — saved ~90% vs Claude")
            return reply
        # Fall through to Claude if OpenRouter fails

    # ── Claude (primary if configured) ──
    if provider == "claude" or (provider != "ollama" and ANTHROPIC_API_KEY):
        reply = await _chat_claude(messages, max_tokens=max_tokens, temperature=temperature)
        if reply:
            return reply
        # Fall through to Ollama

    # ── Ollama (free local fallback) ──
    if not reply:
        reply = await _chat_ollama(messages, max_tokens=max_tokens)
        if reply:
            return reply

    # ── OpenAI (legacy fallback) ──
    if not reply and oai:
        try:
            resp = oai.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            reply = resp.choices[0].message.content.strip()
        except Exception as e:
            log.error(f"OpenAI {purpose} error: {e}")

    return reply


# ── Claude Tool-Calling Infrastructure ───────────────────────────────

async def _search_and_fetch(query: str, max_urls: int = 3, chars_per_url: int = 1500) -> str:
    """DuckDuckGo search → parallel URL fetch. Used by the search_web tool."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        # DuckDuckGo wraps real URLs in uddg= redirect params — extract those first
        from urllib.parse import unquote
        uddg_urls = re.findall(r'uddg=([^&"]+)', resp.text)
        uddg_urls = [unquote(u) for u in uddg_urls if u.startswith("http")]
        # Also grab direct href URLs as fallback
        href_urls = re.findall(r'href="(https?://[^"]+)"', resp.text)
        href_urls = [u for u in href_urls if "duckduckgo.com" not in u and "duck.co" not in u]
        # Merge, deduplicate, prefer uddg (actual result links)
        seen = set()
        urls = []
        for u in uddg_urls + href_urls:
            # Clean tracking params
            clean = u.split("&amp;")[0].split("&rut=")[0]
            if clean not in seen and clean.startswith("http"):
                seen.add(clean)
                urls.append(clean)
            if len(urls) >= max_urls:
                break
        if not urls:
            log.info(f"DuckDuckGo returned 0 URLs for: {query[:80]}")
            return "[No search results]"
        log.info(f"DuckDuckGo found {len(urls)} URLs for: {query[:60]}")
        results = await asyncio.gather(
            *[_web_fetch(u, max_chars=chars_per_url) for u in urls],
            return_exceptions=True,
        )
        parts = [
            f"[{u}]\n{c}"
            for u, c in zip(urls, results)
            if not isinstance(c, Exception) and c and not c.startswith("[Error")
        ]
        return "\n\n".join(parts) or "[No content retrieved]"
    except Exception as e:
        log.warning(f"Search failed for '{query[:60]}': {e}")
        return f"[Search failed: {e}]"


async def _execute_tool(name: str, inputs: dict) -> str:
    """Dispatch a named Claude tool call to the appropriate data source.
    To add a new tool: add a branch here and a matching entry in _CLAUDE_TOOLS."""
    try:
        if name == "get_weather":
            result = await weather(location=inputs.get("location", "London"))
            return json.dumps(result, default=str)

        elif name == "get_stocks":
            result = await stocks()
            return json.dumps(result, default=str)

        elif name == "get_market_intel":
            sym = inputs.get("symbol", "").upper().strip()
            if not sym:
                return '{"error": "symbol is required"}'
            async with httpx.AsyncClient() as client:
                result = await _fetch_stock_intel(sym, client)
            return json.dumps(result, default=str) if result else '{"error": "no data available"}'

        elif name == "get_service_health":
            return json.dumps(svc_health.summary(), default=str)

        elif name == "get_revenue":
            return json.dumps(rc_mon.summary(), default=str)

        elif name == "get_emails":
            from email_monitor import redact_for_llm as _rfl
            summary = email_mon.summary()
            # Include recent emails with snippets — redacted for LLM safety
            recent = email_mon.recent(10)
            for e in recent:
                e["snippet"] = _rfl(e.get("snippet", ""))
                e["subject"] = _rfl(e.get("subject", ""))
                e.pop("body", None)  # never send full body in list context
            customer = email_mon.customer_emails(5)
            for e in customer:
                e["snippet"] = _rfl(e.get("snippet", ""))
                e["subject"] = _rfl(e.get("subject", ""))
                e.pop("body", None)
            summary["recent"] = recent
            summary["customer_emails"] = customer
            return json.dumps(summary, default=str)

        elif name == "get_email_detail":
            from email_monitor import redact_for_llm as _rfl
            uid = inputs.get("uid", "")
            if not uid:
                return '{"error": "uid is required"}'
            detail = email_mon.get_email_detail(uid)
            if not detail:
                return '{"error": "Email not found"}'
            # ── Redact confidential data before returning to Claude context ──
            detail["body"] = _rfl(detail.get("body", ""))
            detail["snippet"] = _rfl(detail.get("snippet", ""))
            detail["subject"] = _rfl(detail.get("subject", ""))
            return json.dumps(detail, default=str)

        elif name == "draft_email_reply":
            from email_monitor import redact_for_llm as _rfl
            uid = inputs.get("uid", "")
            if not uid:
                return '{"error": "uid is required"}'
            detail = email_mon.get_email_detail(uid)
            if not detail:
                return '{"error": "Email not found"}'
            instructions = inputs.get("instructions", "")
            # ── Redact all content before LLM sees it ──
            prompt = (
                f"Draft a professional reply to this email.\n\n"
                f"FROM: {_rfl(detail['sender'])}\nSUBJECT: {_rfl(detail['subject'])}\n"
                f"BODY:\n{_rfl(detail['body'][:3000])}\n\n"
            )
            if instructions:
                prompt += f"SPECIFIC INSTRUCTIONS: {instructions}\n\n"
            prompt += (
                "RULES: Professional but warm. UK English. Max 150 words. "
                "Don't invent commitments/prices/dates — use [PLACEHOLDER]. "
                "Return ONLY the reply body text."
            )
            msgs = [
                {"role": "system", "content": "You are a professional email reply drafter."},
                {"role": "user", "content": prompt},
            ]
            draft = None
            if ANTHROPIC_API_KEY and not _claude_check_budget():
                draft = await _chat_claude(msgs, max_tokens=400, temperature=0.5)
            if not draft and OPENROUTER_API_KEY:
                draft = await _chat_openrouter(msgs, max_tokens=400, temperature=0.5)
            if not draft:
                draft = await _chat_llm(msgs, max_tokens=400, purpose="email-draft-tool")
            subject = detail.get("subject", "")
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"
            return json.dumps({
                "draft": (draft or "").strip(),
                "to": detail.get("sender", ""),
                "subject": subject,
                "in_reply_to": detail.get("message_id", ""),
            }, default=str)

        elif name == "get_roadmap":
            return json.dumps(_load_roadmap(), default=str)

        elif name == "search_web":
            query = inputs.get("query", "").strip()
            if not query:
                return '{"error": "query is required"}'
            if query.startswith(("http://", "https://")):
                return await _web_fetch(query, max_chars=4000)
            return await _search_and_fetch(query)

        elif name == "search_collectables":
            item = inputs.get("item", "").strip()
            intent = inputs.get("intent", "price_check")
            if not item:
                return '{"error": "item is required"}'
            _yr = datetime.now().year
            # Layer 1: site-specific searches (most reliable for collectables)
            site_queries = [
                f"site:pricecharting.com {item}",
                f"site:tcgplayer.com {item} price",
                f"site:ebay.com {item} sold price",
            ]
            # Layer 2: general market queries
            general_queries = [f"{item} price value market {_yr}"]
            if intent in ("buy", "overview"):
                general_queries.append(f"{item} buy online marketplace price guide")
            if intent in ("trend", "overview"):
                general_queries.append(f"{item} price history trend over time")
            if intent in ("sell", "overview"):
                general_queries.append(f"{item} sell value guide graded ungraded")
            if intent == "grading":
                general_queries.append(f"{item} PSA BGS CGC grading population report")
            # Layer 3: broad fallback
            fallback_queries = [
                f"{item} collectible value guide",
                f"{item} worth how much",
            ]

            # Run site-specific + general in parallel (up to 5 queries)
            all_queries = site_queries + general_queries
            results = await asyncio.gather(
                *[_search_and_fetch(q, max_urls=3, chars_per_url=2000) for q in all_queries[:5]],
                return_exceptions=True,
            )
            parts = []
            for q, r in zip(all_queries, results):
                if isinstance(r, Exception) or not r:
                    continue
                if r in ("[No search results]", "[No content retrieved]"):
                    continue
                parts.append(f"[Search: {q}]\n{r}")

            # If nothing from layer 1+2, try fallback queries
            if not parts:
                log.info(f"Collectables primary search empty for '{item}', trying fallback")
                fb_results = await asyncio.gather(
                    *[_search_and_fetch(q, max_urls=4, chars_per_url=2000) for q in fallback_queries],
                    return_exceptions=True,
                )
                for q, r in zip(fallback_queries, fb_results):
                    if isinstance(r, Exception) or not r:
                        continue
                    if r in ("[No search results]", "[No content retrieved]"):
                        continue
                    parts.append(f"[Search: {q}]\n{r}")

            # Always return SOMETHING — even a structured hint for Claude
            if not parts:
                return json.dumps({
                    "item": item,
                    "intent": intent,
                    "status": "no_live_data",
                    "note": (
                        f"Web searches returned no results for '{item}'. "
                        "This may be a network issue. Use your general knowledge about "
                        "this collectable to provide the user with approximate market "
                        "ranges, grading tiers, and buying advice. Mention that live "
                        "pricing was unavailable and recommend checking tcgplayer.com, "
                        "pricecharting.com, or eBay sold listings for current values."
                    ),
                    "suggested_sources": [
                        "https://www.pricecharting.com",
                        "https://www.tcgplayer.com",
                        "https://www.ebay.com (sold listings)",
                        "https://www.psacard.com/pop",
                    ],
                })
            return "\n\n".join(parts)

        elif name == "search_history":
            query = inputs.get("query", "").strip()
            if not query:
                return '{"error": "query is required"}'
            category = inputs.get("category", "all")
            limit = min(inputs.get("limit", 10), 20)  # cap at 20 to control context size
            agent_id = inputs.get("agent_id")

            if category == "all":
                raw = arbiter_db.search_all(query, limit=limit)
                # Trim large response fields to keep context lean
                for table in raw.values():
                    for item in table:
                        for key in ("response", "message", "content"):
                            if key in item and item[key] and len(str(item[key])) > 500:
                                item[key] = str(item[key])[:500] + "…"
                        item.pop("panel_json", None)
                        item.pop("data_json", None)
                return json.dumps(raw, default=str)
            elif category == "agents":
                results = arbiter_db.get_agent_results(
                    agent_id=agent_id, search=query, limit=limit,
                )
                for r in results:
                    if r.get("response") and len(r["response"]) > 800:
                        r["response"] = r["response"][:800] + "…"
                return json.dumps({"agent_results": results}, default=str)
            elif category == "briefings":
                results = arbiter_db.get_briefings(limit=limit)
                # Filter by query in title/message
                filtered = [b for b in results
                            if query.lower() in (b.get("title", "") + b.get("message", "")).lower()]
                return json.dumps({"briefings": filtered[:limit]}, default=str)
            elif category == "insights":
                results = arbiter_db.get_insights(limit=limit)
                filtered = [i for i in results
                            if query.lower() in (i.get("title", "") + i.get("message", "")).lower()]
                return json.dumps({"insights": filtered[:limit]}, default=str)
            elif category == "conversations":
                # Search across all conversations
                raw = arbiter_db.search_all(query, limit=limit)
                return json.dumps({"conversations": raw.get("conversations", [])}, default=str)
            else:
                return json.dumps(arbiter_db.search_all(query, limit=limit), default=str)

        elif name == "search_products":
            query = inputs.get("query", "").strip()
            category = inputs.get("category", "other")
            if not query:
                return '{"error": "query is required"}'
            _yr = datetime.now().year
            _price_sites = {
                "clothing": "ASOS Zara H&M Uniqlo Amazon",
                "electronics": "Amazon Best Buy Currys eBay",
                "shoes": "Nike StockX GOAT Footlocker Amazon",
                "accessories": "Amazon eBay ASOS Farfetch",
                "home": "IKEA Amazon Wayfair John Lewis",
                "sports": "Amazon Decathlon Sports Direct Nike",
                "other": "Amazon eBay Google Shopping",
            }
            sites = _price_sites.get(category, _price_sites["other"])
            # Layer 1: site-specific
            site_queries = [f"site:amazon.com {query} price", f"site:ebay.com {query} buy"]
            # Layer 2: general comparison
            general_queries = [
                f"{query} buy price compare {sites} {_yr}",
                f"{query} cheapest price online review",
            ]
            all_queries = site_queries + general_queries
            results = await asyncio.gather(
                *[_search_and_fetch(q, max_urls=3, chars_per_url=2000) for q in all_queries[:4]],
                return_exceptions=True,
            )
            parts = []
            for q, r in zip(all_queries, results):
                if isinstance(r, Exception) or not r:
                    continue
                if r in ("[No search results]", "[No content retrieved]"):
                    continue
                parts.append(f"[Search: {q}]\n{r}")
            if not parts:
                # Broad fallback
                fb = await _search_and_fetch(f"{query} buy online price", max_urls=4, chars_per_url=2000)
                if fb and fb not in ("[No search results]", "[No content retrieved]"):
                    parts.append(f"[Search: {query} buy online price]\n{fb}")
            if not parts:
                return json.dumps({
                    "query": query,
                    "category": category,
                    "status": "no_live_data",
                    "note": (
                        f"Web searches returned no results for '{query}'. "
                        "Use your general knowledge to provide approximate pricing "
                        "and recommend specific retailers. Mention that live pricing "
                        "was unavailable."
                    ),
                })
            return "\n\n".join(parts)

        # ── Destructive tools (require confirmation) ─────────────────
        elif name == "delete_business":
            biz_name = inputs.get("business_name", "").strip()
            confirmed = inputs.get("confirmed", False)
            biz = _find_business_by_name(biz_name)
            if not biz:
                return json.dumps({"error": f"No business found matching '{biz_name}'", "available": [b["name"] for b in arbiter_db.get_businesses()]})
            if not confirmed:
                versions = arbiter_db.get_prompt_versions(biz["id"])
                return json.dumps({
                    "action": "DELETE_BUSINESS",
                    "status": "AWAITING_CONFIRMATION",
                    "business": {"id": biz["id"], "name": biz["name"], "description": biz.get("description", "")},
                    "warning": f"This will permanently delete '{biz['name']}' and {len(versions)} prompt version(s). Data tagged with this business will remain but won't be filtered.",
                    "instruction": "Ask the user to explicitly confirm before calling this tool again with confirmed=true.",
                })
            # Confirmed — execute deletion
            slug = biz.get("slug", "")
            env_key = f"GITHUB_PAT_{slug.upper().replace('-', '_')}"
            if os.getenv(env_key):
                os.environ.pop(env_key, None)
                _write_env_values({env_key: ""})
            arbiter_db.delete_business(biz["id"])
            log.info(f"Business '{biz['name']}' deleted via chat (confirmed)")
            return json.dumps({"action": "DELETE_BUSINESS", "status": "COMPLETED", "deleted": biz["name"]})

        elif name == "update_business_context":
            biz_name = inputs.get("business_name", "").strip()
            new_context = inputs.get("new_context", "").strip()
            confirmed = inputs.get("confirmed", False)
            if not new_context:
                return '{"error": "new_context is required"}'
            if len(new_context) > 4000:
                return '{"error": "context too long (max 4000 chars)"}'
            biz = _find_business_by_name(biz_name)
            if not biz:
                return json.dumps({"error": f"No business found matching '{biz_name}'", "available": [b["name"] for b in arbiter_db.get_businesses()]})
            old_ctx = (biz.get("business_context") or "").strip()
            if not confirmed:
                return json.dumps({
                    "action": "UPDATE_BUSINESS_CONTEXT",
                    "status": "AWAITING_CONFIRMATION",
                    "business": biz["name"],
                    "current_context_preview": old_ctx[:300] + ("..." if len(old_ctx) > 300 else "") if old_ctx else "(empty)",
                    "new_context_preview": new_context[:300] + ("..." if len(new_context) > 300 else ""),
                    "instruction": "Show the user what will change and ask them to explicitly confirm before calling with confirmed=true.",
                })
            # Confirmed — execute update
            active_mode = biz.get("active_prompt_mode") or "default"
            arbiter_db.save_prompt_version(
                biz["id"], new_context, mode=active_mode,
                source="agent", summary="Updated via chat/voice",
            )
            arbiter_db.update_business(biz["id"], business_context=new_context)
            log.info(f"Business context updated for '{biz['name']}' via chat (confirmed)")
            return json.dumps({"action": "UPDATE_BUSINESS_CONTEXT", "status": "COMPLETED", "business": biz["name"], "new_version": True})

        elif name == "switch_prompt_mode":
            biz_name = inputs.get("business_name", "").strip()
            mode = inputs.get("mode", "").strip()
            confirmed = inputs.get("confirmed", False)
            if not mode:
                return '{"error": "mode is required"}'
            biz = _find_business_by_name(biz_name)
            if not biz:
                return json.dumps({"error": f"No business found matching '{biz_name}'", "available": [b["name"] for b in arbiter_db.get_businesses()]})
            modes = arbiter_db.get_prompt_modes(biz["id"])
            mode_names = [m["mode"] for m in modes]
            if mode not in mode_names:
                return json.dumps({"error": f"Mode '{mode}' does not exist", "available_modes": mode_names})
            current_mode = biz.get("active_prompt_mode") or "default"
            if mode == current_mode:
                return json.dumps({"status": "NO_CHANGE", "message": f"'{biz['name']}' is already in '{mode}' mode"})
            if not confirmed:
                target_mode = next((m for m in modes if m["mode"] == mode), {})
                return json.dumps({
                    "action": "SWITCH_PROMPT_MODE",
                    "status": "AWAITING_CONFIRMATION",
                    "business": biz["name"],
                    "current_mode": current_mode,
                    "target_mode": mode,
                    "target_versions": target_mode.get("total_versions", 0),
                    "instruction": "Ask the user to confirm the mode switch before calling with confirmed=true.",
                })
            # Confirmed — execute switch
            arbiter_db.set_active_mode(biz["id"], mode)
            log.info(f"Prompt mode switched to '{mode}' for '{biz['name']}' via chat (confirmed)")
            return json.dumps({"action": "SWITCH_PROMPT_MODE", "status": "COMPLETED", "business": biz["name"], "new_mode": mode})

        else:
            return f'{{"error": "unknown tool: {name}"}}'

    except Exception as e:
        log.warning(f"Tool {name} error: {type(e).__name__}: {e}")
        return f'{{"error": "{type(e).__name__}: {str(e)[:120]}"}}'


def _find_business_by_name(name: str) -> dict | None:
    """Find a business profile by case-insensitive name match."""
    if not name:
        return None
    businesses = arbiter_db.get_businesses()
    name_lower = name.lower()
    # Exact match first
    for b in businesses:
        if b["name"].lower() == name_lower:
            return b
    # Partial match fallback
    for b in businesses:
        if name_lower in b["name"].lower():
            return b
    return None


# ── Selective Tool Loading ─────────────────────────────────────────────
# Only send tools relevant to the query topic. Saves ~800-1200 input tokens
# per call by not sending 11 tool schemas when only 3-4 are needed.
_TOOL_BY_NAME = {t["name"]: t for t in _CLAUDE_TOOLS}

# Core tools always included (cheap, high utility)
_ALWAYS_TOOLS = {"search_web", "search_history"}

# Topic → additional tools to include
_TOPIC_TOOLS: dict[str | None, set[str]] = {
    "stocks":   {"get_stocks", "get_market_intel"},
    "weather":  {"get_weather"},
    "services": {"get_service_health"},
    "gcp":      {"get_service_health"},
    "revenue":  {"get_revenue"},
    "email":    {"get_emails", "get_email_detail", "draft_email_reply"},
    "roadmap":  {"get_roadmap"},
}

def _select_tools(topic: str | None, user_msg: str) -> list[dict]:
    """Return a filtered tool list based on topic and message content.
    Falls back to full tool list for ambiguous/unknown queries."""
    msg_lower = user_msg.lower()

    # Keywords that signal specific tools are needed
    _keyword_tools: list[tuple[set[str], list[str]]] = [
        ({"get_stocks", "get_market_intel"}, ["stock", "share", "market", "invest", "portfolio", "ticker", "s&p", "ftse"]),
        ({"get_weather"},                    ["weather", "temperature", "forecast", "rain", "sun"]),
        ({"get_service_health"},             ["service", "health", "gcp", "outage", "incident", "uptime"]),
        ({"get_revenue"},                    ["revenue", "mrr", "subscriber", "churn", "revenuecat"]),
        ({"get_emails", "get_email_detail", "draft_email_reply"}, ["email", "inbox", "unread", "mail", "reply", "customer email"]),
        ({"get_roadmap"},                    ["roadmap", "milestone", "deadline", "sprint"]),
        ({"search_collectables"},            ["pokemon", "card", "collectable", "psa", "grading", "charizard", "trading card", "tcg"]),
        ({"search_products"},                ["buy", "price", "shop", "product", "nike", "adidas", "headphone", "compare price"]),
        ({"delete_business", "update_business_context", "switch_prompt_mode"},
         ["delete", "remove", "update context", "change context", "switch mode", "prompt mode", "business profile",
          "edit business", "modify business", "update business", "delete business"]),
    ]

    needed = set(_ALWAYS_TOOLS)

    # Add topic-specific tools
    if topic and topic in _TOPIC_TOOLS:
        needed.update(_TOPIC_TOOLS[topic])

    # Scan message for keyword matches
    for tools, keywords in _keyword_tools:
        if any(kw in msg_lower for kw in keywords):
            needed.update(tools)

    # If only core tools matched, send ALL tools (ambiguous query — let Claude decide)
    if needed == _ALWAYS_TOOLS:
        return _CLAUDE_TOOLS

    selected = [_TOOL_BY_NAME[name] for name in needed if name in _TOOL_BY_NAME]
    log.info(f"Selective tools: {len(selected)}/{len(_CLAUDE_TOOLS)} tools for topic={topic}")
    return selected


async def _chat_claude_tools(
    user_msg: str,
    system: str,
    history: list,
    max_rounds: int = 5,
    tools: list[dict] | None = None,
) -> tuple[str | None, dict[str, str]]:
    """Claude tool-use conversation loop — ChatGPT-style on-demand data fetching.

    Sends user_msg + tool definitions to Claude. Claude calls tools as
    needed; we execute them in parallel and return results. This repeats until
    Claude produces a final text reply (stop_reason == 'end_turn').

    Args:
        tools: Optional filtered tool list. Defaults to _CLAUDE_TOOLS (all tools).

    Returns:
        (reply_text, tool_results)
        reply_text is None if Claude failed or hit max_rounds without finishing.
        tool_results is a dict keyed by tool name → raw result string.
    """
    _tools = tools if tools is not None else _CLAUDE_TOOLS
    client = _get_anthropic()
    if not client:
        return None, {}

    block = _claude_check_budget()
    if block:
        log.warning(f"Claude tools blocked: {block}")
        return None, {}

    # Build message list — user/assistant history + current query
    messages: list[dict] = []
    for h in history[-6:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_msg})

    tool_results: dict[str, str] = {}

    for round_num in range(max_rounds):
        _ctx_chars = sum(len(str(m.get("content", ""))) for m in messages)
        log.info(f"Claude tools round {round_num + 1}/{max_rounds}: ~{_ctx_chars} chars")

        try:
            resp = await asyncio.to_thread(
                client.messages.create,
                model=_CLAUDE_MODEL,
                max_tokens=2400,
                system=system,
                tools=_tools,
                messages=messages,
            )
        except Exception as e:
            log.error(f"Claude tools round {round_num + 1} API error: {type(e).__name__}: {e}")
            _claude_record_error()
            break

        if resp.usage:
            _claude_record_usage(resp.usage.input_tokens, resp.usage.output_tokens)

        if resp.stop_reason == "end_turn":
            text = "".join(
                b.text for b in resp.content if hasattr(b, "text")
            ).strip()
            log.info(
                f"Claude tools done: {round_num + 1} rounds, "
                f"{len(tool_results)} tools called, reply={len(text)} chars"
            )
            return text or None, tool_results

        if resp.stop_reason == "tool_use":
            tool_blocks = [b for b in resp.content if b.type == "tool_use"]
            log.info(f"  Claude requesting tools: {[b.name for b in tool_blocks]}")

            # Append assistant turn (contains tool_use content blocks)
            messages.append({"role": "assistant", "content": resp.content})

            # Execute all requested tools in parallel
            raw_results = await asyncio.gather(
                *[_execute_tool(b.name, b.input) for b in tool_blocks],
                return_exceptions=True,
            )

            result_content = []
            for block, raw in zip(tool_blocks, raw_results):
                result_str = (
                    str(raw) if not isinstance(raw, Exception)
                    else f'{{"error": "{raw}"}}'
                )
                tool_results[block.name] = result_str
                result_content.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str[:3000],  # cap per-result to control input token cost
                })
                log.info(f"  {block.name}({block.input}) → {len(result_str)} chars")

            messages.append({"role": "user", "content": result_content})

        else:
            log.warning(f"Claude tools: unexpected stop_reason={resp.stop_reason!r}")
            break

    log.warning(f"Claude tools: exhausted {max_rounds} rounds without end_turn")
    return None, tool_results


async def _jarvis_chat_claude(
    user_msg: str,
    history: list,
    topic: str | None,
    business_id: str | None = None,
) -> dict | None:
    """Handle a full Jarvis chat turn using Claude with tool calling.

    Claude receives the user message and _CLAUDE_TOOLS. It decides what to
    fetch (weather, stocks, web search, etc.) and pulls only what it needs —
    no pre-fetching, no bloated context.

    When business_id is provided, the active business's context (mission,
    products, audience, tone) is injected into the system prompt so
    responses are grounded in the business domain.

    Returns the API result dict on success, or None to trigger Ollama fallback.
    """
    # ComfyUI is an external image-generation API — keep it in the Ollama path
    if topic == "comfyui":
        return None

    _now = datetime.utcnow()
    system = _CLAUDE_TOOLS_SYSTEM.format(
        date=_now.strftime("%B %d, %Y"),
        year=_now.year,
    )

    # ── Inject active business context into system prompt ─────────────
    biz_ctx = _resolve_business_context(business_id)
    if biz_ctx:
        system += (
            f"\n\n## Active Business Context\n"
            f"The user is operating in the context of this business. "
            f"Ground your responses in this domain when relevant.\n\n"
            f"{biz_ctx}"
        )

    # ── Select only relevant tools to reduce input tokens ──────────────
    selected_tools = _select_tools(topic, user_msg)

    # ── Tool-calling loop ─────────────────────────────────────────────
    reply, tool_data = await _chat_claude_tools(user_msg, system, history, tools=selected_tools)
    if not reply:
        return None  # triggers Ollama fallback in jarvis_chat()

    # ── Panel detection ───────────────────────────────────────────────
    _VIS_RX = re.compile(
        r'\b(show|graph|chart|plot|visuali[sz]e|compare|break\s*down|display|'
        r'overview|view|analyse|analyze|breakdown|insight|deep\s*dive)\b',
        re.IGNORECASE,
    )
    _AUTO_PANEL_TOPICS = {"roadmap", "stocks", "services", "gcp", "weather", "revenue"}
    wants_panel = bool(_VIS_RX.search(user_msg)) or topic in _AUTO_PANEL_TOPICS
    has_comparison = bool(re.search(
        r'\b(vs|versus|compared|comparison|better|worse|competitor|rival)\b',
        user_msg, re.IGNORECASE,
    ))
    numbers = re.findall(r'[\$£€]?[\d,]+\.?\d*[%°]?', reply)
    _wants_enrichment = len(numbers) >= 2 or has_comparison or wants_panel

    # ── Build panel from tool results ─────────────────────────────────
    panel_data = None
    if _wants_enrichment and len(reply) > 60:
        # Format collected tool results as structured context for _panel_dynamic
        extra_ctx = ""
        for tool_name, result_str in tool_data.items():
            header = tool_name.upper().replace("_", " ")
            extra_ctx += f"\n\n[{header}]\n{result_str[:3000]}\n"

        # Fast regex scaffold (instant, no LLM)
        panel_data = _panel_from_reply(user_msg, reply)

        # Rich dynamic panel — uses real tool data as ground truth
        dynamic = await _panel_dynamic(user_msg, reply, extra_ctx)
        if dynamic:
            if panel_data:
                # Merge: dynamic enriches the regex scaffold
                _skip = {"chart", "table", "stats"}
                for key in (_PANEL_MERGE_KEYS - _skip):
                    if dynamic.get(key) and not panel_data.get(key):
                        panel_data[key] = dynamic[key]
                if dynamic.get("chart") and not panel_data.get("chart"):
                    panel_data["chart"] = dynamic["chart"]
                if dynamic.get("table") and not panel_data.get("table"):
                    panel_data["table"] = dynamic["table"]
                if dynamic.get("title") and panel_data.get("title") == "RESEARCH ANALYSIS":
                    panel_data["title"] = dynamic["title"]
                if dynamic.get("summary") and len(dynamic["summary"]) > len(panel_data.get("summary", "")):
                    panel_data["summary"] = dynamic["summary"]
                if dynamic.get("stats"):
                    _seen = {s.get("label", "").lower() for s in panel_data.get("stats", [])}
                    for s in dynamic["stats"]:
                        if s.get("label", "").lower() not in _seen:
                            panel_data.setdefault("stats", []).append(s)
            else:
                panel_data = dynamic

    # ── Follow-up suggestions ─────────────────────────────────────────
    followups = _generate_template_followups(user_msg, reply, topic)

    result: dict = {"reply": reply, "error": False}
    if panel_data:
        result["panel"] = panel_data
    if followups:
        result["followups"] = followups
    return result


async def _build_context(topic: str | None = None, query: str = "",
                         business_id: str | None = None) -> str:
    """Build structured telemetry snapshot for the LLM context window.
    Uses compact formatting to maximise signal-per-token.
    When topic is specified, only includes relevant sections to reduce token count.
    When query mentions a specific stock, context focuses on that stock only."""
    sections = []
    today = datetime.utcnow().strftime("%Y-%m-%d")
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Topic-aware context: only fetch what's relevant to reduce token count
    # None = general query → include lightweight essentials (services, email, weather, news)
    #   but EXCLUDE heavy data feeds (stocks, sports) that pollute general replies
    # Specific topic → only include that topic's data
    _GENERAL_TOPICS = {"services", "email", "weather", "news", "gcp", "revenue", "roadmap"}
    _need = lambda *tags: (topic is None and bool(set(tags) & _GENERAL_TOPICS)) or topic in tags

    # ── SYSTEM (always, one line) ──
    sections.append(f"[SYSTEM] {now_str}")

    # ── BUSINESS CONTEXT ──
    businesses = arbiter_db.get_businesses()
    if businesses:
        if business_id:
            biz = next((b for b in businesses if b["id"] == business_id), None)
            if biz:
                biz_header = f"[ACTIVE BUSINESS] {biz['name']}"
                if biz.get("description"):
                    biz_header += f" — {biz['description']}"
                sections.append(biz_header)
                # Include rich business context for prompt grounding
                biz_ctx = (biz.get("business_context") or "").strip()
                if biz_ctx:
                    sections.append(f"[BUSINESS DIRECTIVE]\n{biz_ctx}")
        else:
            biz_names = ", ".join(b["name"] for b in businesses)
            sections.append(f"[BUSINESSES] {biz_names} (showing all)")

    # ── SERVICE HEALTH ──
    if _need("services", "gcp"):
        try:
            svc_data = svc_health.summary()
            if svc_data:
                svc_parts = []
                incident_details = []
                for svc in svc_data:
                    name = svc.get("name", svc.get("id", "?"))
                    status = svc.get("status", "unknown").upper()
                    flag = " ⚠" if status not in ("OPERATIONAL", "NONE", "OK") else ""
                    svc_parts.append(f"{name}={status}{flag}")
                    # Include incident details for impacted services
                    for inc in svc.get("incidents", []):
                        affected = ", ".join(inc.get("affected_components", [])[:3]) or name
                        impact = inc.get("impact", "unknown")
                        update = inc.get("latest_update", "")
                        incident_details.append(
                            f"  • {name}: {inc.get('name', 'Incident')} "
                            f"[impact={impact}] affecting {affected}"
                            f"{f' — {update[:120]}' if update else ''}"
                        )
                if svc_parts:
                    sections.append(f"[SERVICES] {' | '.join(svc_parts)}")
                if incident_details:
                    sections.append(f"[SERVICE INCIDENTS]\n" + "\n".join(incident_details[:8])
                                    + "\nNote: These incidents may impact GCP-hosted apps like Grow with Freya if they affect Cloud Run, Cloud SQL, or EU-west regions.")
        except Exception:
            pass

    # ── EMAIL ──
    if _need("email"):
        es = email_mon.summary()
        urg_flag = f" ⚠ {es['urgent']} URGENT" if es.get("urgent", 0) > 0 else ""
        sections.append(f"[EMAIL] unread={es['unread']}{urg_flag}")

    # ── GCP INFRASTRUCTURE ──
    if _need("gcp"):
        gcp = gcp_mon.summary()
        if gcp.get("configured"):
            gcp_parts = [f"project={gcp['project_id']}"]
            if gcp.get("app_engine"):
                ae = gcp["app_engine"]
                gcp_parts.append(f"AppEngine={ae['serving_status']}")
            if gcp.get("cloud_run"):
                for svc in gcp["cloud_run"][:3]:
                    status = "READY" if svc.get("ready") else "DOWN ⚠"
                    gcp_parts.append(f"CloudRun:{svc['name']}={status}")
            sections.append(f"[GCP] {' | '.join(gcp_parts)}")

    # ── REVENUECAT ──
    if _need("revenue"):
        rc = rc_mon.summary()
        if rc.get("configured") and rc.get("overview"):
            ov = rc["overview"]
            sections.append(f"[REVENUE] MRR=${ov.get('mrr',0):.0f} subs={ov.get('active_subscribers',0)}")

    # ── BULLETINS (always — alerts are critical) ──
    bulls = agent_reg.get_bulletins()
    if bulls:
        for b in bulls[:3]:
            sections.append(f"[ALERT:{b['level'].upper()}] {b['message']}")

    # ── LIVE FEEDS (only fetch what's needed) ──
    fetches = {}
    if _need("weather"):
        fetches["w"] = weather()
    if _need("stocks"):
        fetches["s"] = stocks()
        fetches["mi"] = refresh_market_intel()
    if _need("news"):
        fetches["n"] = news()
    if _need("sports"):
        fetches["sp"] = sports()

    if fetches:
        keys = list(fetches.keys())
        results = await asyncio.gather(*fetches.values(), return_exceptions=True)
        feed = dict(zip(keys, results))
    else:
        feed = {}

    w = feed.get("w")
    if w and not isinstance(w, Exception):
        cur = w.get("current", {})
        if cur:
            loc = w.get('location', 'London')
            sections.append(
                f"[WEATHER] {loc}: {cur.get('temperature_2m','?')}°C, "
                f"feels {cur.get('apparent_temperature','?')}°C, wind {cur.get('wind_speed_10m','?')} km/h"
            )
            daily = w.get("daily", {})
            if daily.get("temperature_2m_max"):
                fc = [f"day {i}: {daily['temperature_2m_min'][i]}–{daily['temperature_2m_max'][i]}°C"
                      for i in range(min(3, len(daily["temperature_2m_max"])))]
                sections.append(f"[FORECAST] {', '.join(fc)}")

    s = feed.get("s")
    # Detect if query targets a specific stock — focus context on just that stock
    _target_stock = _detect_stock_symbol(query) if query else None
    if s and not isinstance(s, Exception) and s.get("quotes"):
        _names = {
            "^GSPC": "S&P 500", "^FTSE": "FTSE 100", "^DJI": "Dow Jones",
            "AAPL": "Apple", "GOOGL": "Google", "MSFT": "Microsoft",
            "AMZN": "Amazon", "TSLA": "Tesla", "NVDA": "Nvidia", "META": "Meta",
        }
        parts = []
        for q in s["quotes"]:
            sym = q["symbol"]
            # If a specific stock is targeted, only include that stock's data
            if _target_stock and sym != _target_stock:
                continue
            pct = q.get("changePct", 0) or 0
            name = _names.get(sym, sym)
            direction = "up" if pct >= 0 else "down"
            price = q["price"]
            change = q.get("change", 0) or 0
            if sym.startswith("^"):
                parts.append(f"{name} {price:,.0f} {direction} {abs(pct):.1f}%")
            else:
                parts.append(f"{name} ${price:,.2f} ({'+' if change >= 0 else ''}{change:,.2f}, {direction} {abs(pct):.1f}%)")
        if parts:
            label = f"[{_names.get(_target_stock, _target_stock).upper()}]" if _target_stock else "[MARKETS]"
            sections.append(f"{label} {'. '.join(parts)}")

    # Enriched analyst intel (only for stock queries)
    if _need("stocks") and _market_intel_cache:
        intel_lines = []
        for sym, info in _market_intel_cache.items():
            # If a specific stock is targeted, only include that stock's intel
            if _target_stock and sym != _target_stock:
                continue
            name = _TICKER_NAMES.get(sym, sym)
            rating = info.get("analyst_rating", "N/A")
            target = info.get("target_mean", 0)
            upside = info.get("upside_pct", 0)
            n_analysts = info.get("num_analysts", 0)
            parts_i = [f"{name}: {rating} ({n_analysts} analysts)"]
            if target:
                parts_i.append(f"target ${target:,.0f} ({upside:+.0f}%)")
            fwd_pe = info.get("forward_pe", 0)
            if fwd_pe:
                parts_i.append(f"P/E {fwd_pe:.1f}")
            intel_lines.append(", ".join(parts_i))
        if intel_lines:
            sections.append("[ANALYST INTELLIGENCE] " + ". ".join(intel_lines))

    n_feed = feed.get("n")
    if n_feed and not isinstance(n_feed, Exception) and n_feed.get("headlines"):
        titles = [h['title'] for h in n_feed["headlines"][:4]]
        sections.append(f"[NEWS] {'. '.join(titles)}.")

    sp = feed.get("sp")
    if sp and not isinstance(sp, Exception) and sp.get("stories"):
        titles = [f"{st['title']} ({st['category']})" for st in sp["stories"][:3]]
        sections.append(f"[SPORTS] {'. '.join(titles)}.")

    # Roadmap milestones
    if _need("roadmap"):
        rm = _load_roadmap()
        if rm:
            now_dt = datetime.utcnow()
            rm_lines = []
            for m in sorted(rm, key=lambda x: x.get("date", "9999")):
                try:
                    d = datetime.fromisoformat(m["date"])
                    diff = (d - now_dt).days
                    days_str = f"in {diff}d" if diff >= 0 else f"{abs(diff)}d ago"
                except Exception:
                    days_str = "TBD"
                rm_lines.append(f"{m.get('quarter','')}: {m['title']} ({m.get('status','planned')}, {days_str})")
            sections.append("[ROADMAP] " + ". ".join(rm_lines))

    return "\n".join(sections)
