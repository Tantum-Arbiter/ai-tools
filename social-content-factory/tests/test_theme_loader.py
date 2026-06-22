from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from social_content_factory.schemas.theme import Theme
from social_content_factory.theme_loader import ThemeLoadError, load_theme, load_themes

MODULE_ROOT = Path(__file__).parent.parent
THEMES_DIR = MODULE_ROOT / "themes"


def _minimal_theme(slug: str = "x") -> dict[str, object]:
    return {
        "slug": slug,
        "title": "Test theme",
        "subject": "a glowing test pattern",
    }


def _write_catalogue(path: Path, themes: list[dict[str, object]]) -> None:
    path.write_text(yaml.safe_dump({"themes": themes}), encoding="utf-8")


class TestLoadThemes:
    def test_loads_personal_theme_catalogue(self) -> None:
        under_test = load_themes("personal", themes_dir=THEMES_DIR)

        assert under_test
        assert all(isinstance(t, Theme) for t in under_test.values())
        assert "weekly-build" in under_test

    def test_unknown_brand_catalogue_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ThemeLoadError, match="no theme catalogue"):
            load_themes("nope", themes_dir=tmp_path)

    def test_missing_themes_key_raises(self, tmp_path: Path) -> None:
        (tmp_path / "bad.yaml").write_text("not_themes: []\n", encoding="utf-8")

        with pytest.raises(ThemeLoadError, match="themes"):
            load_themes("bad", themes_dir=tmp_path)

    def test_empty_themes_list_raises(self, tmp_path: Path) -> None:
        _write_catalogue(tmp_path / "empty.yaml", [])

        with pytest.raises(ThemeLoadError, match="non-empty"):
            load_themes("empty", themes_dir=tmp_path)

    def test_duplicate_slug_raises(self, tmp_path: Path) -> None:
        _write_catalogue(tmp_path / "dupe.yaml", [_minimal_theme("a"), _minimal_theme("a")])

        with pytest.raises(ThemeLoadError, match="duplicate"):
            load_themes("dupe", themes_dir=tmp_path)

    def test_unknown_field_rejected(self, tmp_path: Path) -> None:
        bad = _minimal_theme("a")
        bad["surprise"] = "field"
        _write_catalogue(tmp_path / "extra.yaml", [bad])

        with pytest.raises(ThemeLoadError):
            load_themes("extra", themes_dir=tmp_path)

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        bad = _minimal_theme("a")
        del bad["subject"]
        _write_catalogue(tmp_path / "missing.yaml", [bad])

        with pytest.raises(ThemeLoadError):
            load_themes("missing", themes_dir=tmp_path)


class TestLoadTheme:
    def test_returns_single_theme_by_slug(self) -> None:
        under_test = load_theme("personal", "weekly-build", themes_dir=THEMES_DIR)

        assert isinstance(under_test, Theme)
        assert under_test.slug == "weekly-build"

    def test_unknown_slug_raises_with_available_list(self) -> None:
        with pytest.raises(ThemeLoadError, match="Available"):
            load_theme("personal", "does-not-exist", themes_dir=THEMES_DIR)
