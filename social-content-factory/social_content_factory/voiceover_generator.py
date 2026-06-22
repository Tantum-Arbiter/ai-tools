from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Final

from social_content_factory.llm_client import (
    LLMClient,
    LLMClientError,
    OllamaLLMClient,
    make_llm_client,
)
from social_content_factory.schemas.brand import Brand
from social_content_factory.schemas.theme import Theme

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final[str] = "http://localhost:11434"
DEFAULT_MODEL: Final[str] = "phi4:14b"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 90.0
MAX_WORDS: Final[int] = 28
VOICEOVER_MODEL_ENV_VAR: Final[str] = "SCF_VOICEOVER_MODEL"


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


class VoiceoverClient:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.model = llm.model

    async def generate(self, brand: Brand, theme: Theme) -> VoiceoverScript:
        try:
            parsed = await self._llm.chat_json(
                system=_SYSTEM_PROMPT,
                user=_user_prompt(brand, theme),
                options={"temperature": 0.6},
            )
        except LLMClientError as exc:
            raise VoiceoverGeneratorError(str(exc)) from exc

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


class OllamaVoiceoverClient(VoiceoverClient):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            OllamaLLMClient(
                base_url=base_url, model=model, timeout_seconds=timeout_seconds
            )
        )
        self.base_url = self._llm.base_url
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "OllamaVoiceoverClient":
        base_url = os.environ.get("SCF_OLLAMA_BASE_URL", DEFAULT_BASE_URL)
        model = os.environ.get(VOICEOVER_MODEL_ENV_VAR, DEFAULT_MODEL)
        return cls(base_url=base_url, model=model)


def make_voiceover_client(brand: Brand) -> VoiceoverClient:
    return VoiceoverClient(
        make_llm_client(brand, model_env_var=VOICEOVER_MODEL_ENV_VAR)
    )


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
