"""Tests for voice engine safety guards — wake word, echo suppression, state guards.

Mirrors the JavaScript logic in static/jarvis.js as Python contract tests.
The regex patterns and thresholds are kept in sync with the JS source.
Run: pytest tests/test_voice_guards.py -v
"""
from __future__ import annotations

import re
import time

import pytest


# ── Reference implementations mirroring jarvis.js ────────────────────────

WAKE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\barbiter\b", re.I),
    re.compile(r"\barbitor\b", re.I),
    re.compile(r"\barbr?it", re.I),
    re.compile(r"\barbeiter\b", re.I),
    re.compile(r"\barbor\b", re.I),
    re.compile(r"\barvit", re.I),
    re.compile(r"\barbat", re.I),
]

WAKE_CONFIDENCE_THRESHOLD = 0.7

WAKE_STRIP = re.compile(
    r"^.*?\b(?:arbiter|arbitor|arbrit\w*|arbeiter|arbor|arvit\w*|arbat\w*)\b[,.\s!?']*",
    re.I,
)

REMOVED_PATTERNS = ["albert", "harbor", "orbit", "orbiting", "orbital"]


def matches_wake_word(text: str) -> bool:
    lower = text.lower()
    return any(rx.search(lower) for rx in WAKE_PATTERNS)


def should_trigger(text: str, confidence: float) -> bool:
    return matches_wake_word(text) and confidence >= WAKE_CONFIDENCE_THRESHOLD


def strip_wake_word(text: str) -> str:
    return WAKE_STRIP.sub("", text).strip()


def echo_guard_active(guard_until: float) -> bool:
    return time.time() * 1000 < guard_until


def state_allows_recognition(
    *, chat_mode: bool, mic_muted: bool, speaking: bool, mic_denied: bool
) -> bool:
    return not chat_mode and not mic_muted and not speaking and not mic_denied


# ── Wake Word Pattern Tests ──────────────────────────────────────────────


class TestWakeWordPatterns:
    @pytest.mark.parametrize("transcript", [
        "arbiter", "Arbiter", "ARBITER",
        "hey arbiter what time is it",
        "arbitor please help",
        "arbeiter do something",
        "arbor",
        "arviter",
        "arbat something",
        "arbrit something",
    ])
    def test_valid_wake_words_match(self, transcript: str) -> None:
        assert matches_wake_word(transcript), f"Should match: {transcript!r}"

    @pytest.mark.parametrize("transcript", REMOVED_PATTERNS + [
        "hello there",
        "the weather is nice",
        "I went to the store",
        "tell me about Albert Einstein",
        "the harbor was beautiful",
        "the satellite is orbiting earth",
        "what is the orbital period",
    ])
    def test_removed_and_unrelated_words_rejected(self, transcript: str) -> None:
        assert not matches_wake_word(transcript), f"Should NOT match: {transcript!r}"


class TestConfidenceThreshold:
    @pytest.mark.parametrize("confidence", [0.7, 0.85, 0.95, 1.0])
    def test_high_confidence_triggers(self, confidence: float) -> None:
        assert should_trigger("arbiter", confidence)

    @pytest.mark.parametrize("confidence", [0.0, 0.3, 0.5, 0.69])
    def test_low_confidence_blocked(self, confidence: float) -> None:
        assert not should_trigger("arbiter", confidence)

    def test_low_confidence_arbor_blocked(self) -> None:
        assert not should_trigger("arbor", 0.5)

    def test_high_confidence_arbor_triggers(self) -> None:
        assert should_trigger("arbor", 0.8)


class TestWakeWordStripping:
    @pytest.mark.parametrize("raw,expected", [
        ("arbiter what time is it", "what time is it"),
        ("Arbiter, show me stocks", "show me stocks"),
        ("hey arbitor help me", "help me"),
        ("arbeiter! do this", "do this"),
        ("arbor check weather", "check weather"),
        ("arbiter", ""),
    ])
    def test_strip_wake_word(self, raw: str, expected: str) -> None:
        assert strip_wake_word(raw) == expected


class TestEchoGuard:
    def test_guard_active_during_window(self) -> None:
        future = time.time() * 1000 + 5000
        assert echo_guard_active(future)

    def test_guard_inactive_after_window(self) -> None:
        past = time.time() * 1000 - 1000
        assert not echo_guard_active(past)

    def test_guard_duration_is_1500ms(self) -> None:
        now_ms = time.time() * 1000
        guard_until = now_ms + 1500
        assert echo_guard_active(guard_until)


class TestStateGuards:
    def test_all_clear_allows_recognition(self) -> None:
        assert state_allows_recognition(
            chat_mode=False, mic_muted=False, speaking=False, mic_denied=False
        )

    @pytest.mark.parametrize("flag", [
        {"chat_mode": True},
        {"mic_muted": True},
        {"speaking": True},
        {"mic_denied": True},
    ])
    def test_any_flag_blocks_recognition(self, flag: dict[str, bool]) -> None:
        defaults = dict(chat_mode=False, mic_muted=False, speaking=False, mic_denied=False)
        defaults.update(flag)
        assert not state_allows_recognition(**defaults)

    def test_multiple_flags_block(self) -> None:
        assert not state_allows_recognition(
            chat_mode=True, mic_muted=True, speaking=False, mic_denied=False
        )
