from __future__ import annotations

from pathlib import Path

import pytest

from social_content_factory.publish_plan import (
    PublishPlan,
    PublishPlanError,
    build_publish_plan,
    extract_instagram_caption,
)


def _make_outbox_dir(tmp_path: Path, brand: str = "personal", slug: str = "weekly-build") -> Path:
    directory = tmp_path / "outbox" / "2026-06-22" / brand / slug
    directory.mkdir(parents=True)
    return directory


def _write_captions(directory: Path, slug: str = "weekly-build") -> Path:
    body = (
        f"# {slug}\n\n"
        f"## Instagram\n\n"
        f"Shipped the renderer. Built it in two days. Tests green.\n\n"
        f"## X\n\n"
        f"Renderer shipped. Two days. Green.\n\n"
        f"---\n"
        f"brand: personal\n"
        f"theme: {slug}\n"
        f"model: phi4:14b\n"
    )
    path = directory / f"{slug}_abcd1234_captions.md"
    path.write_text(body, encoding="utf-8")
    return path


class TestExtractInstagramCaption:
    def test_extracts_instagram_section(self, tmp_path: Path) -> None:
        directory = _make_outbox_dir(tmp_path)
        captions_path = _write_captions(directory)

        under_test = extract_instagram_caption(captions_path)

        assert "Shipped the renderer." in under_test
        assert "Two days" not in under_test  # would only appear in X section

    def test_returns_empty_when_section_missing(self, tmp_path: Path) -> None:
        directory = _make_outbox_dir(tmp_path)
        path = directory / "weekly-build_abcd1234_captions.md"
        path.write_text("# weekly-build\n\n## X\n\nX only.\n", encoding="utf-8")

        under_test = extract_instagram_caption(path)

        assert under_test == ""


class TestBuildPublishPlan:
    def test_image_plan_when_only_png_present(self, tmp_path: Path) -> None:
        directory = _make_outbox_dir(tmp_path)
        (directory / "weekly-build_1x1_abcd1234.png").write_bytes(b"PNG")

        under_test = build_publish_plan(directory)

        assert isinstance(under_test, PublishPlan)
        assert under_test.media_kind == "image"
        assert under_test.asset_path.name == "weekly-build_1x1_abcd1234.png"
        assert under_test.has_video is False

    def test_reel_plan_when_9x16_mp4_present(self, tmp_path: Path) -> None:
        directory = _make_outbox_dir(tmp_path)
        (directory / "weekly-build_1x1_abcd1234.png").write_bytes(b"PNG")
        (directory / "weekly-build_9x16_abcd1234.png").write_bytes(b"PNG")
        (directory / "weekly-build_9x16_abcd1234.mp4").write_bytes(b"MP4")

        under_test = build_publish_plan(directory)

        assert under_test.media_kind == "reel"
        assert under_test.asset_path.suffix == ".mp4"
        assert under_test.has_video is True

    def test_picks_1x1_when_multiple_aspects_present(self, tmp_path: Path) -> None:
        directory = _make_outbox_dir(tmp_path)
        (directory / "weekly-build_4x5_abcd1234.png").write_bytes(b"PNG")
        (directory / "weekly-build_1x1_abcd1234.png").write_bytes(b"PNG")
        (directory / "weekly-build_9x16_abcd1234.png").write_bytes(b"PNG")

        under_test = build_publish_plan(directory)

        assert "_1x1_" in under_test.asset_path.name

    def test_falls_back_to_any_png_if_no_1x1(self, tmp_path: Path) -> None:
        directory = _make_outbox_dir(tmp_path)
        (directory / "weekly-build_4x5_abcd1234.png").write_bytes(b"PNG")

        under_test = build_publish_plan(directory)

        assert under_test.asset_path.name == "weekly-build_4x5_abcd1234.png"

    def test_caption_extracted_from_captions_md(self, tmp_path: Path) -> None:
        directory = _make_outbox_dir(tmp_path)
        (directory / "weekly-build_1x1_abcd1234.png").write_bytes(b"PNG")
        _write_captions(directory)

        under_test = build_publish_plan(directory)

        assert "Shipped the renderer." in under_test.caption
        assert under_test.has_captions is True

    def test_caption_empty_when_no_captions_md(self, tmp_path: Path) -> None:
        directory = _make_outbox_dir(tmp_path)
        (directory / "weekly-build_1x1_abcd1234.png").write_bytes(b"PNG")

        under_test = build_publish_plan(directory)

        assert under_test.caption == ""
        assert under_test.has_captions is False

    def test_brand_and_theme_parsed_from_directory(self, tmp_path: Path) -> None:
        directory = _make_outbox_dir(tmp_path, brand="personal", slug="weekly-build")
        (directory / "weekly-build_1x1_abcd1234.png").write_bytes(b"PNG")

        under_test = build_publish_plan(directory)

        assert under_test.brand_key == "personal"
        assert under_test.theme_slug == "weekly-build"

    def test_raises_when_directory_has_no_assets(self, tmp_path: Path) -> None:
        directory = _make_outbox_dir(tmp_path)

        with pytest.raises(PublishPlanError):
            build_publish_plan(directory)

    def test_raises_when_directory_does_not_exist(self, tmp_path: Path) -> None:
        with pytest.raises(PublishPlanError):
            build_publish_plan(tmp_path / "ghost")

    def test_prefer_image_param_forces_image_mode_even_with_video(
        self, tmp_path: Path
    ) -> None:
        directory = _make_outbox_dir(tmp_path)
        (directory / "weekly-build_1x1_abcd1234.png").write_bytes(b"PNG")
        (directory / "weekly-build_9x16_abcd1234.mp4").write_bytes(b"MP4")

        under_test = build_publish_plan(directory, prefer_image=True)

        assert under_test.media_kind == "image"
        assert under_test.asset_path.suffix == ".png"
        assert under_test.has_video is True
