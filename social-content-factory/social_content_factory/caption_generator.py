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
IG_LIMIT: Final[int] = 2200
X_LIMIT: Final[int] = 280


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


class OllamaCaptionClient:
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
    def from_env(cls) -> "OllamaCaptionClient":
        base_url = os.environ.get("SCF_OLLAMA_BASE_URL", DEFAULT_BASE_URL)
        model = os.environ.get("SCF_CAPTION_MODEL", DEFAULT_MODEL)
        return cls(base_url=base_url, model=model)

    async def generate(self, brand: Brand, theme: Theme) -> CaptionSet:
        payload = {
            "model": self.model,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(brand, theme)},
            ],
            "options": {"temperature": 0.7},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as http:
                response = await http.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise CaptionGeneratorError(f"Ollama request failed: {exc}") from exc

        if response.status_code >= 400:
            raise CaptionGeneratorError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            body = response.json()
            content = body["message"]["content"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise CaptionGeneratorError(f"unexpected Ollama response shape: {exc}") from exc

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise CaptionGeneratorError(
                f"phi4 did not return valid JSON content: {content[:200]}"
            ) from exc

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
