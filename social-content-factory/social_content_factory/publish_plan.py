from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

MediaKind = Literal["reel", "image"]

INSTAGRAM_SECTION_RE = re.compile(
    r"^##\s+Instagram\s*\n+(?P<body>.*?)(?=^##\s|^---\s*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
PREFERRED_IMAGE_ASPECT = "1x1"
VIDEO_ASPECT = "9x16"


class PublishPlanError(Exception):
    """Raised when an outbox directory cannot be turned into a publish plan."""


@dataclass(frozen=True)
class PublishPlan:
    brand_key: str
    theme_slug: str
    directory: Path
    media_kind: MediaKind
    asset_path: Path
    caption: str
    has_video: bool
    has_captions: bool


def build_publish_plan(directory: Path, *, prefer_image: bool = False) -> PublishPlan:
    if not directory.exists() or not directory.is_dir():
        raise PublishPlanError(f"outbox directory not found: {directory}")

    pngs = sorted(directory.glob("*.png"))
    video = _find_video(directory)

    if not pngs and video is None:
        raise PublishPlanError(f"no publishable assets in {directory}")

    use_video = video is not None and not prefer_image
    if use_video:
        asset_path = video  # type: ignore[assignment]
        media_kind: MediaKind = "reel"
    else:
        asset_path = _pick_image(pngs)
        media_kind = "image"

    captions_path = _find_captions(directory)
    if captions_path is not None:
        caption = extract_instagram_caption(captions_path)
        has_captions = True
    else:
        caption = ""
        has_captions = False

    brand_key, theme_slug = _parse_brand_and_theme(directory)

    return PublishPlan(
        brand_key=brand_key,
        theme_slug=theme_slug,
        directory=directory,
        media_kind=media_kind,
        asset_path=asset_path,
        caption=caption,
        has_video=video is not None,
        has_captions=has_captions,
    )


def extract_instagram_caption(captions_path: Path) -> str:
    body = captions_path.read_text(encoding="utf-8")
    match = INSTAGRAM_SECTION_RE.search(body)
    if not match:
        return ""
    return match.group("body").strip()


def _find_video(directory: Path) -> Path | None:
    candidates = sorted(directory.glob(f"*_{VIDEO_ASPECT}_*.mp4"))
    return candidates[0] if candidates else None


def _pick_image(pngs: list[Path]) -> Path:
    if not pngs:
        raise PublishPlanError("no PNG assets available")
    for png in pngs:
        if f"_{PREFERRED_IMAGE_ASPECT}_" in png.name:
            return png
    return pngs[0]


def _find_captions(directory: Path) -> Path | None:
    candidates = sorted(directory.glob("*_captions.md"))
    return candidates[0] if candidates else None


def _parse_brand_and_theme(directory: Path) -> tuple[str, str]:
    theme_slug = directory.name
    brand_key = directory.parent.name if directory.parent is not None else ""
    return brand_key, theme_slug
