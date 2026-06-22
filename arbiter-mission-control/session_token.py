"""HMAC-signed short-lived session tokens for SSE clients.

The browser dashboard uses `new EventSource(url)` which cannot set custom
HTTP headers. Rather than fall back to `?api_key=<bearer>` (which would
leak the long-lived bearer token into server access logs, browser history,
and the Referer header), the dashboard exchanges its bearer for a short
lived session token via /api/auth/session and passes that on the query
string instead.

Tokens encode `(expiry_unix, ip)` and are signed HMAC-SHA256 with a
server-side secret. They are stateless: the server only needs to verify
the signature, expiry, and IP match. There is no token registry to
manage. Compromise window is bounded by the TTL (default 5 minutes).
"""
from __future__ import annotations

import base64
import hmac
import json
from datetime import datetime, timezone
from hashlib import sha256


class SessionTokenError(Exception):
    pass


_MIN_SECRET_BYTES = 32


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


class SessionTokenSigner:
    def __init__(self, secret: bytes) -> None:
        if len(secret) < _MIN_SECRET_BYTES:
            raise ValueError(
                f"secret must be at least {_MIN_SECRET_BYTES} bytes; got {len(secret)}",
            )
        self._secret = secret

    def mint(self, *, ip: str, now: datetime, ttl_seconds: int) -> str:
        payload = {
            "exp": int(now.timestamp()) + int(ttl_seconds),
            "ip": ip,
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_b64 = _b64u_encode(payload_bytes)
        sig = hmac.new(self._secret, payload_b64.encode("ascii"), sha256).digest()
        return f"{payload_b64}.{_b64u_encode(sig)}"

    def verify(self, token: str, *, ip: str, now: datetime) -> None:
        if not token or token.count(".") != 1:
            raise SessionTokenError("malformed token")
        payload_b64, sig_b64 = token.split(".", 1)
        if not payload_b64 or not sig_b64:
            raise SessionTokenError("malformed token")

        try:
            expected_sig = hmac.new(
                self._secret, payload_b64.encode("ascii"), sha256,
            ).digest()
            actual_sig = _b64u_decode(sig_b64)
        except (ValueError, TypeError) as exc:
            raise SessionTokenError("malformed signature") from exc
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise SessionTokenError("invalid signature")

        try:
            payload = json.loads(_b64u_decode(payload_b64).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise SessionTokenError("malformed payload") from exc
        if not isinstance(payload, dict) or "exp" not in payload or "ip" not in payload:
            raise SessionTokenError("malformed payload")

        if payload["ip"] != ip:
            raise SessionTokenError("token bound to different ip")
        if int(payload["exp"]) < int(now.timestamp()):
            raise SessionTokenError("token expired")


def derive_secret_from_bearer(bearer: str) -> bytes:
    """Bootstrap a deterministic signing secret from the operator's bearer.

    If no dedicated ARBITER_SESSION_SECRET is provided, derive 32 bytes
    via HKDF-Extract-style hashing from the bearer. Same bearer => same
    secret across restarts, so previously-issued tokens stay valid for
    their TTL. Different bearer => different secret => old tokens reject.
    """
    if not bearer:
        raise ValueError("cannot derive secret from empty bearer")
    return sha256(b"arbiter-session-v1\x00" + bearer.encode("utf-8")).digest()
