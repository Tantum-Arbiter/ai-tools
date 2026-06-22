from __future__ import annotations

import pytest

from social_content_factory.brief_builder import build_brief
from social_content_factory.schemas.brand import Brand
from social_content_factory.schemas.brief import Brief
from social_content_factory.schemas.theme import Theme


@pytest.fixture
def brand() -> Brand:
    return Brand(
        key="personal",
        name="Sir Luke",
        voice="calm, technical",
        audience="builders",
        visual_style="dark holographic, teal accents",
        negative_prompts=["faces", "text overlays"],
        default_formats=["1x1", "9x16"],
    )


@pytest.fixture
def theme() -> Theme:
    return Theme(
        slug="weekly-build",
        title="Weekly Build",
        subject="a holographic terminal floating above a desk",
        narrative="what shipped this week",
    )


class TestBuildBrief:
    def test_returns_brief_with_brand_and_theme_metadata(self, brand: Brand, theme: Theme) -> None:
        under_test = build_brief(brand, theme)

        assert isinstance(under_test, Brief)
        assert under_test.brand_key == "personal"
        assert under_test.theme_slug == "weekly-build"

    def test_prompt_contains_theme_subject_and_brand_style(self, brand: Brand, theme: Theme) -> None:
        under_test = build_brief(brand, theme)

        assert theme.subject in under_test.prompt
        assert brand.visual_style in under_test.prompt

    def test_negative_prompt_joins_brand_negatives(self, brand: Brand, theme: Theme) -> None:
        under_test = build_brief(brand, theme)

        assert "faces" in under_test.negative_prompt
        assert "text overlays" in under_test.negative_prompt

    def test_formats_default_to_brand_formats(self, brand: Brand, theme: Theme) -> None:
        under_test = build_brief(brand, theme)

        assert under_test.formats == ["1x1", "9x16"]

    def test_theme_format_overrides_win(self, brand: Brand) -> None:
        theme = Theme(
            slug="portrait-only",
            title="Portrait only",
            subject="x",
            format_overrides=["9x16"],
        )

        under_test = build_brief(brand, theme)

        assert under_test.formats == ["9x16"]

    def test_explicit_seed_is_respected(self, brand: Brand, theme: Theme) -> None:
        under_test = build_brief(brand, theme, seed=42)

        assert under_test.seed == 42

    def test_seed_is_deterministic_when_omitted(self, brand: Brand, theme: Theme) -> None:
        first = build_brief(brand, theme)
        second = build_brief(brand, theme)

        assert first.seed == second.seed

    def test_seed_differs_per_theme(self, brand: Brand, theme: Theme) -> None:
        other = Theme(slug="other", title="Other", subject="y")

        first = build_brief(brand, theme)
        second = build_brief(brand, other)

        assert first.seed != second.seed

    def test_prompt_hash_is_sixteen_hex_chars(self, brand: Brand, theme: Theme) -> None:
        under_test = build_brief(brand, theme)

        assert len(under_test.prompt_hash) == 16
        assert all(c in "0123456789abcdef" for c in under_test.prompt_hash)

    def test_narrative_included_when_present(self, brand: Brand, theme: Theme) -> None:
        under_test = build_brief(brand, theme)

        assert theme.narrative in under_test.prompt

    def test_narrative_optional(self, brand: Brand) -> None:
        theme = Theme(slug="bare", title="Bare", subject="just a subject")

        under_test = build_brief(brand, theme)

        assert under_test.prompt.startswith("just a subject")
