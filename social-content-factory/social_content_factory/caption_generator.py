from __future__ import annotations

import logging
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
IG_LIMIT: Final[int] = 2200
X_LIMIT: Final[int] = 280
CAPTION_MODEL_ENV_VAR: Final[str] = "SCF_CAPTION_MODEL"


class CaptionGeneratorError(Exception):
    """Base error for the caption generator."""


class CaptionGeneratorConfigError(CaptionGeneratorError):
    """Raised when caption generator configuration is missing or invalid."""


@dataclass(frozen=True)
class CaptionSet:
    instagram: str
    x: str
    model: str


_SYSTEM_PROMPT = (
    "You write social media captions in the operator's voice. "
    "Return a JSON object with exactly two keys: 'instagram' and 'x'. "
    "'instagram' is one to three short paragraphs, ends with a question. "
    "'x' is a single line, never longer than 280 characters, ends with a question. "
    "Never include URLs, emojis-only output, or hashtags-only output. "
    "Never invent facts not present in the brief."
)


class CaptionClient:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.model = llm.model

    async def generate(self, brand: Brand, theme: Theme) -> CaptionSet:
        try:
            parsed = await self._llm.chat_json(
                system=_SYSTEM_PROMPT,
                user=_user_prompt(brand, theme),
                options={"temperature": 0.7},
            )
        except LLMClientError as exc:
            raise CaptionGeneratorError(str(exc)) from exc

        instagram = (parsed.get("instagram") or "").strip()
        x_caption = (parsed.get("x") or "").strip()
        if not instagram or not x_caption:
            raise CaptionGeneratorError(
                f"missing caption variant — instagram={bool(instagram)} x={bool(x_caption)}"
            )

        instagram = _truncate(instagram, IG_LIMIT)
        x_caption = _truncate(x_caption, X_LIMIT)

        logger.info(
            "captions generated brand=%s theme=%s model=%s ig_len=%d x_len=%d",
            brand.key, theme.slug, self.model, len(instagram), len(x_caption),
        )
        return CaptionSet(instagram=instagram, x=x_caption, model=self.model)


class OllamaCaptionClient(CaptionClient):
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
    def from_env(cls) -> "OllamaCaptionClient":
        import os
        base_url = os.environ.get("SCF_OLLAMA_BASE_URL", DEFAULT_BASE_URL)
        model = os.environ.get(CAPTION_MODEL_ENV_VAR, DEFAULT_MODEL)
        return cls(base_url=base_url, model=model)


def make_caption_client(brand: Brand) -> CaptionClient:
    return CaptionClient(make_llm_client(brand, model_env_var=CAPTION_MODEL_ENV_VAR))


def _user_prompt(brand: Brand, theme: Theme) -> str:
    cta = theme.cta or "ask the audience a thoughtful question"
    narrative = theme.narrative or theme.subject
    return (
        f"Brand voice: {brand.voice}\n"
        f"Audience: {brand.audience}\n"
        f"Theme slug: {theme.slug}\n"
        f"Theme title: {theme.title}\n"
        f"Narrative: {narrative}\n"
        f"CTA hint: {cta}\n"
        f"Tags: {', '.join(theme.tags) if theme.tags else 'none'}\n"
        f"Write the two captions now. Respond with JSON only."
    )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1].rstrip() + "…"
