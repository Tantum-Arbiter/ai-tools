from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from social_content_factory import cli, pipeline
from social_content_factory.comfyui_client import ComfyUIExecutionError
from social_content_factory.outbox_writer import CaptionsWriteResult, OutboxWriteResult
from social_content_factory.pipeline import RenderResult

runner = CliRunner()

FAKE_IMAGE = OutboxWriteResult(
    image_path=Path("/tmp/fake.png"),
    metadata_path=Path("/tmp/fake.metadata.json"),
    directory=Path("/tmp"),
)
FAKE_CAPTIONS = CaptionsWriteResult(
    path=Path("/tmp/fake_captions.md"),
    directory=Path("/tmp"),
)
FAKE_RESULT = RenderResult(images=[FAKE_IMAGE], captions=None)
FAKE_RESULT_WITH_CAPTIONS = RenderResult(images=[FAKE_IMAGE], captions=FAKE_CAPTIONS)


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCF_COMFYUI_BASE_URL", "http://192.168.1.213:8188")
    monkeypatch.setenv("SCF_COMFYUI_MODEL", "fake-model.safetensors")


class TestRenderCommand:
    def test_help_lists_render_command(self) -> None:
        result = runner.invoke(cli.app, ["--help"])

        assert result.exit_code == 0
        assert "render" in result.stdout

    def test_render_help_lists_required_flags(self) -> None:
        result = runner.invoke(cli.app, ["render", "--help"])

        assert result.exit_code == 0
        assert "--brand" in result.stdout
        assert "--theme" in result.stdout
        assert "--aspect-ratio" in result.stdout
        assert "--no-captions" in result.stdout
        assert "--video" in result.stdout

    def test_missing_brand_exits_nonzero(self, configured_env: None) -> None:
        result = runner.invoke(cli.app, ["render", "--theme", "weekly-build"])

        assert result.exit_code != 0

    def test_missing_base_url_env_exits_two(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCF_COMFYUI_BASE_URL", raising=False)

        result = runner.invoke(cli.app, ["render", "--brand", "personal", "--theme", "weekly-build"])

        assert result.exit_code == 2
        assert "SCF_COMFYUI_BASE_URL" in result.stderr

    def test_calls_pipeline_with_parsed_args(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_render = AsyncMock(return_value=FAKE_RESULT)
        monkeypatch.setattr(pipeline, "render_theme", mock_render)

        result = runner.invoke(
            cli.app,
            ["render", "--brand", "personal", "--theme", "weekly-build", "--aspect-ratio", "1x1"],
        )

        assert result.exit_code == 0, result.stderr
        mock_render.assert_awaited_once()
        kwargs = mock_render.await_args.kwargs
        assert kwargs["brand_key"] == "personal"
        assert kwargs["theme_slug"] == "weekly-build"
        assert kwargs["aspect_ratio"] == "1x1"

    def test_echoes_resulting_image_paths(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pipeline, "render_theme", AsyncMock(return_value=FAKE_RESULT))

        result = runner.invoke(
            cli.app, ["render", "--brand", "personal", "--theme", "weekly-build"]
        )

        assert "/tmp/fake.png" in result.stdout

    def test_echoes_caption_path_when_present(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            pipeline, "render_theme", AsyncMock(return_value=FAKE_RESULT_WITH_CAPTIONS)
        )

        result = runner.invoke(
            cli.app, ["render", "--brand", "personal", "--theme", "weekly-build"]
        )

        assert "/tmp/fake_captions.md" in result.stdout

    def test_no_captions_flag_skips_caption_client(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_render = AsyncMock(return_value=FAKE_RESULT)
        monkeypatch.setattr(pipeline, "render_theme", mock_render)

        result = runner.invoke(
            cli.app,
            ["render", "--brand", "personal", "--theme", "weekly-build", "--no-captions"],
        )

        assert result.exit_code == 0, result.stderr
        assert mock_render.await_args.kwargs["caption_client"] is None

    def test_default_passes_caption_client_to_pipeline(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_render = AsyncMock(return_value=FAKE_RESULT)
        monkeypatch.setattr(pipeline, "render_theme", mock_render)

        result = runner.invoke(
            cli.app, ["render", "--brand", "personal", "--theme", "weekly-build"]
        )

        assert result.exit_code == 0, result.stderr
        assert mock_render.await_args.kwargs["caption_client"] is not None

    def test_passes_default_status_log_path_to_pipeline(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_render = AsyncMock(return_value=FAKE_RESULT)
        monkeypatch.setattr(pipeline, "render_theme", mock_render)

        result = runner.invoke(
            cli.app, ["render", "--brand", "personal", "--theme", "weekly-build"]
        )

        assert result.exit_code == 0, result.stderr
        assert (
            mock_render.await_args.kwargs["status_log_path"]
            == pipeline.DEFAULT_STATUS_LOG_PATH
        )

    def test_comfyui_error_exits_three(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            pipeline, "render_theme", AsyncMock(side_effect=ComfyUIExecutionError("OOM"))
        )

        result = runner.invoke(
            cli.app, ["render", "--brand", "personal", "--theme", "weekly-build"]
        )

        assert result.exit_code == 3
        assert "OOM" in result.stderr

    def test_outbox_override_passed_to_pipeline(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        mock_render = AsyncMock(return_value=FAKE_RESULT)
        monkeypatch.setattr(pipeline, "render_theme", mock_render)

        result = runner.invoke(
            cli.app,
            [
                "render", "--brand", "personal", "--theme", "weekly-build",
                "--outbox", str(tmp_path / "custom-outbox"),
            ],
        )

        assert result.exit_code == 0, result.stderr
        kwargs = mock_render.await_args.kwargs
        assert kwargs["outbox_root"] == tmp_path / "custom-outbox"


    def test_default_skips_video_clients(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_render = AsyncMock(return_value=FAKE_RESULT)
        monkeypatch.setattr(pipeline, "render_theme", mock_render)

        result = runner.invoke(
            cli.app, ["render", "--brand", "personal", "--theme", "weekly-build"]
        )

        assert result.exit_code == 0, result.stderr
        kwargs = mock_render.await_args.kwargs
        assert kwargs["voiceover_client"] is None
        assert kwargs["tts_client"] is None
        assert kwargs["video_renderer"] is None

    def test_video_flag_passes_all_three_clients(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_render = AsyncMock(return_value=FAKE_RESULT)
        monkeypatch.setattr(pipeline, "render_theme", mock_render)

        result = runner.invoke(
            cli.app,
            ["render", "--brand", "personal", "--theme", "weekly-build", "--video"],
        )

        assert result.exit_code == 0, result.stderr
        kwargs = mock_render.await_args.kwargs
        assert kwargs["voiceover_client"] is not None
        assert kwargs["tts_client"] is not None
        assert kwargs["video_renderer"] is not None

    def test_echoes_video_path_when_present(
        self, configured_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from social_content_factory.pipeline import VideoWriteResult

        video = VideoWriteResult(
            video_path=Path("/tmp/fake.mp4"),
            audio_path=Path("/tmp/fake.mp3"),
            duration_seconds=8.0,
            voice="en-GB-RyanNeural",
            script_model="phi4:14b",
        )
        result_with_video = RenderResult(images=[FAKE_IMAGE], captions=None, video=video)
        monkeypatch.setattr(
            pipeline, "render_theme", AsyncMock(return_value=result_with_video)
        )

        result = runner.invoke(
            cli.app,
            ["render", "--brand", "personal", "--theme", "weekly-build", "--video"],
        )

        assert "/tmp/fake.mp4" in result.stdout
