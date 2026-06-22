from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from social_content_factory.ingest.ranker import RankedCandidate
from social_content_factory.ingest.suggested_writer import (
    SuggestedWriterError,
    load_suggestions,
    write_suggestions,
)
from social_content_factory.schemas.suggested_theme import SuggestedTheme


def _candidate(slug: str = "phase-4", score: float = 0.82) -> RankedCandidate:
    return RankedCandidate(
        score=score,
        slug=slug,
        title=f"Title {slug}",
        subject="a glowing terminal beside a calm desk",
        narrative="phase 4 publish hook shipped",
        tags=["build", "ship"],
        source="github",
        source_url=f"https://github.com/owner/repo/releases/tag/{slug}",
        ingested_at=datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc),
        model="phi4:14b",
        raw_tag=slug,
    )


class TestWriteSuggestions:
    def test_creates_file_with_themes_key(self, tmp_path: Path) -> None:
        write_suggestions("personal", [_candidate()], themes_dir=tmp_path)

        path = tmp_path / "personal.suggested.yaml"
        assert path.exists()
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        assert "themes" in raw
        assert len(raw["themes"]) == 1
        entry = raw["themes"][0]
        assert entry["slug"] == "phase-4"
        assert entry["score"] == pytest.approx(0.82)
        assert entry["source"] == "github"
        assert entry["source_url"].endswith("phase-4")

    def test_round_trips_via_load(self, tmp_path: Path) -> None:
        write_suggestions("personal", [_candidate()], themes_dir=tmp_path)

        loaded = load_suggestions("personal", themes_dir=tmp_path)

        assert len(loaded) == 1
        assert isinstance(loaded[0], SuggestedTheme)
        assert loaded[0].slug == "phase-4"
        assert loaded[0].score == pytest.approx(0.82)

    def test_overwrites_atomically(self, tmp_path: Path) -> None:
        write_suggestions("personal", [_candidate("first", 0.7)], themes_dir=tmp_path)
        write_suggestions("personal", [_candidate("second", 0.9)], themes_dir=tmp_path)

        loaded = load_suggestions("personal", themes_dir=tmp_path)

        assert [s.slug for s in loaded] == ["second"]

    def test_merges_with_existing_dedupe_by_slug(self, tmp_path: Path) -> None:
        write_suggestions(
            "personal",
            [_candidate("phase-4", 0.5), _candidate("phase-3", 0.6)],
            themes_dir=tmp_path,
        )

        write_suggestions(
            "personal",
            [_candidate("phase-4", 0.9), _candidate("phase-5", 0.7)],
            themes_dir=tmp_path,
            merge=True,
        )

        loaded = load_suggestions("personal", themes_dir=tmp_path)

        by_slug = {s.slug: s for s in loaded}
        assert set(by_slug) == {"phase-3", "phase-4", "phase-5"}
        assert by_slug["phase-4"].score == pytest.approx(0.9)

    def test_sorted_by_score_descending(self, tmp_path: Path) -> None:
        write_suggestions(
            "personal",
            [_candidate("a", 0.4), _candidate("b", 0.9), _candidate("c", 0.7)],
            themes_dir=tmp_path,
        )

        loaded = load_suggestions("personal", themes_dir=tmp_path)

        assert [s.slug for s in loaded] == ["b", "c", "a"]


class TestLoadSuggestions:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_suggestions("personal", themes_dir=tmp_path) == []

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        (tmp_path / "personal.suggested.yaml").write_text(
            "themes:\n  - not-a-mapping\n", encoding="utf-8"
        )

        with pytest.raises(SuggestedWriterError):
            load_suggestions("personal", themes_dir=tmp_path)
