from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from social_content_factory.caption_generator import CaptionGeneratorError, CaptionSet
from social_content_factory.comfyui_client import RenderedImage
from social_content_factory.pipeline import render_theme
from social_content_factory.tts_client import TTSError, TTSResult
from social_content_factory.video_renderer import VideoRenderError, VideoRenderResult
from social_content_factory.voiceover_generator import (
    VoiceoverGeneratorError,
    VoiceoverScript,
)

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


class FakeCaptionClient:
    def __init__(self, model: str = "phi4:14b") -> None:
        self.model = model
        self.calls: list[tuple[str, str]] = []
        self._raise: Exception | None = None
        self._instagram = "IG caption body.\n\nWhat would you ship next?"
        self._x = "X caption — short and curious. What now?"

    def fail_with(self, exc: Exception) -> None:
        self._raise = exc

    def set_variants(self, *, instagram: str, x: str) -> None:
        self._instagram = instagram
        self._x = x

    async def generate(self, brand, theme) -> CaptionSet:
        self.calls.append((brand.key, theme.slug))
        if self._raise is not None:
            raise self._raise
        return CaptionSet(instagram=self._instagram, x=self._x, model=self.model)


class FakeVoiceoverClient:
    def __init__(self, model: str = "phi4:14b", text: str = "Today we shipped a renderer.") -> None:
        self.model = model
        self.calls: list[tuple[str, str]] = []
        self._raise: Exception | None = None
        self._text = text

    def fail_with(self, exc: Exception) -> None:
        self._raise = exc

    async def generate(self, brand, theme) -> VoiceoverScript:
        self.calls.append((brand.key, theme.slug))
        if self._raise is not None:
            raise self._raise
        return VoiceoverScript(text=self._text, model=self.model)


class FakeTTSClient:
    def __init__(self, voice: str = "en-GB-RyanNeural") -> None:
        self.voice = voice
        self.calls: list[tuple[str, Path]] = []
        self._raise: Exception | None = None

    def fail_with(self, exc: Exception) -> None:
        self._raise = exc

    async def synthesize(self, text: str, output_path: Path) -> TTSResult:
        self.calls.append((text, output_path))
        if self._raise is not None:
            raise self._raise
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"FAKE_MP3")
        return TTSResult(audio_path=output_path, voice=self.voice)


class FakeVideoRenderer:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._raise: Exception | None = None

    def fail_with(self, exc: Exception) -> None:
        self._raise = exc

    async def render(
        self,
        *,
        image_path: Path,
        audio_path: Path,
        output_path: Path,
        duration_seconds: float,
    ) -> VideoRenderResult:
        self.calls.append({
            "image_path": image_path,
            "audio_path": audio_path,
            "output_path": output_path,
            "duration_seconds": duration_seconds,
        })
        if self._raise is not None:
            raise self._raise
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"FAKE_MP4")
        return VideoRenderResult(video_path=output_path, duration_seconds=duration_seconds)


async def _run(tmp_path: Path, **overrides):
    client = overrides.pop("client", FakeComfyUIClient())
    caption_client = overrides.pop("caption_client", None)
    voiceover_client = overrides.pop("voiceover_client", None)
    tts_client = overrides.pop("tts_client", None)
    video_renderer = overrides.pop("video_renderer", None)
    result = await render_theme(
        brand_key=overrides.pop("brand_key", "personal"),
        theme_slug=overrides.pop("theme_slug", "weekly-build"),
        client=client,
        caption_client=caption_client,
        voiceover_client=voiceover_client,
        tts_client=tts_client,
        video_renderer=video_renderer,
        brands_dir=BRANDS_DIR,
        themes_dir=THEMES_DIR,
        outbox_root=tmp_path / "outbox",
        workflow_template_path=WORKFLOW_PATH,
        **overrides,
    )
    return result, client


class TestRenderTheme:
    async def test_writes_one_image_per_brand_format(self, tmp_path: Path) -> None:
        (result, _) = await _run(tmp_path)

        aspects = {r.image_path.name.split("_")[1] for r in result.images}
        assert aspects == {"1x1", "4x5", "9x16"}
        for r in result.images:
            assert r.image_path.exists()

    async def test_filters_to_explicit_aspect_ratio(self, tmp_path: Path) -> None:
        (result, _) = await _run(tmp_path, aspect_ratio="1x1")

        assert len(result.images) == 1
        assert "_1x1_" in result.images[0].image_path.name

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
        (result, _) = await _run(tmp_path, aspect_ratio="1x1", client=client)

        meta = json.loads(result.images[0].metadata_path.read_text(encoding="utf-8"))
        assert meta["checkpoint"] == "custom_checkpoint.safetensors"

    async def test_metadata_extra_includes_prompt_id_and_filename(self, tmp_path: Path) -> None:
        (result, _) = await _run(tmp_path, aspect_ratio="1x1")

        meta = json.loads(result.images[0].metadata_path.read_text(encoding="utf-8"))
        assert meta["extra"]["prompt_id"] == "prompt-1"
        assert meta["extra"]["comfyui_filename"] == "fake_00001.png"

    async def test_writes_actual_image_bytes_to_disk(self, tmp_path: Path) -> None:
        (result, _) = await _run(tmp_path, aspect_ratio="1x1")

        assert result.images[0].image_path.read_bytes() == b"FAKE_PNG_1"

    async def test_metadata_includes_git_sha_when_provided(self, tmp_path: Path) -> None:
        (result, _) = await _run(tmp_path, aspect_ratio="1x1", git_sha="deadbeef")

        meta = json.loads(result.images[0].metadata_path.read_text(encoding="utf-8"))
        assert meta["git_sha"] == "deadbeef"

    async def test_unknown_brand_raises(self, tmp_path: Path) -> None:
        from social_content_factory.brand_loader import BrandLoadError

        with pytest.raises(BrandLoadError):
            await _run(tmp_path, brand_key="ghost")

    async def test_unknown_theme_raises(self, tmp_path: Path) -> None:
        from social_content_factory.theme_loader import ThemeLoadError

        with pytest.raises(ThemeLoadError):
            await _run(tmp_path, theme_slug="ghost-theme")

    async def test_captions_none_when_no_caption_client(self, tmp_path: Path) -> None:
        (result, _) = await _run(tmp_path, aspect_ratio="1x1")

        assert result.captions is None


class ConcurrencyTrackingClient:
    def __init__(self, model: str = "fake-model.safetensors") -> None:
        self.model = model
        self._in_flight = 0
        self.peak_in_flight = 0
        self._counter = 0

    async def render(self, workflow: dict) -> RenderedImage:
        self._in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
        self._counter += 1
        c = self._counter
        await asyncio.sleep(0.01)
        self._in_flight -= 1
        return RenderedImage(
            image_bytes=f"FAKE_PNG_{c}".encode("utf-8"),
            filename=f"fake_{c:05d}.png",
            subfolder="",
            prompt_id=f"prompt-{c}",
        )


class TestParallelRender:
    async def test_renders_all_formats_concurrently(self, tmp_path: Path) -> None:
        client = ConcurrencyTrackingClient()
        (_, _) = await _run(tmp_path, client=client)

        assert client.peak_in_flight == 3

    async def test_results_preserve_brand_format_order(self, tmp_path: Path) -> None:
        (result, _) = await _run(tmp_path)

        ordered_aspects = [r.image_path.name.split("_")[1] for r in result.images]
        assert ordered_aspects == ["1x1", "4x5", "9x16"]


class TestCaptions:
    async def test_calls_caption_client_once_per_theme(self, tmp_path: Path) -> None:
        caption_client = FakeCaptionClient()
        (_, _) = await _run(tmp_path, caption_client=caption_client)

        assert caption_client.calls == [("personal", "weekly-build")]

    async def test_writes_captions_file_alongside_images(self, tmp_path: Path) -> None:
        caption_client = FakeCaptionClient()
        caption_client.set_variants(
            instagram="unique-ig-token-xyz", x="unique-x-token-pdq"
        )
        (result, _) = await _run(
            tmp_path, aspect_ratio="1x1", caption_client=caption_client
        )

        assert result.captions is not None
        body = result.captions.path.read_text(encoding="utf-8")
        assert "unique-ig-token-xyz" in body
        assert "unique-x-token-pdq" in body
        assert result.captions.directory == result.images[0].image_path.parent

    async def test_captions_filename_uses_theme_and_prompt_hash(
        self, tmp_path: Path
    ) -> None:
        caption_client = FakeCaptionClient()
        (result, _) = await _run(
            tmp_path, aspect_ratio="1x1", caption_client=caption_client
        )

        assert result.captions is not None
        assert result.captions.path.name.startswith("weekly-build_")
        assert result.captions.path.name.endswith("_captions.md")

    async def test_caption_failure_is_warning_not_fatal(self, tmp_path: Path) -> None:
        caption_client = FakeCaptionClient()
        caption_client.fail_with(CaptionGeneratorError("ollama down"))

        (result, _) = await _run(
            tmp_path, aspect_ratio="1x1", caption_client=caption_client
        )

        assert len(result.images) == 1
        assert result.images[0].image_path.exists()
        assert result.captions is None

    async def test_captions_file_records_model_from_caption_client(
        self, tmp_path: Path
    ) -> None:
        caption_client = FakeCaptionClient(model="phi4:14b")
        (result, _) = await _run(
            tmp_path, aspect_ratio="1x1", caption_client=caption_client
        )

        assert result.captions is not None
        body = result.captions.path.read_text(encoding="utf-8")
        assert "model: phi4:14b" in body



class TestVideo:
    async def test_video_none_when_no_video_clients(self, tmp_path: Path) -> None:
        (result, _) = await _run(tmp_path)

        assert result.video is None

    async def test_renders_video_when_all_clients_provided(self, tmp_path: Path) -> None:
        voiceover = FakeVoiceoverClient()
        tts = FakeTTSClient()
        renderer = FakeVideoRenderer()

        (result, _) = await _run(
            tmp_path,
            voiceover_client=voiceover,
            tts_client=tts,
            video_renderer=renderer,
        )

        assert result.video is not None
        assert result.video.video_path.exists()
        assert result.video.video_path.read_bytes() == b"FAKE_MP4"

    async def test_video_uses_9x16_image(self, tmp_path: Path) -> None:
        voiceover = FakeVoiceoverClient()
        tts = FakeTTSClient()
        renderer = FakeVideoRenderer()

        (result, _) = await _run(
            tmp_path,
            voiceover_client=voiceover,
            tts_client=tts,
            video_renderer=renderer,
        )

        assert len(renderer.calls) == 1
        used_image = renderer.calls[0]["image_path"]
        assert "_9x16_" in used_image.name

    async def test_audio_and_video_written_alongside_image(self, tmp_path: Path) -> None:
        voiceover = FakeVoiceoverClient()
        tts = FakeTTSClient()
        renderer = FakeVideoRenderer()

        (result, _) = await _run(
            tmp_path,
            voiceover_client=voiceover,
            tts_client=tts,
            video_renderer=renderer,
        )

        assert result.video is not None
        image_9x16 = next(r for r in result.images if "_9x16_" in r.image_path.name)
        assert result.video.video_path.parent == image_9x16.image_path.parent
        assert result.video.video_path.suffix == ".mp4"
        assert result.video.audio_path.suffix == ".mp3"
        assert result.video.audio_path.parent == image_9x16.image_path.parent

    async def test_video_skipped_when_no_9x16_format(self, tmp_path: Path) -> None:
        voiceover = FakeVoiceoverClient()
        tts = FakeTTSClient()
        renderer = FakeVideoRenderer()

        (result, _) = await _run(
            tmp_path,
            aspect_ratio="1x1",
            voiceover_client=voiceover,
            tts_client=tts,
            video_renderer=renderer,
        )

        assert result.video is None
        assert voiceover.calls == []
        assert tts.calls == []
        assert renderer.calls == []

    async def test_voiceover_failure_degrades_to_none(self, tmp_path: Path) -> None:
        voiceover = FakeVoiceoverClient()
        voiceover.fail_with(VoiceoverGeneratorError("ollama down"))
        tts = FakeTTSClient()
        renderer = FakeVideoRenderer()

        (result, _) = await _run(
            tmp_path,
            voiceover_client=voiceover,
            tts_client=tts,
            video_renderer=renderer,
        )

        assert result.video is None
        assert tts.calls == []
        assert renderer.calls == []
        assert len(result.images) == 3

    async def test_tts_failure_degrades_to_none(self, tmp_path: Path) -> None:
        voiceover = FakeVoiceoverClient()
        tts = FakeTTSClient()
        tts.fail_with(TTSError("microsoft down"))
        renderer = FakeVideoRenderer()

        (result, _) = await _run(
            tmp_path,
            voiceover_client=voiceover,
            tts_client=tts,
            video_renderer=renderer,
        )

        assert result.video is None
        assert renderer.calls == []

    async def test_video_render_failure_degrades_to_none(self, tmp_path: Path) -> None:
        voiceover = FakeVoiceoverClient()
        tts = FakeTTSClient()
        renderer = FakeVideoRenderer()
        renderer.fail_with(VideoRenderError("ffmpeg crashed"))

        (result, _) = await _run(
            tmp_path,
            voiceover_client=voiceover,
            tts_client=tts,
            video_renderer=renderer,
        )

        assert result.video is None
        assert len(result.images) == 3

    async def test_video_records_voice_and_model(self, tmp_path: Path) -> None:
        voiceover = FakeVoiceoverClient(model="phi4:14b")
        tts = FakeTTSClient(voice="en-GB-RyanNeural")
        renderer = FakeVideoRenderer()

        (result, _) = await _run(
            tmp_path,
            voiceover_client=voiceover,
            tts_client=tts,
            video_renderer=renderer,
        )

        assert result.video is not None
        assert result.video.voice == "en-GB-RyanNeural"
        assert result.video.script_model == "phi4:14b"

    async def test_video_requires_all_three_clients(self, tmp_path: Path) -> None:
        voiceover = FakeVoiceoverClient()
        tts = FakeTTSClient()

        (result, _) = await _run(
            tmp_path,
            voiceover_client=voiceover,
            tts_client=tts,
            video_renderer=None,
        )

        assert result.video is None
        assert voiceover.calls == []
        assert tts.calls == []
