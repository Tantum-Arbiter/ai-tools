"""Tests for the short-lived signed session token used by SSE clients."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from session_token import SessionTokenSigner, SessionTokenError


_SECRET = b"shared-secret-for-tests-32-bytes-long-xxx"
_T0 = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def under_test() -> SessionTokenSigner:
    return SessionTokenSigner(secret=_SECRET)


class TestMintVerifyRoundTrip:
    def test_round_trip_succeeds_within_ttl(
        self, under_test: SessionTokenSigner,
    ) -> None:
        token = under_test.mint(ip="10.0.0.1", now=_T0, ttl_seconds=300)

        under_test.verify(token, ip="10.0.0.1", now=_T0 + timedelta(seconds=10))

    def test_token_has_no_raw_secret(
        self, under_test: SessionTokenSigner,
    ) -> None:
        token = under_test.mint(ip="10.0.0.1", now=_T0, ttl_seconds=300)

        assert _SECRET.decode("ascii", errors="ignore") not in token

    def test_token_is_url_safe(
        self, under_test: SessionTokenSigner,
    ) -> None:
        token = under_test.mint(ip="10.0.0.1", now=_T0, ttl_seconds=300)

        assert all(c.isalnum() or c in "-_." for c in token)


class TestVerifyFailures:
    def test_rejects_expired_token(
        self, under_test: SessionTokenSigner,
    ) -> None:
        token = under_test.mint(ip="10.0.0.1", now=_T0, ttl_seconds=60)

        with pytest.raises(SessionTokenError, match="expired"):
            under_test.verify(
                token, ip="10.0.0.1", now=_T0 + timedelta(seconds=61),
            )

    def test_rejects_wrong_ip(self, under_test: SessionTokenSigner) -> None:
        token = under_test.mint(ip="10.0.0.1", now=_T0, ttl_seconds=300)

        with pytest.raises(SessionTokenError, match="ip"):
            under_test.verify(token, ip="10.0.0.2", now=_T0)

    def test_rejects_tampered_payload(
        self, under_test: SessionTokenSigner,
    ) -> None:
        token = under_test.mint(ip="10.0.0.1", now=_T0, ttl_seconds=300)
        payload, sig = token.split(".")
        tampered_payload = payload[:-1] + ("a" if payload[-1] != "a" else "b")
        tampered = f"{tampered_payload}.{sig}"

        with pytest.raises(SessionTokenError, match="signature"):
            under_test.verify(tampered, ip="10.0.0.1", now=_T0)

    def test_rejects_tampered_signature(
        self, under_test: SessionTokenSigner,
    ) -> None:
        token = under_test.mint(ip="10.0.0.1", now=_T0, ttl_seconds=300)
        payload, sig = token.split(".")
        tampered = f"{payload}.{sig[:-1]}{'a' if sig[-1] != 'a' else 'b'}"

        with pytest.raises(SessionTokenError, match="signature"):
            under_test.verify(tampered, ip="10.0.0.1", now=_T0)

    @pytest.mark.parametrize("garbage", ["", "abc", "abc.def", "x.y.z", "..."])
    def test_rejects_malformed_token(
        self, under_test: SessionTokenSigner, garbage: str,
    ) -> None:
        with pytest.raises(SessionTokenError):
            under_test.verify(garbage, ip="10.0.0.1", now=_T0)

    def test_rejects_token_signed_with_different_secret(self) -> None:
        signer_a = SessionTokenSigner(secret=b"secret-a-aaaaaaaaaaaaaaaaaaaaaaaaaa")
        signer_b = SessionTokenSigner(secret=b"secret-b-bbbbbbbbbbbbbbbbbbbbbbbbbb")
        token = signer_a.mint(ip="10.0.0.1", now=_T0, ttl_seconds=300)

        with pytest.raises(SessionTokenError, match="signature"):
            signer_b.verify(token, ip="10.0.0.1", now=_T0)


class TestConstructorValidation:
    def test_rejects_short_secret(self) -> None:
        with pytest.raises(ValueError, match="secret"):
            SessionTokenSigner(secret=b"too-short")

    def test_accepts_minimum_length_secret(self) -> None:
        SessionTokenSigner(secret=b"x" * 32)
