"""FastAPI routes for work-ai-tools.

All GitHub endpoints are READ-ONLY.
No edit/delete/close/reassign routes exist.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from .config import load_config
from .github_api_client import GitHubAPIClient
from .github_client import GitHubScraper
from .monday_client import MondayClient
from .safety import (
    ConfirmationSigner,
    OperationBlockedError,
    SafetyAuditLog,
    SafetyGate,
)

router = APIRouter(prefix="/api/work", tags=["work"])
_log = logging.getLogger("work_ai.routes")

_gate: SafetyGate | None = None
_github_api: GitHubAPIClient | None = None
_github_scraper: GitHubScraper | None = None
_github: GitHubScraper | GitHubAPIClient | None = None
_monday: MondayClient | None = None


def init_work_ai(secret: bytes, log_dir: str = "logs") -> None:
    global _gate, _github, _github_api, _github_scraper, _monday
    import os
    from pathlib import Path

    logging.getLogger("work_ai").setLevel(logging.DEBUG)

    config = load_config()
    signer = ConfirmationSigner(secret)
    audit = SafetyAuditLog(Path(log_dir))
    _gate = SafetyGate(signer, audit)

    pat = os.getenv("DAYJOB_GITHUB_PAT_SEARCH", "")
    if config.github.has_config:
        _github_scraper = GitHubScraper(config.github, _gate)
        if pat:
            _github_api = GitHubAPIClient(config.github, _gate, pat)
            _github = _github_api
            _log.info("GitHub API client initialised (PAT-based, scraper fallback ready)")
        else:
            _github = _github_scraper
            _log.info("GitHub scraper initialised (CDP-based)")
    if config.monday.api_token:
        _monday = MondayClient(config.monday, _gate)


def _require_github() -> GitHubScraper | GitHubAPIClient:
    if _github is None:
        raise HTTPException(503, "GitHub not configured")
    return _github


def _require_monday() -> MondayClient:
    if _monday is None:
        raise HTTPException(503, "Monday.com not configured")
    return _monday


def _handle_safety_error(exc: Exception) -> None:
    if isinstance(exc, OperationBlockedError):
        raise HTTPException(403, str(exc))
    raise exc


@router.get("/github/epics/{repo}")
async def github_epics(repo: str) -> list[dict]:
    try:
        cards = await _require_github().search_epics(repo)
        return [asdict(c) for c in cards]
    except Exception as exc:
        _handle_safety_error(exc)
        return []


@router.get("/github/cards/{repo}")
async def github_cards(repo: str, q: str = "", labels: str = "") -> list[dict]:
    try:
        cards = await _require_github().search_cards(repo, query=q, labels=labels)
        return [asdict(c) for c in cards]
    except Exception as exc:
        _handle_safety_error(exc)
        return []


@router.get("/github/iterations")
async def github_iterations() -> list[dict]:
    try:
        items = await _require_github().get_project_items()
        return [asdict(i) for i in items]
    except Exception as exc:
        _handle_safety_error(exc)
        return []


@router.get("/query")
async def work_query(q: str = "") -> dict:
    from .llm_handler import parse_query, fetch_data, build_panel, summarize_results

    log = logging.getLogger("work_ai.query")

    if not q.strip():
        return {"title": "RESULTS", "items": []}

    parsed = parse_query(q.strip())
    log.info(
        "parsed query: action=%s term=%r repo=%s squad=%s labels=%s",
        parsed.action, parsed.search_term, parsed.repo, parsed.squad, parsed.label_filter,
    )
    try:
        items = await fetch_data(parsed, _github, _monday)
    except Exception as exc:
        if _github_api and _github_scraper and _github is _github_api:
            print(f"[WORK-AI] API failed ({exc}), falling back to scraper")
            try:
                items = await fetch_data(parsed, _github_scraper, _monday)
            except Exception as fallback_exc:
                log.error("fetch_data fallback failed: %s", fallback_exc, exc_info=True)
                return {"title": "ERROR", "items": [], "error": str(fallback_exc)}
        else:
            log.error("fetch_data failed: %s", exc, exc_info=True)
            return {"title": "ERROR", "items": [], "error": str(exc)}

    log.info("fetch_data returned %d items", len(items))

    panel = build_panel(items, parsed)
    summary = await summarize_results(items, parsed)

    return {
        "title": panel.get("title", "RESULTS") if panel else "RESULTS",
        "items": items,
        "panel": panel,
        "summary": summary,
        "query": {
            "service": parsed.service,
            "action": parsed.action,
            "search_term": parsed.search_term,
            "status_filter": parsed.status_filter,
            "label_filter": parsed.label_filter,
            "squad": parsed.squad,
        },
    }
