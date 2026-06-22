from __future__ import annotations

import httpx
import pytest

from social_content_factory.brand_loader import load_brand
from social_content_factory.schemas.brand import Brand
from social_content_factory.theme_loader import load_theme
from social_content_factory.voiceover_generator import (
    MAX_WORDS,
    OllamaVoiceoverClient,
    VoiceoverClient,
    VoiceoverGeneratorError,
    make_voiceover_client,
)

MODULE_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
BRANDS_DIR = MODULE_ROOT / "brands"
THEMES_DIR = MODULE_ROOT / "themes"


@pytest.fixture
def brand_and_theme():
    brand = load_brand("personal", brands_dir=BRANDS_DIR)
    theme = load_theme("personal", "weekly-build", themes_dir=THEMES_DIR)
    return brand, theme


def _ok_payload(text: str) -> dict:
    return {"message": {"content": '{"script": ' + repr(text).replace("'", '"') + "}"}}


class TestFromEnv:
    def test_uses_defaults_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SCF_OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("SCF_VOICEOVER_MODEL", raising=False)

        under_test = OllamaVoiceoverClient.from_env()

        assert under_test.base_url == "http://localhost:11434"
        assert under_test.model == "phi4:14b"

    def test_respects_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCF_OLLAMA_BASE_URL", "http://10.0.0.5:11434")
        monkeypatch.setenv("SCF_VOICEOVER_MODEL", "phi4-mini:3.8b")

        under_test = OllamaVoiceoverClient.from_env()

        assert under_test.base_url == "http://10.0.0.5:11434"
        assert under_test.model == "phi4-mini:3.8b"


class TestGenerate:
    async def test_returns_script_text(self, brand_and_theme, respx_mock) -> None:
        brand, theme = brand_and_theme
        respx_mock.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(
                200, json=_ok_payload("This week we shipped the render pipeline and pushed the captions module to green.")
            )
        )
        under_test = OllamaVoiceoverClient(base_url="http://localhost:11434", model="phi4:14b")

        result = await under_test.generate(brand, theme)

        assert "render pipeline" in result.text
        assert result.model == "phi4:14b"

    async def test_truncates_over_max_words(self, brand_and_theme, respx_mock) -> None:
        brand, theme = brand_and_theme
        long_text = " ".join(["word"] * (MAX_WORDS + 12))
        respx_mock.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json=_ok_payload(long_text))
        )
        under_test = OllamaVoiceoverClient(base_url="http://localhost:11434", model="phi4:14b")

        result = await under_test.generate(brand, theme)

        assert len(result.text.split()) <= MAX_WORDS

    async def test_raises_on_network_failure(self, brand_and_theme, respx_mock) -> None:
        brand, theme = brand_and_theme
        respx_mock.post("http://localhost:11434/api/chat").mock(
            side_effect=httpx.ConnectError("ollama down")
        )
        under_test = OllamaVoiceoverClient(base_url="http://localhost:11434", model="phi4:14b")

        with pytest.raises(VoiceoverGeneratorError):
            await under_test.generate(brand, theme)

    async def test_raises_on_malformed_json_content(self, brand_and_theme, respx_mock) -> None:
        brand, theme = brand_and_theme
        respx_mock.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={"message": {"content": "not json"}})
        )
        under_test = OllamaVoiceoverClient(base_url="http://localhost:11434", model="phi4:14b")

        with pytest.raises(VoiceoverGeneratorError):
            await under_test.generate(brand, theme)

    async def test_raises_on_empty_script(self, brand_and_theme, respx_mock) -> None:
        brand, theme = brand_and_theme
        respx_mock.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json=_ok_payload("   "))
        )
        under_test = OllamaVoiceoverClient(base_url="http://localhost:11434", model="phi4:14b")

        with pytest.raises(VoiceoverGeneratorError):
            await under_test.generate(brand, theme)

    async def test_raises_on_http_error_status(self, brand_and_theme, respx_mock) -> None:
        brand, theme = brand_and_theme
        respx_mock.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(503, text="service unavailable")
        )
        under_test = OllamaVoiceoverClient(base_url="http://localhost:11434", model="phi4:14b")

        with pytest.raises(VoiceoverGeneratorError):
            await under_test.generate(brand, theme)

    async def test_strips_trailing_question_mark(self, brand_and_theme, respx_mock) -> None:
        brand, theme = brand_and_theme
        respx_mock.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(
                200, json=_ok_payload("Captions and renders are green this week, all tests passing?")
            )
        )
        under_test = OllamaVoiceoverClient(base_url="http://localhost:11434", model="phi4:14b")

        result = await under_test.generate(brand, theme)

        assert not result.text.endswith("?")

    async def test_request_payload_carries_model(self, brand_and_theme, respx_mock) -> None:
        brand, theme = brand_and_theme
        route = respx_mock.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json=_ok_payload("A short narration line about this week."))
        )
        under_test = OllamaVoiceoverClient(base_url="http://localhost:11434", model="phi4:14b")

        await under_test.generate(brand, theme)

        sent = route.calls.last.request
        import json as _json

        body = _json.loads(sent.content)
        assert body["model"] == "phi4:14b"
        assert body["format"] == "json"


def _openrouter_brand() -> Brand:
    return Brand(
        key="router",
        name="Router",
        voice="calm",
        audience="builders",
        visual_style="dark",
        negative_prompts=["nsfw"],
        default_formats=["1x1"],
        llm_provider="openrouter",
        llm_model="anthropic/claude-sonnet-4-5",
    )


def _openrouter_payload(script: str) -> dict:
    import json as _json
    return {
        "choices": [
            {"message": {"content": _json.dumps({"script": script})}}
        ]
    }


class TestMakeVoiceoverClient:
    async def test_uses_openrouter_when_brand_configured(
        self, brand_and_theme, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, theme = brand_and_theme
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        route = respx_mock.post(
            "https://openrouter.ai/api/v1/chat/completions"
        ).mock(
            return_value=httpx.Response(
                200,
                json=_openrouter_payload(
                    "We routed voiceover narration through OpenRouter using the brand-configured model today."
                ),
            )
        )

        under_test = make_voiceover_client(_openrouter_brand())
        result = await under_test.generate(_openrouter_brand(), theme)

        assert "openrouter" in result.text.lower()
        assert result.model == "anthropic/claude-sonnet-4-5"
        assert route.called

    def test_phi4_brand_returns_voiceover_client(
        self, brand_and_theme, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        brand, _ = brand_and_theme
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        under_test = make_voiceover_client(brand)

        assert isinstance(under_test, VoiceoverClient)
        assert under_test.model == "phi4:14b"
