from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from social_content_factory.brand_loader import load_brand
from social_content_factory.caption_generator import (
    IG_LIMIT,
    X_LIMIT,
    CaptionGeneratorError,
    OllamaCaptionClient,
)
from social_content_factory.theme_loader import load_theme

MODULE_ROOT = Path(__file__).resolve().parent.parent
BRANDS_DIR = MODULE_ROOT / "brands"
THEMES_DIR = MODULE_ROOT / "themes"
OLLAMA_URL = "http://localhost:11434"
CHAT_PATH = "/api/chat"


@pytest.fixture
def brand():
    return load_brand("personal", brands_dir=BRANDS_DIR)


@pytest.fixture
def theme():
    return load_theme("personal", "weekly-build", themes_dir=THEMES_DIR)


def _ollama_response(*, instagram: str = "ok-ig", x: str = "ok-x", model: str = "phi4:14b") -> dict:
    return {
        "model": model,
        "message": {
            "role": "assistant",
            "content": json.dumps({"instagram": instagram, "x": x}),
        },
        "done": True,
    }


class TestFromEnv:
    def test_uses_defaults_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SCF_OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("SCF_CAPTION_MODEL", raising=False)

        under_test = OllamaCaptionClient.from_env()

        assert under_test.base_url == "http://localhost:11434"
        assert under_test.model == "phi4:14b"

    def test_respects_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCF_OLLAMA_BASE_URL", "http://other:99/")
        monkeypatch.setenv("SCF_CAPTION_MODEL", "llama3:8b")

        under_test = OllamaCaptionClient.from_env()

        assert under_test.base_url == "http://other:99"
        assert under_test.model == "llama3:8b"


class TestGenerate:
    async def test_returns_both_variants(self, brand, theme, respx_mock) -> None:
        respx_mock.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(
            return_value=httpx.Response(
                200,
                json=_ollama_response(
                    instagram="shipped the voice pipeline this week ✨",
                    x="Voice pipeline: local phi4 → edge-tts, sub-2s, offline.",
                ),
            )
        )

        under_test = OllamaCaptionClient(base_url=OLLAMA_URL, model="phi4:14b")
        captions = await under_test.generate(brand, theme)

        assert "voice pipeline" in captions.instagram
        assert "phi4" in captions.x
        assert captions.model == "phi4:14b"

    async def test_truncates_x_over_limit(self, brand, theme, respx_mock) -> None:
        respx_mock.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(
            return_value=httpx.Response(200, json=_ollama_response(x="x" * 400))
        )

        under_test = OllamaCaptionClient(base_url=OLLAMA_URL, model="phi4:14b")
        captions = await under_test.generate(brand, theme)

        assert len(captions.x) <= X_LIMIT

    async def test_truncates_instagram_over_limit(self, brand, theme, respx_mock) -> None:
        respx_mock.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(
            return_value=httpx.Response(200, json=_ollama_response(instagram="i" * 3000))
        )

        under_test = OllamaCaptionClient(base_url=OLLAMA_URL, model="phi4:14b")
        captions = await under_test.generate(brand, theme)

        assert len(captions.instagram) <= IG_LIMIT

    async def test_raises_on_network_failure(self, brand, theme, respx_mock) -> None:
        respx_mock.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        under_test = OllamaCaptionClient(base_url=OLLAMA_URL, model="phi4:14b")
        with pytest.raises(CaptionGeneratorError):
            await under_test.generate(brand, theme)

    async def test_raises_on_malformed_json_content(self, brand, theme, respx_mock) -> None:
        respx_mock.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(
            return_value=httpx.Response(
                200,
                json={"message": {"content": "this is not JSON at all"}, "done": True},
            )
        )

        under_test = OllamaCaptionClient(base_url=OLLAMA_URL, model="phi4:14b")
        with pytest.raises(CaptionGeneratorError):
            await under_test.generate(brand, theme)

    async def test_raises_on_empty_variant(self, brand, theme, respx_mock) -> None:
        respx_mock.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(
            return_value=httpx.Response(200, json=_ollama_response(instagram="", x="ok"))
        )

        under_test = OllamaCaptionClient(base_url=OLLAMA_URL, model="phi4:14b")
        with pytest.raises(CaptionGeneratorError):
            await under_test.generate(brand, theme)

    async def test_raises_on_http_error_status(self, brand, theme, respx_mock) -> None:
        respx_mock.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(
            return_value=httpx.Response(500, json={"error": "boom"})
        )

        under_test = OllamaCaptionClient(base_url=OLLAMA_URL, model="phi4:14b")
        with pytest.raises(CaptionGeneratorError):
            await under_test.generate(brand, theme)

    async def test_request_payload_carries_model_and_context(self, brand, theme, respx_mock) -> None:
        route = respx_mock.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(
            return_value=httpx.Response(200, json=_ollama_response())
        )

        under_test = OllamaCaptionClient(base_url=OLLAMA_URL, model="phi4:14b")
        await under_test.generate(brand, theme)

        body = json.loads(route.calls.last.request.content.decode())
        assert body["model"] == "phi4:14b"
        assert body.get("format") == "json"
        messages_text = json.dumps(body["messages"]).lower()
        assert "weekly-build" in messages_text or theme.subject.lower()[:20] in messages_text
        assert "calm" in messages_text
