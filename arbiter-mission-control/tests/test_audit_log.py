"""Tests for the JSONL audit logger."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from audit_log import AuditLogger, is_sensitive_request


class _FakeClock:
    def __init__(self, when: datetime) -> None:
        self._when = when

    def __call__(self) -> datetime:
        return self._when

    def set(self, when: datetime) -> None:
        self._when = when


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def clock() -> _FakeClock:
    return _FakeClock(datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def logger(tmp_path: Path, clock: _FakeClock) -> AuditLogger:
    return AuditLogger(log_dir=tmp_path, clock=clock)


class TestRecord:
    def test_writes_jsonl_with_core_fields(
        self, logger: AuditLogger, tmp_path: Path,
    ) -> None:
        logger.record(
            event="auth_fail", route="/api/settings", ip="10.0.0.1", status=401,
        )

        rows = _read_lines(tmp_path / "audit-2026-06-22.jsonl")
        assert len(rows) == 1
        row = rows[0]
        assert row["event"] == "auth_fail"
        assert row["route"] == "/api/settings"
        assert row["ip"] == "10.0.0.1"
        assert row["status"] == 401
        assert row["ts"] == "2026-06-22T12:00:00+00:00"

    def test_appends_multiple_records_to_same_day_file(
        self, logger: AuditLogger, tmp_path: Path,
    ) -> None:
        logger.record(event="auth_fail", route="/api/x", ip="1.1.1.1", status=401)
        logger.record(event="write", route="/api/y", ip="2.2.2.2", status=200)

        rows = _read_lines(tmp_path / "audit-2026-06-22.jsonl")
        assert [r["route"] for r in rows] == ["/api/x", "/api/y"]

    def test_rolls_to_new_file_on_new_utc_day(
        self, logger: AuditLogger, clock: _FakeClock, tmp_path: Path,
    ) -> None:
        logger.record(event="x", route="/api/a", ip="1.1.1.1", status=200)
        clock.set(datetime(2026, 6, 23, 0, 0, 1, tzinfo=timezone.utc))
        logger.record(event="x", route="/api/b", ip="1.1.1.1", status=200)

        assert (tmp_path / "audit-2026-06-22.jsonl").exists()
        assert (tmp_path / "audit-2026-06-23.jsonl").exists()

    def test_merges_extra_fields(self, logger: AuditLogger, tmp_path: Path) -> None:
        logger.record(
            event="rate_limited", route="/api/auth/check", ip="1.1.1.1",
            status=429, extra={"retry_after": 30, "limiter": "auth_check"},
        )

        row = _read_lines(tmp_path / "audit-2026-06-22.jsonl")[0]
        assert row["retry_after"] == 30
        assert row["limiter"] == "auth_check"

    @pytest.mark.parametrize(
        "leaky_key",
        ["api_key", "API_KEY", "authorization", "Authorization", "token", "password", "secret"],
    )
    def test_drops_token_like_fields_from_extra(
        self, logger: AuditLogger, tmp_path: Path, leaky_key: str,
    ) -> None:
        logger.record(
            event="x", route="/api/a", ip="1.1.1.1", status=200,
            extra={leaky_key: "should-not-appear", "safe": "ok"},
        )

        row = _read_lines(tmp_path / "audit-2026-06-22.jsonl")[0]
        assert leaky_key not in row
        assert "should-not-appear" not in json.dumps(row)
        assert row["safe"] == "ok"

    def test_creates_log_dir_if_missing(
        self, tmp_path: Path, clock: _FakeClock,
    ) -> None:
        nested = tmp_path / "deep" / "logs"

        under_test = AuditLogger(log_dir=nested, clock=clock)
        under_test.record(event="x", route="/api/a", ip="1.1.1.1", status=200)

        assert (nested / "audit-2026-06-22.jsonl").exists()


class TestIsSensitiveRequest:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("POST", "/api/settings"),
            ("PUT", "/api/settings/business"),
            ("DELETE", "/api/agents/researcher"),
            ("PATCH", "/api/ceo/runs/123"),
        ],
    )
    def test_writes_on_api_are_sensitive(self, method: str, path: str) -> None:
        assert is_sensitive_request(method, path) is True

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/status"),
            ("GET", "/api/agents"),
            ("GET", "/static/foo.js"),
            ("POST", "/static/foo.js"),
            ("POST", "/favicon.ico"),
        ],
    )
    def test_reads_and_non_api_routes_are_not_sensitive(
        self, method: str, path: str,
    ) -> None:
        assert is_sensitive_request(method, path) is False
