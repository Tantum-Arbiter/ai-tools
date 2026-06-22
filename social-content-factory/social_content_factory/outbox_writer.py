from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

SCHEMA_VERSION: Final[int] = 1
PROMPT_HASH_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{16}$")
SHORT_HASH_LEN: Final[int] = 8


class OutboxWriterError(Exception):
    """Raised when the outbox writer cannot validate inputs or write files."""


@dataclass(frozen=True)
class OutboxWriteResult:
    image_path: Path
    metadata_path: Path
    directory: Path


@dataclass(frozen=True)
class CaptionsWriteResult:
    path: Path
    directory: Path


def write_render(
    *,
    outbox_root: Path,
    brand_key: str,
    theme_slug: str,
    aspect_ratio: str,
    image_bytes: bytes,
    seed: int,
    prompt_hash: str,
    checkpoint: str,
    timestamp: datetime | None = None,
    git_sha: str | None = None,
    extra: dict | None = None,
) -> OutboxWriteResult:
    if not PROMPT_HASH_PATTERN.match(prompt_hash):
        raise OutboxWriterError(
            f"prompt_hash must be 16 lowercase hex chars, got {prompt_hash!r}"
        )

    ts = timestamp or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    directory = outbox_root / ts.strftime("%Y-%m-%d") / brand_key / theme_slug
    directory.mkdir(parents=True, exist_ok=True)

    short_hash = prompt_hash[:SHORT_HASH_LEN]
    base = f"{theme_slug}_{aspect_ratio}_{short_hash}"
    image_path = directory / f"{base}.png"
    metadata_path = directory / f"{base}.metadata.json"

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "brand": brand_key,
        "theme": theme_slug,
        "aspect_ratio": aspect_ratio,
        "seed": seed,
        "prompt_hash": prompt_hash,
        "checkpoint": checkpoint,
        "git_sha": git_sha,
        "timestamp": ts.isoformat(),
        "extra": extra or {},
    }

    _atomic_write_bytes(image_path, image_bytes)
    _atomic_write_bytes(
        metadata_path,
        (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )

    return OutboxWriteResult(
        image_path=image_path,
        metadata_path=metadata_path,
        directory=directory,
    )


def write_captions(
    *,
    outbox_root: Path,
    brand_key: str,
    theme_slug: str,
    instagram: str,
    x: str,
    model: str,
    prompt_hash: str,
    timestamp: datetime | None = None,
) -> CaptionsWriteResult:
    if not PROMPT_HASH_PATTERN.match(prompt_hash):
        raise OutboxWriterError(
            f"prompt_hash must be 16 lowercase hex chars, got {prompt_hash!r}"
        )
    if not instagram.strip() or not x.strip():
        raise OutboxWriterError("instagram and x captions must both be non-empty")

    ts = timestamp or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    directory = outbox_root / ts.strftime("%Y-%m-%d") / brand_key / theme_slug
    directory.mkdir(parents=True, exist_ok=True)

    short_hash = prompt_hash[:SHORT_HASH_LEN]
    path = directory / f"{theme_slug}_{short_hash}_captions.md"

    body = (
        f"# {theme_slug}\n\n"
        f"## Instagram\n\n{instagram.strip()}\n\n"
        f"## X\n\n{x.strip()}\n\n"
        f"---\n"
        f"brand: {brand_key}\n"
        f"theme: {theme_slug}\n"
        f"model: {model}\n"
        f"prompt_hash: {prompt_hash}\n"
        f"generated_at: {ts.isoformat()}\n"
    )
    _atomic_write_bytes(path, body.encode("utf-8"))

    return CaptionsWriteResult(path=path, directory=directory)


def current_git_sha(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha if len(sha) == 40 else None


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp.{uuid.uuid4().hex}")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
