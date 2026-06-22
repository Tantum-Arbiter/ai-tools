from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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
from .status_log import RenderStatusEntry, StatusLogError, append_status_entry
from .theme_loader import load_theme
from .tts_client import TTSError, TTSResult
from .video_renderer import VideoRenderError, VideoRenderResult
from .voiceover_generator import VoiceoverGeneratorError, VoiceoverScript
from .workflow_template import build_workflow, load_workflow_template

logger = logging.getLogger(__name__)

MODULE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BRANDS_DIR = MODULE_ROOT / "brands"
DEFAULT_THEMES_DIR = MODULE_ROOT / "themes"
DEFAULT_WORKFLOW_PATH = MODULE_ROOT / "workflows" / "image_sd35_base.json"
DEFAULT_OUTBOX_ROOT = MODULE_ROOT / "outbox"
DEFAULT_STATUS_LOG_PATH = MODULE_ROOT / "data" / "factory_status.jsonl"


class RenderClient(Protocol):
    model: str

    async def render(self, workflow: dict) -> RenderedImage: ...


class CaptionClient(Protocol):
    model: str

    async def generate(self, brand: Brand, theme: Theme) -> CaptionSet: ...


class VoiceoverClient(Protocol):
    model: str

    async def generate(self, brand: Brand, theme: Theme) -> VoiceoverScript: ...


class TTSClient(Protocol):
    voice: str

    async def synthesize(self, text: str, output_path: Path) -> TTSResult: ...


class VideoRenderer(Protocol):
    async def render(
        self,
        *,
        image_path: Path,
        audio_path: Path,
        output_path: Path,
        duration_seconds: float,
    ) -> VideoRenderResult: ...


VIDEO_ASPECT_RATIO: str = "9x16"
WORDS_PER_SECOND: float = 2.5
VIDEO_TAIL_BUFFER_SECONDS: float = 1.0


@dataclass(frozen=True)
class VideoWriteResult:
    video_path: Path
    audio_path: Path
    duration_seconds: float
    voice: str
    script_model: str


@dataclass(frozen=True)
class RenderResult:
    images: list[OutboxWriteResult]
    captions: CaptionsWriteResult | None
    video: VideoWriteResult | None = None


async def render_theme(
    *,
    brand_key: str,
    theme_slug: str,
    client: RenderClient,
    caption_client: CaptionClient | None = None,
    voiceover_client: VoiceoverClient | None = None,
    tts_client: TTSClient | None = None,
    video_renderer: VideoRenderer | None = None,
    aspect_ratio: str | None = None,
    brands_dir: Path = DEFAULT_BRANDS_DIR,
    themes_dir: Path = DEFAULT_THEMES_DIR,
    outbox_root: Path = DEFAULT_OUTBOX_ROOT,
    workflow_template_path: Path = DEFAULT_WORKFLOW_PATH,
    git_sha: str | None = None,
    status_log_path: Path | None = None,
) -> RenderResult:
    started_at = time.monotonic()
    formats_used: list[str] = []
    try:
        brand = load_brand(brand_key, brands_dir=brands_dir)
        theme = load_theme(brand_key, theme_slug, themes_dir=themes_dir)
        brief = build_brief(brand, theme)
        template = load_workflow_template(workflow_template_path)

        formats = [aspect_ratio] if aspect_ratio else brief.formats
        formats_used = list(formats)

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

        video: VideoWriteResult | None = None
        if voiceover_client is not None and tts_client is not None and video_renderer is not None:
            image_9x16 = _find_aspect(images, VIDEO_ASPECT_RATIO)
            if image_9x16 is not None:
                video = await _generate_and_render_video(
                    voiceover_client=voiceover_client,
                    tts_client=tts_client,
                    video_renderer=video_renderer,
                    brand=brand,
                    theme=theme,
                    image_9x16=image_9x16,
                )
    except Exception as exc:
        _record_status(
            status_log_path,
            brand_key=brand_key,
            theme_slug=theme_slug,
            status="failure",
            formats=formats_used,
            outputs=[],
            error=str(exc),
            duration_seconds=round(time.monotonic() - started_at, 3),
        )
        raise

    _record_status(
        status_log_path,
        brand_key=brand_key,
        theme_slug=theme_slug,
        status="success",
        formats=formats_used,
        outputs=[str(image.image_path) for image in images],
        error=None,
        duration_seconds=round(time.monotonic() - started_at, 3),
    )
    return RenderResult(images=images, captions=captions, video=video)


def _record_status(
    status_log_path: Path | None,
    *,
    brand_key: str,
    theme_slug: str,
    status: str,
    formats: list[str],
    outputs: list[str],
    error: str | None,
    duration_seconds: float,
) -> None:
    if status_log_path is None:
        return
    entry = RenderStatusEntry(
        timestamp=datetime.now(timezone.utc),
        brand=brand_key,
        theme=theme_slug,
        status=status,
        formats=formats,
        outputs=outputs,
        error=error,
        duration_seconds=duration_seconds,
    )
    try:
        append_status_entry(status_log_path, entry)
    except (OSError, StatusLogError) as exc:
        logger.warning("failed to record render status: %s", exc)


def _find_aspect(images: list[OutboxWriteResult], aspect: str) -> OutboxWriteResult | None:
    needle = f"_{aspect}_"
    for img in images:
        if needle in img.image_path.name:
            return img
    return None


async def _generate_and_render_video(
    *,
    voiceover_client: VoiceoverClient,
    tts_client: TTSClient,
    video_renderer: VideoRenderer,
    brand: Brand,
    theme: Theme,
    image_9x16: OutboxWriteResult,
) -> VideoWriteResult | None:
    try:
        script = await voiceover_client.generate(brand, theme)
    except VoiceoverGeneratorError as exc:
        logger.warning(
            "voiceover generation failed brand=%s theme=%s err=%s",
            brand.key, theme.slug, exc,
        )
        return None

    base = image_9x16.image_path.with_suffix("")
    audio_path = base.with_name(f"{base.name}.mp3")
    video_path = base.with_name(f"{base.name}.mp4")

    try:
        tts_result = await tts_client.synthesize(script.text, audio_path)
    except TTSError as exc:
        logger.warning(
            "tts synthesis failed brand=%s theme=%s err=%s",
            brand.key, theme.slug, exc,
        )
        return None

    duration_seconds = _estimate_duration_seconds(script.text)

    try:
        render_result = await video_renderer.render(
            image_path=image_9x16.image_path,
            audio_path=tts_result.audio_path,
            output_path=video_path,
            duration_seconds=duration_seconds,
        )
    except VideoRenderError as exc:
        logger.warning(
            "video render failed brand=%s theme=%s err=%s",
            brand.key, theme.slug, exc,
        )
        return None

    logger.info(
        "video written brand=%s theme=%s duration=%.2fs -> %s",
        brand.key, theme.slug, render_result.duration_seconds, render_result.video_path,
    )
    return VideoWriteResult(
        video_path=render_result.video_path,
        audio_path=tts_result.audio_path,
        duration_seconds=render_result.duration_seconds,
        voice=tts_result.voice,
        script_model=script.model,
    )


def _estimate_duration_seconds(text: str) -> float:
    words = max(1, len(text.split()))
    return round(words / WORDS_PER_SECOND + VIDEO_TAIL_BUFFER_SECONDS, 2)


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
