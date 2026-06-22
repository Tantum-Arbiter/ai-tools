from __future__ import annotations

import json
from pathlib import Path

import pytest

from social_content_factory.comfyui_client import RenderedImage
from social_content_factory.pipeline import render_theme

MODULE_ROOT = Path(__file__).resolve().parent.parent
BRANDS_DIR = MODULE_ROOT / "brands"
THEMES_DIR = MODULE_ROOT / "themes"
WORKFLOW_PATH = MODULE_ROOT / "workflows" / "image_sd35_base.json"


class FakeComfyUIClient:
    def __init__(self, model: str = "fake-model.safetensors") -> None:
        self.model = model
        self.workflows: list[dict] = []
        self._counter = 0

    async def render(self, workflow: dict) -> RenderedImage:
        self._counter += 1
        self.workflows.append(workflow)
        return RenderedImage(
            image_bytes=f"FAKE_PNG_{self._counter}".encode("utf-8"),
            filename=f"fake_{self._counter:05d}.png",
            subfolder="",
            prompt_id=f"prompt-{self._counter}",
        )


async def _run(tmp_path: Path, **overrides):
    client = overrides.pop("client", FakeComfyUIClient())
    return await render_theme(
        brand_key=overrides.pop("brand_key", "personal"),
        theme_slug=overrides.pop("theme_slug", "weekly-build"),
        client=client,
        brands_dir=BRANDS_DIR,
        themes_dir=THEMES_DIR,
        outbox_root=tmp_path / "outbox",
        workflow_template_path=WORKFLOW_PATH,
        **overrides,
    ), client


class TestRenderTheme:
    async def test_writes_one_image_per_brand_format(self, tmp_path: Path) -> None:
        (results, _) = await _run(tmp_path)

        aspects = {r.aspect_ratio if hasattr(r, "aspect_ratio") else r.image_path.name.split("_")[1] for r in results}
        assert aspects == {"1x1", "9x16"}
        for r in results:
            assert r.image_path.exists()

    async def test_filters_to_explicit_aspect_ratio(self, tmp_path: Path) -> None:
        (results, _) = await _run(tmp_path, aspect_ratio="1x1")

        assert len(results) == 1
        assert "_1x1_" in results[0].image_path.name

    async def test_passes_brief_prompt_to_workflow(self, tmp_path: Path) -> None:
        (_, client) = await _run(tmp_path, aspect_ratio="1x1")

        positive = client.workflows[0]["5"]["inputs"]["text"]
        negative = client.workflows[0]["6"]["inputs"]["text"]
        assert "what shipped this week" in positive
        assert "real human faces" in negative

    async def test_uses_client_model_in_workflow(self, tmp_path: Path) -> None:
        client = FakeComfyUIClient(model="custom_checkpoint.safetensors")
        (_, _) = await _run(tmp_path, aspect_ratio="1x1", client=client)

        ckpt = client.workflows[0]["3"]["inputs"]["ckpt_name"]
        assert ckpt == "custom_checkpoint.safetensors"

    async def test_metadata_records_checkpoint_from_client(self, tmp_path: Path) -> None:
        client = FakeComfyUIClient(model="custom_checkpoint.safetensors")
        (results, _) = await _run(tmp_path, aspect_ratio="1x1", client=client)

        meta = json.loads(results[0].metadata_path.read_text(encoding="utf-8"))
        assert meta["checkpoint"] == "custom_checkpoint.safetensors"

    async def test_metadata_extra_includes_prompt_id_and_filename(self, tmp_path: Path) -> None:
        (results, _) = await _run(tmp_path, aspect_ratio="1x1")

        meta = json.loads(results[0].metadata_path.read_text(encoding="utf-8"))
        assert meta["extra"]["prompt_id"] == "prompt-1"
        assert meta["extra"]["comfyui_filename"] == "fake_00001.png"

    async def test_writes_actual_image_bytes_to_disk(self, tmp_path: Path) -> None:
        (results, _) = await _run(tmp_path, aspect_ratio="1x1")

        assert results[0].image_path.read_bytes() == b"FAKE_PNG_1"

    async def test_metadata_includes_git_sha_when_provided(self, tmp_path: Path) -> None:
        (results, _) = await _run(tmp_path, aspect_ratio="1x1", git_sha="deadbeef")

        meta = json.loads(results[0].metadata_path.read_text(encoding="utf-8"))
        assert meta["git_sha"] == "deadbeef"

    async def test_unknown_brand_raises(self, tmp_path: Path) -> None:
        from social_content_factory.brand_loader import BrandLoadError

        with pytest.raises(BrandLoadError):
            await _run(tmp_path, brand_key="ghost")

    async def test_unknown_theme_raises(self, tmp_path: Path) -> None:
        from social_content_factory.theme_loader import ThemeLoadError

        with pytest.raises(ThemeLoadError):
            await _run(tmp_path, theme_slug="ghost-theme")
