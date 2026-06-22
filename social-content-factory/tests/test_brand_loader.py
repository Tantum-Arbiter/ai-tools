from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from social_content_factory.brand_loader import BrandLoadError, load_brand
from social_content_factory.llm_client import (
    LLMClientConfigError,
    OllamaLLMClient,
    OpenRouterLLMClient,
    make_llm_client,
)
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

    def test_legacy_openai_provider_rejected(self, tmp_path: Path) -> None:
        payload = _minimal_brand_dict("legacy")
        payload["llm_provider"] = "openai"
        path = tmp_path / "legacy.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        with pytest.raises(BrandLoadError):
            load_brand("legacy", brands_dir=tmp_path)

    def test_openrouter_requires_llm_model(self, tmp_path: Path) -> None:
        payload = _minimal_brand_dict("router")
        payload["llm_provider"] = "openrouter"
        path = tmp_path / "router.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        with pytest.raises(BrandLoadError, match="llm_model"):
            load_brand("router", brands_dir=tmp_path)

    def test_openrouter_with_model_loads(self, tmp_path: Path) -> None:
        payload = _minimal_brand_dict("router")
        payload["llm_provider"] = "openrouter"
        payload["llm_model"] = "anthropic/claude-sonnet-4-5"
        path = tmp_path / "router.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        under_test = load_brand("router", brands_dir=tmp_path)

        assert under_test.llm_provider == "openrouter"
        assert under_test.llm_model == "anthropic/claude-sonnet-4-5"

    def test_phi4_llm_model_optional(self, tmp_path: Path) -> None:
        payload = _minimal_brand_dict("local")
        path = tmp_path / "local.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")

        under_test = load_brand("local", brands_dir=tmp_path)

        assert under_test.llm_provider == "phi4"
        assert under_test.llm_model is None


class TestMakeLLMClient:
    def _brand(self, **overrides: object) -> Brand:
        payload: dict[str, object] = {
            "key": "t",
            "name": "t",
            "voice": "v",
            "audience": "a",
            "visual_style": "s",
            "negative_prompts": ["nsfw"],
            "default_formats": ["1x1"],
        }
        payload.update(overrides)
        return Brand(**payload)

    def test_phi4_brand_returns_ollama_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCF_OLLAMA_BASE_URL", raising=False)
        monkeypatch.setenv("SCF_CAPTION_MODEL", "phi4:14b")
        brand = self._brand(llm_provider="phi4")

        client = make_llm_client(brand, model_env_var="SCF_CAPTION_MODEL")

        assert isinstance(client, OllamaLLMClient)
        assert client.model == "phi4:14b"

    def test_openrouter_brand_returns_openrouter_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        brand = self._brand(
            llm_provider="openrouter", llm_model="anthropic/claude-sonnet-4-5"
        )

        client = make_llm_client(brand, model_env_var="SCF_CAPTION_MODEL")

        assert isinstance(client, OpenRouterLLMClient)
        assert client.model == "anthropic/claude-sonnet-4-5"

    def test_openrouter_brand_missing_api_key_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        brand = self._brand(
            llm_provider="openrouter", llm_model="anthropic/claude-sonnet-4-5"
        )

        with pytest.raises(LLMClientConfigError, match="OPENROUTER_API_KEY"):
            make_llm_client(brand, model_env_var="SCF_CAPTION_MODEL")
