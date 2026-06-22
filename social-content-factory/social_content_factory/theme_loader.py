from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from social_content_factory.schemas.theme import Theme


class ThemeLoadError(Exception):
    """Raised when a theme YAML cannot be located, parsed, or validated."""


def load_themes(brand_key: str, themes_dir: Path) -> dict[str, Theme]:
    yaml_path = themes_dir / f"{brand_key}.yaml"
    if not yaml_path.exists():
        raise ThemeLoadError(f"no theme catalogue for brand '{brand_key}' at {yaml_path}")

    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ThemeLoadError(f"invalid YAML in {yaml_path}: {exc}") from exc

    if not isinstance(raw, dict) or "themes" not in raw:
        raise ThemeLoadError(f"{yaml_path} must be a mapping with a 'themes' key")

    entries = raw["themes"]
    if not isinstance(entries, list) or not entries:
        raise ThemeLoadError(f"{yaml_path} 'themes' must be a non-empty list")

    catalogue: dict[str, Theme] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ThemeLoadError(f"{yaml_path} themes[{index}] must be a mapping")
        try:
            theme = Theme(**entry)
        except ValidationError as exc:
            raise ThemeLoadError(f"invalid theme at {yaml_path} themes[{index}]:\n{exc}") from exc
        if theme.slug in catalogue:
            raise ThemeLoadError(f"duplicate theme slug '{theme.slug}' in {yaml_path}")
        catalogue[theme.slug] = theme

    return catalogue


def load_theme(brand_key: str, slug: str, themes_dir: Path) -> Theme:
    catalogue = load_themes(brand_key, themes_dir)
    if slug not in catalogue:
        available = ", ".join(sorted(catalogue)) or "(none)"
        raise ThemeLoadError(
            f"unknown theme '{slug}' for brand '{brand_key}'. Available: {available}"
        )
    return catalogue[slug]
