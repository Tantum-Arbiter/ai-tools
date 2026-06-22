"""Tests for the SSE chat-stream event formatter (chat_stream.py)."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat_stream import (
    EVENT_ACTIONS,
    EVENT_DELTA,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_FOLLOWUPS,
    EVENT_META,
    EVENT_PANEL,
    chunk_text,
    format_keepalive,
    format_sse_event,
    iter_chat_stream_events,
    iter_error_stream,
)


def _parse_frames(frames: list[str]) -> list[tuple[str, object]]:
    parsed: list[tuple[str, object]] = []
    for frame in frames:
        assert frame.endswith("\n\n"), "every SSE frame must terminate with a blank line"
        lines = [ln for ln in frame.splitlines() if ln]
        event_lines = [ln for ln in lines if ln.startswith("event: ")]
        data_lines = [ln for ln in lines if ln.startswith("data: ")]
        assert len(event_lines) == 1 and len(data_lines) == 1
        event = event_lines[0][len("event: "):]
        data = json.loads(data_lines[0][len("data: "):])
        parsed.append((event, data))
    return parsed


class TestFormatSseEvent:
    def test_format_basic_event(self) -> None:
        under_test = format_sse_event("delta", {"text": "hello"})

        assert under_test == 'event: delta\ndata: {"text":"hello"}\n\n'

    def test_format_rejects_empty_event_name(self) -> None:
        with pytest.raises(ValueError):
            format_sse_event("", {"x": 1})

    def test_keepalive_is_a_comment_line(self) -> None:
        assert format_keepalive() == ": keepalive\n\n"


class TestChunkText:
    @pytest.mark.parametrize("words_per_chunk", [1, 2, 3, 5])
    def test_concatenated_chunks_equal_input(self, words_per_chunk: int) -> None:
        text = "The quick brown fox jumps over the lazy dog."

        result = list(chunk_text(text, words_per_chunk=words_per_chunk))

        assert "".join(result) == text
        assert all(c for c in result)

    def test_empty_text_yields_nothing(self) -> None:
        assert list(chunk_text("")) == []

    def test_rejects_zero_words(self) -> None:
        with pytest.raises(ValueError):
            list(chunk_text("hi", words_per_chunk=0))

    def test_preserves_internal_whitespace(self) -> None:
        text = "alpha  beta\tgamma\n delta"

        result = list(chunk_text(text, words_per_chunk=2))

        assert "".join(result) == text


class TestIterChatStreamEvents:
    def test_minimal_reply_only(self) -> None:
        frames = list(iter_chat_stream_events("Hello world", chunk_words=1))
        parsed = _parse_frames(frames)

        assert [e for e, _ in parsed] == [EVENT_META, EVENT_DELTA, EVENT_DELTA, EVENT_DONE]
        assert parsed[0][1] == {"topic": None, "error": False}
        assert parsed[-1][1] == {"reply": "Hello world"}

    def test_full_payload_order(self) -> None:
        panel = {"title": "STATUS", "stats": [{"label": "x", "value": 1}]}
        actions = [{"action": "open_url", "url": "https://example.com"}]
        followups = ["What next?", "Show me more"]

        frames = list(
            iter_chat_stream_events(
                "Done.",
                panel=panel,
                actions=actions,
                followups=followups,
                topic="stocks",
            )
        )
        parsed = _parse_frames(frames)
        events = [e for e, _ in parsed]

        assert events[0] == EVENT_META
        assert events[-1] == EVENT_DONE
        ordered = [e for e in events if e != EVENT_DELTA]
        assert ordered == [EVENT_META, EVENT_PANEL, EVENT_ACTIONS, EVENT_FOLLOWUPS, EVENT_DONE]
        assert dict(parsed)[EVENT_PANEL] == panel
        assert dict(parsed)[EVENT_ACTIONS] == actions
        assert dict(parsed)[EVENT_FOLLOWUPS] == followups
        assert dict(parsed)[EVENT_META]["topic"] == "stocks"

    def test_empty_reply_still_emits_meta_and_done(self) -> None:
        frames = list(iter_chat_stream_events(""))

        parsed = _parse_frames(frames)
        events = [e for e, _ in parsed]

        assert events == [EVENT_META, EVENT_DONE]


class TestIterErrorStream:
    def test_error_stream_shape(self) -> None:
        frames = list(iter_error_stream("boom"))

        parsed = _parse_frames(frames)

        assert [e for e, _ in parsed] == [EVENT_ERROR, EVENT_DONE]
        assert parsed[0][1] == {"message": "boom"}
        assert parsed[-1][1] == {"reply": "", "error": True}
