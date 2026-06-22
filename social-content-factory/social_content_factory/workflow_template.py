from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Final

FORMAT_DIMENSIONS: Final[dict[str, tuple[int, int]]] = {
    "1x1": (1024, 1024),
    "4x5": (1024, 1280),
    "9x16": (768, 1344),
}


class WorkflowTemplateError(Exception):
    """Raised when a workflow template cannot be loaded or parsed."""


class UnknownFormatError(WorkflowTemplateError):
    """Raised when an aspect ratio has no dimension mapping."""


def load_workflow_template(path: Path) -> dict:
    if not path.exists():
        raise WorkflowTemplateError(f"workflow template not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowTemplateError(f"failed to parse workflow template {path}: {exc}") from exc


def build_workflow(
    template: dict,
    *,
    model: str,
    positive: str,
    negative: str,
    seed: int,
    aspect_ratio: str,
    steps: int = 35,
    cfg: float = 5.5,
    filename_prefix: str = "scf",
) -> dict:
    if aspect_ratio not in FORMAT_DIMENSIONS:
        raise UnknownFormatError(
            f"unknown aspect_ratio {aspect_ratio!r}; known: {sorted(FORMAT_DIMENSIONS)}"
        )
    width, height = FORMAT_DIMENSIONS[aspect_ratio]

    workflow = copy.deepcopy(template)
    workflow["3"]["inputs"]["ckpt_name"] = model
    workflow["5"]["inputs"]["text"] = positive
    workflow["6"]["inputs"]["text"] = negative
    workflow["1"]["inputs"]["seed"] = int(seed)
    workflow["1"]["inputs"]["steps"] = int(steps)
    workflow["1"]["inputs"]["cfg"] = float(cfg)
    workflow["7"]["inputs"]["width"] = width
    workflow["7"]["inputs"]["height"] = height
    workflow["8"]["inputs"]["filename_prefix"] = filename_prefix
    return workflow
