from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

DEFAULT_API_BASE: Final[str] = "https://api.github.com"
DEFAULT_PER_PAGE: Final[int] = 100
DEFAULT_HTTP_TIMEOUT_SECONDS: Final[float] = 30.0
MAX_PAGES: Final[int] = 10

NEXT_LINK_RE = re.compile(r"<(?P<url>[^>]+)>;\s*rel=\"next\"")


class GitHubReleasesError(Exception):
    """Raised when the GitHub releases endpoint fails or returns an unexpected payload."""


@dataclass(frozen=True)
class RawIngestItem:
    source: str
    tag: str
    title: str
    body: str
    url: str
    published_at: datetime


class GitHubReleasesClient:
    def __init__(
        self,
        *,
        token: str | None,
        api_base: str = DEFAULT_API_BASE,
        http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.http_timeout_seconds = http_timeout_seconds
        self.headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    @classmethod
    def from_env(cls) -> "GitHubReleasesClient":
        return cls(token=os.environ.get("GITHUB_TOKEN") or None)

    async def fetch_releases(
        self,
        repo: str,
        *,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[RawIngestItem]:
        url: str | None = f"{self.api_base}/repos/{repo}/releases"
        params: dict[str, str] | None = {"per_page": str(DEFAULT_PER_PAGE)}
        items: list[RawIngestItem] = []
        pages = 0

        async with httpx.AsyncClient(timeout=self.http_timeout_seconds) as client:
            while url is not None and pages < MAX_PAGES:
                response = await client.get(url, params=params, headers=self.headers)
                if response.status_code >= 400:
                    raise GitHubReleasesError(
                        f"github releases fetch failed for {repo}: "
                        f"HTTP {response.status_code} {response.text[:200]}"
                    )
                payload = self._parse_payload(response, repo)
                for entry in payload:
                    item = self._coerce_item(entry)
                    if item is None:
                        continue
                    if since is not None and item.published_at < since:
                        continue
                    items.append(item)
                    if limit is not None and len(items) >= limit:
                        return items

                url = self._next_url(response.headers.get("Link"))
                params = None
                pages += 1

        return items

    @staticmethod
    def _parse_payload(response: httpx.Response, repo: str) -> list[dict[str, Any]]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubReleasesError(
                f"github returned non-JSON for {repo}"
            ) from exc
        if not isinstance(payload, list):
            raise GitHubReleasesError(
                f"github returned non-list payload for {repo}: {payload!r}"
            )
        return payload

    @staticmethod
    def _coerce_item(entry: dict[str, Any]) -> RawIngestItem | None:
        if not isinstance(entry, dict):
            return None
        if entry.get("draft") or entry.get("prerelease"):
            return None
        tag = entry.get("tag_name")
        published = entry.get("published_at")
        if not tag or not published:
            return None
        try:
            published_at = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        except ValueError:
            return None
        return RawIngestItem(
            source="github",
            tag=str(tag),
            title=str(entry.get("name") or tag),
            body=str(entry.get("body") or ""),
            url=str(entry.get("html_url") or ""),
            published_at=published_at,
        )

    @staticmethod
    def _next_url(link_header: str | None) -> str | None:
        if not link_header:
            return None
        match = NEXT_LINK_RE.search(link_header)
        return match.group("url") if match else None
