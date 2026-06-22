from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer

from . import pipeline
from .brand_loader import BrandLoadError, load_brand
from .caption_generator import OllamaCaptionClient
from .comfyui_client import ComfyUIClient, ComfyUIConfigError, ComfyUIError
from .instagram_publisher import (
    InstagramConfigError,
    InstagramError,
    InstagramPublisher,
)
from .publish_plan import PublishPlanError, build_publish_plan
from .schemas.brand import Brand
from .tts_client import EdgeTTSClient
from .video_renderer import KenBurnsRenderer
from .voiceover_generator import OllamaVoiceoverClient

app = typer.Typer(
    name="factory",
    help="social-content-factory — theme to social-ready assets via local ComfyUI.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root() -> None:
    """Reserved for cross-command options. Forces subcommand mode."""


@app.command()
def render(
    brand: str = typer.Option(..., "--brand", help="Brand key (e.g. 'personal')."),
    theme: str = typer.Option(..., "--theme", help="Theme slug from themes/<brand>.yaml."),
    aspect_ratio: str | None = typer.Option(
        None, "--aspect-ratio", help="Render only this aspect ratio (default: all brand formats)."
    ),
    outbox: Path | None = typer.Option(
        None, "--outbox", help="Override outbox root directory."
    ),
    no_captions: bool = typer.Option(
        False, "--no-captions", help="Skip caption generation via local Ollama/phi4."
    ),
    video: bool = typer.Option(
        False, "--video", help="Also render a Ken Burns MP4 with en-GB voiceover (9x16 only)."
    ),
) -> None:
    """Render a theme into social-ready assets on the local ComfyUI host."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        client = ComfyUIClient.from_env()
    except ComfyUIConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    caption_client = None if no_captions else OllamaCaptionClient.from_env()
    voiceover_client = OllamaVoiceoverClient.from_env() if video else None
    tts_client = EdgeTTSClient.from_env() if video else None
    video_renderer = KenBurnsRenderer() if video else None

    try:
        result = asyncio.run(
            pipeline.render_theme(
                brand_key=brand,
                theme_slug=theme,
                client=client,
                caption_client=caption_client,
                voiceover_client=voiceover_client,
                tts_client=tts_client,
                video_renderer=video_renderer,
                aspect_ratio=aspect_ratio,
                outbox_root=outbox or pipeline.DEFAULT_OUTBOX_ROOT,
                git_sha=pipeline.resolve_git_sha(),
            )
        )
    except ComfyUIError as exc:
        typer.echo(f"comfyui error: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    for image in result.images:
        typer.echo(str(image.image_path))
    if result.captions is not None:
        typer.echo(str(result.captions.path))
    if result.video is not None:
        typer.echo(str(result.video.video_path))


SUPPORTED_PLATFORMS = ("instagram",)


def _load_brand_for_publish(brand_key: str) -> Brand:
    return load_brand(brand_key, brands_dir=pipeline.DEFAULT_BRANDS_DIR)


@app.command()
def publish(
    outbox_dir: Path = typer.Argument(
        ..., exists=True, file_okay=False, dir_okay=True, resolve_path=True,
        help="Outbox directory to publish (e.g. outbox/2026-06-22/personal/weekly-build).",
    ),
    platform: str = typer.Option(
        "instagram", "--platform", help="Target platform. Only 'instagram' is supported."
    ),
    confirm: bool = typer.Option(
        False, "--confirm",
        help="Required to perform a live post. Without it, runs dry-run.",
    ),
    prefer_image: bool = typer.Option(
        False, "--prefer-image",
        help="Force image upload even when a 9x16 .mp4 is available.",
    ),
) -> None:
    """Publish an outbox directory. Dry-run by default; --confirm posts live."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if platform not in SUPPORTED_PLATFORMS:
        typer.echo(
            f"error: unsupported platform '{platform}' (supported: {', '.join(SUPPORTED_PLATFORMS)})",
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        plan = build_publish_plan(outbox_dir, prefer_image=prefer_image)
    except PublishPlanError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    try:
        brand = _load_brand_for_publish(plan.brand_key)
    except BrandLoadError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    typer.echo(
        f"plan: brand={plan.brand_key} theme={plan.theme_slug} "
        f"kind={plan.media_kind} asset={plan.asset_path.name} "
        f"caption_len={len(plan.caption)}"
    )

    if confirm and not brand.allow_auto_publish:
        typer.echo(
            f"error: brand '{plan.brand_key}' has allow_auto_publish=false; "
            "set it to true in brands/<key>.yaml before --confirm",
            err=True,
        )
        raise typer.Exit(code=4)

    dry_run = not confirm

    try:
        publisher = InstagramPublisher.from_env()
    except InstagramConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    try:
        result = asyncio.run(publisher.publish(plan, dry_run=dry_run))
    except InstagramError as exc:
        typer.echo(f"instagram error: {exc}", err=True)
        raise typer.Exit(code=5) from exc

    if result.dry_run:
        typer.echo(f"dry-run ok: asset_url={result.asset_url}")
    else:
        typer.echo(
            f"published: media_id={result.media_id} permalink={result.permalink}"
        )


if __name__ == "__main__":
    app()
