from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer
import yaml

from . import pipeline
from .brand_loader import BrandLoadError, load_brand
from .caption_generator import make_caption_client
from .comfyui_client import ComfyUIClient, ComfyUIConfigError, ComfyUIError
from .ingest.github_releases import GitHubReleasesClient, GitHubReleasesError
from .ingest.ranker import make_ranker_client, rank_items
from .ingest.suggested_writer import (
    SuggestedWriterError,
    load_suggestions,
    remove_suggestion,
    write_suggestions,
)
from .llm_client import LLMClientConfigError
from .schemas.suggested_theme import SuggestedTheme
from .theme_loader import ThemeLoadError, load_themes
from .instagram_publisher import (
    InstagramConfigError,
    InstagramError,
    InstagramPublisher,
)
from .publish_plan import PublishPlanError, build_publish_plan
from .schemas.brand import Brand
from .tts_client import EdgeTTSClient
from .video_renderer import KenBurnsRenderer
from .voiceover_generator import make_voiceover_client

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

    try:
        brand_obj = load_brand(brand, brands_dir=pipeline.DEFAULT_BRANDS_DIR)
    except BrandLoadError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        caption_client = None if no_captions else make_caption_client(brand_obj)
        voiceover_client = make_voiceover_client(brand_obj) if video else None
    except LLMClientConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
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
                status_log_path=pipeline.DEFAULT_STATUS_LOG_PATH,
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


SUPPORTED_INGEST_SOURCES = ("github",)


@app.command()
def ingest(
    brand: str = typer.Option(..., "--brand", help="Brand key (e.g. 'personal')."),
    source: str = typer.Option(
        "github", "--source", help="Ingest source. Only 'github' is supported."
    ),
    min_score: float | None = typer.Option(
        None, "--min-score",
        help="Override brand.ingest.min_score (0..1). Lower means more candidates.",
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Max releases to fetch per repo.",
    ),
    merge: bool = typer.Option(
        False, "--merge",
        help="Merge with existing suggestions instead of replacing.",
    ),
) -> None:
    """Auto-ingest theme candidates from upstream sources into themes/<brand>.suggested.yaml."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if source not in SUPPORTED_INGEST_SOURCES:
        typer.echo(
            f"error: unsupported source '{source}' "
            f"(supported: {', '.join(SUPPORTED_INGEST_SOURCES)})",
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        brand_model = load_brand(brand, brands_dir=pipeline.DEFAULT_BRANDS_DIR)
    except BrandLoadError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    if brand_model.ingest is None or not brand_model.ingest.github_repos:
        typer.echo(
            f"error: brand '{brand}' has no ingest.github_repos configured",
            err=True,
        )
        raise typer.Exit(code=3)

    threshold = min_score if min_score is not None else brand_model.ingest.min_score

    try:
        candidates = asyncio.run(
            _run_github_ingest(brand_model, limit=limit, min_score=threshold)
        )
    except LLMClientConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except GitHubReleasesError as exc:
        typer.echo(f"github error: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    except SuggestedWriterError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    if not candidates:
        typer.echo(f"no candidates met min_score={threshold:.2f}")
        return

    path = write_suggestions(
        brand_model.key,
        candidates,
        themes_dir=pipeline.DEFAULT_THEMES_DIR,
        merge=merge,
    )
    typer.echo(f"wrote {len(candidates)} suggestion(s) to {path}")


async def _run_github_ingest(
    brand: Brand, *, limit: int | None, min_score: float
):
    assert brand.ingest is not None
    collector = GitHubReleasesClient.from_env()
    ranker = make_ranker_client(brand)

    raw_items = []
    for repo in brand.ingest.github_repos:
        raw_items.extend(await collector.fetch_releases(repo, limit=limit))

    return await rank_items(ranker, brand, raw_items, min_score=min_score)


_THEME_FIELDS: tuple[str, ...] = (
    "slug", "title", "subject", "narrative", "tags", "cta", "format_overrides",
)


def _suggested_to_theme_entry(suggested: SuggestedTheme) -> dict:
    dumped = suggested.model_dump(mode="json", exclude_none=True)
    return {k: dumped[k] for k in _THEME_FIELDS if k in dumped}


def _append_theme_entry(themes_path: Path, entry: dict) -> None:
    raw = yaml.safe_load(themes_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "themes" not in raw:
        raise ThemeLoadError(
            f"{themes_path} must be a mapping with a 'themes' key"
        )
    raw["themes"].append(entry)
    themes_path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


@app.command()
def promote(
    slug: str = typer.Argument(..., help="Suggested theme slug to promote."),
    brand: str = typer.Option(..., "--brand", help="Brand key (e.g. 'personal')."),
) -> None:
    """Promote a suggested theme into themes/<brand>.yaml. Removes it from the suggested file."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    themes_dir = pipeline.DEFAULT_THEMES_DIR
    themes_path = themes_dir / f"{brand}.yaml"
    if not themes_path.exists():
        typer.echo(
            f"error: no main theme catalogue at {themes_path}", err=True
        )
        raise typer.Exit(code=3)

    try:
        existing = load_themes(brand, themes_dir=themes_dir)
    except ThemeLoadError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    if slug in existing:
        typer.echo(
            f"error: slug '{slug}' already exists in {themes_path.name}; "
            "edit it manually instead of promoting",
            err=True,
        )
        raise typer.Exit(code=4)

    try:
        suggestions = load_suggestions(brand, themes_dir=themes_dir)
    except SuggestedWriterError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    suggestion = next((s for s in suggestions if s.slug == slug), None)
    if suggestion is None:
        typer.echo(
            f"error: no suggested theme '{slug}' for brand '{brand}'",
            err=True,
        )
        raise typer.Exit(code=3)

    entry = _suggested_to_theme_entry(suggestion)
    _append_theme_entry(themes_path, entry)
    remove_suggestion(brand, slug, themes_dir=themes_dir)
    typer.echo(f"promoted '{slug}' into {themes_path}")


if __name__ == "__main__":
    app()
