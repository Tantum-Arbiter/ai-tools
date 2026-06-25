"""Tamper-proof safety gate for Day Job integrations.

Defence-in-depth:
  Layer 1 — Token scoping (external, not in this file)
  Layer 2 — Operation allowlist (this file: OPERATION_ALLOWLIST)
  Layer 3 — Mutation gate (this file: ConfirmationSigner)
  Layer 4 — Audit log (this file: SafetyGate.audit)

No generic query/execute methods exist. The LLM never touches tokens.
Even if every software layer is bypassed, token scoping (Layer 1) limits
blast radius to sprint iteration field changes — trivially reversible.
"""
from __future__ import annotations

import enum
import hmac
import json
import threading
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable

UtcTimestamp = Callable[[], float]


class Tier(enum.Enum):
    READ = "read"
    GATED_WRITE = "gated_write"
    BLOCKED = "blocked"


class Service(enum.Enum):
    MONDAY = "monday"
    GITHUB = "github"
    SLACK = "slack"
    CLARITY = "clarity"
    SHAREPOINT = "sharepoint"


@dataclass(frozen=True)
class Operation:
    service: Service
    name: str
    tier: Tier


OPERATION_ALLOWLIST: dict[tuple[Service, str], Tier] = {
    # ── Monday.com — PERMANENTLY READ ONLY ──
    (Service.MONDAY, "get_boards"): Tier.READ,
    (Service.MONDAY, "get_items"): Tier.READ,
    (Service.MONDAY, "get_updates"): Tier.READ,
    (Service.MONDAY, "search_items"): Tier.READ,
    # ── GitHub — read-only scraper (no edit/delete/close methods exist) ──
    (Service.GITHUB, "search_epics"): Tier.READ,
    (Service.GITHUB, "search_cards"): Tier.READ,
    (Service.GITHUB, "get_sprint_items"): Tier.READ,
    # ── Slack — read + gated send ──
    (Service.SLACK, "get_channel_history"): Tier.READ,
    (Service.SLACK, "send_message"): Tier.GATED_WRITE,
    # ── Clarity — read + gated fill/submit ──
    (Service.CLARITY, "get_timesheet"): Tier.READ,
    (Service.CLARITY, "fill_timesheet"): Tier.GATED_WRITE,
    (Service.CLARITY, "submit_timesheet"): Tier.GATED_WRITE,
    # ── SharePoint/PPT — read + gated upload ──
    (Service.SHAREPOINT, "download_ppt"): Tier.READ,
    (Service.SHAREPOINT, "upload_ppt"): Tier.GATED_WRITE,
}


class SafetyError(Exception):
    pass


class OperationBlockedError(SafetyError):
    pass


class ConfirmationRequiredError(SafetyError):
    pass


class InvalidConfirmationError(SafetyError):
    pass


_MIN_SECRET_BYTES = 32
_CONFIRM_TTL_SECONDS = 120


class ConfirmationSigner:
    """HMAC-signed one-time confirmation tokens.

    Only the server can mint these. The LLM cannot forge them.
    Each token is bound to a specific operation + parameters + expiry.
    """

    def __init__(self, secret: bytes) -> None:
        if len(secret) < _MIN_SECRET_BYTES:
            raise ValueError(
                f"secret must be >= {_MIN_SECRET_BYTES} bytes; got {len(secret)}",
            )
        self._secret = secret

    def mint(
        self,
        *,
        service: Service,
        operation: str,
        params_hash: str,
        now: float,
    ) -> str:
        payload = json.dumps(
            {
                "svc": service.value,
                "op": operation,
                "ph": params_hash,
                "exp": int(now) + _CONFIRM_TTL_SECONDS,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        sig = hmac.new(self._secret, payload.encode(), sha256).hexdigest()
        return f"{payload}|{sig}"

    def verify(
        self,
        token: str,
        *,
        service: Service,
        operation: str,
        params_hash: str,
        now: float,
    ) -> None:
        if "|" not in token:
            raise InvalidConfirmationError("malformed confirmation token")
        payload_str, sig = token.rsplit("|", 1)
        expected = hmac.new(self._secret, payload_str.encode(), sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise InvalidConfirmationError("invalid confirmation signature")
        try:
            payload = json.loads(payload_str)
        except (json.JSONDecodeError, ValueError) as exc:
            raise InvalidConfirmationError("malformed payload") from exc
        if payload.get("svc") != service.value:
            raise InvalidConfirmationError("token bound to different service")
        if payload.get("op") != operation:
            raise InvalidConfirmationError("token bound to different operation")
        if payload.get("ph") != params_hash:
            raise InvalidConfirmationError("token bound to different parameters")
        if payload.get("exp", 0) < int(now):
            raise InvalidConfirmationError("confirmation token expired")


def hash_params(params: dict[str, object]) -> str:
    raw = json.dumps(params, separators=(",", ":"), sort_keys=True)
    return sha256(raw.encode()).hexdigest()[:16]


class SafetyAuditLog:
    """Append-only JSONL log of every Day Job operation (reads and writes)."""

    def __init__(self, log_dir: Path, clock: UtcTimestamp | None = None) -> None:
        self._dir = Path(log_dir)
        self._clock = clock or time.time
        self._lock = threading.Lock()
        self._dir.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        service: str,
        operation: str,
        tier: str,
        params: dict[str, object] | None = None,
        result: str = "ok",
        detail: str = "",
    ) -> dict[str, object]:
        now = self._clock()
        from datetime import datetime, timezone

        ts = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")
        row: dict[str, object] = {
            "ts": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "service": service,
            "operation": operation,
            "tier": tier,
            "result": result,
        }
        if detail:
            row["detail"] = detail
        if params:
            row["params"] = params
        target = self._dir / f"dayjob-audit-{ts}.jsonl"
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with target.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return row


class SafetyGate:
    """Central enforcement point for all Day Job operations.

    Every client method calls gate.check() before doing anything.
    - READ operations pass through.
    - GATED_WRITE operations require a valid confirmation token.
    - Anything not in the allowlist is BLOCKED — hard stop.
    """

    def __init__(
        self,
        signer: ConfirmationSigner,
        audit: SafetyAuditLog,
        clock: UtcTimestamp | None = None,
    ) -> None:
        self._signer = signer
        self._audit = audit
        self._clock = clock or time.time

    def check(
        self,
        *,
        service: Service,
        operation: str,
        params: dict[str, object] | None = None,
        confirmation_token: str | None = None,
    ) -> None:
        key = (service, operation)
        tier = OPERATION_ALLOWLIST.get(key)

        if tier is None:
            self._audit.record(
                service=service.value,
                operation=operation,
                tier="blocked",
                params=params,
                result="blocked",
                detail="operation not in allowlist",
            )
            raise OperationBlockedError(
                f"Operation '{operation}' on {service.value} is not permitted. "
                f"Only allowlisted operations can execute."
            )

        if tier == Tier.BLOCKED:
            self._audit.record(
                service=service.value,
                operation=operation,
                tier="blocked",
                params=params,
                result="blocked",
                detail="operation explicitly blocked",
            )
            raise OperationBlockedError(
                f"Operation '{operation}' on {service.value} is explicitly blocked."
            )

        if tier == Tier.READ:
            self._audit.record(
                service=service.value,
                operation=operation,
                tier="read",
                params=params,
                result="ok",
            )
            return

        if tier == Tier.GATED_WRITE:
            if confirmation_token is None:
                self._audit.record(
                    service=service.value,
                    operation=operation,
                    tier="gated_write",
                    params=params,
                    result="needs_confirmation",
                )
                raise ConfirmationRequiredError(
                    f"Operation '{operation}' on {service.value} requires "
                    f"human confirmation. Use the preview endpoint first."
                )
            ph = hash_params(params or {})
            try:
                self._signer.verify(
                    confirmation_token,
                    service=service,
                    operation=operation,
                    params_hash=ph,
                    now=self._clock(),
                )
            except InvalidConfirmationError:
                self._audit.record(
                    service=service.value,
                    operation=operation,
                    tier="gated_write",
                    params=params,
                    result="invalid_token",
                    detail="confirmation token rejected",
                )
                raise
            self._audit.record(
                service=service.value,
                operation=operation,
                tier="gated_write",
                params=params,
                result="confirmed",
                detail="valid confirmation token",
            )
            return

    def mint_confirmation(
        self,
        *,
        service: Service,
        operation: str,
        params: dict[str, object] | None = None,
    ) -> str:
        key = (service, operation)
        tier = OPERATION_ALLOWLIST.get(key)
        if tier != Tier.GATED_WRITE:
            raise SafetyError(
                f"Cannot mint confirmation for '{operation}' on {service.value} — "
                f"not a gated write operation."
            )
        ph = hash_params(params or {})
        return self._signer.mint(
            service=service,
            operation=operation,
            params_hash=ph,
            now=self._clock(),
        )

