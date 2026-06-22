from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from social_content_factory.ingest.github_releases import (
    DEFAULT_API_BASE,
    GitHubReleasesClient,
    GitHubReleasesError,
    RawIngestItem,
)


def _release_payload(tag: str, published: str, body: str = "Notes") -> dict:
    return {
        "tag_name": tag,
        "name": f"Release {tag}",
        "body": body,
        "published_at": published,
        "html_url": f"https://github.com/owner/repo/releases/tag/{tag}",
        "draft": False,
        "prerelease": False,
    }


class TestGitHubReleasesClientInit:
    def test_uses_token_auth_header_when_provided(self) -> None:
        under_test = GitHubReleasesClient(token="ghp_test")

        assert under_test.headers["Authorization"] == "Bearer ghp_test"
        assert under_test.headers["Accept"].startswith("application/vnd.github")

    def test_omits_auth_header_when_no_token(self) -> None:
        under_test = GitHubReleasesClient(token=None)

        assert "Authorization" not in under_test.headers

    def test_from_env_reads_github_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_env")

        under_test = GitHubReleasesClient.from_env()

        assert under_test.headers["Authorization"] == "Bearer ghp_env"

    def test_from_env_no_token_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        under_test = GitHubReleasesClient.from_env()

        assert "Authorization" not in under_test.headers


class TestFetchReleases:
    @respx.mock
    async def test_returns_parsed_items(self) -> None:
        respx.get(f"{DEFAULT_API_BASE}/repos/owner/repo/releases").mock(
            return_value=httpx.Response(
                200,
                json=[
                    _release_payload("v1.0", "2026-06-20T10:00:00Z", "First"),
                    _release_payload("v0.9", "2026-06-10T10:00:00Z", "Earlier"),
                ],
            )
        )

        under_test = GitHubReleasesClient(token=None)
        items = await under_test.fetch_releases("owner/repo")

        assert len(items) == 2
        assert all(isinstance(item, RawIngestItem) for item in items)
        assert items[0].tag == "v1.0"
        assert items[0].url == "https://github.com/owner/repo/releases/tag/v1.0"
        assert items[0].body == "First"
        assert items[0].source == "github"
        assert items[0].published_at.tzinfo is not None

    @respx.mock
    async def test_drops_drafts_and_prereleases(self) -> None:
        payload = [
            _release_payload("v1.0", "2026-06-20T10:00:00Z"),
            {**_release_payload("v0.9-rc", "2026-06-19T10:00:00Z"), "prerelease": True},
            {**_release_payload("v0.8", "2026-06-18T10:00:00Z"), "draft": True},
        ]
        respx.get(f"{DEFAULT_API_BASE}/repos/owner/repo/releases").mock(
            return_value=httpx.Response(200, json=payload)
        )

        under_test = GitHubReleasesClient(token=None)
        items = await under_test.fetch_releases("owner/repo")

        assert [item.tag for item in items] == ["v1.0"]

    @respx.mock
    async def test_filters_by_since(self) -> None:
        respx.get(f"{DEFAULT_API_BASE}/repos/owner/repo/releases").mock(
            return_value=httpx.Response(
                200,
                json=[
                    _release_payload("v1.0", "2026-06-20T10:00:00Z"),
                    _release_payload("v0.9", "2026-05-01T10:00:00Z"),
                ],
            )
        )
        cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)

        under_test = GitHubReleasesClient(token=None)
        items = await under_test.fetch_releases("owner/repo", since=cutoff)

        assert [item.tag for item in items] == ["v1.0"]

    @respx.mock
    async def test_respects_limit(self) -> None:
        respx.get(f"{DEFAULT_API_BASE}/repos/owner/repo/releases").mock(
            return_value=httpx.Response(
                200,
                json=[
                    _release_payload("v3", "2026-06-22T10:00:00Z"),
                    _release_payload("v2", "2026-06-21T10:00:00Z"),
                    _release_payload("v1", "2026-06-20T10:00:00Z"),
                ],
            )
        )

        under_test = GitHubReleasesClient(token=None)
        items = await under_test.fetch_releases("owner/repo", limit=2)

        assert len(items) == 2
        assert [item.tag for item in items] == ["v3", "v2"]

    @respx.mock
    async def test_404_raises_releases_error(self) -> None:
        respx.get(f"{DEFAULT_API_BASE}/repos/owner/ghost/releases").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )

        under_test = GitHubReleasesClient(token=None)

        with pytest.raises(GitHubReleasesError):
            await under_test.fetch_releases("owner/ghost")

    @respx.mock
    async def test_rate_limited_raises_releases_error(self) -> None:
        respx.get(f"{DEFAULT_API_BASE}/repos/owner/repo/releases").mock(
            return_value=httpx.Response(403, json={"message": "rate limit"})
        )

        under_test = GitHubReleasesClient(token=None)

        with pytest.raises(GitHubReleasesError):
            await under_test.fetch_releases("owner/repo")

    @respx.mock
    async def test_follows_next_link_for_pagination(self) -> None:
        page1_url = f"{DEFAULT_API_BASE}/repos/owner/repo/releases"
        page2_url = f"{page1_url}?page=2"
        respx.get(page1_url, params={"per_page": "100"}).mock(
            return_value=httpx.Response(
                200,
                headers={"Link": f'<{page2_url}>; rel="next"'},
                json=[_release_payload("v2", "2026-06-22T10:00:00Z")],
            )
        )
        respx.get(page2_url).mock(
            return_value=httpx.Response(
                200, json=[_release_payload("v1", "2026-06-20T10:00:00Z")]
            )
        )

        under_test = GitHubReleasesClient(token=None)
        items = await under_test.fetch_releases("owner/repo")

        assert [item.tag for item in items] == ["v2", "v1"]
