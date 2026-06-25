"""LLM integration — query parsing, data fetching, panel building.

Uses local Ollama (phi4) by default for natural language query interpretation.
Falls back to regex-based parsing when LLM is unavailable.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass

import httpx

from .github_api_client import GitHubAPIClient
from .github_client import Card, GitHubScraper, ProjectItem
from .monday_client import MondayClient

_log = logging.getLogger("work_ai.llm")

GitHubClient = GitHubScraper | GitHubAPIClient

OLLAMA_BASE_URL = os.getenv("WORK_AI_LLM_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("WORK_AI_LLM_MODEL", "phi4:14b")


@dataclass(frozen=True)
class DayJobQuery:
    service: str
    action: str
    search_term: str
    repo: str
    squad: str = ""
    label_filter: str = ""
    status_filter: str = ""


PROJECT_STATUSES: list[str] = [
    "Sprint Backlog",
    "In Progress",
    "Ready to Demo",
    "Ready for QA",
    "QA",
    "Ready for NFT",
    "NFT in progress",
    "Done",
]

APP_LABELS: dict[str, str] = {
    "lar": "app-lar",
    "action man": "app-lar",
    "dm": "app-dm",
    "cmi": "app-cmi",
    "download": "app-download",
    "lci": "app-lci",
    "lcm": "app-lcm",
    "mali": "app-mali",
    "meo": "app-meo",
    "ome": "app-ome",
    "roc": "app-roc",
    "sse": "app-sse",
    "ssei": "app-ssei",
    "tm": "app-tm",
    "tmi": "app-tmi",
    "video": "app-video",
    "video-sky": "app-video-sky",
    "backstage": "app-backstage",
}

SQUAD_LABELS: dict[str, str] = {
    "a": "Squad A",
    "b": "Squad B",
    "c": "Squad C",
    "d": "Squad D",
}

PLANNING_LABELS: list[str] = ["Planning"]

_SQUAD_RX = re.compile(r"\bsquad\s+([a-dA-D])\b", re.IGNORECASE)
_ALL_SQUADS_RX = re.compile(r"\ball\s+squads?\b", re.IGNORECASE)
_PLANNING_RX = re.compile(
    r"\b(planning|coming\s+next|next\s+sprint|upcoming|planned|queued|ready\s+for\s+dev)\b",
    re.IGNORECASE,
)

_STATUS_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bnft\s+in\s+progress\b", re.IGNORECASE), "NFT in progress"),
    (re.compile(r"\bin\s+progress\b", re.IGNORECASE), "In Progress"),
    (re.compile(r"\bready\s+to\s+demo\b", re.IGNORECASE), "Ready to Demo"),
    (re.compile(r"\bready\s+for\s+qa\b", re.IGNORECASE), "Ready for QA"),
    (re.compile(r"\bready\s+for\s+nft\b", re.IGNORECASE), "Ready for NFT"),
    (re.compile(r"\bin\s+qa\b", re.IGNORECASE), "QA"),
    (re.compile(r"\b(sprint\s+backlog|backlog)\b", re.IGNORECASE), "Sprint Backlog"),
    (re.compile(r"\bdone\b", re.IGNORECASE), "Done"),
]

_GITHUB_PATTERNS = [
    (re.compile(r"\b(epic|epics)\b", re.IGNORECASE), "epics"),
    (re.compile(r"\b(sprint|board|iteration)\b", re.IGNORECASE), "sprint"),
    (re.compile(
        r"\b(issue|card|ticket|bug|story|task|search|find|look\s*up|status\s+of)\b",
        re.IGNORECASE,
    ), "search"),
]

_MONDAY_PATTERNS = [
    (re.compile(r"\b(monday|board)\b", re.IGNORECASE), "boards"),
]


def _detect_squad(query: str) -> str:
    if _ALL_SQUADS_RX.search(query):
        return "all"
    m = _SQUAD_RX.search(query)
    return m.group(1).lower() if m else ""


def _detect_planning(query: str) -> bool:
    return bool(_PLANNING_RX.search(query))


def _detect_status(query: str) -> str:
    found: list[str] = []
    remaining = query
    for pattern, status in _STATUS_MAP:
        if pattern.search(remaining):
            found.append(status)
            remaining = pattern.sub("", remaining)
    return ",".join(found)


def _detect_app_label(query: str) -> str:
    q = query.lower()
    for name, label in sorted(APP_LABELS.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(name)}\b", q):
            return label
    return ""


def _build_label_filter(squad: str, planning: bool, app_label: str = "") -> str:
    labels: list[str] = []
    if app_label:
        labels.append(app_label)
    if squad and squad != "all":
        squad_label = SQUAD_LABELS.get(squad, "")
        if squad_label:
            labels.append(squad_label)
    if planning:
        labels.extend(PLANNING_LABELS)
    return ",".join(labels)


_STATUS_PHRASES_RX = re.compile(
    r"\b(in\s+progress|in\s+review|to\s+do|done|blocked|ready\s+for\s+dev|"
    r"ready\s+for\s+review|in\s+testing|in\s+qa|ready\s+for\s+qa|"
    r"ready\s+to\s+demo|ready\s+for\s+nft|nft\s+in\s+progress|"
    r"sprint\s+backlog|backlog|ready\s+to\s+deploy|"
    r"deployed|won\'t\s+do|cancelled|on\s+hold)\b",
    re.IGNORECASE,
)

_APP_NAME_RX = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(APP_LABELS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

_NOISE_RX = re.compile(
    r"\b(show|me|the|find|search|for|look|up|what|is|are|was|were|"
    r"status|of|my|our|all|any|open|closed|github|day\s*job|arbiter|"
    r"please|sir|can|you|could|would|i|want|to|get|do|does|"
    r"a|an|it|its|that|this|these|those|there|here|or|and|"
    r"view|across|streams?|every|everything|"
    r"epic|epics|sprint|board|iteration|card|cards|ticket|tickets|"
    r"issue|issues|bug|bugs|story|stories|task|tasks|item|items|"
    r"lakitu|scupper|repo|repository|project|"
    r"squad|squads|team|planning|planned|upcoming|coming|next|"
    r"in|on|from|about|tell|give|list|see|with|has|have|had|"
    r"regarding|related|"
    r"currently|current|right\s+now|at\s+the\s+moment)\b",
    re.IGNORECASE,
)


def _extract_search_term(query: str, action: str) -> str:
    cleaned = _STATUS_PHRASES_RX.sub(" ", query)
    cleaned = _APP_NAME_RX.sub(" ", cleaned)
    cleaned = _NOISE_RX.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ?!.,")
    return cleaned


def parse_query(query: str, default_repo: str = "lakitu") -> DayJobQuery:
    q = query.lower().strip()

    for pattern, action in _MONDAY_PATTERNS:
        if pattern.search(q) and "monday" in q:
            return DayJobQuery(
                service="monday", action=action, search_term="", repo="",
            )

    action = "search"
    for pattern, act in _GITHUB_PATTERNS:
        if pattern.search(q):
            action = act
            break

    squad = _detect_squad(q)
    planning = _detect_planning(q)
    status_filter = _detect_status(q)
    app_label = _detect_app_label(q)

    if squad or planning or status_filter or app_label:
        action = "sprint"

    label_filter = _build_label_filter(squad, planning, app_label)
    search_term = _extract_search_term(q, action)

    if app_label and not search_term:
        for name, label in APP_LABELS.items():
            if label == app_label:
                search_term = name
                break

    repo_match = re.search(r"\b(lakitu|scupper)\b", q, re.IGNORECASE)
    repo = repo_match.group(1).lower() if repo_match else default_repo

    return DayJobQuery(
        service="github", action=action, search_term=search_term, repo=repo,
        squad=squad, label_filter=label_filter, status_filter=status_filter,
    )


async def ask_llm(prompt: str, system: str = "") -> str:
    """Send a prompt to local Ollama and return the response text."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
    except Exception as exc:
        _log.warning("Ollama unavailable (%s), using regex parsing only", exc)
        return ""


async def summarize_results(items: list[dict], query: DayJobQuery) -> str:
    """Use local LLM to produce a concise summary of the results."""
    if not items:
        return f"No {query.action} data found for {query.service}."

    context = build_context(items, query)
    summary = await ask_llm(
        prompt=f"Summarize this work data concisely for a developer dashboard:\n\n{context}",
        system="You are a concise work assistant. Summarize project board data in 2-3 sentences. Focus on counts, statuses, and key items.",
    )
    return summary if summary else f"{len(items)} items found."


async def fetch_data(
    query: DayJobQuery,
    github: GitHubClient | None,
    monday: MondayClient | None,
) -> list[dict]:
    if query.service == "monday" and monday:
        boards = await monday.get_boards()
        return boards if isinstance(boards, list) else []

    if query.service == "github" and github:
        if query.action == "epics":
            cards = await github.search_epics(query.repo)
            return [asdict(c) for c in cards]

        if query.action == "search" and query.search_term and not query.status_filter and not query.label_filter and not query.squad:
            cards = await github.search_cards(
                query.repo, query=query.search_term,
            )
            return [asdict(c) for c in cards]

        project_items = await github.get_project_items()
        items = [asdict(i) for i in project_items]
        print(f"[WORK-AI] Total project items: {len(items)}")
        if items:
            for s in items[:3]:
                print(f"[WORK-AI]   sample: title={s.get('title','')[:50]} labels={s.get('labels',[])} status={s.get('status','')}")

        if query.status_filter:
            targets = {s.strip().lower() for s in query.status_filter.split(",") if s.strip()}
            items = [
                i for i in items
                if i.get("status", "").lower() in targets
            ]

        if query.squad and query.squad != "all":
            target_squad = query.squad.upper()
            items = [
                i for i in items
                if i.get("squad", "").upper() == target_squad
            ]

        if query.label_filter or query.search_term:
            label_parts = [
                lbl.strip().lower()
                for lbl in (query.label_filter or "").split(",")
                if lbl.strip()
            ]
            app_labels = {l for l in label_parts if l.startswith("app-")}
            squad_labels = {l for l in label_parts if l.startswith("squad")}
            other_labels = {l for l in label_parts if l not in app_labels and l not in squad_labels}
            term = query.search_term.lower() if query.search_term else ""

            def _matches_item(i: dict) -> bool:
                item_labels = {lbl.lower() for lbl in i.get("labels", [])}
                title_lower = i.get("title", "").lower()
                stream_lower = i.get("stream", "").lower()
                milestone_lower = i.get("milestone", "").lower()
                all_text = f"{title_lower} {' '.join(item_labels)} {stream_lower} {milestone_lower}"

                if app_labels and not (app_labels & item_labels):
                    if not term or term not in all_text:
                        return False

                if squad_labels and not (squad_labels & item_labels):
                    return False

                if other_labels and not (other_labels & item_labels):
                    return False

                if term and term not in all_text:
                    return False

                return True

            pre_count = len(items)
            items = [i for i in items if _matches_item(i)]
            print(f"[WORK-AI] Label/search filter: app_labels={app_labels} term={term!r} — {pre_count} → {len(items)}")

        if query.squad == "all":
            items = _group_by_squad(items)

        return items

    return []


def _group_by_squad(items: list[dict]) -> list[dict]:
    def squad_key(item: dict) -> str:
        squad = item.get("squad", "").strip().upper()
        if squad in ("A", "B", "C", "D"):
            return squad
        labels = item.get("labels", [])
        for label in labels:
            for letter, squad_name in SQUAD_LABELS.items():
                if squad_name.lower() == label.lower():
                    return letter.upper()
        return "Z"
    return sorted(items, key=squad_key)


def build_context(items: list[dict], query: DayJobQuery) -> str:
    if not items:
        return f"[WORK-AI] No {query.action} data found for {query.service}."

    lines = [f"[WORK-AI — {query.service.upper()} {query.action.upper()}]"]
    for item in items[:20]:
        if "number" in item:
            status = item.get("state", "open")
            labels = ", ".join(item.get("labels", [])[:3])
            assignees = ", ".join(item.get("assignees", [])[:2])
            line = f"  #{item['number']} {item['title']} [{status}]"
            if labels:
                line += f" labels={labels}"
            if assignees:
                line += f" assigned={assignees}"
            line += f" → {item.get('url', '')}"
            lines.append(line)
        elif "status" in item:
            line = f"  {item.get('title', '?')} [{item.get('status', '?')}]"
            assignees = ", ".join(item.get("assignees", [])[:2])
            if assignees:
                line += f" assigned={assignees}"
            line += f" → {item.get('url', '')}"
            lines.append(line)
        else:
            lines.append(f"  {item.get('name', item.get('title', item.get('id', '?')))}")

    if len(items) > 20:
        lines.append(f"  ... and {len(items) - 20} more")
    return "\n".join(lines)


def build_panel(items: list[dict], query: DayJobQuery) -> dict | None:
    if not items:
        return None

    title = f"WORK-AI — {query.service.upper()}"
    if query.action == "epics":
        title = f"EPICS — {query.repo.upper()}"
    elif query.action == "sprint":
        parts: list[str] = []
        if query.status_filter:
            parts.append(query.status_filter.upper())
        if query.label_filter:
            label_parts = [
                lbl.strip().replace("app-", "").upper()
                for lbl in query.label_filter.split(",")
                if lbl.strip() and lbl.strip().lower() != "planning"
            ]
            if label_parts:
                parts.extend(label_parts)
            if any(lbl.strip().lower() == "planning" for lbl in query.label_filter.split(",")):
                parts.append("PLANNING")
        if query.search_term:
            parts.append(query.search_term.upper())
        if query.squad == "all":
            parts.append("ALL SQUADS")
        elif query.squad:
            parts.append(f"SQUAD {query.squad.upper()}")
        title = " — ".join(parts) if parts else "SPRINT BOARD"
    elif query.action == "search" and query.search_term:
        title = f"SEARCH: {query.search_term.upper()}"

    table_rows: list[list[str]] = []
    has_project_fields = any("squad" in i for i in items)
    has_number = any(i.get("number") for i in items)

    if has_project_fields:
        sorted_items = sorted(items, key=lambda i: (i.get("stream", ""), i.get("status", "")))
        headers = ["#", "Title", "Stream", "Squad", "Status", "Assignees"]
        for item in sorted_items[:40]:
            num = item.get("number", 0)
            table_rows.append([
                f"#{num}" if num else "",
                item.get("title", "")[:60],
                item.get("stream", ""),
                item.get("squad", ""),
                item.get("status", ""),
                ", ".join(item.get("assignees", [])[:2]),
            ])
    elif has_number:
        headers = ["#", "Title", "Status", "Labels", "Assignees", "Link"]
        for item in items[:30]:
            table_rows.append([
                str(item.get("number", "")),
                item.get("title", "")[:60],
                item.get("state", item.get("status", "")),
                ", ".join(item.get("labels", [])[:3]),
                ", ".join(item.get("assignees", [])[:2]),
                item.get("url", ""),
            ])
    else:
        headers = ["Title", "Status", "Assignees", "Link"]
        for item in items[:30]:
            table_rows.append([
                item.get("title", item.get("name", ""))[:60],
                item.get("status", ""),
                ", ".join(item.get("assignees", [])[:2]),
                item.get("url", ""),
            ])

    status_counts: dict[str, int] = {}
    for item in items:
        s = (item.get("state") or item.get("status") or "unknown").lower()
        status_counts[s] = status_counts.get(s, 0) + 1

    stats = [{"label": "Total Items", "value": str(len(items))}]
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        stats.append({"label": status.title(), "value": str(count)})

    return {
        "title": title,
        "stats": stats[:6],
        "table": {"headers": headers, "rows": table_rows},
        "summary": f"{len(items)} items from {query.service} ({query.action})",
    }
