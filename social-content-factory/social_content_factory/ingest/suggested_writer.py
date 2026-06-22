from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml
from pydantic import ValidationError

from social_content_factory.ingest.ranker import RankedCandidate
from social_content_factory.schemas.suggested_theme import SuggestedTheme


class SuggestedWriterError(Exception):
    """Raised when the suggested-themes YAML cannot be parsed or written."""


def _path_for(brand_key: str, themes_dir: Path) -> Path:
    return themes_dir / f"{brand_key}.suggested.yaml"


def _candidate_to_suggested(candidate: RankedCandidate) -> SuggestedTheme:
    return SuggestedTheme(
        slug=candidate.slug,
        title=candidate.title,
        subject=candidate.subject,
        narrative=candidate.narrative or None,
        tags=list(candidate.tags),
        source=candidate.source,
        source_url=candidate.source_url,
        score=candidate.score,
        ingested_at=candidate.ingested_at,
        model_used=candidate.model or None,
        raw_tag=candidate.raw_tag or None,
    )


def load_suggestions(brand_key: str, *, themes_dir: Path) -> list[SuggestedTheme]:
    path = _path_for(brand_key, themes_dir)
    if not path.exists():
        return []

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SuggestedWriterError(f"invalid YAML in {path}: {exc}") from exc

    if raw is None:
        return []
    if not isinstance(raw, dict) or "themes" not in raw:
        raise SuggestedWriterError(f"{path} must be a mapping with a 'themes' key")

    entries = raw["themes"] or []
    if not isinstance(entries, list):
        raise SuggestedWriterError(f"{path} 'themes' must be a list")

    suggestions: list[SuggestedTheme] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SuggestedWriterError(
                f"{path} themes[{index}] must be a mapping"
            )
        try:
            suggestions.append(SuggestedTheme(**entry))
        except ValidationError as exc:
            raise SuggestedWriterError(
                f"invalid suggested theme at {path} themes[{index}]:\n{exc}"
            ) from exc
    return suggestions


def remove_suggestion(
    brand_key: str, slug: str, *, themes_dir: Path
) -> SuggestedTheme | None:
    suggestions = load_suggestions(brand_key, themes_dir=themes_dir)
    keep: list[SuggestedTheme] = []
    removed: SuggestedTheme | None = None
    for suggestion in suggestions:
        if suggestion.slug == slug and removed is None:
            removed = suggestion
            continue
        keep.append(suggestion)
    if removed is None:
        return None
    _write_suggestions_list(brand_key, keep, themes_dir=themes_dir)
    return removed


def _write_suggestions_list(
    brand_key: str, suggestions: list[SuggestedTheme], *, themes_dir: Path
) -> Path:
    themes_dir.mkdir(parents=True, exist_ok=True)
    path = _path_for(brand_key, themes_dir)
    ordered = sorted(suggestions, key=lambda s: s.score, reverse=True)
    payload = {
        "themes": [
            s.model_dump(mode="json", exclude_none=True) for s in ordered
        ]
    }
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=f".{brand_key}.suggested.",
        suffix=".yaml.tmp",
        dir=str(themes_dir),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, sort_keys=False, allow_unicode=True)
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return path


def write_suggestions(
    brand_key: str,
    candidates: list[RankedCandidate],
    *,
    themes_dir: Path,
    merge: bool = False,
) -> Path:
    by_slug: dict[str, SuggestedTheme] = {}
    if merge:
        for existing in load_suggestions(brand_key, themes_dir=themes_dir):
            by_slug[existing.slug] = existing
    for candidate in candidates:
        suggestion = _candidate_to_suggested(candidate)
        by_slug[suggestion.slug] = suggestion

    return _write_suggestions_list(
        brand_key, list(by_slug.values()), themes_dir=themes_dir
    )
