"""Tests for the security-headers helper."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from security_headers import build_security_headers, parse_csp


@pytest.fixture
def headers() -> dict[str, str]:
    return build_security_headers()


class TestStaticHeaders:
    def test_includes_nosniff(self, headers: dict[str, str]) -> None:
        assert headers["X-Content-Type-Options"] == "nosniff"

    def test_blocks_framing(self, headers: dict[str, str]) -> None:
        assert headers["X-Frame-Options"] == "DENY"

    def test_no_referrer_to_prevent_query_string_token_leak(
        self, headers: dict[str, str],
    ) -> None:
        assert headers["Referrer-Policy"] == "no-referrer"

    def test_permissions_policy_disables_sensitive_features(
        self, headers: dict[str, str],
    ) -> None:
        policy = headers["Permissions-Policy"]

        assert "geolocation=()" in policy
        assert "camera=()" in policy
        assert "microphone=(self)" in policy


class TestCsp:
    def test_default_src_is_self_only(self, headers: dict[str, str]) -> None:
        csp = parse_csp(headers["Content-Security-Policy"])

        assert csp["default-src"] == ["'self'"]

    def test_script_src_allows_self_inline_and_jsdelivr(
        self, headers: dict[str, str],
    ) -> None:
        csp = parse_csp(headers["Content-Security-Policy"])

        script_src = csp["script-src"]
        assert "'self'" in script_src
        assert "'unsafe-inline'" in script_src
        assert "https://cdn.jsdelivr.net" in script_src

    def test_style_src_allows_inline(self, headers: dict[str, str]) -> None:
        csp = parse_csp(headers["Content-Security-Policy"])

        assert "'unsafe-inline'" in csp["style-src"]

    def test_connect_src_is_self_only_to_block_exfil(
        self, headers: dict[str, str],
    ) -> None:
        csp = parse_csp(headers["Content-Security-Policy"])

        assert csp["connect-src"] == ["'self'"]

    def test_img_src_allows_data_and_blob_for_svgs_and_charts(
        self, headers: dict[str, str],
    ) -> None:
        csp = parse_csp(headers["Content-Security-Policy"])

        img_src = csp["img-src"]
        assert "'self'" in img_src
        assert "data:" in img_src
        assert "blob:" in img_src

    def test_object_src_blocked(self, headers: dict[str, str]) -> None:
        csp = parse_csp(headers["Content-Security-Policy"])

        assert csp["object-src"] == ["'none'"]

    def test_frame_ancestors_blocked(self, headers: dict[str, str]) -> None:
        csp = parse_csp(headers["Content-Security-Policy"])

        assert csp["frame-ancestors"] == ["'none'"]

    def test_base_uri_self(self, headers: dict[str, str]) -> None:
        csp = parse_csp(headers["Content-Security-Policy"])

        assert csp["base-uri"] == ["'self'"]


class TestParseCsp:
    def test_parses_multiple_directives(self) -> None:
        csp = parse_csp("default-src 'self'; script-src 'self' 'unsafe-inline'")

        assert csp["default-src"] == ["'self'"]
        assert csp["script-src"] == ["'self'", "'unsafe-inline'"]

    def test_trims_whitespace(self) -> None:
        csp = parse_csp("  default-src   'self'  ;  img-src 'self' data:  ")

        assert csp["default-src"] == ["'self'"]
        assert csp["img-src"] == ["'self'", "data:"]

    def test_empty_string_yields_empty_dict(self) -> None:
        assert parse_csp("") == {}
