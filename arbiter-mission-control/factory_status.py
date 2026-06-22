"""Read-only view of social-content-factory's JSONL render status log.

ARBITER tails ``social-content-factory/data/factory_status.jsonl`` and surfaces
the last few render attempts on the dashboard. This module is sync; the SSE
poller in ``server.py`` wraps it with ``asyncio.to_thread``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RenderStatusEntry":
        return cls(
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            brand=str(payload["brand"]),
            theme=str(payload["theme"]),
            status=str(payload["status"]),
            formats=list(payload.get("formats") or []),
            outputs=list(payload.get("outputs") or []),
            error=payload.get("error"),
            duration_seconds=float(payload.get("duration_seconds") or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "brand": self.brand,
            "theme": self.theme,
            "status": self.status,
            "formats": list(self.formats),
            "outputs": list(self.outputs),
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


class FactoryStatusReader:
    """Tails the factory status JSONL file.

    Missing log file is treated as "no renders yet" rather than an error;
    the factory may simply not have run on this machine.
    """

    def __init__(self, log_path: Path) -> None:
        self._log_path = Path(log_path)

    @property
    def log_path(self) -> Path:
        return self._log_path

    def mtime(self) -> float | None:
        try:
            return self._log_path.stat().st_mtime
        except FileNotFoundError:
            return None

    def load_recent(self, *, limit: int = 5) -> list[RenderStatusEntry]:
        if limit <= 0:
            return []
        try:
            raw = self._log_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []

        entries: list[RenderStatusEntry] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                entries.append(RenderStatusEntry.from_dict(payload))
            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
                logger.warning("skipping malformed factory status line: %s", exc)
                continue

        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:limit]


class FactoryStatusPoller:
    """Edge-triggered wrapper around :class:`FactoryStatusReader`.

    ``tick()`` returns a fresh entry list only when the underlying log's mtime
    changes since the last successful read; otherwise ``None``. Designed to be
    called from an asyncio loop via ``asyncio.to_thread``.
    """

    def __init__(self, reader: FactoryStatusReader, *, limit: int = 5) -> None:
        self._reader = reader
        self._limit = limit
        self._last_mtime: float | None = None

    @property
    def reader(self) -> FactoryStatusReader:
        return self._reader

    def tick(self) -> list[RenderStatusEntry] | None:
        mtime = self._reader.mtime()
        if mtime is None:
            return None
        if self._last_mtime is not None and mtime <= self._last_mtime:
            return None
        entries = self._reader.load_recent(limit=self._limit)
        self._last_mtime = mtime
        return entries
