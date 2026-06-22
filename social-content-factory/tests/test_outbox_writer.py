from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from social_content_factory.outbox_writer import (
    OutboxWriteResult,
    OutboxWriterError,
    current_git_sha,
    write_render,
)

FIXED_TS = datetime(2026, 6, 22, 14, 30, 0, tzinfo=timezone.utc)


def _write(
    tmp_path: Path,
    *,
    aspect_ratio: str = "1x1",
    prompt_hash: str = "092667cad1f9a70a",
    extra: dict | None = None,
    git_sha: str | None = None,
) -> OutboxWriteResult:
    return write_render(
        outbox_root=tmp_path / "outbox",
        brand_key="personal",
        theme_slug="weekly-build",
        aspect_ratio=aspect_ratio,
        image_bytes=b"\x89PNG\r\n\x1a\nFAKE",
        seed=3084366091,
        prompt_hash=prompt_hash,
        checkpoint="sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors",
        timestamp=FIXED_TS,
        git_sha=git_sha,
        extra=extra,
    )


class TestWriteRender:
    def test_creates_dated_brand_theme_directory(self, tmp_path: Path) -> None:
        result = _write(tmp_path)

        assert result.directory == tmp_path / "outbox" / "2026-06-22" / "personal" / "weekly-build"
        assert result.directory.is_dir()

    def test_image_path_uses_slug_aspect_and_short_hash(self, tmp_path: Path) -> None:
        result = _write(tmp_path)

        assert result.image_path.name == "weekly-build_1x1_092667ca.png"

    def test_writes_image_bytes(self, tmp_path: Path) -> None:
        result = _write(tmp_path)

        assert result.image_path.read_bytes() == b"\x89PNG\r\n\x1a\nFAKE"

    def test_writes_metadata_json_sibling(self, tmp_path: Path) -> None:
        result = _write(tmp_path)

        assert result.metadata_path.name == "weekly-build_1x1_092667ca.metadata.json"
        assert result.metadata_path.parent == result.image_path.parent

    def test_metadata_includes_required_fields(self, tmp_path: Path) -> None:
        result = _write(tmp_path)
        meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))

        assert meta["schema_version"] == 1
        assert meta["brand"] == "personal"
        assert meta["theme"] == "weekly-build"
        assert meta["aspect_ratio"] == "1x1"
        assert meta["seed"] == 3084366091
        assert meta["prompt_hash"] == "092667cad1f9a70a"
        assert meta["checkpoint"] == "sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors"
        assert meta["timestamp"] == "2026-06-22T14:30:00+00:00"

    def test_metadata_includes_git_sha_when_provided(self, tmp_path: Path) -> None:
        result = _write(tmp_path, git_sha="deadbeefcafe")

        meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        assert meta["git_sha"] == "deadbeefcafe"

    def test_metadata_git_sha_null_when_omitted(self, tmp_path: Path) -> None:
        result = _write(tmp_path)

        meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        assert meta["git_sha"] is None

    def test_metadata_does_not_include_full_prompt(self, tmp_path: Path) -> None:
        result = _write(tmp_path, extra={"prompt_id": "abc-123"})

        meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        assert "prompt" not in meta
        assert "negative_prompt" not in meta

    def test_extra_fields_merged_into_metadata(self, tmp_path: Path) -> None:
        result = _write(tmp_path, extra={"prompt_id": "abc-123", "comfyui_subfolder": ""})

        meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        assert meta["extra"] == {"prompt_id": "abc-123", "comfyui_subfolder": ""}

    def test_different_aspects_do_not_collide(self, tmp_path: Path) -> None:
        r1 = _write(tmp_path, aspect_ratio="1x1")
        r2 = _write(tmp_path, aspect_ratio="9x16")

        assert r1.image_path != r2.image_path
        assert r1.image_path.exists() and r2.image_path.exists()

    def test_different_prompt_hashes_do_not_collide(self, tmp_path: Path) -> None:
        r1 = _write(tmp_path, prompt_hash="aaaaaaaabbbbcccc")
        r2 = _write(tmp_path, prompt_hash="ddddddddeeeeffff")

        assert r1.image_path.name == "weekly-build_1x1_aaaaaaaa.png"
        assert r2.image_path.name == "weekly-build_1x1_dddddddd.png"

    def test_idempotent_overwrite(self, tmp_path: Path) -> None:
        _write(tmp_path)
        result = _write(tmp_path)

        assert result.image_path.read_bytes() == b"\x89PNG\r\n\x1a\nFAKE"

    def test_no_tmp_files_left_behind(self, tmp_path: Path) -> None:
        result = _write(tmp_path)

        leftovers = list(result.directory.glob(".*.tmp.*"))
        assert leftovers == []

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        nested = tmp_path / "deeply" / "nested" / "outbox"
        write_render(
            outbox_root=nested,
            brand_key="personal",
            theme_slug="weekly-build",
            aspect_ratio="1x1",
            image_bytes=b"x",
            seed=1,
            prompt_hash="0" * 16,
            checkpoint="m",
            timestamp=FIXED_TS,
        )

        assert (nested / "2026-06-22" / "personal" / "weekly-build").is_dir()

    def test_invalid_prompt_hash_raises(self, tmp_path: Path) -> None:
        with pytest.raises(OutboxWriterError, match="prompt_hash"):
            _write(tmp_path, prompt_hash="short")

    def test_default_timestamp_is_utc_now(self, tmp_path: Path) -> None:
        result = write_render(
            outbox_root=tmp_path / "outbox",
            brand_key="personal",
            theme_slug="weekly-build",
            aspect_ratio="1x1",
            image_bytes=b"x",
            seed=1,
            prompt_hash="0" * 16,
            checkpoint="m",
        )

        meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        assert meta["timestamp"].endswith("+00:00")


class TestCurrentGitSha:
    def test_returns_sha_when_in_git_repo(self) -> None:
        result = current_git_sha(Path(__file__).resolve().parent.parent.parent)

        assert result is None or (isinstance(result, str) and len(result) == 40)

    def test_returns_none_when_not_a_repo(self, tmp_path: Path) -> None:
        assert current_git_sha(tmp_path) is None
