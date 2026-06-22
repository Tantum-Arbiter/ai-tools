"""Forensic audit log — JSONL, one file per UTC day.

Used by the mission-control server to record auth failures (401 / 429
across any route) and writes to /api/* paths. Lets the operator answer
"did anyone use my token while I was away?" after the fact.

Never persists token values, Authorization headers, or anything matching
a token-like field name. The logger sanitises `extra` payloads before
writing.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

UtcClock = Callable[[], datetime]

_FORBIDDEN_FIELDS = frozenset({
    "api_key", "apikey", "authorization", "auth", "token",
    "password", "secret", "bearer", "cookie",
})

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sanitise(extra: dict[str, object] | None) -> dict[str, object]:
    if not extra:
        return {}
    return {k: v for k, v in extra.items() if k.lower() not in _FORBIDDEN_FIELDS}


class AuditLogger:
    def __init__(
        self,
        log_dir: Path,
        clock: UtcClock | None = None,
    ) -> None:
        self._dir = Path(log_dir)
        self._clock: UtcClock = clock if clock is not None else _utcnow
        self._lock = threading.Lock()
        self._dir.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        event: str,
        route: str,
        ip: str,
        status: int,
        extra: dict[str, object] | None = None,
    ) -> None:
        now = self._clock()
        row: dict[str, object] = {
            "ts": now.isoformat(),
            "event": event,
            "route": route,
            "ip": ip,
            "status": status,
        }
        row.update(_sanitise(extra))
        target = self._dir / f"audit-{now.strftime('%Y-%m-%d')}.jsonl"
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with target.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


def is_sensitive_request(method: str, path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    return method.upper() in _WRITE_METHODS
