"""Tests for the per-client response gate.

The gate is a pure transform: it decides what a given client is allowed to
see in a response from /api/jarvis/*. Mobile gets a safe subset of actions;
web/desktop is untouched.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from client_gate import (
    MOBILE,
    WEB,
    MOBILE_SAFE_ACTIONS,
    filter_response_for_client,
    normalise_client,
    should_intercept_desktop_command,
)


class TestNormaliseClient:
    @pytest.mark.parametrize("raw,expected", [
        ("mobile", MOBILE),
        ("MOBILE", MOBILE),
        ("  mobile  ", MOBILE),
        ("web", WEB),
        ("Web", WEB),
    ])
    def test_known_clients_normalise(self, raw, expected):
        assert normalise_client(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", "unknown", "desktop", "android"])
    def test_unknown_strings_collapse_to_web(self, raw):
        assert normalise_client(raw) == WEB

    @pytest.mark.parametrize("raw", [None, 0, 1, {}, [], object()])
    def test_non_strings_collapse_to_web(self, raw):
        assert normalise_client(raw) == WEB


class TestFilterResponseForClient:
    def test_web_client_response_passes_through_unchanged(self):
        under_test = {
            "reply": "ok",
            "error": False,
            "actions": [
                {"action": "open_browser", "url": "https://x"},
                {"action": "activate_app", "app": "Slack"},
            ],
        }

        result = filter_response_for_client(under_test, WEB)

        assert result is under_test

    def test_mobile_strips_unsafe_actions(self):
        under_test = {
            "reply": "ok",
            "actions": [
                {"action": "open_browser", "url": "https://x"},
                {"action": "activate_app", "app": "Slack"},
                {"action": "desktop_focus_window"},
            ],
        }

        result = filter_response_for_client(under_test, MOBILE)

        assert [a["action"] for a in result["actions"]] == ["open_browser"]

    def test_mobile_preserves_all_safe_action_types(self):
        actions = [{"action": a, "url": "https://x"} for a in MOBILE_SAFE_ACTIONS]
        under_test = {"reply": "ok", "actions": actions}

        result = filter_response_for_client(under_test, MOBILE)

        assert result["actions"] == actions

    def test_mobile_returns_shallow_copy_when_filtering(self):
        under_test = {
            "reply": "ok",
            "actions": [
                {"action": "open_browser", "url": "https://x"},
                {"action": "activate_app", "app": "Slack"},
            ],
        }

        result = filter_response_for_client(under_test, MOBILE)

        assert result is not under_test
        assert len(under_test["actions"]) == 2, "input must not be mutated"

    def test_mobile_returns_original_when_nothing_to_strip(self):
        under_test = {
            "reply": "ok",
            "actions": [{"action": "open_browser", "url": "https://x"}],
        }

        result = filter_response_for_client(under_test, MOBILE)

        assert result is under_test

    def test_mobile_preserves_panel_followups_reply(self):
        under_test = {
            "reply": "here you go",
            "error": False,
            "panel": {"title": "Stocks", "sections": [{"chart": {"type": "line"}}]},
            "followups": ["why?", "what next?"],
            "actions": [{"action": "activate_app", "app": "Slack"}],
        }

        result = filter_response_for_client(under_test, MOBILE)

        assert result["reply"] == "here you go"
        assert result["panel"] == under_test["panel"]
        assert result["followups"] == ["why?", "what next?"]
        assert result["actions"] == []

    def test_mobile_with_no_actions_field_unchanged(self):
        under_test = {"reply": "ok", "error": False}

        result = filter_response_for_client(under_test, MOBILE)

        assert result is under_test

    @pytest.mark.parametrize("bad_actions", [None, "open_browser", 42, {"action": "x"}])
    def test_mobile_with_malformed_actions_field_unchanged(self, bad_actions):
        under_test = {"reply": "ok", "actions": bad_actions}

        result = filter_response_for_client(under_test, MOBILE)

        assert result is under_test

    def test_mobile_skips_non_dict_action_entries(self):
        under_test = {
            "reply": "ok",
            "actions": [
                {"action": "open_browser", "url": "https://x"},
                "garbage",
                None,
                42,
            ],
        }

        result = filter_response_for_client(under_test, MOBILE)

        assert result["actions"] == [{"action": "open_browser", "url": "https://x"}]

    def test_non_dict_response_passes_through(self):
        assert filter_response_for_client("oops", MOBILE) == "oops"
        assert filter_response_for_client(None, MOBILE) is None


class TestShouldInterceptDesktopCommand:
    def test_mobile_skips_intercept(self):
        assert should_intercept_desktop_command(MOBILE) is False

    @pytest.mark.parametrize("client", [WEB, "unknown", ""])
    def test_other_clients_still_intercept(self, client):
        assert should_intercept_desktop_command(client) is True
