from __future__ import annotations

from pathlib import Path

import pytest

from social_content_factory import tts_client as under_test_module
from social_content_factory.tts_client import (
    DEFAULT_VOICE,
    EdgeTTSClient,
    TTSError,
)


class FakeCommunicate:
    instances: list["FakeCommunicate"] = []

    def __init__(self, text: str, voice: str) -> None:
        self.text = text
        self.voice = voice
        self.saved_to: str | None = None
        self._raise: Exception | None = None
        FakeCommunicate.instances.append(self)

    async def save(self, audio_fname: str) -> None:
        if self._raise is not None:
            raise self._raise
        self.saved_to = audio_fname
        Path(audio_fname).write_bytes(b"FAKE_MP3_BYTES")


@pytest.fixture(autouse=True)
def _reset_fake_instances() -> None:
    FakeCommunicate.instances.clear()


@pytest.fixture
def patched_communicate(monkeypatch: pytest.MonkeyPatch) -> type[FakeCommunicate]:
    monkeypatch.setattr(under_test_module.edge_tts, "Communicate", FakeCommunicate)
    return FakeCommunicate


class TestFromEnv:
    def test_uses_default_voice_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SCF_TTS_VOICE", raising=False)

        under_test = EdgeTTSClient.from_env()

        assert under_test.voice == DEFAULT_VOICE
        assert DEFAULT_VOICE == "en-GB-RyanNeural"

    def test_respects_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCF_TTS_VOICE", "en-US-AriaNeural")

        under_test = EdgeTTSClient.from_env()

        assert under_test.voice == "en-US-AriaNeural"


class TestSynthesize:
    async def test_writes_audio_file_to_path(
        self, tmp_path: Path, patched_communicate: type[FakeCommunicate]
    ) -> None:
        out = tmp_path / "voiceover.mp3"
        under_test = EdgeTTSClient(voice="en-GB-RyanNeural")

        result = await under_test.synthesize("Hello world", out)

        assert result.audio_path == out
        assert out.read_bytes() == b"FAKE_MP3_BYTES"

    async def test_passes_text_and_voice_to_communicate(
        self, tmp_path: Path, patched_communicate: type[FakeCommunicate]
    ) -> None:
        under_test = EdgeTTSClient(voice="en-GB-RyanNeural")

        await under_test.synthesize("Shipped the renderer.", tmp_path / "v.mp3")

        assert len(patched_communicate.instances) == 1
        call = patched_communicate.instances[0]
        assert call.text == "Shipped the renderer."
        assert call.voice == "en-GB-RyanNeural"

    async def test_creates_parent_directories(
        self, tmp_path: Path, patched_communicate: type[FakeCommunicate]
    ) -> None:
        out = tmp_path / "deep" / "nested" / "v.mp3"
        under_test = EdgeTTSClient(voice="en-GB-RyanNeural")

        await under_test.synthesize("Test", out)

        assert out.exists()

    async def test_result_carries_voice(
        self, tmp_path: Path, patched_communicate: type[FakeCommunicate]
    ) -> None:
        under_test = EdgeTTSClient(voice="en-GB-RyanNeural")

        result = await under_test.synthesize("Test", tmp_path / "v.mp3")

        assert result.voice == "en-GB-RyanNeural"

    async def test_raises_on_empty_text(
        self, tmp_path: Path, patched_communicate: type[FakeCommunicate]
    ) -> None:
        under_test = EdgeTTSClient(voice="en-GB-RyanNeural")

        with pytest.raises(TTSError):
            await under_test.synthesize("   ", tmp_path / "v.mp3")

    async def test_wraps_communicate_failure_in_tts_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class BoomCommunicate(FakeCommunicate):
            def __init__(self, text: str, voice: str) -> None:
                super().__init__(text, voice)
                self._raise = RuntimeError("microsoft is down")

        monkeypatch.setattr(under_test_module.edge_tts, "Communicate", BoomCommunicate)
        under_test = EdgeTTSClient(voice="en-GB-RyanNeural")

        with pytest.raises(TTSError):
            await under_test.synthesize("Test", tmp_path / "v.mp3")
