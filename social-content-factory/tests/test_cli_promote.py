from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from social_content_factory import cli
from social_content_factory.ingest.ranker import RankedCandidate
from social_content_factory.ingest.suggested_writer import write_suggestions

runner = CliRunner()


def _candidate(slug: str = "phase-4", score: float = 0.82) -> RankedCandidate:
    return RankedCandidate(
        score=score,
        slug=slug,
        title=f"Title {slug}",
        subject="a glowing terminal",
        narrative="shipped",
        tags=["build", "ship"],
        source="github",
        source_url=f"https://github.com/owner/repo/releases/tag/{slug}",
        ingested_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
        model="phi4:14b",
        raw_tag=slug,
    )


def _seed_main_themes(themes_dir: Path, slugs: list[str]) -> Path:
    payload = {
        "themes": [
            {
                "slug": s,
                "title": f"Existing {s}",
                "subject": "existing subject",
                "tags": ["pre"],
            }
            for s in slugs
        ]
    }
    path = themes_dir / "personal.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


@pytest.fixture
def themes_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    themes_dir = tmp_path / "themes"
    themes_dir.mkdir()
    monkeypatch.setattr(cli.pipeline, "DEFAULT_THEMES_DIR", themes_dir)
    return themes_dir


class TestPromoteCommand:
    def test_moves_suggestion_to_main_catalogue(
        self, themes_setup: Path
    ) -> None:
        _seed_main_themes(themes_setup, ["weekly-build"])
        write_suggestions(
            "personal",
            [_candidate("phase-4", 0.8), _candidate("phase-3", 0.6)],
            themes_dir=themes_setup,
        )

        result = runner.invoke(
            cli.app, ["promote", "phase-4", "--brand", "personal"]
        )

        assert result.exit_code == 0, result.output
        main = yaml.safe_load((themes_setup / "personal.yaml").read_text())
        suggested = yaml.safe_load(
            (themes_setup / "personal.suggested.yaml").read_text()
        )
        main_slugs = [t["slug"] for t in main["themes"]]
        suggested_slugs = [t["slug"] for t in suggested["themes"]]
        assert "phase-4" in main_slugs
        assert "phase-4" not in suggested_slugs
        assert "phase-3" in suggested_slugs

    def test_promoted_entry_strips_ingest_sidecar(
        self, themes_setup: Path
    ) -> None:
        _seed_main_themes(themes_setup, ["weekly-build"])
        write_suggestions(
            "personal", [_candidate("phase-4", 0.8)], themes_dir=themes_setup
        )

        result = runner.invoke(
            cli.app, ["promote", "phase-4", "--brand", "personal"]
        )

        assert result.exit_code == 0
        main = yaml.safe_load((themes_setup / "personal.yaml").read_text())
        entry = next(t for t in main["themes"] if t["slug"] == "phase-4")
        assert "score" not in entry
        assert "source" not in entry
        assert "source_url" not in entry
        assert "ingested_at" not in entry
        assert entry["title"] == "Title phase-4"
        assert entry["subject"] == "a glowing terminal"

    def test_refuses_when_slug_already_in_main_catalogue(
        self, themes_setup: Path
    ) -> None:
        _seed_main_themes(themes_setup, ["phase-4"])
        write_suggestions(
            "personal", [_candidate("phase-4", 0.8)], themes_dir=themes_setup
        )

        result = runner.invoke(
            cli.app, ["promote", "phase-4", "--brand", "personal"]
        )

        assert result.exit_code == 4
        assert "already" in result.output.lower()

    def test_unknown_slug_exits_3(self, themes_setup: Path) -> None:
        _seed_main_themes(themes_setup, ["weekly-build"])
        write_suggestions(
            "personal", [_candidate("phase-4", 0.8)], themes_dir=themes_setup
        )

        result = runner.invoke(
            cli.app, ["promote", "missing", "--brand", "personal"]
        )

        assert result.exit_code == 3
        assert "missing" in result.output.lower()

    def test_no_suggestions_file_exits_3(self, themes_setup: Path) -> None:
        _seed_main_themes(themes_setup, ["weekly-build"])

        result = runner.invoke(
            cli.app, ["promote", "phase-4", "--brand", "personal"]
        )

        assert result.exit_code == 3
