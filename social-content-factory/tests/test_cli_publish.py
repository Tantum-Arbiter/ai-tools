from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from social_content_factory import cli
from social_content_factory.instagram_publisher import (
    InstagramPublishError,
    PublishResult,
)
from social_content_factory.publish_plan import PublishPlan

runner = CliRunner()


def _make_outbox(tmp_path: Path, brand: str = "personal", slug: str = "weekly-build") -> Path:
    directory = tmp_path / "outbox" / "2026-06-22" / brand / slug
    directory.mkdir(parents=True)
    (directory / f"{slug}_1x1_abcd1234.png").write_bytes(b"PNG")
    body = (
        f"# {slug}\n\n## Instagram\n\nShipped a renderer.\n\n## X\n\nShipped.\n\n---\n"
        f"brand: {brand}\ntheme: {slug}\n"
    )
    (directory / f"{slug}_abcd1234_captions.md").write_text(body, encoding="utf-8")
    return directory


def _fake_dry_run_result(plan: PublishPlan) -> PublishResult:
    return PublishResult(
        dry_run=True,
        media_kind=plan.media_kind,
        asset_url=f"https://cdn.example.com/{plan.asset_path.name}",
        caption_preview=plan.caption[:120],
        media_id=None,
        permalink=None,
    )


def _fake_live_result(plan: PublishPlan) -> PublishResult:
    return PublishResult(
        dry_run=False,
        media_kind=plan.media_kind,
        asset_url=f"https://cdn.example.com/{plan.asset_path.name}",
        caption_preview=plan.caption[:120],
        media_id="media-1",
        permalink="https://ig.example/p/abc",
    )


@pytest.fixture
def publisher_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("META_INSTAGRAM_ACCOUNT_ID", "acct")
    monkeypatch.setenv("MEDIA_CDN_BASE_URL", "https://cdn.example.com")


class TestPublishCommand:
    def test_help_lists_publish_command(self) -> None:
        result = runner.invoke(cli.app, ["--help"])

        assert result.exit_code == 0
        assert "publish" in result.stdout

    def test_publish_help_lists_flags(self) -> None:
        result = runner.invoke(cli.app, ["publish", "--help"])

        assert result.exit_code == 0
        assert "--platform" in result.stdout
        assert "--confirm" in result.stdout
        assert "--prefer-image" in result.stdout

    def test_missing_directory_arg_exits_nonzero(self) -> None:
        result = runner.invoke(cli.app, ["publish"])

        assert result.exit_code != 0

    def test_default_is_dry_run(
        self, publisher_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        directory = _make_outbox(tmp_path)
        captured: dict[str, object] = {}

        async def fake_publish(self, plan: PublishPlan, *, dry_run: bool) -> PublishResult:
            captured["dry_run"] = dry_run
            captured["plan"] = plan
            return _fake_dry_run_result(plan)

        monkeypatch.setattr(
            "social_content_factory.instagram_publisher.InstagramPublisher.publish",
            fake_publish,
        )

        result = runner.invoke(cli.app, ["publish", str(directory)])

        assert result.exit_code == 0, result.stdout
        assert captured["dry_run"] is True
        assert "dry-run" in result.stdout.lower()

    def test_confirm_flag_runs_live_publish(
        self, publisher_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        directory = _make_outbox(tmp_path)
        captured: dict[str, object] = {}

        async def fake_publish(self, plan: PublishPlan, *, dry_run: bool) -> PublishResult:
            captured["dry_run"] = dry_run
            return _fake_live_result(plan)

        monkeypatch.setattr(
            "social_content_factory.instagram_publisher.InstagramPublisher.publish",
            fake_publish,
        )
        monkeypatch.setattr(
            "social_content_factory.cli._load_brand_for_publish",
            lambda _key: _BRAND_AUTO_PUBLISH_ALLOWED,
        )

        result = runner.invoke(cli.app, ["publish", str(directory), "--confirm"])

        assert result.exit_code == 0, result.stdout
        assert captured["dry_run"] is False
        assert "media-1" in result.stdout

    def test_confirm_without_allow_auto_publish_refuses(
        self, publisher_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        directory = _make_outbox(tmp_path)
        called = AsyncMock()
        monkeypatch.setattr(
            "social_content_factory.instagram_publisher.InstagramPublisher.publish",
            called,
        )

        result = runner.invoke(cli.app, ["publish", str(directory), "--confirm"])

        assert result.exit_code != 0
        assert "allow_auto_publish" in (result.stdout + (result.stderr or ""))
        called.assert_not_awaited()

    def test_unknown_platform_exits_nonzero(
        self, publisher_env: None, tmp_path: Path
    ) -> None:
        directory = _make_outbox(tmp_path)

        result = runner.invoke(
            cli.app, ["publish", str(directory), "--platform", "tiktok"]
        )

        assert result.exit_code != 0

    def test_prefer_image_forces_image_mode(
        self, publisher_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        directory = _make_outbox(tmp_path)
        (directory / "weekly-build_9x16_abcd1234.mp4").write_bytes(b"MP4")
        captured: dict[str, object] = {}

        async def fake_publish(self, plan: PublishPlan, *, dry_run: bool) -> PublishResult:
            captured["plan"] = plan
            return _fake_dry_run_result(plan)

        monkeypatch.setattr(
            "social_content_factory.instagram_publisher.InstagramPublisher.publish",
            fake_publish,
        )

        result = runner.invoke(
            cli.app, ["publish", str(directory), "--prefer-image"]
        )

        assert result.exit_code == 0, result.stdout
        plan: PublishPlan = captured["plan"]  # type: ignore[assignment]
        assert plan.media_kind == "image"

    def test_publish_error_exits_nonzero(
        self, publisher_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        directory = _make_outbox(tmp_path)

        async def boom(self, plan: PublishPlan, *, dry_run: bool) -> PublishResult:
            raise InstagramPublishError("boom")

        monkeypatch.setattr(
            "social_content_factory.instagram_publisher.InstagramPublisher.publish",
            boom,
        )
        monkeypatch.setattr(
            "social_content_factory.cli._load_brand_for_publish",
            lambda _key: _BRAND_AUTO_PUBLISH_ALLOWED,
        )

        result = runner.invoke(cli.app, ["publish", str(directory), "--confirm"])

        assert result.exit_code != 0


class _AllowAutoPublishStub:
    allow_auto_publish = True


_BRAND_AUTO_PUBLISH_ALLOWED = _AllowAutoPublishStub()
