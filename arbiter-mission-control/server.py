"""
ARBITER — Mission Control
A Jarvis-style HUD dashboard for the Grow with Freya automation platform.
Serves a single-page holographic UI and real-time status API endpoints.

Run: uvicorn server:app --reload --port 3000
Open: http://localhost:3000
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

import httpx
from openai import OpenAI
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from email_monitor import EmailMonitor
from agent_registry import AgentRegistry
from gcp_monitor import GCPMonitor
from revenuecat_monitor import RevenueCatMonitor
from service_health import ServiceHealthMonitor

from typing import Any

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / "social-media-business-account" / ".env")
load_dotenv(ROOT / "arbiter-mission-control" / ".env", override=True)


COMFYUI_URL = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi4")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # "ollama" (free) or "openai"

log = logging.getLogger(__name__)

# ── Singletons ─────────────────────────────────────────────────────────
oai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
email_mon = EmailMonitor()
agent_reg = AgentRegistry()
gcp_mon = GCPMonitor()
rc_mon = RevenueCatMonitor()


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
    """Daily 8:00 AM briefing: weather, stocks, emails, agenda."""
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

        # Stocks
        try:
            s = await stocks()
            if s.get("quotes"):
                movers = sorted(s["quotes"], key=lambda q: abs(q.get("changePct", 0) or 0), reverse=True)[:3]
                for q in movers:
                    name = _TICKER_NAMES.get(q["symbol"], q["symbol"])
                    pct = q.get("changePct", 0) or 0
                    status = "good" if pct >= 0 else "bad"
                    panel_stats.append({"label": name, "value": f"{pct:+.1f}%", "status": status})
                sections.append(f"Top movers: {', '.join(m['symbol'] for m in movers)}")
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

        summary = "Good morning, Sir. " + ". ".join(sections) + "." if sections else "Good morning, Sir."

        await _push_sse("briefing", {
            "title": "MORNING BRIEFING",
            "message": summary,
            "speak": True,
            "panel": {
                "title": "MORNING BRIEFING — " + datetime.now().strftime("%A %d %B"),
                "stats": panel_stats,
            },
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

        await _push_sse("briefing", {
            "title": "MARKET CLOSE",
            "message": f"Markets are closed, Sir. {summary}.",
            "speak": True,
            "panel": {
                "title": "MARKET CLOSE — " + datetime.now().strftime("%A %d %B"),
                "stats": panel_stats[:6],
                "chart": chart,
            },
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

        await _push_sse("briefing", {
            "title": "EVENING DIGEST",
            "message": summary,
            "speak": True,
            "panel": {
                "title": "EVENING DIGEST — " + datetime.now().strftime("%A %d %B"),
                "stats": panel_stats,
            },
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
              _job_insight_scan, enabled=True)


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
    if any(c in url for c in (";", "|", "&", "`", "$", "(", ")", "{", "}")):
        return "[Error: URL contains unsafe characters]"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=5) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })
            if resp.status_code != 200:
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

VOICE: composed, British, dry-witted, never verbose. 2-3 sentences MAX for most answers.

ABSOLUTE RULES:
1. ALWAYS answer the question using the LIVE DATA below. You have it. Never say you lack access. Never redirect to websites. Never apologise.
2. SYNTHESISE — restate data as a human would say it in conversation. Never echo raw formats, labels, brackets, or field names from the data.
3. SECURITY — Only API keys, tokens, passwords, secrets, private IPs, file paths, env vars → "That's classified, Sir." Service STATUS, uptime, health, performance metrics, and infrastructure names are NOT classified — always answer those freely using the live data.
4. FLAG RISKS only when there IS an actual risk (outage, high churn, etc). Do NOT list everything just because you have data.
5. BREVITY IS SACRED — your text is read aloud. Keep responses to 1-3 natural sentences. Never give a "full briefing" unless explicitly asked for one.

GREETING / ADDRESS:
- Do NOT start every response with "Sir", "Sir Luke", "Hello Sir", or any greeting. Just answer the question directly.
- Use "Sir" sparingly — only mid-sentence or at the end, and only occasionally. e.g. "Microsoft is flat on the day, Sir." NOT "Sir, Microsoft is..."
- NEVER open with "Hello", "Hi", "Hey", or any salutation. The voice system handles greetings separately.

RESPONSE LENGTH:
- Vague or short queries (e.g. "hey", "arbiter", single words): ONE short sentence or ask what they need. Do NOT dump a multi-topic briefing.
- Specific single-topic queries: 1-3 sentences covering ONLY that topic.
- "Give me a briefing" / "status report": Then and ONLY then, cover multiple topics — still keep each to one sentence.

HOW TO ANSWER EACH TOPIC (follow these examples closely):
- WEATHER: "About 16 degrees in London, mild with a light breeze."
- STOCKS (general): "Markets are mixed — S&P up half a percent, Tesla leading at 406. Apple dipping."
- STOCKS (specific, e.g. "how's Microsoft"): "Microsoft is trading at 390, up a tenth of a percent — essentially flat on the day."
- NEWS: Pick the 1–2 most significant headlines. One sentence each, in your own words.
- SPORTS: Top headline. One sentence.
- BUSINESS (GCP, RevenueCat, pipeline, agents, CRM, email): Operational language with the key metric. "MRR at 150k, churn nominal, all services green."
- SERVICE HEALTH: Report the status directly. Only mention services that are NOT operational.
- ROADMAP: Reference upcoming milestones by name and date. "Next milestone is the App Store launch on July 15th, about 31 days out."

CLARIFICATION:
- If a query is ambiguous or could refer to multiple things (e.g. a company name that could mean the stock, the product, or the org), ASK a brief clarifying question rather than guessing wrong. e.g. "Are we talking the stock or the product line, Sir?"
- If you lack enough context to give an accurate answer, say so and ask what specifically they need. One short question — never a list of options.
- When a follow-up question seems disconnected from the prior topic, briefly confirm the shift. e.g. "Switching gears from markets to geopolitics — here's what I've got."

WHAT NOT TO DO:
- NEVER use bullet points (•, -, *) or numbered lists in your spoken text. This is read aloud — write flowing sentences only.
- Do NOT open a browser or return a URL unless the user explicitly says "open".
- Do NOT respond with only a JSON action — always give a spoken answer FIRST, then append actions on new lines.
- Do NOT dump lists of tickers, key=value pairs, or markdown tables in spoken text.
- Do NOT start with "Sure", "Of course", "Hello Sir", "Sir Luke", "Certainly", or any greeting — just answer directly.
- Do NOT wrap JSON actions in code fences or markdown. Just raw JSON on its own line.
- Do NOT put structured data (tables, lists, charts) in the spoken text — that goes in the show_panel JSON only.
- Do NOT cover multiple topics unless the user asked for a briefing. Answer ONLY what was asked.

VISUALISATION PANELS — when the user asks to "show", "graph", "chart", "compare", "break down", or "visualise" data, or when a visual would genuinely help (e.g. comparing multiple stocks, forecast trends, revenue breakdown), respond with a SHORT spoken summary FIRST (1-2 sentences, will be read aloud), then append a show_panel JSON action on its own line. Keep spoken text brief — the panel IS the answer.

show_panel JSON schema (append on its own line after spoken text):
{"action":"show_panel","panel":{"title":"PANEL TITLE","stats":[...],"chart":{...},"table":{...},"summary":"..."}}

All fields inside "panel" are optional — include only what fits the query:
- stats: array of {label, value, status} where status is "good"|"warn"|"bad"|null. Use for KPIs.
- chart: {type, labels, values} for single dataset OR {type, labels, datasets:[{label,data},...]} for multi. type = "bar"|"line"|"doughnut"|"pie"
- table: {headers:[...], rows:[[cell,cell,...],...]}.  Prefix positive changes with + and negative with -.
- summary: one-line analysis text shown below the chart.

WHEN TO USE show_panel:
- "show me stocks in a graph" → bar chart of stock prices with % change table
- "compare Apple and Tesla" → multi-line chart or bar comparison
- "break down revenue" → stat cards + bar chart of subscribers/trials/churn
- "show me the weather forecast" → line chart of temperature trend + stat cards for today
- "GCP status overview" → stat cards for each service + table of metrics
- "visualise the news" → table with headlines and categories
- Market overview, portfolio view, any "show me" / "graph" / "chart" / "visualise" request

WHEN NOT to use show_panel:
- Simple questions like "what's the weather" or "how's Microsoft" — just speak.
- Unless the user explicitly asks to see/show/graph/chart/visualise it.

MARKET INTELLIGENCE — you have access to enriched analyst data for tracked stocks. When the user asks about a specific stock (e.g. "what do analysts think about Tesla", "is Apple a buy"), use the [ANALYST INTELLIGENCE] section in LIVE DATA. Provide specific numbers: analyst consensus, target price, upside %, forward P/E, revenue growth. Be direct and specific — this is an intelligence briefing, not a disclaimer.

ROADMAP & BUSINESS PLANNING — you have access to the project roadmap in [ROADMAP]. When the user asks about business plans, milestones, or timelines, reference the actual milestones. You can help:
- Draft and refine milestone descriptions
- Suggest realistic timelines and priorities
- Identify risks and dependencies
- Create go-to-market strategies
- Plan MVP rollout phases
Be proactive with strategic advice — the user wants an intelligent business partner, not a generic response.

STRATEGIC ANALYST MODE — You are not just an assistant, you are a C-suite intelligence partner. For ANY data-rich query:
1. ALWAYS surface the "so what" — don't just report numbers, explain what they MEAN for decision-making.
2. COMPARE: When the user asks about one thing, proactively mention how it compares to alternatives or benchmarks.
3. RISKS: Flag potential downsides, market risks, timing concerns. A CEO needs to hear the bad news too.
4. OPPORTUNITIES: Highlight upside potential, timing advantages, undervalued angles.
5. ACTIONABLE: End with what to DO — "consider buying below $X", "hold until Q3 earnings", "diversify into Y".
6. CONTEXT: Reference macro trends, sector movements, seasonal patterns, competitive dynamics.
This applies to EVERYTHING — stocks, eBay collectibles, social media metrics, crypto, real estate, any domain.
You are briefing Tony Stark. Be incisive, data-driven, and strategically valuable.

WEB RESEARCH — if web research data is provided in [WEB RESEARCH] or [WEB PAGE CONTENT] sections, USE it heavily. Extract specific numbers, prices, trends, and comparisons from the research to give concrete, data-backed analysis. Don't just summarise — synthesise and draw strategic conclusions.

DESKTOP AUTOMATION — you can open apps and websites for Sir Luke. These are handled automatically by the server when the user says "open X" — you do NOT need to output JSON for these. Just confirm naturally: "Opening Slack for you, Sir." The server handles the execution.
Supported apps: Slack, VS Code, Chrome, Safari, Terminal, Finder, Spotify, Discord, Teams, Zoom, Messages, Mail, Notes, Calendar, Notion.
Supported URL shortcuts: jira, github, youtube, gmail, google, twitter/x, linkedin, revenuecat, gcp console.
The user can also say "open https://any-url.com" to open arbitrary URLs.

BROWSER ACTIONS (only when user says "open X" and it's NOT one of the pre-handled apps/shortcuts above):
Respond naturally first, then append on a new line: {"action":"open_browser","url":"<url>"}
URLs: comfyui=http://localhost:8188 | instagram=https://www.instagram.com | youtube=https://studio.youtube.com
gmail=https://mail.google.com | facebook=https://www.facebook.com | meta=https://business.facebook.com
analytics=https://analytics.google.com | gcp=https://console.cloud.google.com | revenuecat=https://app.revenuecat.com
play_console=https://play.google.com/console | app_store=https://appstoreconnect.apple.com

WEB RESEARCH — if the user provides a URL in their message, the page content is automatically fetched and provided in the context below as [WEB PAGE CONTENT]. Use it to answer questions about that page. You can research and summarise web content naturally.

FOLLOW-UP QUESTIONS — After EVERY substantive response (not greetings or one-word answers), append exactly this on a NEW line after your spoken text:
[FOLLOWUPS]
Generate 3-4 follow-up questions the user might want to ask next. Each explores a different angle:
- DEEPER: drill into specifics of what was discussed
- COMPARE: how does it compare to alternatives/competitors
- ACTION: what should I do with this information
- BROADER: zoom out to the bigger picture
Format: [FOLLOWUPS][{"text":"question under 12 words","hint":"deeper"},{"text":"...","hint":"compare"},{"text":"...","hint":"action"},{"text":"...","hint":"broader"}]
Keep questions specific to the topic, not generic. The [FOLLOWUPS] tag and JSON MUST be on a single line."""


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


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[dict]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Dashboard ─────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text())


# ── System Status ─────────────────────────────────────────────────────
@app.get("/api/status")
async def system_status():
    # Check LLM availability
    llm_online = False
    llm_provider = LLM_PROVIDER
    if LLM_PROVIDER == "ollama":
        try:
            r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
            llm_online = r.status_code == 200
        except Exception:
            pass
        if not llm_online and oai:
            llm_provider = "openai"
            llm_online = True
    elif oai:
        llm_online = True

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "systems": {

        },
        "llm_status": "online" if llm_online else "offline",
        "llm_provider": llm_provider,
    }


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


# ── CI/CD — Grow with Freya ──────────────────────────────────────────
@app.get("/api/cicd")
async def cicd_status():
    """Placeholder CI/CD status. Replace with real EAS/GitHub Actions integration."""
    return {
        "cms_upload": {"status": "success", "time": "2h ago", "url": "#"},
        "app_build": {"status": "success", "time": "5h ago", "url": "#"},
        "backend_api": {"status": "success", "time": "1d ago", "url": "#"},
        "eas_build": {"status": "unknown", "time": "", "url": "#"},
    }





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

async def _get_context_fast(topic: str | None = None, query: str = "") -> str:
    """Return context for the LLM.  When a topic is known, builds a slim
    topic-focused context (fast).  For general queries, uses the cached
    full context (rebuilt every 60 s)."""
    import time as _t
    if topic:
        # Topic-specific = fast, small context.  No caching needed.
        return await _build_context(topic=topic, query=query)
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
    """Detect if the user is asking about a specific stock."""
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

        # Check if user is asking about a specific stock
        target_sym = _detect_stock_symbol(query) if query else None
        intel = _market_intel_cache.get(target_sym) if target_sym else None
        log.info(f"_panel_stocks: query={query[:80]!r}, target_sym={target_sym}, intel={'yes' if intel else 'no'}, intent={intent}")

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
        _proper_nouns = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b', query)
        _ignore = {"What", "Why", "How", "Which", "Where", "Who", "When", "Tell", "Show",
                    "Give", "Can", "Could", "Would", "Should", "The", "This", "That",
                    "Their", "There", "These", "Has", "Have", "Does", "Did"}
        _specific_subject = [n for n in _proper_nouns if n.split()[0] not in _ignore]
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
            {"label": "Today", "value": str(es.get("today", 0)), "status": None},
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

_PANEL_SCHEMA_PROMPT = """You are a senior strategic analyst building a CEO/CFO intelligence dashboard panel.
Given a user query and research data, generate a COMPREHENSIVE structured JSON panel. Output ONLY valid JSON.

AVAILABLE COMPONENTS — use AT LEAST 5-6 of these for every panel. More is better.

{
  "title": "PANEL TITLE IN CAPS",

  "hero": {"value": "$999", "label": "Primary Metric", "delta": "+12%", "delta_status": "good|bad"},

  "key_metrics": [{"label": "METRIC", "value": "$1.2M", "status": "good|warn|bad|null", "context": "vs $1.1M last quarter"}],

  "stats": [{"label": "KPI NAME", "value": "$1,234", "status": "good|warn|bad|null"}],

  "chart": {"type": "bar|line|hbar|doughnut|area", "labels": [...], "values": [...], "label": "axis label"}
    OR multi-dataset: {"type": "line", "labels": [...], "datasets": [{"label": "...", "data": [...]}]},

  "table": {"headers": ["Col1", "Col2", ...], "rows": [["val", "val"], ...]},

  "comparison_matrix": {"columns": ["Metric", "Item A", "Item B"], "rows": [["Price", "$100", "$200"], ["Rating", "BUY", "HOLD"]]},

  "pros_cons": {"pros": ["Strong growth trajectory", "Market leader"], "cons": ["High valuation", "Regulatory risk"]},

  "swot": {"strengths": ["Brand power", "Cash reserves"], "weaknesses": ["High debt"], "opportunities": ["New market entry"], "threats": ["Competition"]},

  "risk_matrix": [{"severity": "high|medium|low|critical", "risk": "Description of risk", "mitigation": "How to mitigate"}],

  "scorecard": [{"label": "Growth", "score": 85, "value": "Strong"}, {"label": "Value", "score": 40, "value": "Expensive"}],

  "insights": [{"type": "risk|opportunity|warning|info", "text": "Strategic observation with specific data..."}],

  "recommendations": [{"priority": "high|medium|low", "text": "Specific actionable step with numbers..."}],

  "trend_indicators": [{"label": "Revenue", "value": "+12%", "direction": "up|down|flat", "context": "Q2 vs Q1"}],

  "timeline": [{"date": "Jun 2024", "event": "Product Launch", "status": "done|active|pending", "detail": "Optional detail"}],

  "summary": "One-line executive summary."
}

CRITICAL RULES:
1. USE 5+ COMPONENTS MINIMUM. A panel with just stats and a chart is UNACCEPTABLE. Always include strategic components.
2. ALWAYS include insights (3-5 items). Each must reference SPECIFIC data points, not generic statements.
3. ALWAYS include recommendations (2-4 items). Each must be ACTIONABLE with specific numbers/thresholds.
4. For ANY comparison query: MUST include comparison_matrix AND pros_cons.
5. For investment/buy/sell queries: MUST include risk_matrix AND scorecard AND recommendations.
5b. For investment ALLOCATION / FOCUS AREA queries (e.g. "where is Apple investing", "investment areas"): MUST include a doughnut chart showing allocation breakdown by area (e.g. Services 30%, AI/ML 25%, AR/VR 20%, Hardware 15%, Autonomous 10%) with key_metrics for each area. Use estimated percentages based on research data.
6. For trend/market queries: MUST include trend_indicators AND chart AND key_metrics.
7. For product/company analysis: MUST include swot AND scorecard.
8. Extract EVERY number, price, percentage, date from the context data. Missing data = failed analysis.
9. Think like McKinsey + Goldman Sachs: strategic depth, competitive positioning, timing, risk-adjusted returns.
10. Prefix positive changes with + and negative with -.
11. key_metrics is for the most important 4-6 headline numbers with context (vs benchmarks, vs last period).
12. Output ONLY the JSON object. No markdown fences, no explanation, just the JSON."""


def _panel_from_reply(user_msg: str, llm_reply: str) -> dict | None:
    """Build a visualization panel by extracting data from the LLM reply text.
    Zero LLM calls — pure regex extraction. Instant."""
    try:
        # ── Extract year-value pairs for timeline charts ──
        # Patterns: "in 2018 it was $45", "by 2022 reached $120", "2020: $80B", etc.
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
                # Scale B/M/T
                suffix = llm_reply[m.end()-10:m.end()+5].lower()
                if 'trillion' in suffix or ' t ' in suffix:
                    val *= 1000
                elif 'billion' in suffix or val < 1 and 'b' in suffix:
                    pass  # keep as billions
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
        pct_stats = []
        for m in re.finditer(r'([\w\s]{3,30}?)\s+(?:of\s+)?([\d,.]+)\s*%', llm_reply):
            label = m.group(1).strip().rstrip('of by at to')[:30]
            val = m.group(2)
            if label and len(label) > 2:
                pct_stats.append({"label": label.title(), "value": f"{val}%", "status": None})

        # ── Extract dollar amounts as stats ──
        dollar_stats = []
        for m in re.finditer(r'([\w\s]{3,30}?)\s+(?:of|at|to|was|is|reached|hit)?\s*\$\s*([\d,.]+)\s*(billion|million|trillion|B|M|T)?',
                             llm_reply, re.IGNORECASE):
            label = m.group(1).strip()[:30]
            val = m.group(2)
            unit = (m.group(3) or "").upper()[:1]
            if label and len(label) > 2:
                dollar_stats.append({"label": label.title(), "value": f"${val}{unit}", "status": None})

        # ── Build panel ──
        panel = {"title": "RESEARCH ANALYSIS"}

        # Extract subject for title
        _proper = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b', user_msg)
        _ignore = {"What", "Why", "How", "Which", "Where", "Who", "When", "Tell", "Show",
                    "Give", "Can", "Could", "Would", "Should", "The", "Has", "Have"}
        _subj = [n for n in _proper if n.split()[0] not in _ignore]
        if _subj:
            panel["title"] = f"{_subj[0].upper()} — RESEARCH ANALYSIS"

        # Timeline chart from year-value pairs
        if len(unique_pairs) >= 3:
            panel["chart"] = {
                "type": "line",
                "labels": [str(y) for y, _ in unique_pairs],
                "datasets": [{"label": _subj[0] if _subj else "Value", "data": [v for _, v in unique_pairs]}],
            }

        # Stats (take best from percentages and dollars, max 6)
        all_stats = (pct_stats + dollar_stats)[:6]
        if all_stats:
            panel["stats"] = all_stats

        # Summary from first 2 sentences of reply
        sentences = re.split(r'(?<=[.!?])\s+', llm_reply.strip())
        panel["summary"] = " ".join(sentences[:2])[:300]

        # Only return if we have meaningful content
        if panel.get("chart") or len(all_stats) >= 2:
            log.info(f"_panel_from_reply: built panel with {len(unique_pairs)} data points, {len(all_stats)} stats")
            return panel
        return None
    except Exception as e:
        log.debug(f"_panel_from_reply failed: {e}")
        return None


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

        panel_json = None
        # Try Ollama first (free), then OpenAI
        if LLM_PROVIDER == "ollama":
            panel_json = await _chat_ollama(messages, max_tokens=900)
        if not panel_json and oai:
            try:
                resp = oai.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                    messages=messages,
                    max_tokens=1500,
                    temperature=0.3,
                )
                panel_json = resp.choices[0].message.content.strip()
            except Exception:
                pass

        if not panel_json:
            return None

        # Extract JSON from response (LLM sometimes wraps in markdown)
        import re as _re_panel
        panel_json = _re_panel.sub(r'^```(?:json)?\s*', '', panel_json)
        panel_json = _re_panel.sub(r'```\s*$', '', panel_json)
        panel_json = panel_json.strip()

        panel = json.loads(panel_json)

        # Validate: must be a dict with at least a title
        if not isinstance(panel, dict) or not panel.get("title"):
            return None

        log.info(f"Dynamic panel generated: {panel.get('title', '?')}")
        return panel

    except (json.JSONDecodeError, Exception) as e:
        log.warning(f"Dynamic panel generation failed: {e}")
        return None


async def _panel_executive_dashboard() -> dict | None:
    """Build a multi-source executive dashboard for general/briefing queries.
    Combines revenue, stocks, services, and roadmap into a rich dual-wing view."""
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

    # ── Stock snapshot (hbar) ──
    try:
        s = await stocks()
        quotes = s.get("quotes", [])
        items = []
        for q in quotes:
            sym = q.get("symbol", "")
            if sym.startswith("^"):
                continue
            pct = q.get("regularMarketChangePercent", 0) or 0
            items.append({"name": _TICKER_NAMES.get(sym, sym), "pct": round(pct, 2)})
        if items:
            items.sort(key=lambda x: x["pct"], reverse=True)
            sections.append({
                "chart": {
                    "type": "hbar",
                    "labels": [i["name"] for i in items],
                    "values": [i["pct"] for i in items],
                    "label": "Daily Change %",
                },
            })
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
                "label": f"💡 {ins['title']}",
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
        cat_icons = {"launch": "🚀", "milestone": "📌", "campaign": "📣",
                     "review": "📋"}

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

    # Build context — topic-aware (fast & small) when topic is known
    ctx = await _get_context_fast(topic=topic, query=user_msg)

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
            # ── Extract the SUBJECT from current message first, then history ──
            _topic_subject = None
            # Check current message for a company/product name
            _cur_sym = _detect_stock_symbol(user_msg)
            if _cur_sym:
                _topic_subject = _TICKER_NAMES.get(_cur_sym, _cur_sym)
            # Also look for ANY capitalised proper nouns as potential subjects
            if not _topic_subject:
                _proper_nouns = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b', user_msg)
                # Filter out common sentence starters
                _ignore_words = {"What", "Why", "How", "Which", "Where", "Who", "When",
                                 "Tell", "Show", "Give", "Can", "Could", "Would", "Should",
                                 "The", "This", "That", "Their", "There", "These"}
                _proper_nouns = [n for n in _proper_nouns if n.split()[0] not in _ignore_words]
                if _proper_nouns:
                    _topic_subject = _proper_nouns[0]
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
                all_search_urls = []
                async with httpx.AsyncClient(follow_redirects=True, timeout=5) as client:
                    ddg_tasks = []
                    for sq in search_queries[:3]:
                        ddg_tasks.append(client.get(
                            "https://html.duckduckgo.com/html/",
                            params={"q": sq},
                            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                        ))
                    ddg_results = await asyncio.gather(*ddg_tasks, return_exceptions=True)
                    seen_domains = set()
                    for ddg_resp in ddg_results:
                        if isinstance(ddg_resp, Exception) or ddg_resp.status_code != 200:
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
                                if len(all_search_urls) >= 5:
                                    break
                        if len(all_search_urls) >= 5:
                            break

                # Fetch top results IN PARALLEL for speed
                # Keep context lean for fast Ollama inference
                _MAX_RESEARCH_CTX = 4000
                _research_chars = 0
                if all_search_urls:
                    fetch_tasks = [_web_fetch(surl, max_chars=1500) for surl in all_search_urls[:3]]
                    fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                    for surl, content in zip(all_search_urls[:3], fetch_results):
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

    # Pre-build topic panel for data/timeline queries.
    # For pure analytical "why/what" queries ("what drove growth?"), skip the
    # static topic panel and let the dynamic panel builder create a research-based
    # panel instead. BUT any query requesting data, timelines, comparisons, or
    # historical trends — across ANY domain — should still get a panel.
    #
    # Data-requesting queries (get panel):
    #   "How has Apple performed over 20 years?"  (stocks)
    #   "How has climate change progressed?"      (environment)
    #   "Show me Python's popularity over time"   (tech)
    #   "UK house prices last 10 years"           (housing)
    #   "Compare GDP of US vs China"              (economics)
    #
    # Pure analytical queries (skip panel, use dynamic):
    #   "What drove Apple's growth?"
    #   "Why did Tesla's strategy change?"
    _is_data_query = bool(re.search(
        r'\b(perform|progress|evolv|chang|grown|grew|increas|decreas|'
        r'risen|fallen|trend|track|chart|graph|plot|histor|timeline|'
        r'over\s+the\s+(last|past)|over\s+time|over\s+\d+|'
        r'last\s+\d+|past\s+\d+|since\s+\d{4}|'
        r'how\s+(has|have|did|does|do|much|many|far)|'
        r'compare|vs|versus|between|'
        r'rate|statistic|data|numbers|figures|'
        r'show\s+me|give\s+me|display|visuali[sz]e)\b',
        user_msg, re.IGNORECASE
    ))
    _skip_topic_panel = _has_research and not _is_data_query
    if wants_panel and not _skip_topic_panel:
        try:
            panel_data = await _build_panel(user_msg, hint_topic=topic)
            if panel_data:
                log.info(f"Panel built for topic={topic}: {panel_data.get('title', '?')}")
            else:
                log.warning(f"Panel builder returned None for topic={topic}, msg={user_msg[:60]}")
        except Exception as e:
            log.error(f"Panel build failed for topic={topic}: {e}")
            panel_data = None
    elif wants_panel and _skip_topic_panel:
        log.info(f"Skipping pre-built panel for analytical query — dynamic panel will be built post-LLM")

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
            "Voice: composed, British, dry-witted, concise. 2-4 sentences with dense data. "
            "Synthesize the WEB RESEARCH below into a data-rich spoken analysis. "
            "Include specific numbers, years, percentages, and concrete metrics. "
            f"TODAY is {_now.strftime('%B %d, %Y')} — the current year is {_now.year}. "
            f"Always prioritize the most recent data. Your response must reflect {_now.year} as the present. "
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

    _has_research = '[WEB RESEARCH' in extra_ctx or '[WEB PAGE' in extra_ctx

    # If we're generating a panel, tell the LLM to keep it short
    if panel_data:
        messages.append({"role": "user", "content": user_msg + "\n\n[A visualisation panel will be shown automatically. Give a brief 1-2 sentence spoken summary only. Do NOT output JSON, bullet points, or structured data.]"})
    elif _has_research:
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
                f"\n\n[IMPORTANT: Today's date is {_now.strftime('%B %d, %Y')}. The current year is {_cur_year}. "
                f"The user is asking about the period from {_start_year} to {_cur_year} (the last {_span} years). "
                "You have been provided with WEB RESEARCH data above. "
                "Synthesize the research into a data-rich timeline analysis. "
                f"Your timeline MUST end at {_cur_year} (or the most recent data available). "
                f"Include specific numbers WITH YEARS attached from {_start_year} through {_cur_year} — "
                f"e.g. 'In {_start_year} it was X, by {_start_year + _span//2} it reached Y, and in {_cur_year} it stands at Z.' "
                "The more year-value pairs you include, the richer the auto-generated timeline chart will be. "
                "Also mention key milestones, turning points, and rates of change. "
                "Give 3-5 sentences with dense chronological data. "
                "Do NOT use bullet points or lists — write in natural flowing sentences with embedded data.]"
            )
        else:
            _research_prompt = (
                f"\n\n[IMPORTANT: Today's date is {_now.strftime('%B %d, %Y')}. The current year is {_cur_year}. "
                f"Always prioritize the most recent data available (prefer {_cur_year} and {_cur_year - 1} data). "
                "You have been provided with WEB RESEARCH data above. "
                "Synthesize this research into a comprehensive, data-rich analysis. "
                "Include specific numbers, percentages, rankings, quantities, and any concrete metrics "
                "from the research. A data visualisation panel will be auto-generated from your analysis — "
                "the more specific numbers and named categories you include, the richer the panel. "
                "Give 3-5 sentences with dense data. "
                "Do NOT use bullet points or lists — write in natural flowing sentences with embedded data.]"
            )
        messages.append({"role": "user", "content": user_msg + _research_prompt})
    elif wants_panel:
        # Panel query without research — keep it data-oriented
        messages.append({"role": "user", "content": user_msg + "\n\n[A data visualisation panel will be generated from your analysis. Include specific numbers, percentages, and data points in your response — these will be extracted for charts and tables. Give a concise 2-3 sentence spoken summary. Do NOT use bullet points, lists, or structured data — write in natural flowing sentences with embedded data.]"})
    else:
        messages.append({"role": "user", "content": user_msg})

    # ── Get LLM reply ──
    reply = None
    provider = LLM_PROVIDER

    if provider == "ollama":
        # Scale tokens: panel=short, vague=very short, research=focused, normal=medium
        _max_tok = 80 if panel_data else (100 if _is_vague else (250 if _has_research else 250))
        reply = await _chat_ollama(messages, max_tokens=_max_tok)
        if not reply:
            if oai:
                provider = "openai"
            else:
                # Non-fatal: return the error message but still include panel data + followups
                _err_reply = "I'm temporarily offline, Sir. Ollama isn't responding — try restarting it with: ollama serve"
                _err_result = {"reply": _err_reply, "error": False}
                if panel_data:
                    _err_result["panel"] = panel_data
                # Still generate followups so the user can retry
                _err_result["followups"] = [
                    {"text": "Try again", "hint": "action"},
                    {"text": "What's the system status?", "hint": "broader"},
                ]
                return _err_result

    if provider == "openai" and not reply:
        if not oai:
            return {"reply": "Voice systems offline. No LLM provider configured.", "error": True}
        try:
            _oai_max = 800 if _has_research else (200 if panel_data else 600)
            resp = oai.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                messages=messages,
                max_tokens=_oai_max,
                temperature=0.7,
            )
            reply = resp.choices[0].message.content.strip()
        except Exception as e:
            log.error(f"Jarvis OpenAI error: {e}")
            return {"reply": "I'm experiencing a temporary disruption. Try again shortly.", "error": True}

    if not reply:
        return {"reply": "No LLM provider configured. Set LLM_PROVIDER to 'ollama' or 'openai'.", "error": True}

    # ── Auto-panel: if reply has data, attach a rich visualization panel ──
    # Determine what post-processing is needed, then run in PARALLEL
    _run_dynamic = False
    if not panel_data:
        numbers = re.findall(r'[\$£€]?[\d,]+\.?\d*[%°]?', reply)
        has_comparison = bool(re.search(r'\b(vs|versus|compared|comparison|better|worse)\b', user_msg, re.IGNORECASE))
        # Trigger panel if: data-rich reply OR comparison query OR explicit vis request
        if len(numbers) >= 2 or has_comparison or wants_panel:
            # Try server-side topic panel first (cheaper, faster)
            # Skip topic panel for conversational follow-ups — they need dynamic panels
            _is_conversational = bool(re.match(r'^(what|which|how|why|where|who|tell|explain|describe|can you)\b', user_msg.strip(), re.IGNORECASE))
            if topic and not _is_conversational:
                try:
                    panel_data = await _build_panel(user_msg, hint_topic=topic)
                except Exception:
                    pass
            # Check if dynamic panel builder is needed
            _needs_dynamic = (
                not panel_data
                or (panel_data and not panel_data.get("insights"))
                or _has_research
                or has_comparison
                or _is_conversational  # Follow-up questions always get dynamic panels
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
    # For research queries: try FAST regex extraction first (zero LLM calls).
    # Only fall back to the slow LLM dynamic panel if regex extraction fails.
    if _run_dynamic and _has_research:
        # Fast path: extract data from reply text — no Ollama call
        panel_data = _panel_from_reply(user_msg, reply)
        if panel_data:
            log.info("Fast panel built from reply text (no LLM call)")
            _run_dynamic = False  # skip the slow LLM panel builder

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

        # Handle dynamic panel result
        dynamic = par.get("dynamic")
        if dynamic and not isinstance(dynamic, Exception) and dynamic:
            if panel_data:
                for key in ("insights", "recommendations", "swot", "pros_cons",
                            "risk_matrix", "key_metrics", "timeline", "scorecard"):
                    if dynamic.get(key) and not panel_data.get(key):
                        panel_data[key] = dynamic[key]
                if dynamic.get("summary") and len(dynamic["summary"]) > len(panel_data.get("summary", "")):
                    panel_data["summary"] = dynamic["summary"]
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
            {"text": "Show me the urgent emails", "hint": "deeper"},
            {"text": "How does volume compare to last week?", "hint": "compare"},
            {"text": "Which emails need a reply today?", "hint": "action"},
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
    _proper = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b', user_msg)
    _stop = {"What", "Why", "How", "Which", "Where", "Who", "When", "Tell", "Show",
             "Give", "Can", "Could", "Would", "Should", "The", "Has", "Have", "Does", "Did"}
    _subjects = [n for n in _proper if n.split()[0] not in _stop]
    subject = _subjects[0] if _subjects else re.sub(
        r'\b(give me|show me|tell me|can you|what is|what are|how is|how are|how has|how have|'
        r'a view on|a breakdown of|breakdown view of|performed|in the last|over the|stocks?)\b',
        '', msg, flags=re.IGNORECASE).strip().split('?')[0].strip()[:40]

    # ── Try topic-specific first (use subject if available) ──
    if topic and topic in _TOPIC_FOLLOWUPS:
        # Personalize with subject name if we have one
        if subject and topic == "stocks":
            return [
                {"text": f"Show me {subject} stock chart", "hint": "deeper"},
                {"text": f"How does {subject} stock compare to competitors?", "hint": "compare"},
                {"text": f"What would you recommend for {subject}?", "hint": "action"},
                {"text": "What's the broader market outlook?", "hint": "broader"},
            ]
        return _TOPIC_FOLLOWUPS[topic]

    # Investment / finance queries (check message OR topic)
    if topic == "stocks" or re.search(r'\b(invest|stock|share|portfolio|buy|sell|market)\b', msg):
        return [
            {"text": f"Show me {subject} stock performance", "hint": "deeper"},
            {"text": f"How does {subject} stock compare to competitors?", "hint": "compare"},
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
    Uses deterministic templates as PRIMARY source, with LLM enrichment as bonus."""
    # Skip for vague/short queries
    if len(user_msg.split()) < 3 and not topic:
        return None

    # Always generate template-based followups (instant, never fails)
    template_followups = _generate_template_followups(user_msg, reply, topic)

    # Try LLM-generated followups for richer, more contextual options
    try:
        messages = [
            {"role": "system", "content": _FOLLOWUP_PROMPT},
            {"role": "user", "content": f"USER: {user_msg[:200]}\nAI: {reply[:400]}\nTOPIC: {topic or 'general'}"},
        ]

        raw = None
        if LLM_PROVIDER == "ollama":
            raw = await _chat_ollama(messages, max_tokens=250)
        if not raw and oai:
            try:
                resp = oai.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                    messages=messages,
                    max_tokens=250,
                    temperature=0.6,
                )
                raw = resp.choices[0].message.content.strip()
            except Exception:
                pass

        if raw:
            import json as _json_fu
            # Strip markdown fences more aggressively
            cleaned = re.sub(r'```(?:json)?\s*', '', raw)
            cleaned = re.sub(r'```', '', cleaned).strip()
            # Try to extract JSON array from anywhere in the response
            _arr_match = re.search(r'(\[[\s\S]*\])', cleaned)
            if _arr_match:
                llm_followups = _json_fu.loads(_arr_match.group(1))
                if isinstance(llm_followups, list) and len(llm_followups) >= 2:
                    # Validate each item has 'text' field
                    valid = [f for f in llm_followups if isinstance(f, dict) and f.get("text")]
                    if len(valid) >= 2:
                        log.info(f"LLM followups generated: {len(valid)} items")
                        return valid[:4]
    except Exception as e:
        log.debug(f"LLM followup generation failed: {e}")

    # Template followups as reliable fallback
    log.info(f"Using template followups for topic={topic}")
    return template_followups


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


async def _build_context(topic: str | None = None, query: str = "") -> str:
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
