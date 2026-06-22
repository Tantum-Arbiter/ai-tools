from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from typer.testing import CliRunner

from social_content_factory import cli
from social_content_factory.ingest.github_releases import (
    GitHubReleasesError,
    RawIngestItem,
)
from social_content_factory.ingest.ranker import RankedCandidate

runner = CliRunner()


def _write_brand(tmp_path: Path, ingest: dict | None = None) -> Path:
    brand = {
        "key": "personal",
        "name": "Sir Luke",
        "voice": "calm",
        "audience": "builders",
        "visual_style": "dark holo",
        "negative_prompts": ["nsfw"],
        "default_formats": ["1x1"],
    }
    if ingest is not None:
        brand["ingest"] = ingest
    brands_dir = tmp_path / "brands"
    brands_dir.mkdir()
    (brands_dir / "personal.yaml").write_text(
        yaml.safe_dump(brand), encoding="utf-8"
    )
    return brands_dir


def _item(tag: str = "v0.4") -> RawIngestItem:
    return RawIngestItem(
        source="github",
        tag=tag,
        title=f"Release {tag}",
        body="notes",
        url=f"https://github.com/owner/repo/releases/tag/{tag}",
        published_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
    )


def _candidate(slug: str = "phase-4", score: float = 0.82) -> RankedCandidate:
    return RankedCandidate(
        score=score,
        slug=slug,
        title=f"Title {slug}",
        subject="a glowing terminal",
        narrative="shipped",
        tags=["build"],
        source="github",
        source_url=f"https://github.com/owner/repo/releases/tag/{slug}",
        ingested_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
        model="phi4:14b",
        raw_tag=slug,
    )


@pytest.fixture
def patched_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    brands_dir = _write_brand(
        tmp_path, ingest={"github_repos": ["owner/repo"], "min_score": 0.5}
    )
    themes_dir = tmp_path / "themes"
    themes_dir.mkdir()
    monkeypatch.setattr(cli.pipeline, "DEFAULT_BRANDS_DIR", brands_dir)
    monkeypatch.setattr(cli.pipeline, "DEFAULT_THEMES_DIR", themes_dir)
    return brands_dir, themes_dir


class TestIngestCommand:
    def test_unknown_source_exits_2(self, patched_dirs) -> None:
        result = runner.invoke(
            cli.app, ["ingest", "--brand", "personal", "--source", "rss"]
        )
        assert result.exit_code == 2
        assert "unsupported source" in result.output

    def test_brand_without_ingest_block_exits_3(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        brands_dir = _write_brand(tmp_path, ingest=None)
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        monkeypatch.setattr(cli.pipeline, "DEFAULT_BRANDS_DIR", brands_dir)
        monkeypatch.setattr(cli.pipeline, "DEFAULT_THEMES_DIR", themes_dir)

        result = runner.invoke(
            cli.app, ["ingest", "--brand", "personal", "--source", "github"]
        )
        assert result.exit_code == 3
        assert "ingest" in result.output

    def test_happy_path_writes_suggested_yaml(
        self, patched_dirs, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, themes_dir = patched_dirs

        fetch_mock = AsyncMock(return_value=[_item("v0-4"), _item("v0-3")])
        monkeypatch.setattr(
            cli.GitHubReleasesClient, "fetch_releases", fetch_mock
        )

        async def fake_rank(self, brand, item):
            return _candidate(slug=item.tag, score=0.8 if item.tag == "v0-4" else 0.4)

        monkeypatch.setattr(cli.OllamaRankerClient, "rank", fake_rank)

        result = runner.invoke(
            cli.app,
            ["ingest", "--brand", "personal", "--source", "github"],
        )

        assert result.exit_code == 0, result.output
        suggested = themes_dir / "personal.suggested.yaml"
        assert suggested.exists()
        loaded = yaml.safe_load(suggested.read_text(encoding="utf-8"))
        slugs = [t["slug"] for t in loaded["themes"]]
        assert slugs == ["v0-4"]

    def test_collector_failure_exits_3(
        self, patched_dirs, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(self, *args, **kwargs):
            raise GitHubReleasesError("404")

        monkeypatch.setattr(cli.GitHubReleasesClient, "fetch_releases", boom)

        result = runner.invoke(
            cli.app,
            ["ingest", "--brand", "personal", "--source", "github"],
        )
        assert result.exit_code == 3
        assert "github" in result.output.lower()
