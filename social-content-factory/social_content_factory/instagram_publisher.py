from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Final

import httpx

from social_content_factory.publish_plan import PublishPlan

logger = logging.getLogger(__name__)

DEFAULT_API_BASE: Final[str] = "https://graph.instagram.com/v21.0"
DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 5.0
DEFAULT_TIMEOUT_SECONDS: Final[float] = 300.0
DEFAULT_HTTP_TIMEOUT_SECONDS: Final[float] = 30.0
CAPTION_PREVIEW_LEN: Final[int] = 120


class InstagramError(Exception):
    """Base error for the Instagram publisher."""


class InstagramConfigError(InstagramError):
    """Raised when required env vars are missing."""


class InstagramPublishError(InstagramError):
    """Raised when the Graph API returns a failure status."""


class InstagramTimeoutError(InstagramError):
    """Raised when container processing does not finish in time."""


@dataclass(frozen=True)
class PublishResult:
    dry_run: bool
    media_kind: str
    asset_url: str
    caption_preview: str
    media_id: str | None
    permalink: str | None


class InstagramPublisher:
    def __init__(
        self,
        *,
        token: str,
        account_id: str,
        cdn_base_url: str,
        api_base: str = DEFAULT_API_BASE,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self.token = token
        self.account_id = account_id
        self.cdn_base_url = cdn_base_url
        self.api_base = api_base.rstrip("/")
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.http_timeout_seconds = http_timeout_seconds

    @classmethod
    def from_env(cls) -> "InstagramPublisher":
        token = os.environ.get("META_ACCESS_TOKEN")
        account_id = os.environ.get("META_INSTAGRAM_ACCOUNT_ID")
        cdn_base_url = os.environ.get("MEDIA_CDN_BASE_URL")
        missing = [
            name
            for name, value in (
                ("META_ACCESS_TOKEN", token),
                ("META_INSTAGRAM_ACCOUNT_ID", account_id),
                ("MEDIA_CDN_BASE_URL", cdn_base_url),
            )
            if not value
        ]
        if missing:
            raise InstagramConfigError(
                "missing required Instagram env vars: " + ", ".join(missing)
            )
        assert token and account_id and cdn_base_url
        return cls(token=token, account_id=account_id, cdn_base_url=cdn_base_url)

    async def publish(self, plan: PublishPlan, *, dry_run: bool) -> PublishResult:
        asset_url = self._asset_url(plan)
        caption_preview = plan.caption[:CAPTION_PREVIEW_LEN]

        if dry_run:
            logger.info(
                "instagram dry-run: brand=%s theme=%s kind=%s asset=%s caption_len=%d",
                plan.brand_key,
                plan.theme_slug,
                plan.media_kind,
                plan.asset_path.name,
                len(plan.caption),
            )
            return PublishResult(
                dry_run=True,
                media_kind=plan.media_kind,
                asset_url=asset_url,
                caption_preview=caption_preview,
                media_id=None,
                permalink=None,
            )

        async with httpx.AsyncClient(timeout=self.http_timeout_seconds) as client:
            container_id = await self._create_container(client, plan, asset_url)
            await self._wait_for_processing(client, container_id)
            media_id = await self._publish_container(client, container_id)
            permalink = await self._get_permalink(client, media_id)

        logger.info(
            "instagram published: brand=%s theme=%s media_id=%s",
            plan.brand_key,
            plan.theme_slug,
            media_id,
        )
        return PublishResult(
            dry_run=False,
            media_kind=plan.media_kind,
            asset_url=asset_url,
            caption_preview=caption_preview,
            media_id=media_id,
            permalink=permalink,
        )

    def _asset_url(self, plan: PublishPlan) -> str:
        return f"{self.cdn_base_url.rstrip('/')}/{plan.asset_path.name}"

    async def _create_container(
        self, client: httpx.AsyncClient, plan: PublishPlan, asset_url: str
    ) -> str:
        params: dict[str, str] = {
            "caption": plan.caption,
            "access_token": self.token,
        }
        if plan.media_kind == "reel":
            params["media_type"] = "REELS"
            params["video_url"] = asset_url
            params["share_to_feed"] = "true"
        else:
            params["image_url"] = asset_url

        response = await client.post(
            f"{self.api_base}/{self.account_id}/media", params=params
        )
        data = self._json_or_raise(response, action="create container")
        container_id = data.get("id")
        if not container_id:
            raise InstagramPublishError(f"missing container id in response: {data}")
        return str(container_id)

    async def _wait_for_processing(
        self, client: httpx.AsyncClient, container_id: str
    ) -> None:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            response = await client.get(
                f"{self.api_base}/{container_id}",
                params={"fields": "status_code,status", "access_token": self.token},
            )
            data = self._json_or_raise(response, action="poll container")
            status = str(data.get("status_code", ""))
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise InstagramPublishError(
                    f"container processing failed: {data}"
                )
            if time.monotonic() >= deadline:
                raise InstagramTimeoutError(
                    f"container {container_id} did not finish in {self.timeout_seconds}s"
                )
            await asyncio.sleep(self.poll_interval_seconds)

    async def _publish_container(
        self, client: httpx.AsyncClient, container_id: str
    ) -> str:
        response = await client.post(
            f"{self.api_base}/{self.account_id}/media_publish",
            params={"creation_id": container_id, "access_token": self.token},
        )
        data = self._json_or_raise(response, action="publish container")
        media_id = data.get("id")
        if not media_id:
            raise InstagramPublishError(f"missing media id in response: {data}")
        return str(media_id)

    async def _get_permalink(
        self, client: httpx.AsyncClient, media_id: str
    ) -> str:
        response = await client.get(
            f"{self.api_base}/{media_id}",
            params={"fields": "permalink", "access_token": self.token},
        )
        data = self._json_or_raise(response, action="fetch permalink")
        return str(data.get("permalink", ""))

    @staticmethod
    def _json_or_raise(response: httpx.Response, *, action: str) -> dict[str, Any]:
        if response.status_code >= 400:
            raise InstagramPublishError(
                f"{action} failed: HTTP {response.status_code} {response.text}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise InstagramPublishError(f"{action} returned non-JSON body") from exc
        if not isinstance(payload, dict):
            raise InstagramPublishError(f"{action} returned non-object body: {payload!r}")
        return payload
