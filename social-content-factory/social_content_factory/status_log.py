from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

VALID_STATUSES: Final[frozenset[str]] = frozenset({"success", "failure"})


class StatusLogError(Exception):
    """Raised when a status log entry is invalid or cannot be persisted."""


@dataclass(frozen=True)
class RenderStatusEntry:
    timestamp: datetime
    brand: str
    theme: str
    status: str
    formats: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    error: str | None = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        ts = self.timestamp if self.timestamp.tzinfo else self.timestamp.replace(
            tzinfo=timezone.utc
        )
        return {
            "timestamp": ts.isoformat(),
            "brand": self.brand,
            "theme": self.theme,
            "status": self.status,
            "formats": list(self.formats),
            "outputs": list(self.outputs),
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> RenderStatusEntry:
        timestamp = datetime.fromisoformat(raw["timestamp"])
        return cls(
            timestamp=timestamp,
            brand=str(raw["brand"]),
            theme=str(raw["theme"]),
            status=str(raw["status"]),
            formats=list(raw.get("formats") or []),
            outputs=list(raw.get("outputs") or []),
            error=raw.get("error"),
            duration_seconds=float(raw.get("duration_seconds") or 0.0),
        )


def append_status_entry(log_path: Path, entry: RenderStatusEntry) -> None:
    if entry.status not in VALID_STATUSES:
        raise StatusLogError(
            f"status must be one of {sorted(VALID_STATUSES)}, got {entry.status!r}"
        )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry.to_dict(), sort_keys=True) + "\n"
    _atomic_append_text(log_path, line)


def read_recent_entries(log_path: Path, *, limit: int) -> list[RenderStatusEntry]:
    if limit <= 0:
        return []
    if not log_path.exists():
        return []

    lines = log_path.read_text(encoding="utf-8").splitlines()
    entries: list[RenderStatusEntry] = []
    for raw_line in reversed(lines):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
            entries.append(RenderStatusEntry.from_dict(record))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            logger.warning("skipping corrupt status log line: %s", exc)
            continue
        if len(entries) >= limit:
            break
    return entries


def _atomic_append_text(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp.{uuid.uuid4().hex}")
    try:
        existing = path.read_bytes() if path.exists() else b""
        with tmp.open("wb") as fp:
            fp.write(existing)
            fp.write(text.encode("utf-8"))
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
