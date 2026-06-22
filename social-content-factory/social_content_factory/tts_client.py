from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import edge_tts

logger = logging.getLogger(__name__)

DEFAULT_VOICE: Final[str] = "en-GB-RyanNeural"


class TTSError(Exception):
    """Raised when text-to-speech synthesis fails."""


@dataclass(frozen=True)
class TTSResult:
    audio_path: Path
    voice: str


class EdgeTTSClient:
    def __init__(self, *, voice: str = DEFAULT_VOICE) -> None:
        self.voice = voice

    @classmethod
    def from_env(cls) -> "EdgeTTSClient":
        return cls(voice=os.environ.get("SCF_TTS_VOICE", DEFAULT_VOICE))

    async def synthesize(self, text: str, output_path: Path) -> TTSResult:
        if not text or not text.strip():
            raise TTSError("voiceover text must be non-empty")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            communicator = edge_tts.Communicate(text, self.voice)
            await communicator.save(str(output_path))
        except Exception as exc:
            raise TTSError(f"edge-tts synthesis failed: {exc}") from exc

        logger.info(
            "tts written voice=%s words=%d -> %s",
            self.voice, len(text.split()), output_path,
        )
        return TTSResult(audio_path=output_path, voice=self.voice)
