from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .brand_loader import load_brand
from .brief_builder import build_brief
from .caption_generator import CaptionGeneratorError, CaptionSet
from .comfyui_client import RenderedImage
from .outbox_writer import (
    CaptionsWriteResult,
    OutboxWriteResult,
    current_git_sha,
    write_captions,
    write_render,
)
from .schemas.brand import Brand
from .schemas.theme import Theme
from .theme_loader import load_theme
from .workflow_template import build_workflow, load_workflow_template

logger = logging.getLogger(__name__)

MODULE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BRANDS_DIR = MODULE_ROOT / "brands"
DEFAULT_THEMES_DIR = MODULE_ROOT / "themes"
DEFAULT_WORKFLOW_PATH = MODULE_ROOT / "workflows" / "image_sd35_base.json"
DEFAULT_OUTBOX_ROOT = MODULE_ROOT / "outbox"


class RenderClient(Protocol):
    model: str

    async def render(self, workflow: dict) -> RenderedImage: ...


class CaptionClient(Protocol):
    model: str

    async def generate(self, brand: Brand, theme: Theme) -> CaptionSet: ...


@dataclass(frozen=True)
class RenderResult:
    images: list[OutboxWriteResult]
    captions: CaptionsWriteResult | None


async def render_theme(
    *,
    brand_key: str,
    theme_slug: str,
    client: RenderClient,
    caption_client: CaptionClient | None = None,
    aspect_ratio: str | None = None,
    brands_dir: Path = DEFAULT_BRANDS_DIR,
    themes_dir: Path = DEFAULT_THEMES_DIR,
    outbox_root: Path = DEFAULT_OUTBOX_ROOT,
    workflow_template_path: Path = DEFAULT_WORKFLOW_PATH,
    git_sha: str | None = None,
) -> RenderResult:
    brand = load_brand(brand_key, brands_dir=brands_dir)
    theme = load_theme(brand_key, theme_slug, themes_dir=themes_dir)
    brief = build_brief(brand, theme)
    template = load_workflow_template(workflow_template_path)

    formats = [aspect_ratio] if aspect_ratio else brief.formats

    async def _render_one(fmt: str) -> OutboxWriteResult:
        workflow = build_workflow(
            template,
            model=client.model,
            positive=brief.prompt,
            negative=brief.negative_prompt,
            seed=brief.seed,
            aspect_ratio=fmt,
            filename_prefix=f"{brand_key}_{theme_slug}_{fmt}",
        )
        rendered = await client.render(workflow)
        result = write_render(
            outbox_root=outbox_root,
            brand_key=brand_key,
            theme_slug=theme_slug,
            aspect_ratio=fmt,
            image_bytes=rendered.image_bytes,
            seed=brief.seed,
            prompt_hash=brief.prompt_hash,
            checkpoint=client.model,
            git_sha=git_sha,
            extra={
                "prompt_id": rendered.prompt_id,
                "comfyui_filename": rendered.filename,
            },
        )
        logger.info(
            "rendered brand=%s theme=%s aspect=%s -> %s",
            brand_key, theme_slug, fmt, result.image_path,
        )
        return result

    images = list(await asyncio.gather(*(_render_one(fmt) for fmt in formats)))

    captions: CaptionsWriteResult | None = None
    if caption_client is not None:
        captions = await _generate_and_persist_captions(
            caption_client=caption_client,
            brand=brand,
            theme=theme,
            outbox_root=outbox_root,
            prompt_hash=brief.prompt_hash,
        )

    return RenderResult(images=images, captions=captions)


async def _generate_and_persist_captions(
    *,
    caption_client: CaptionClient,
    brand: Brand,
    theme: Theme,
    outbox_root: Path,
    prompt_hash: str,
) -> CaptionsWriteResult | None:
    try:
        captions = await caption_client.generate(brand, theme)
    except CaptionGeneratorError as exc:
        logger.warning(
            "caption generation failed brand=%s theme=%s err=%s",
            brand.key, theme.slug, exc,
        )
        return None

    result = write_captions(
        outbox_root=outbox_root,
        brand_key=brand.key,
        theme_slug=theme.slug,
        instagram=captions.instagram,
        x=captions.x,
        model=captions.model,
        prompt_hash=prompt_hash,
    )
    logger.info(
        "captions written brand=%s theme=%s -> %s",
        brand.key, theme.slug, result.path,
    )
    return result


def resolve_git_sha() -> str | None:
    return current_git_sha(MODULE_ROOT.parent)
