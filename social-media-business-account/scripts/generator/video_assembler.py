"""
Video Assembler
Turns a static ComfyUI image into a short-form video using:
  1. Ken Burns effect (slow zoom/pan via FFmpeg) — works on any image
  2. Kokoro TTS voiceover (free, local, runs on CPU)
  3. FFmpeg assembly: video + audio + burned-in captions
Outputs 9:16 MP4 ready for Instagram Reels and YouTube Shorts.
"""
import os
import re
import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("CONTENT_OUTPUT_DIR", "data/content"))
FFMPEG = os.getenv("FFMPEG_PATH", "ffmpeg")  # Must be in PATH on Windows


class VideoAssembler:
    def create_short(
        self,
        image_path: Path,
        script: str,
        caption_text: str,
        duration: int = 28,
        music_mood: str = "soft piano",
    ) -> Path:
        """Full pipeline: image → Ken Burns video → TTS audio → assembled MP4."""
        output_dir = OUTPUT_DIR / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = image_path.stem
        final_output = output_dir / f"{stem}_reel.mp4"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Step 1: TTS voiceover
            log.info("Generating TTS voiceover...")
            audio_path = self._generate_tts(script, tmp_path / "voiceover.wav")

            # Step 2: Ken Burns video from image
            log.info("Applying Ken Burns effect...")
            raw_video = tmp_path / "ken_burns.mp4"
            self._apply_ken_burns(image_path, raw_video, duration)

            # Step 3: Assemble: video + voiceover + caption overlay
            log.info("Assembling final video...")
            self._assemble(
                video=raw_video,
                audio=audio_path,
                caption=caption_text,
                output=final_output,
                duration=duration,
            )

        log.info(f"Video ready: {final_output}")
        return final_output

    # ── TTS via Kokoro (local, free) ──────────────────────────────────
    def _generate_tts(self, script: str, output_path: Path) -> Path:
        """Generate voiceover using Kokoro TTS. Falls back to gTTS if not installed."""
        try:
            import kokoro
            # Kokoro v1 API
            pipeline = kokoro.KPipeline(lang_code="en-gb")  # British English
            samples, _ = pipeline(script, voice="af_heart", speed=0.9)
            import soundfile as sf
            sf.write(str(output_path), samples, 24000)
            return output_path
        except ImportError:
            log.warning("Kokoro not installed. Falling back to gTTS (requires internet).")
            return self._gtts_fallback(script, output_path)

    def _gtts_fallback(self, script: str, output_path: Path) -> Path:
        from gtts import gTTS
        tts = gTTS(text=script, lang="en", tld="co.uk", slow=False)
        mp3 = output_path.with_suffix(".mp3")
        tts.save(str(mp3))
        # Convert to WAV for consistent downstream handling
        subprocess.run([FFMPEG, "-y", "-i", str(mp3), str(output_path)], check=True,
                       capture_output=True)
        return output_path

    # ── Ken Burns effect via FFmpeg ───────────────────────────────────
    def _apply_ken_burns(self, image: Path, output: Path, duration: int):
        """Slow zoom-in from 100% to 115% over video duration. Looks professional."""
        fps = 25
        total_frames = duration * fps
        # zoompan filter: slow zoom from 1.0 to 1.15
        vf = (
            f"zoompan=z='min(zoom+0.0005,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1080x1920:fps={fps},"
            f"format=yuv420p"
        )
        cmd = [
            FFMPEG, "-y",
            "-loop", "1", "-i", str(image),
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            str(output),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    # ── Final assembly: video + audio + caption ───────────────────────
    def _assemble(self, video: Path, audio: Path, caption: str, output: Path, duration: int):
        """Combine video, audio, and text overlay into final MP4."""
        # Sanitize caption for FFmpeg drawtext filter
        safe_caption = self._wrap_text(caption[:120], max_chars=32)
        escaped = safe_caption.replace("'", "\\'").replace(":", "\\:")

        drawtext_filter = (
            f"drawtext=text='{escaped}'"
            f":fontsize=48:fontcolor=white:font=Arial"
            f":x=(w-text_w)/2:y=h-200"
            f":borderw=3:bordercolor=black@0.8"
            f":line_spacing=12"
        )

        cmd = [
            FFMPEG, "-y",
            "-i", str(video),
            "-i", str(audio),
            "-vf", drawtext_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(duration),
            "-shortest",
            "-movflags", "+faststart",
            str(output),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    @staticmethod
    def _wrap_text(text: str, max_chars: int = 32) -> str:
        """Wrap text for caption overlay."""
        words = text.split()
        lines, current = [], []
        for word in words:
            if sum(len(w) for w in current) + len(current) + len(word) > max_chars:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))
        return "\n".join(lines[:3])  # Max 3 lines
