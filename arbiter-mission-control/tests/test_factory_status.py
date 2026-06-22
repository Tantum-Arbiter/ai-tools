"""Tests for ARBITER's read-only view of social-content-factory render status."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from factory_status import FactoryStatusPoller, FactoryStatusReader, RenderStatusEntry


def _line(
    *,
    theme: str = "weekly-build",
    status: str = "success",
    brand: str = "personal",
    error: str | None = None,
    outputs: tuple[str, ...] = ("/tmp/out/fake.png",),
    formats: tuple[str, ...] = ("1x1",),
    timestamp: str = "2026-06-22T14:30:00+00:00",
) -> str:
    return json.dumps({
        "brand": brand,
        "theme": theme,
        "status": status,
        "formats": list(formats),
        "outputs": list(outputs),
        "error": error,
        "duration_seconds": 1.5,
        "timestamp": timestamp,
    })


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "factory_status.jsonl"


class TestFactoryStatusReader:
    def test_load_recent_returns_empty_when_log_missing(self, log_path: Path) -> None:
        under_test = FactoryStatusReader(log_path)

        assert under_test.load_recent(limit=5) == []

    def test_load_recent_returns_entries_newest_first(self, log_path: Path) -> None:
        log_path.write_text(
            "\n".join([
                _line(theme="oldest", timestamp="2026-06-20T09:00:00+00:00"),
                _line(theme="middle", timestamp="2026-06-21T09:00:00+00:00"),
                _line(theme="newest", timestamp="2026-06-22T09:00:00+00:00"),
            ]) + "\n",
            encoding="utf-8",
        )
        under_test = FactoryStatusReader(log_path)

        result = under_test.load_recent(limit=5)

        assert [e.theme for e in result] == ["newest", "middle", "oldest"]

    def test_load_recent_caps_at_limit(self, log_path: Path) -> None:
        log_path.write_text(
            "\n".join(_line(theme=f"t{i}") for i in range(10)) + "\n",
            encoding="utf-8",
        )
        under_test = FactoryStatusReader(log_path)

        result = under_test.load_recent(limit=3)

        assert len(result) == 3

    def test_load_recent_skips_corrupt_and_blank_lines(self, log_path: Path) -> None:
        log_path.write_text(
            _line(theme="good") + "\n\n{not json\n",
            encoding="utf-8",
        )
        under_test = FactoryStatusReader(log_path)

        result = under_test.load_recent(limit=5)

        assert len(result) == 1
        assert result[0].theme == "good"

    def test_load_recent_parses_failure_entries(self, log_path: Path) -> None:
        log_path.write_text(
            _line(status="failure", outputs=(), error="ComfyUI offline") + "\n",
            encoding="utf-8",
        )
        under_test = FactoryStatusReader(log_path)

        result = under_test.load_recent(limit=5)

        assert result[0].status == "failure"
        assert result[0].error == "ComfyUI offline"
        assert result[0].outputs == []

    def test_mtime_returns_none_when_log_missing(self, log_path: Path) -> None:
        under_test = FactoryStatusReader(log_path)

        assert under_test.mtime() is None

    def test_mtime_returns_float_seconds(self, log_path: Path) -> None:
        log_path.write_text(_line() + "\n", encoding="utf-8")
        under_test = FactoryStatusReader(log_path)

        result = under_test.mtime()

        assert isinstance(result, float)
        assert result > 0

    def test_entry_to_dict_round_trips(self, log_path: Path) -> None:
        log_path.write_text(_line() + "\n", encoding="utf-8")
        under_test = FactoryStatusReader(log_path)

        [entry] = under_test.load_recent(limit=1)
        as_dict = entry.to_dict()

        assert as_dict["theme"] == "weekly-build"
        assert as_dict["status"] == "success"
        assert as_dict["timestamp"] == "2026-06-22T14:30:00+00:00"


class TestRenderStatusEntry:
    def test_parses_iso_timestamp_to_aware_datetime(self) -> None:
        under_test = RenderStatusEntry.from_dict({
            "timestamp": "2026-06-22T14:30:00+00:00",
            "brand": "personal", "theme": "t", "status": "success",
            "formats": [], "outputs": [], "error": None,
            "duration_seconds": 0.0,
        })

        assert under_test.timestamp == datetime(2026, 6, 22, 14, 30, tzinfo=timezone.utc)


class TestFactoryStatusPoller:
    def test_first_tick_emits_when_log_exists(self, log_path: Path) -> None:
        log_path.write_text(_line() + "\n", encoding="utf-8")
        reader = FactoryStatusReader(log_path)
        under_test = FactoryStatusPoller(reader, limit=5)

        result = under_test.tick()

        assert result is not None
        assert len(result) == 1

    def test_first_tick_returns_none_when_log_missing(self, log_path: Path) -> None:
        reader = FactoryStatusReader(log_path)
        under_test = FactoryStatusPoller(reader, limit=5)

        assert under_test.tick() is None

    def test_second_tick_returns_none_when_unchanged(self, log_path: Path) -> None:
        log_path.write_text(_line() + "\n", encoding="utf-8")
        under_test = FactoryStatusPoller(FactoryStatusReader(log_path), limit=5)
        under_test.tick()

        assert under_test.tick() is None

    def test_tick_emits_again_when_log_changes(self, log_path: Path) -> None:
        log_path.write_text(_line(theme="a") + "\n", encoding="utf-8")
        under_test = FactoryStatusPoller(FactoryStatusReader(log_path), limit=5)
        under_test.tick()

        os.utime(log_path, (1, 1))
        log_path.write_text(
            _line(theme="a") + "\n" + _line(theme="b", timestamp="2026-06-23T09:00:00+00:00") + "\n",
            encoding="utf-8",
        )

        result = under_test.tick()

        assert result is not None
        assert [e.theme for e in result] == ["b", "a"]
