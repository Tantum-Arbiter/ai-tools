"""Per-client response shaping for /api/jarvis/*.

The desktop frontend can execute the full action set (open_browser, open_url,
activate_app, etc.). The mobile app can only handle a safe subset
(open_browser, open_url). This module is the single source of truth for
which response fields are returned to which client.

Kept dependency-free and pure so it can be unit-tested in isolation without
spinning up FastAPI or the LLM stack.
"""
from __future__ import annotations

from typing import Final

MOBILE = "mobile"
WEB = "web"

MOBILE_SAFE_ACTIONS: Final[frozenset[str]] = frozenset({
    "open_browser",
    "open_url",
})

_KNOWN_CLIENTS: Final[frozenset[str]] = frozenset({MOBILE, WEB})


def normalise_client(raw: object) -> str:
    """Coerce an arbitrary request value into a known client tag.

    Unknown values, empty strings, and non-strings all collapse to ``WEB`` so
    that callers can treat a missing/garbled header as the (permissive) web
    case rather than the (restrictive) mobile case.
    """
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in _KNOWN_CLIENTS:
            return value
    return WEB


def filter_response_for_client(response: dict, client: str) -> dict:
    """Return a shallow copy of ``response`` shaped for ``client``.

    For ``MOBILE`` the action list is filtered to ``MOBILE_SAFE_ACTIONS``.
    For any other client (including ``WEB``) the response is returned
    unchanged so existing desktop callers are unaffected.

    Non-dict inputs and missing/non-list action fields pass through untouched.
    """
    if not isinstance(response, dict):
        return response
    if client != MOBILE:
        return response

    actions = response.get("actions")
    if not isinstance(actions, list):
        return response

    filtered = [
        a for a in actions
        if isinstance(a, dict) and a.get("action") in MOBILE_SAFE_ACTIONS
    ]
    if len(filtered) == len(actions):
        return response

    out = dict(response)
    out["actions"] = filtered
    return out


def should_intercept_desktop_command(client: str) -> bool:
    """Whether the server should run its built-in ``_detect_desktop_command``
    intercept (which fires AppleScript / ``open`` shell commands on the host
    Mac). Mobile clients can't action those, so we let the LLM answer
    conversationally instead.
    """
    return client != MOBILE
