from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Final

import httpx

from social_content_factory.schemas.brand import Brand
from social_content_factory.schemas.theme import Theme

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final[str] = "http://localhost:11434"
DEFAULT_MODEL: Final[str] = "phi4:14b"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 90.0
MAX_WORDS: Final[int] = 28


class VoiceoverGeneratorError(Exception):
    """Base error for the voiceover script generator."""


class VoiceoverGeneratorConfigError(VoiceoverGeneratorError):
    """Raised when voiceover generator configuration is missing or invalid."""


@dataclass(frozen=True)
class VoiceoverScript:
    text: str
    model: str


_SYSTEM_PROMPT = (
    "You write short voiceover narration scripts for short-form social video. "
    "Return a JSON object with exactly one key: 'script'. "
    "'script' is a single declarative sentence, 18 to 25 words, in the operator's voice. "
    "Never end with a question mark. Never include URLs, hashtags, or emojis. "
    "Never invent facts not present in the brief."
)


class OllamaVoiceoverClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "OllamaVoiceoverClient":
        base_url = os.environ.get("SCF_OLLAMA_BASE_URL", DEFAULT_BASE_URL)
        model = os.environ.get("SCF_VOICEOVER_MODEL", DEFAULT_MODEL)
        return cls(base_url=base_url, model=model)

    async def generate(self, brand: Brand, theme: Theme) -> VoiceoverScript:
        payload = {
            "model": self.model,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(brand, theme)},
            ],
            "options": {"temperature": 0.6},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as http:
                response = await http.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise VoiceoverGeneratorError(f"Ollama request failed: {exc}") from exc

        if response.status_code >= 400:
            raise VoiceoverGeneratorError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            body = response.json()
            content = body["message"]["content"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise VoiceoverGeneratorError(f"unexpected Ollama response shape: {exc}") from exc

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise VoiceoverGeneratorError(
                f"phi4 did not return valid JSON content: {content[:200]}"
            ) from exc

        text = (parsed.get("script") or "").strip()
        if not text:
            raise VoiceoverGeneratorError("voiceover script was empty")

        text = _trim_words(text, MAX_WORDS)
        text = text.rstrip("?").rstrip()

        logger.info(
            "voiceover generated brand=%s theme=%s model=%s words=%d",
            brand.key, theme.slug, self.model, len(text.split()),
        )
        return VoiceoverScript(text=text, model=self.model)


def _user_prompt(brand: Brand, theme: Theme) -> str:
    narrative = theme.narrative or theme.subject
    return (
        f"Brand voice: {brand.voice}\n"
        f"Audience: {brand.audience}\n"
        f"Theme slug: {theme.slug}\n"
        f"Theme title: {theme.title}\n"
        f"Narrative: {narrative}\n"
        f"Tags: {', '.join(theme.tags) if theme.tags else 'none'}\n"
        f"Write one declarative narration sentence (18\u201325 words). Respond with JSON only."
    )


def _trim_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    trimmed = " ".join(words[:max_words]).rstrip(".,;:!?")
    return trimmed + "."
