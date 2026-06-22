from __future__ import annotations

import json
from pathlib import Path

import pytest

from social_content_factory.workflow_template import (
    FORMAT_DIMENSIONS,
    UnknownFormatError,
    WorkflowTemplateError,
    build_workflow,
    load_workflow_template,
)

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"


def _template() -> dict:
    return load_workflow_template(WORKFLOWS_DIR / "image_sd35_base.json")


class TestLoadWorkflowTemplate:
    def test_loads_sd35_base_template(self) -> None:
        under_test = _template()

        assert under_test["3"]["class_type"] == "CheckpointLoaderSimple"
        assert under_test["7"]["class_type"] == "EmptySD3LatentImage"
        assert under_test["1"]["class_type"] == "KSampler"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(WorkflowTemplateError, match="not found"):
            load_workflow_template(tmp_path / "nope.json")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(WorkflowTemplateError, match="parse"):
            load_workflow_template(bad)


class TestBuildWorkflow:
    def test_sets_model_name(self) -> None:
        under_test = build_workflow(
            _template(),
            model="my_model.safetensors",
            positive="a calm holographic terminal",
            negative="text, watermark",
            seed=42,
            aspect_ratio="1x1",
        )

        assert under_test["3"]["inputs"]["ckpt_name"] == "my_model.safetensors"

    def test_sets_positive_prompt(self) -> None:
        under_test = build_workflow(
            _template(),
            model="m",
            positive="a calm holographic terminal",
            negative="text, watermark",
            seed=42,
            aspect_ratio="1x1",
        )

        assert under_test["5"]["inputs"]["text"] == "a calm holographic terminal"

    def test_sets_negative_prompt(self) -> None:
        under_test = build_workflow(
            _template(),
            model="m",
            positive="p",
            negative="text, watermark, logo",
            seed=42,
            aspect_ratio="1x1",
        )

        assert under_test["6"]["inputs"]["text"] == "text, watermark, logo"

    def test_sets_seed_as_int(self) -> None:
        under_test = build_workflow(
            _template(), model="m", positive="p", negative="n", seed=3084366091, aspect_ratio="1x1"
        )

        assert under_test["1"]["inputs"]["seed"] == 3084366091
        assert isinstance(under_test["1"]["inputs"]["seed"], int)

    def test_sets_default_steps_and_cfg(self) -> None:
        under_test = build_workflow(
            _template(), model="m", positive="p", negative="n", seed=1, aspect_ratio="1x1"
        )

        assert under_test["1"]["inputs"]["steps"] == 35
        assert under_test["1"]["inputs"]["cfg"] == 5.5

    def test_steps_and_cfg_overridable(self) -> None:
        under_test = build_workflow(
            _template(),
            model="m", positive="p", negative="n", seed=1, aspect_ratio="1x1",
            steps=40, cfg=6.0,
        )

        assert under_test["1"]["inputs"]["steps"] == 40
        assert under_test["1"]["inputs"]["cfg"] == 6.0

    @pytest.mark.parametrize("aspect_ratio,expected", [
        ("1x1", (1024, 1024)),
        ("4x5", (1024, 1280)),
        ("9x16", (768, 1344)),
    ])
    def test_sets_dimensions_for_known_format(self, aspect_ratio: str, expected: tuple[int, int]) -> None:
        under_test = build_workflow(
            _template(), model="m", positive="p", negative="n", seed=1, aspect_ratio=aspect_ratio
        )

        assert under_test["7"]["inputs"]["width"] == expected[0]
        assert under_test["7"]["inputs"]["height"] == expected[1]

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(UnknownFormatError, match="banana"):
            build_workflow(
                _template(), model="m", positive="p", negative="n", seed=1, aspect_ratio="banana"
            )

    def test_does_not_mutate_template(self) -> None:
        template = _template()
        original = json.dumps(template, sort_keys=True)

        build_workflow(template, model="m", positive="p", negative="n", seed=1, aspect_ratio="1x1")

        assert json.dumps(template, sort_keys=True) == original

    def test_sets_filename_prefix(self) -> None:
        under_test = build_workflow(
            _template(),
            model="m", positive="p", negative="n", seed=1, aspect_ratio="1x1",
            filename_prefix="personal_weekly-build",
        )

        assert under_test["8"]["inputs"]["filename_prefix"] == "personal_weekly-build"

    def test_default_filename_prefix(self) -> None:
        under_test = build_workflow(
            _template(), model="m", positive="p", negative="n", seed=1, aspect_ratio="1x1"
        )

        assert under_test["8"]["inputs"]["filename_prefix"] == "scf"

    def test_format_dimensions_table_exposed(self) -> None:
        assert "1x1" in FORMAT_DIMENSIONS
        assert "9x16" in FORMAT_DIMENSIONS
        assert FORMAT_DIMENSIONS["1x1"] == (1024, 1024)
