from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from social_content_factory.status_log import (
    RenderStatusEntry,
    StatusLogError,
    append_status_entry,
    read_recent_entries,
)

FIXED_TS = datetime(2026, 6, 22, 14, 30, 0, tzinfo=timezone.utc)


def _entry(
    *,
    brand: str = "personal",
    theme: str = "weekly-build",
    status: str = "success",
    formats: tuple[str, ...] = ("1x1",),
    outputs: tuple[str, ...] = ("/tmp/out/fake.png",),
    error: str | None = None,
    duration_seconds: float = 1.23,
    timestamp: datetime = FIXED_TS,
) -> RenderStatusEntry:
    return RenderStatusEntry(
        timestamp=timestamp,
        brand=brand,
        theme=theme,
        status=status,
        formats=list(formats),
        outputs=list(outputs),
        error=error,
        duration_seconds=duration_seconds,
    )


class TestAppendStatusEntry:
    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        log_path = tmp_path / "data" / "factory_status.jsonl"

        append_status_entry(log_path, _entry())

        assert log_path.exists()

    def test_appends_one_line_per_entry(self, tmp_path: Path) -> None:
        log_path = tmp_path / "factory_status.jsonl"

        append_status_entry(log_path, _entry(theme="a"))
        append_status_entry(log_path, _entry(theme="b"))

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_each_line_is_valid_json_with_expected_keys(
        self, tmp_path: Path
    ) -> None:
        log_path = tmp_path / "factory_status.jsonl"

        append_status_entry(log_path, _entry())

        line = log_path.read_text(encoding="utf-8").splitlines()[0]
        record = json.loads(line)
        assert record["brand"] == "personal"
        assert record["theme"] == "weekly-build"
        assert record["status"] == "success"
        assert record["formats"] == ["1x1"]
        assert record["outputs"] == ["/tmp/out/fake.png"]
        assert record["error"] is None
        assert record["duration_seconds"] == 1.23
        assert record["timestamp"] == "2026-06-22T14:30:00+00:00"

    def test_rejects_invalid_status(self, tmp_path: Path) -> None:
        log_path = tmp_path / "factory_status.jsonl"

        with pytest.raises(StatusLogError, match="status"):
            append_status_entry(log_path, _entry(status="weird"))

    def test_failure_entry_records_error(self, tmp_path: Path) -> None:
        log_path = tmp_path / "factory_status.jsonl"

        append_status_entry(
            log_path,
            _entry(status="failure", outputs=(), error="ComfyUI offline"),
        )

        record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert record["status"] == "failure"
        assert record["error"] == "ComfyUI offline"
        assert record["outputs"] == []


class TestReadRecentEntries:
    def test_returns_empty_when_log_missing(self, tmp_path: Path) -> None:
        result = read_recent_entries(tmp_path / "missing.jsonl", limit=5)

        assert result == []

    def test_returns_entries_in_reverse_chronological_order(
        self, tmp_path: Path
    ) -> None:
        log_path = tmp_path / "factory_status.jsonl"
        append_status_entry(log_path, _entry(theme="oldest"))
        append_status_entry(log_path, _entry(theme="middle"))
        append_status_entry(log_path, _entry(theme="newest"))

        result = read_recent_entries(log_path, limit=5)

        assert [e.theme for e in result] == ["newest", "middle", "oldest"]

    def test_caps_results_at_limit(self, tmp_path: Path) -> None:
        log_path = tmp_path / "factory_status.jsonl"
        for i in range(10):
            append_status_entry(log_path, _entry(theme=f"t{i}"))

        result = read_recent_entries(log_path, limit=3)

        assert len(result) == 3
        assert [e.theme for e in result] == ["t9", "t8", "t7"]

    def test_skips_blank_and_corrupt_lines(self, tmp_path: Path) -> None:
        log_path = tmp_path / "factory_status.jsonl"
        append_status_entry(log_path, _entry(theme="good"))
        with log_path.open("a", encoding="utf-8") as fp:
            fp.write("\n")
            fp.write("{not json at all\n")

        result = read_recent_entries(log_path, limit=5)

        assert len(result) == 1
        assert result[0].theme == "good"
