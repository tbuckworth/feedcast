"""Audio generation using Chatterbox TTS with Derek Perkins voice cloning."""

import re
from pathlib import Path

DEFAULT_VOICE_SAMPLE = "voice_samples/derek_perkins.wav"
MAX_CHUNK_CHARS = 1500  # Safe limit for Chatterbox TTS


def get_device() -> str:
    """Get the best available compute device."""
    import torch
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    # Split by sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        # If single sentence is too long, split by comma or just force split
        if len(sentence) > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            # Split long sentence by commas
            parts = re.split(r'(?<=,)\s+', sentence)
            for part in parts:
                if len(part) > max_chars:
                    # Force split at max_chars
                    for i in range(0, len(part), max_chars):
                        chunks.append(part[i:i+max_chars].strip())
                elif len(current_chunk) + len(part) + 1 <= max_chars:
                    current_chunk = current_chunk + " " + part if current_chunk else part
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = part
        elif len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk = current_chunk + " " + sentence if current_chunk else sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    return [c for c in chunks if c]  # Filter empty chunks


class AudioGenerator:
    """Generates audio from text using Chatterbox TTS with voice cloning."""

    def __init__(self, voice: str = None, speed: float = None, voice_sample: str = None):
        # voice/speed params kept for backward compatibility (ignored)
        self._model = None
        self._device = None

        if voice_sample is None:
            project_root = Path(__file__).parent.parent
            self._voice_sample = project_root / DEFAULT_VOICE_SAMPLE
        else:
            self._voice_sample = Path(voice_sample)

    @property
    def device(self) -> str:
        if self._device is None:
            self._device = get_device()
        return self._device

    @property
    def model(self):
        if self._model is None:
            from chatterbox.tts import ChatterboxTTS
            self._model = ChatterboxTTS.from_pretrained(device=self.device)
        return self._model

    def _sanitize_filename(self, text: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9\s-]", "", text[:50])
        safe = re.sub(r"\s+", "_", safe.strip())
        return safe.lower() or "audio"

    def generate(self, text: str, output_path: Path, title: str = "audio") -> Path:
        import torch
        import torchaudio

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._voice_sample.exists():
            raise FileNotFoundError(f"Voice sample not found: {self._voice_sample}")

        # Split long text into chunks
        chunks = split_into_chunks(text)
        print(f"    Generating audio in {len(chunks)} chunks...")

        audio_segments = []
        for i, chunk in enumerate(chunks):
            print(f"    Chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
            wav = self.model.generate(text=chunk, audio_prompt_path=str(self._voice_sample))
            if wav is not None and wav.numel() > 0:
                audio_segments.append(wav)

        if not audio_segments:
            raise ValueError("No audio generated from text")

        # Concatenate all segments
        full_audio = torch.cat(audio_segments, dim=1)

        wav_path = output_path.with_suffix(".wav")
        torchaudio.save(str(wav_path), full_audio, self.model.sr)
        return wav_path

    def generate_episode(self, text: str, output_dir: Path, episode_id: str, title: str) -> Path:
        safe_title = self._sanitize_filename(title)
        filename = f"{episode_id}_{safe_title}"
        output_path = output_dir / f"{filename}.wav"
        return self.generate(text, output_path, title)
