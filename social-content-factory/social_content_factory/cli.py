from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer

from . import pipeline
from .caption_generator import OllamaCaptionClient
from .comfyui_client import ComfyUIClient, ComfyUIConfigError, ComfyUIError

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
) -> None:
    """Render a theme into social-ready assets on the local ComfyUI host."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        client = ComfyUIClient.from_env()
    except ComfyUIConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    caption_client = None if no_captions else OllamaCaptionClient.from_env()

    try:
        result = asyncio.run(
            pipeline.render_theme(
                brand_key=brand,
                theme_slug=theme,
                client=client,
                caption_client=caption_client,
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


if __name__ == "__main__":
    app()
