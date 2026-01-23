"""Audio generation using Kokoro TTS."""

import re
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline


class AudioGenerator:
    """Generates audio from text using Kokoro TTS."""

    def __init__(self, voice: str = "bm_george", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self._pipeline = None

    @property
    def pipeline(self) -> KPipeline:
        """Lazy-load the TTS pipeline."""
        if self._pipeline is None:
            # Use American English for 'a' voices, British for 'b' voices
            lang_code = "a" if self.voice.startswith("a") else "b"
            self._pipeline = KPipeline(lang_code=lang_code)
        return self._pipeline

    def _sanitize_filename(self, text: str) -> str:
        """Create a safe filename from text."""
        # Take first 50 chars, remove non-alphanumeric
        safe = re.sub(r"[^a-zA-Z0-9\s-]", "", text[:50])
        safe = re.sub(r"\s+", "_", safe.strip())
        return safe.lower() or "audio"

    def generate(
        self,
        text: str,
        output_path: Path,
        title: str = "audio",
    ) -> Path:
        """Generate audio from text and save to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate audio
        audio_segments = []
        for _, _, audio in self.pipeline(text, voice=self.voice, speed=self.speed):
            audio_segments.append(audio)

        if not audio_segments:
            raise ValueError("No audio generated from text")

        # Concatenate all segments
        full_audio = np.concatenate(audio_segments)

        # Save as WAV first, then we can convert to MP3 if needed
        wav_path = output_path.with_suffix(".wav")
        sf.write(wav_path, full_audio, 24000)

        return wav_path

    def generate_episode(
        self,
        text: str,
        output_dir: Path,
        episode_id: str,
        title: str,
    ) -> Path:
        """Generate an episode audio file."""
        safe_title = self._sanitize_filename(title)
        filename = f"{episode_id}_{safe_title}"
        output_path = output_dir / f"{filename}.wav"

        return self.generate(text, output_path, title)
