"""Per-key sliding-window rate limiter.

Designed for guarding the auth-check oracle and the 401 path in the
mission-control server. Pure in-memory, no external deps, deterministic
under an injected clock so tests stay fast and timer-free.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Callable

Clock = Callable[[], float]


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Clock | None = None,
    ) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be > 0")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._max = max_requests
        self._window = float(window_seconds)
        self._clock: Clock = clock if clock is not None else time.monotonic
        self._buckets: dict[str, deque[float]] = {}

    def check(self, key: str) -> bool:
        now = self._clock()
        bucket = self._prune(key, now)
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        return True

    def retry_after(self, key: str) -> float:
        bucket = self._buckets.get(key)
        if not bucket or len(bucket) < self._max:
            return 0.0
        now = self._clock()
        return max(0.0, bucket[0] + self._window - now)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._buckets.clear()
            return
        self._buckets.pop(key, None)

    def _prune(self, key: str, now: float) -> deque[float]:
        cutoff = now - self._window
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = deque()
            self._buckets[key] = bucket
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        return bucket
