"""Audio generation using DeepInfra Chatterbox-Turbo API with voice cloning."""

import base64
import os
import re
from pathlib import Path

import requests

DEFAULT_VOICE_SAMPLE = "voice_samples/derek_perkins.wav"
MAX_CHUNK_CHARS = 1500  # Safe limit for Chatterbox TTS
DEEPINFRA_API_URL = "https://api.deepinfra.com/v1/inference/ResembleAI/chatterbox-turbo"


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


def generate_with_deepinfra(text: str, voice_sample_path: Path, api_key: str) -> bytes:
    """Generate audio using DeepInfra Chatterbox API."""
    with open(voice_sample_path, "rb") as f:
        voice_b64 = base64.b64encode(f.read()).decode()

    response = requests.post(
        DEEPINFRA_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "audio_prompt": voice_b64,
            "output_format": "wav",
        },
        timeout=120,
    )

    if response.status_code != 200:
        raise RuntimeError(f"DeepInfra API error {response.status_code}: {response.text}")

    # Check if response is raw audio (binary) or JSON
    content_type = response.headers.get("content-type", "")
    print(f"      Response content-type: {content_type}")

    if "audio" in content_type:
        print(f"      Got raw audio response: {len(response.content)} bytes")
        return response.content

    # Try to parse as JSON
    try:
        result = response.json()
        print(f"      JSON response keys: {list(result.keys())}")
    except Exception as e:
        raise RuntimeError(f"Failed to parse response: {e}, content-type: {content_type}, content: {response.text[:500]}")

    # Try different possible keys for audio data
    audio_data = None
    for key in ["audio", "audio_base64", "output", "data"]:
        if key in result:
            audio_data = result[key]
            print(f"      Found audio in key '{key}', type: {type(audio_data).__name__}, len: {len(str(audio_data)[:100])}")
            break

    if audio_data is None:
        raise RuntimeError(f"No audio in response. Keys: {list(result.keys())}, Response: {str(result)[:500]}")

    # Handle if audio_data is a dict with nested data
    if isinstance(audio_data, dict):
        print(f"      Audio data is dict with keys: {list(audio_data.keys())}")
        audio_data = audio_data.get("audio") or audio_data.get("data")

    if not audio_data:
        raise RuntimeError(f"Empty audio data in response: {result}")

    # Check if it's a URL instead of base64
    if isinstance(audio_data, str) and audio_data.startswith("http"):
        print(f"      Audio is URL: {audio_data[:100]}")
        audio_response = requests.get(audio_data, timeout=60)
        return audio_response.content

    print(f"      Decoding base64 audio, length: {len(audio_data)}")
    return base64.b64decode(audio_data)


class AudioGenerator:
    """Generates audio from text using DeepInfra Chatterbox API with voice cloning."""

    def __init__(self, voice: str = None, speed: float = None, voice_sample: str = None):
        # voice/speed params kept for backward compatibility (ignored)
        self._api_key = os.environ.get("DEEPINFRA_API_KEY")
        if not self._api_key:
            raise ValueError("DEEPINFRA_API_KEY environment variable not set")

        if voice_sample is None:
            project_root = Path(__file__).parent.parent
            self._voice_sample = project_root / DEFAULT_VOICE_SAMPLE
        else:
            self._voice_sample = Path(voice_sample)

    def _sanitize_filename(self, text: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9\s-]", "", text[:50])
        safe = re.sub(r"\s+", "_", safe.strip())
        return safe.lower() or "audio"

    def generate(self, text: str, output_path: Path, title: str = "audio") -> Path:
        import wave

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._voice_sample.exists():
            raise FileNotFoundError(f"Voice sample not found: {self._voice_sample}")

        # Split long text into chunks
        chunks = split_into_chunks(text)
        print(f"    Generating audio in {len(chunks)} chunks via DeepInfra API...")

        audio_segments = []
        for i, chunk in enumerate(chunks):
            print(f"    Chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
            audio_bytes = generate_with_deepinfra(chunk, self._voice_sample, self._api_key)
            if audio_bytes:
                audio_segments.append(audio_bytes)

        if not audio_segments:
            raise ValueError("No audio generated from text")

        # Concatenate WAV files
        wav_path = output_path.with_suffix(".wav")

        # Read first segment to get audio parameters
        import io
        with wave.open(io.BytesIO(audio_segments[0]), 'rb') as first_wav:
            params = first_wav.getparams()

        # Write concatenated audio
        with wave.open(str(wav_path), 'wb') as output_wav:
            output_wav.setparams(params)
            for segment in audio_segments:
                with wave.open(io.BytesIO(segment), 'rb') as seg_wav:
                    output_wav.writeframes(seg_wav.readframes(seg_wav.getnframes()))

        return wav_path

    def generate_episode(self, text: str, output_dir: Path, episode_id: str, title: str) -> Path:
        safe_title = self._sanitize_filename(title)
        filename = f"{episode_id}_{safe_title}"
        output_path = output_dir / f"{filename}.wav"
        return self.generate(text, output_path, title)
