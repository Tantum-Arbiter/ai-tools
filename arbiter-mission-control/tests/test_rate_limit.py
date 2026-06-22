"""Tests for the per-key sliding-window rate limiter."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rate_limit import SlidingWindowRateLimiter


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


@pytest.fixture
def clock() -> _FakeClock:
    return _FakeClock()


class TestSlidingWindowRateLimiter:
    def test_allows_requests_up_to_max(self, clock: _FakeClock) -> None:
        under_test = SlidingWindowRateLimiter(max_requests=3, window_seconds=60.0, clock=clock)

        results = [under_test.check("ip-a") for _ in range(3)]

        assert results == [True, True, True]

    def test_blocks_request_after_max(self, clock: _FakeClock) -> None:
        under_test = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0, clock=clock)
        under_test.check("ip-a")
        under_test.check("ip-a")

        blocked = under_test.check("ip-a")

        assert blocked is False

    def test_allows_again_after_window_slides(self, clock: _FakeClock) -> None:
        under_test = SlidingWindowRateLimiter(max_requests=1, window_seconds=10.0, clock=clock)
        under_test.check("ip-a")
        assert under_test.check("ip-a") is False

        clock.advance(10.5)
        allowed = under_test.check("ip-a")

        assert allowed is True

    def test_per_key_isolation(self, clock: _FakeClock) -> None:
        under_test = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0, clock=clock)
        under_test.check("ip-a")

        allowed_other = under_test.check("ip-b")
        blocked_same = under_test.check("ip-a")

        assert allowed_other is True
        assert blocked_same is False

    def test_retry_after_zero_when_under_limit(self, clock: _FakeClock) -> None:
        under_test = SlidingWindowRateLimiter(max_requests=3, window_seconds=60.0, clock=clock)
        under_test.check("ip-a")

        wait = under_test.retry_after("ip-a")

        assert wait == 0.0

    def test_retry_after_when_blocked(self, clock: _FakeClock) -> None:
        under_test = SlidingWindowRateLimiter(max_requests=1, window_seconds=30.0, clock=clock)
        under_test.check("ip-a")
        clock.advance(5.0)

        wait = under_test.retry_after("ip-a")

        assert wait == pytest.approx(25.0)

    def test_blocked_check_does_not_consume_quota(self, clock: _FakeClock) -> None:
        under_test = SlidingWindowRateLimiter(max_requests=1, window_seconds=10.0, clock=clock)
        under_test.check("ip-a")

        for _ in range(5):
            assert under_test.check("ip-a") is False

        clock.advance(10.5)
        assert under_test.check("ip-a") is True

    def test_reset_clears_specific_key(self, clock: _FakeClock) -> None:
        under_test = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0, clock=clock)
        under_test.check("ip-a")
        under_test.check("ip-b")

        under_test.reset("ip-a")

        assert under_test.check("ip-a") is True
        assert under_test.check("ip-b") is False

    def test_reset_all_clears_every_key(self, clock: _FakeClock) -> None:
        under_test = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0, clock=clock)
        under_test.check("ip-a")
        under_test.check("ip-b")

        under_test.reset()

        assert under_test.check("ip-a") is True
        assert under_test.check("ip-b") is True

    @pytest.mark.parametrize("max_requests", [0, -1])
    def test_invalid_max_requests_rejected(self, max_requests: int) -> None:
        with pytest.raises(ValueError):
            SlidingWindowRateLimiter(max_requests=max_requests, window_seconds=60.0)

    @pytest.mark.parametrize("window_seconds", [0.0, -1.0])
    def test_invalid_window_rejected(self, window_seconds: float) -> None:
        with pytest.raises(ValueError):
            SlidingWindowRateLimiter(max_requests=5, window_seconds=window_seconds)
