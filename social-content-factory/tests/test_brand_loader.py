from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from social_content_factory.brand_loader import BrandLoadError, load_brand
from social_content_factory.schemas.brand import Brand

MODULE_ROOT = Path(__file__).parent.parent
BRANDS_DIR = MODULE_ROOT / "brands"


def _minimal_brand_dict(key: str) -> dict[str, object]:
    return {
        "key": key,
        "name": "Test Brand",
        "voice": "neutral",
        "audience": "anyone",
        "visual_style": "clean",
        "negative_prompts": ["nsfw"],
        "default_formats": ["1x1"],
    }


class TestLoadBrand:
    def test_loads_personal_brand_yaml(self) -> None:
        under_test = load_brand("personal", brands_dir=BRANDS_DIR)

        assert isinstance(under_test, Brand)
        assert under_test.key == "personal"
        assert under_test.name
        assert under_test.voice
        assert under_test.audience
        assert under_test.visual_style
        assert under_test.negative_prompts
        assert under_test.default_formats

    def test_personal_brand_defaults_match_locked_decisions(self) -> None:
        under_test = load_brand("personal", brands_dir=BRANDS_DIR)

        assert under_test.allow_auto_publish is False
        assert under_test.llm_provider == "phi4"

    def test_unknown_brand_key_raises(self, tmp_path: Path) -> None:
        with pytest.raises(BrandLoadError, match="unknown brand"):
            load_brand("does-not-exist", brands_dir=tmp_path)

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("name: Bad\n", encoding="utf-8")

        with pytest.raises(BrandLoadError):
            load_brand("bad", brands_dir=tmp_path)

    def test_unknown_field_rejected(self, tmp_path: Path) -> None:
        payload = _minimal_brand_dict("extra")
        payload["surprise"] = "field"
        path = tmp_path / "extra.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        with pytest.raises(BrandLoadError):
            load_brand("extra", brands_dir=tmp_path)

    def test_allow_auto_publish_defaults_false(self, tmp_path: Path) -> None:
        payload = _minimal_brand_dict("minimal")
        path = tmp_path / "minimal.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        under_test = load_brand("minimal", brands_dir=tmp_path)

        assert under_test.allow_auto_publish is False
        assert under_test.llm_provider == "phi4"

    def test_top_level_must_be_mapping(self, tmp_path: Path) -> None:
        path = tmp_path / "list.yaml"
        path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

        with pytest.raises(BrandLoadError, match="mapping"):
            load_brand("list", brands_dir=tmp_path)

    def test_invalid_format_rejected(self, tmp_path: Path) -> None:
        payload = _minimal_brand_dict("badfmt")
        payload["default_formats"] = ["3x4"]
        path = tmp_path / "badfmt.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        with pytest.raises(BrandLoadError):
            load_brand("badfmt", brands_dir=tmp_path)

    def test_slug_validation_rejects_spaces(self, tmp_path: Path) -> None:
        payload = _minimal_brand_dict("bad slug")
        path = tmp_path / "bad slug.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        with pytest.raises(BrandLoadError):
            load_brand("bad slug", brands_dir=tmp_path)
