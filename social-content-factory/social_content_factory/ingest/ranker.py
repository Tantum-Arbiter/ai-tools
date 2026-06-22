from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final

import httpx

from social_content_factory.ingest.github_releases import RawIngestItem
from social_content_factory.schemas.brand import Brand

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final[str] = "http://localhost:11434"
DEFAULT_MODEL: Final[str] = "phi4:14b"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 90.0


class RankerError(Exception):
    """Raised when the ranker cannot produce a valid ranked candidate."""


@dataclass(frozen=True)
class RankedCandidate:
    score: float
    slug: str
    title: str
    subject: str
    narrative: str
    tags: list[str]
    source: str
    source_url: str
    ingested_at: datetime
    model: str = ""
    raw_tag: str = ""
    raw_body: str = field(default="", repr=False)


_SYSTEM_PROMPT = (
    "You curate raw release notes into social-media theme briefs in the operator's voice. "
    "Return a JSON object with exactly these keys: "
    "'score' (float 0..1, how well this fits the brand and would land as a single-screen post), "
    "'slug' (kebab-case, alphanumeric and hyphens only), "
    "'title' (short headline), "
    "'subject' (one sentence describing the visual subject of a single still image), "
    "'narrative' (one sentence operator-voice take), "
    "'tags' (1-5 short kebab-case tags). "
    "Never invent facts. If the release is uninteresting for the brand, set score below 0.3."
)


class OllamaRankerClient:
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
    def from_env(cls) -> "OllamaRankerClient":
        base_url = os.environ.get("SCF_OLLAMA_BASE_URL", DEFAULT_BASE_URL)
        model = os.environ.get("SCF_RANKER_MODEL", DEFAULT_MODEL)
        return cls(base_url=base_url, model=model)

    async def rank(self, brand: Brand, item: RawIngestItem) -> RankedCandidate:
        payload = {
            "model": self.model,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(brand, item)},
            ],
            "options": {"temperature": 0.4},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as http:
                response = await http.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise RankerError(f"Ollama request failed: {exc}") from exc

        if response.status_code >= 400:
            raise RankerError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            body = response.json()
            content = body["message"]["content"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RankerError(f"unexpected Ollama response shape: {exc}") from exc

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RankerError(
                f"phi4 did not return valid JSON content: {content[:200]}"
            ) from exc

        return _coerce_candidate(parsed, item, self.model)


async def rank_items(
    client: OllamaRankerClient,
    brand: Brand,
    items: list[RawIngestItem],
    *,
    min_score: float = 0.5,
) -> list[RankedCandidate]:
    candidates: list[RankedCandidate] = []
    for item in items:
        try:
            candidate = await client.rank(brand, item)
        except RankerError as exc:
            logger.warning("ranker dropped item tag=%s: %s", item.tag, exc)
            continue
        if candidate.score < min_score:
            logger.info(
                "ranker filtered tag=%s score=%.2f below min=%.2f",
                item.tag, candidate.score, min_score,
            )
            continue
        candidates.append(candidate)

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def _coerce_candidate(
    parsed: Any, item: RawIngestItem, model: str
) -> RankedCandidate:
    if not isinstance(parsed, dict):
        raise RankerError(f"phi4 returned non-object payload: {parsed!r}")

    try:
        score_raw = parsed["score"]
        slug = str(parsed["slug"]).strip()
        title = str(parsed["title"]).strip()
        subject = str(parsed["subject"]).strip()
        narrative = str(parsed["narrative"]).strip()
        tags_raw = parsed["tags"]
    except KeyError as exc:
        raise RankerError(f"phi4 payload missing key: {exc}") from exc

    if not slug or not title or not subject or not narrative:
        raise RankerError("phi4 payload had empty required field")

    try:
        score = float(score_raw)
    except (TypeError, ValueError) as exc:
        raise RankerError(f"phi4 score not numeric: {score_raw!r}") from exc
    score = max(0.0, min(1.0, score))

    if not isinstance(tags_raw, list):
        raise RankerError(f"phi4 tags not a list: {tags_raw!r}")
    tags = [str(t).strip() for t in tags_raw if str(t).strip()]

    return RankedCandidate(
        score=score,
        slug=_normalise_slug(slug),
        title=title,
        subject=subject,
        narrative=narrative,
        tags=tags,
        source=item.source,
        source_url=item.url,
        ingested_at=datetime.now(timezone.utc),
        model=model,
        raw_tag=item.tag,
        raw_body=item.body,
    )


def _normalise_slug(value: str) -> str:
    cleaned = value.lower().replace("_", "-")
    return "".join(ch for ch in cleaned if ch.isalnum() or ch == "-").strip("-")


def _user_prompt(brand: Brand, item: RawIngestItem) -> str:
    body = item.body.strip()
    if len(body) > 1500:
        body = body[:1500] + "…"
    return (
        f"Brand voice: {brand.voice}\n"
        f"Audience: {brand.audience}\n"
        f"Visual style: {brand.visual_style}\n"
        f"Source: {item.source}\n"
        f"Release tag: {item.tag}\n"
        f"Release title: {item.title}\n"
        f"Release body:\n{body}\n"
        f"Respond with JSON only."
    )
