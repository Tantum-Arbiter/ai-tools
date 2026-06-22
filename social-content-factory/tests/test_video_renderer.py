from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from social_content_factory import video_renderer as under_test_module
from social_content_factory.video_renderer import (
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    KenBurnsRenderer,
    VideoRenderError,
)


class FakeProcess:
    def __init__(self, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return (b"", self._stderr)


@pytest.fixture
def captured_argv(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    captured: list[list[str]] = []

    async def fake_exec(*argv: Any, **kwargs: Any) -> FakeProcess:
        captured.append(list(argv))
        # Touch the output file so downstream existence assertions pass.
        for arg in argv:
            if isinstance(arg, str) and arg.endswith(".mp4"):
                Path(arg).parent.mkdir(parents=True, exist_ok=True)
                Path(arg).write_bytes(b"FAKE_MP4")
        return FakeProcess(returncode=0)

    monkeypatch.setattr(under_test_module.asyncio, "create_subprocess_exec", fake_exec)
    return captured


@pytest.fixture
def failing_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_exec(*argv: Any, **kwargs: Any) -> FakeProcess:
        return FakeProcess(returncode=1, stderr=b"ffmpeg: bad codec")

    monkeypatch.setattr(under_test_module.asyncio, "create_subprocess_exec", fake_exec)


@pytest.fixture
def existing_inputs(tmp_path: Path) -> tuple[Path, Path]:
    image = tmp_path / "img_9x16.png"
    audio = tmp_path / "voice.mp3"
    image.write_bytes(b"FAKE_PNG")
    audio.write_bytes(b"FAKE_MP3")
    return image, audio


class TestRender:
    async def test_writes_output_file(
        self,
        tmp_path: Path,
        existing_inputs: tuple[Path, Path],
        captured_argv: list[list[str]],
    ) -> None:
        image, audio = existing_inputs
        out = tmp_path / "video.mp4"
        under_test = KenBurnsRenderer()

        result = await under_test.render(
            image_path=image, audio_path=audio, output_path=out, duration_seconds=8.0
        )

        assert result.video_path == out
        assert out.read_bytes() == b"FAKE_MP4"
        assert result.duration_seconds == 8.0

    async def test_invokes_ffmpeg_with_both_inputs(
        self,
        tmp_path: Path,
        existing_inputs: tuple[Path, Path],
        captured_argv: list[list[str]],
    ) -> None:
        image, audio = existing_inputs
        out = tmp_path / "video.mp4"
        under_test = KenBurnsRenderer()

        await under_test.render(
            image_path=image, audio_path=audio, output_path=out, duration_seconds=8.0
        )

        argv = captured_argv[0]
        assert argv[0].endswith("ffmpeg")
        assert str(image) in argv
        assert str(audio) in argv
        assert str(out) in argv

    async def test_includes_zoompan_filter_and_target_resolution(
        self,
        tmp_path: Path,
        existing_inputs: tuple[Path, Path],
        captured_argv: list[list[str]],
    ) -> None:
        image, audio = existing_inputs
        under_test = KenBurnsRenderer()

        await under_test.render(
            image_path=image, audio_path=audio,
            output_path=tmp_path / "v.mp4", duration_seconds=6.0,
        )

        argv = captured_argv[0]
        joined = " ".join(argv)
        assert "zoompan" in joined
        assert f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}" in joined

    async def test_uses_h264_and_aac(
        self,
        tmp_path: Path,
        existing_inputs: tuple[Path, Path],
        captured_argv: list[list[str]],
    ) -> None:
        image, audio = existing_inputs
        under_test = KenBurnsRenderer()

        await under_test.render(
            image_path=image, audio_path=audio,
            output_path=tmp_path / "v.mp4", duration_seconds=7.0,
        )

        argv = captured_argv[0]
        assert "libx264" in argv
        assert "aac" in argv

    async def test_passes_duration_via_t_flag(
        self,
        tmp_path: Path,
        existing_inputs: tuple[Path, Path],
        captured_argv: list[list[str]],
    ) -> None:
        image, audio = existing_inputs
        under_test = KenBurnsRenderer()

        await under_test.render(
            image_path=image, audio_path=audio,
            output_path=tmp_path / "v.mp4", duration_seconds=7.5,
        )

        argv = captured_argv[0]
        assert "-t" in argv
        idx = argv.index("-t")
        assert argv[idx + 1] == "7.5"

    async def test_fps_in_filter(
        self,
        tmp_path: Path,
        existing_inputs: tuple[Path, Path],
        captured_argv: list[list[str]],
    ) -> None:
        image, audio = existing_inputs
        under_test = KenBurnsRenderer()

        await under_test.render(
            image_path=image, audio_path=audio,
            output_path=tmp_path / "v.mp4", duration_seconds=8.0,
        )

        argv = captured_argv[0]
        joined = " ".join(argv)
        assert f"fps={DEFAULT_FPS}" in joined

    async def test_raises_on_missing_image(
        self, tmp_path: Path, captured_argv: list[list[str]]
    ) -> None:
        audio = tmp_path / "voice.mp3"
        audio.write_bytes(b"FAKE_MP3")
        under_test = KenBurnsRenderer()

        with pytest.raises(VideoRenderError):
            await under_test.render(
                image_path=tmp_path / "missing.png",
                audio_path=audio,
                output_path=tmp_path / "v.mp4",
                duration_seconds=8.0,
            )

    async def test_raises_on_missing_audio(
        self, tmp_path: Path, captured_argv: list[list[str]]
    ) -> None:
        image = tmp_path / "img.png"
        image.write_bytes(b"FAKE_PNG")
        under_test = KenBurnsRenderer()

        with pytest.raises(VideoRenderError):
            await under_test.render(
                image_path=image,
                audio_path=tmp_path / "missing.mp3",
                output_path=tmp_path / "v.mp4",
                duration_seconds=8.0,
            )

    async def test_raises_on_nonzero_exit(
        self,
        tmp_path: Path,
        existing_inputs: tuple[Path, Path],
        failing_subprocess: None,
    ) -> None:
        image, audio = existing_inputs
        under_test = KenBurnsRenderer()

        with pytest.raises(VideoRenderError) as exc_info:
            await under_test.render(
                image_path=image, audio_path=audio,
                output_path=tmp_path / "v.mp4", duration_seconds=8.0,
            )

        assert "bad codec" in str(exc_info.value)

    async def test_creates_output_parent_directory(
        self,
        tmp_path: Path,
        existing_inputs: tuple[Path, Path],
        captured_argv: list[list[str]],
    ) -> None:
        image, audio = existing_inputs
        out = tmp_path / "deep" / "nested" / "v.mp4"
        under_test = KenBurnsRenderer()

        await under_test.render(
            image_path=image, audio_path=audio,
            output_path=out, duration_seconds=8.0,
        )

        assert out.parent.exists()
