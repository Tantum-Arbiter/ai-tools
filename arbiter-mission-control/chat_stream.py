"""SSE event formatting for the /api/jarvis/chat/stream endpoint.

The mobile app consumes Server-Sent Events so the operator sees the reply
materialise token-by-token instead of waiting for the full JSON body. This
module is intentionally side-effect free: callers pass in the already-computed
chat result and receive an iterator of wire-formatted SSE strings. Wiring it
into FastAPI is a thin shim in server.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

EVENT_META = "meta"
EVENT_DELTA = "delta"
EVENT_PANEL = "panel"
EVENT_ACTIONS = "actions"
EVENT_FOLLOWUPS = "followups"
EVENT_ERROR = "error"
EVENT_DONE = "done"
EVENT_KEEPALIVE = "ping"

DEFAULT_CHUNK_WORDS = 3

_WORD_BOUNDARY = re.compile(r"(\s+)")


def format_sse_event(event: str, data: Any) -> str:
    """Format a single SSE event frame.

    Per the spec, every event ends in a blank line. We always emit both
    ``event:`` and ``data:`` fields so the client doesn't have to guess.
    """
    if not event or not isinstance(event, str):
        raise ValueError("event name must be a non-empty string")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def format_keepalive() -> str:
    """SSE comment line — used for periodic keepalives during slow generations."""
    return ": keepalive\n\n"


def chunk_text(text: str, words_per_chunk: int = DEFAULT_CHUNK_WORDS) -> Iterator[str]:
    """Split ``text`` into roughly word-sized chunks preserving whitespace.

    The split is whitespace-aware so the receiver can simply concatenate
    chunks without re-spacing. Empty strings yield nothing.
    """
    if words_per_chunk < 1:
        raise ValueError("words_per_chunk must be >= 1")
    if not text:
        return
    tokens = _WORD_BOUNDARY.split(text)
    buf: list[str] = []
    word_count = 0
    for tok in tokens:
        if not tok:
            continue
        buf.append(tok)
        if not tok.isspace():
            word_count += 1
        if word_count >= words_per_chunk:
            yield "".join(buf)
            buf = []
            word_count = 0
    if buf:
        yield "".join(buf)


def iter_chat_stream_events(
    reply: str,
    *,
    panel: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
    followups: list[str] | None = None,
    error: bool = False,
    topic: str | None = None,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
) -> Iterator[str]:
    """Yield the full sequence of SSE frames for a completed chat result.

    The order is fixed:
        meta -> delta* -> panel? -> actions? -> followups? -> done

    Callers (the route handler) typically stream this generator directly into
    a StreamingResponse; tests can collect the frames eagerly.
    """
    yield format_sse_event(EVENT_META, {"topic": topic, "error": bool(error)})

    for piece in chunk_text(reply, words_per_chunk=chunk_words):
        yield format_sse_event(EVENT_DELTA, {"text": piece})

    if panel is not None:
        yield format_sse_event(EVENT_PANEL, panel)
    if actions:
        yield format_sse_event(EVENT_ACTIONS, actions)
    if followups:
        yield format_sse_event(EVENT_FOLLOWUPS, followups)

    yield format_sse_event(EVENT_DONE, {"reply": reply})


def iter_error_stream(message: str) -> Iterator[str]:
    """Emit a single error event followed by done — used when chat fails outright."""
    yield format_sse_event(EVENT_ERROR, {"message": message})
    yield format_sse_event(EVENT_DONE, {"reply": "", "error": True})
