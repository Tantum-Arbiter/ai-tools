from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

DEFAULT_WIDTH: Final[int] = 1080
DEFAULT_HEIGHT: Final[int] = 1920
DEFAULT_FPS: Final[int] = 30
DEFAULT_FFMPEG_BIN: Final[str] = "ffmpeg"
DEFAULT_ZOOM_PER_FRAME: Final[float] = 0.0015
DEFAULT_ZOOM_CAP: Final[float] = 1.5
DEFAULT_AUDIO_BITRATE: Final[str] = "128k"


class VideoRenderError(Exception):
    """Raised when ffmpeg fails to produce the expected output."""


@dataclass(frozen=True)
class VideoRenderResult:
    video_path: Path
    duration_seconds: float


class KenBurnsRenderer:
    def __init__(
        self,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
        ffmpeg_bin: str | None = None,
        zoom_per_frame: float = DEFAULT_ZOOM_PER_FRAME,
        zoom_cap: float = DEFAULT_ZOOM_CAP,
        audio_bitrate: str = DEFAULT_AUDIO_BITRATE,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.ffmpeg_bin = ffmpeg_bin or shutil.which("ffmpeg") or DEFAULT_FFMPEG_BIN
        self.zoom_per_frame = zoom_per_frame
        self.zoom_cap = zoom_cap
        self.audio_bitrate = audio_bitrate

    async def render(
        self,
        *,
        image_path: Path,
        audio_path: Path,
        output_path: Path,
        duration_seconds: float,
    ) -> VideoRenderResult:
        if not image_path.exists():
            raise VideoRenderError(f"image not found: {image_path}")
        if not audio_path.exists():
            raise VideoRenderError(f"audio not found: {audio_path}")
        if duration_seconds <= 0:
            raise VideoRenderError(f"duration_seconds must be positive, got {duration_seconds}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        frames = max(1, int(round(duration_seconds * self.fps)))
        zoom_expr = f"min(zoom+{self.zoom_per_frame},{self.zoom_cap})"
        filter_complex = (
            f"[0:v]zoompan=z='{zoom_expr}':d={frames}"
            f":s={self.width}x{self.height}:fps={self.fps}[v]"
        )

        argv = [
            self.ffmpeg_bin,
            "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-i", str(audio_path),
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", self.audio_bitrate,
            "-t", _format_duration(duration_seconds),
            "-shortest",
            str(output_path),
        ]

        logger.info(
            "ffmpeg render image=%s audio=%s duration=%.2fs -> %s",
            image_path, audio_path, duration_seconds, output_path,
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
        except FileNotFoundError as exc:
            raise VideoRenderError(f"ffmpeg binary not found at {self.ffmpeg_bin}") from exc
        except OSError as exc:
            raise VideoRenderError(f"ffmpeg invocation failed: {exc}") from exc

        if process.returncode != 0:
            tail = stderr.decode("utf-8", errors="replace")[-400:]
            raise VideoRenderError(f"ffmpeg exited {process.returncode}: {tail}")

        return VideoRenderResult(video_path=output_path, duration_seconds=duration_seconds)


def _format_duration(seconds: float) -> str:
    if seconds == int(seconds):
        return f"{int(seconds)}"
    return f"{seconds:g}"
