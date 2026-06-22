from __future__ import annotations

import hashlib

from social_content_factory.schemas.brand import Brand
from social_content_factory.schemas.brief import Brief
from social_content_factory.schemas.theme import Theme


def build_brief(brand: Brand, theme: Theme, seed: int | None = None) -> Brief:
    prompt = _compose_prompt(brand, theme)
    negative_prompt = ", ".join(brand.negative_prompts)
    formats = theme.format_overrides or brand.default_formats
    final_seed = seed if seed is not None else _deterministic_seed(brand.key, theme.slug)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    return Brief(
        brand_key=brand.key,
        theme_slug=theme.slug,
        prompt=prompt,
        negative_prompt=negative_prompt,
        formats=list(formats),
        seed=final_seed,
        prompt_hash=prompt_hash,
    )


def _compose_prompt(brand: Brand, theme: Theme) -> str:
    parts = [theme.subject]
    if theme.narrative:
        parts.append(theme.narrative)
    parts.append(brand.visual_style)
    return ", ".join(parts)


def _deterministic_seed(brand_key: str, theme_slug: str) -> int:
    digest = hashlib.sha256(f"{brand_key}/{theme_slug}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")
