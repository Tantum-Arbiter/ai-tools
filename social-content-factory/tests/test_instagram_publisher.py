from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from social_content_factory.instagram_publisher import (
    DEFAULT_API_BASE,
    InstagramConfigError,
    InstagramPublishError,
    InstagramPublisher,
    InstagramTimeoutError,
)
from social_content_factory.publish_plan import PublishPlan


def _make_image_plan(tmp_path: Path) -> PublishPlan:
    directory = tmp_path / "outbox" / "personal" / "weekly-build"
    directory.mkdir(parents=True)
    asset = directory / "weekly-build_1x1_abcd1234.png"
    asset.write_bytes(b"PNG")
    return PublishPlan(
        brand_key="personal",
        theme_slug="weekly-build",
        directory=directory,
        media_kind="image",
        asset_path=asset,
        caption="Shipped a renderer.",
        has_video=False,
        has_captions=True,
    )


def _make_reel_plan(tmp_path: Path) -> PublishPlan:
    directory = tmp_path / "outbox" / "personal" / "weekly-build"
    directory.mkdir(parents=True)
    asset = directory / "weekly-build_9x16_abcd1234.mp4"
    asset.write_bytes(b"MP4")
    return PublishPlan(
        brand_key="personal",
        theme_slug="weekly-build",
        directory=directory,
        media_kind="reel",
        asset_path=asset,
        caption="Shipped a renderer.",
        has_video=True,
        has_captions=True,
    )


def _make_publisher() -> InstagramPublisher:
    return InstagramPublisher(
        token="FAKE_TOKEN",
        account_id="123456",
        cdn_base_url="https://cdn.example.com/",
        poll_interval_seconds=0.0,
        timeout_seconds=2.0,
    )


class TestFromEnv:
    def test_reads_required_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
        monkeypatch.setenv("META_INSTAGRAM_ACCOUNT_ID", "acct")
        monkeypatch.setenv("MEDIA_CDN_BASE_URL", "https://cdn.example.com")

        under_test = InstagramPublisher.from_env()

        assert under_test.token == "tok"
        assert under_test.account_id == "acct"
        assert under_test.cdn_base_url == "https://cdn.example.com"

    def test_raises_when_token_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("META_INSTAGRAM_ACCOUNT_ID", "acct")
        monkeypatch.setenv("MEDIA_CDN_BASE_URL", "https://cdn.example.com")

        with pytest.raises(InstagramConfigError):
            InstagramPublisher.from_env()

    def test_raises_when_account_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
        monkeypatch.delenv("META_INSTAGRAM_ACCOUNT_ID", raising=False)
        monkeypatch.setenv("MEDIA_CDN_BASE_URL", "https://cdn.example.com")

        with pytest.raises(InstagramConfigError):
            InstagramPublisher.from_env()

    def test_raises_when_cdn_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
        monkeypatch.setenv("META_INSTAGRAM_ACCOUNT_ID", "acct")
        monkeypatch.delenv("MEDIA_CDN_BASE_URL", raising=False)

        with pytest.raises(InstagramConfigError):
            InstagramPublisher.from_env()


class TestDryRun:
    @respx.mock
    async def test_dry_run_makes_no_http_calls(self, tmp_path: Path) -> None:
        plan = _make_image_plan(tmp_path)
        under_test = _make_publisher()

        result = await under_test.publish(plan, dry_run=True)

        assert result.dry_run is True
        assert result.media_id is None
        assert result.permalink is None
        assert respx.calls.call_count == 0

    async def test_dry_run_derives_asset_url(self, tmp_path: Path) -> None:
        plan = _make_image_plan(tmp_path)
        under_test = _make_publisher()

        result = await under_test.publish(plan, dry_run=True)

        assert result.asset_url == "https://cdn.example.com/weekly-build_1x1_abcd1234.png"

    async def test_dry_run_includes_caption_preview(self, tmp_path: Path) -> None:
        plan = _make_image_plan(tmp_path)
        under_test = _make_publisher()

        result = await under_test.publish(plan, dry_run=True)

        assert "renderer" in result.caption_preview


class TestPublishImage:
    @respx.mock
    async def test_image_happy_path(self, tmp_path: Path) -> None:
        plan = _make_image_plan(tmp_path)
        under_test = _make_publisher()
        base = f"{DEFAULT_API_BASE}/123456/media"

        respx.post(base).mock(return_value=httpx.Response(200, json={"id": "container-1"}))
        respx.get(f"{DEFAULT_API_BASE}/container-1").mock(
            return_value=httpx.Response(200, json={"status_code": "FINISHED"})
        )
        respx.post(f"{DEFAULT_API_BASE}/123456/media_publish").mock(
            return_value=httpx.Response(200, json={"id": "media-9"})
        )
        respx.get(f"{DEFAULT_API_BASE}/media-9").mock(
            return_value=httpx.Response(200, json={"permalink": "https://ig.example/p/abc"})
        )

        result = await under_test.publish(plan, dry_run=False)

        assert result.dry_run is False
        assert result.media_id == "media-9"
        assert result.permalink == "https://ig.example/p/abc"

    @respx.mock
    async def test_create_container_uses_image_url_for_image(self, tmp_path: Path) -> None:
        plan = _make_image_plan(tmp_path)
        under_test = _make_publisher()
        base = f"{DEFAULT_API_BASE}/123456/media"
        create = respx.post(base).mock(
            return_value=httpx.Response(200, json={"id": "container-1"})
        )
        respx.get(f"{DEFAULT_API_BASE}/container-1").mock(
            return_value=httpx.Response(200, json={"status_code": "FINISHED"})
        )
        respx.post(f"{DEFAULT_API_BASE}/123456/media_publish").mock(
            return_value=httpx.Response(200, json={"id": "media-1"})
        )
        respx.get(f"{DEFAULT_API_BASE}/media-1").mock(
            return_value=httpx.Response(200, json={"permalink": "p"})
        )

        await under_test.publish(plan, dry_run=False)

        params = dict(create.calls.last.request.url.params)
        assert "image_url" in params
        assert params["caption"] == "Shipped a renderer."
        assert "media_type" not in params

    @respx.mock
    async def test_4xx_on_create_raises_publish_error(self, tmp_path: Path) -> None:
        plan = _make_image_plan(tmp_path)
        under_test = _make_publisher()
        respx.post(f"{DEFAULT_API_BASE}/123456/media").mock(
            return_value=httpx.Response(400, json={"error": "bad request"})
        )

        with pytest.raises(InstagramPublishError):
            await under_test.publish(plan, dry_run=False)


class TestPublishReel:
    @respx.mock
    async def test_reel_uses_reels_media_type_and_video_url(self, tmp_path: Path) -> None:
        plan = _make_reel_plan(tmp_path)
        under_test = _make_publisher()
        base = f"{DEFAULT_API_BASE}/123456/media"
        create = respx.post(base).mock(
            return_value=httpx.Response(200, json={"id": "container-2"})
        )
        respx.get(f"{DEFAULT_API_BASE}/container-2").mock(
            return_value=httpx.Response(200, json={"status_code": "FINISHED"})
        )
        respx.post(f"{DEFAULT_API_BASE}/123456/media_publish").mock(
            return_value=httpx.Response(200, json={"id": "media-2"})
        )
        respx.get(f"{DEFAULT_API_BASE}/media-2").mock(
            return_value=httpx.Response(200, json={"permalink": "p"})
        )

        await under_test.publish(plan, dry_run=False)

        params = dict(create.calls.last.request.url.params)
        assert params["media_type"] == "REELS"
        assert "video_url" in params
        assert params["share_to_feed"] == "true"


class TestProcessingPoll:
    @respx.mock
    async def test_error_status_raises(self, tmp_path: Path) -> None:
        plan = _make_image_plan(tmp_path)
        under_test = _make_publisher()
        respx.post(f"{DEFAULT_API_BASE}/123456/media").mock(
            return_value=httpx.Response(200, json={"id": "container-x"})
        )
        respx.get(f"{DEFAULT_API_BASE}/container-x").mock(
            return_value=httpx.Response(200, json={"status_code": "ERROR"})
        )

        with pytest.raises(InstagramPublishError):
            await under_test.publish(plan, dry_run=False)

    @respx.mock
    async def test_in_progress_then_finished_succeeds(self, tmp_path: Path) -> None:
        plan = _make_image_plan(tmp_path)
        under_test = _make_publisher()
        respx.post(f"{DEFAULT_API_BASE}/123456/media").mock(
            return_value=httpx.Response(200, json={"id": "container-p"})
        )
        respx.get(f"{DEFAULT_API_BASE}/container-p").mock(
            side_effect=[
                httpx.Response(200, json={"status_code": "IN_PROGRESS"}),
                httpx.Response(200, json={"status_code": "FINISHED"}),
            ]
        )
        respx.post(f"{DEFAULT_API_BASE}/123456/media_publish").mock(
            return_value=httpx.Response(200, json={"id": "media-p"})
        )
        respx.get(f"{DEFAULT_API_BASE}/media-p").mock(
            return_value=httpx.Response(200, json={"permalink": "p"})
        )

        result = await under_test.publish(plan, dry_run=False)

        assert result.media_id == "media-p"

    @respx.mock
    async def test_polling_timeout_raises(self, tmp_path: Path) -> None:
        plan = _make_image_plan(tmp_path)
        under_test = InstagramPublisher(
            token="t",
            account_id="123456",
            cdn_base_url="https://cdn.example.com/",
            poll_interval_seconds=0.01,
            timeout_seconds=0.02,
        )
        respx.post(f"{DEFAULT_API_BASE}/123456/media").mock(
            return_value=httpx.Response(200, json={"id": "container-t"})
        )
        respx.get(f"{DEFAULT_API_BASE}/container-t").mock(
            return_value=httpx.Response(200, json={"status_code": "IN_PROGRESS"})
        )

        with pytest.raises(InstagramTimeoutError):
            await under_test.publish(plan, dry_run=False)
