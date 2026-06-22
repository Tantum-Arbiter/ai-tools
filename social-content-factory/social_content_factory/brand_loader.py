from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from social_content_factory.schemas.brand import Brand


class BrandLoadError(Exception):
    """Raised when a brand YAML cannot be located, parsed, or validated."""


def load_brand(key: str, brands_dir: Path) -> Brand:
    yaml_path = brands_dir / f"{key}.yaml"
    if not yaml_path.exists():
        raise BrandLoadError(f"unknown brand '{key}' (no file at {yaml_path})")

    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise BrandLoadError(f"invalid YAML in {yaml_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise BrandLoadError(f"{yaml_path} must be a YAML mapping at the top level")

    raw.setdefault("key", key)

    try:
        return Brand(**raw)
    except ValidationError as exc:
        raise BrandLoadError(f"invalid brand YAML {yaml_path}:\n{exc}") from exc
