"""Audio generation using DeepInfra Chatterbox-Turbo API with voice cloning."""

import base64
import os
import re
from pathlib import Path

import requests

DEFAULT_VOICE_SAMPLE = "voice_samples/derek_perkins.wav"
MAX_CHUNK_CHARS = 1500  # Safe limit for Chatterbox TTS

# DeepInfra API endpoints
DEEPINFRA_VOICE_UPLOAD_URL = "https://api.deepinfra.com/v1/voices/add"
DEEPINFRA_API_URL = "https://api.deepinfra.com/v1/inference/ResembleAI/chatterbox-turbo"


def upload_voice_to_deepinfra(voice_path: Path, api_key: str) -> str:
    """Upload voice sample to DeepInfra and return voice_id.

    Uploads fresh each session to ensure the voice exists on the server
    handling requests (avoids cross-region replication issues).
    """
    print(f"    Uploading voice sample: {voice_path.name}")

    with open(voice_path, "rb") as f:
        response = requests.post(
            DEEPINFRA_VOICE_UPLOAD_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"files": (voice_path.name, f, "audio/wav")},
            data={"name": voice_path.stem, "description": f"Voice clone of {voice_path.stem}"},
            timeout=60,
        )

    if response.status_code != 200:
        raise RuntimeError(f"Failed to upload voice: {response.status_code} - {response.text}")

    result = response.json()
    voice_id = result.get("voice_id")

    if not voice_id:
        raise RuntimeError(f"No voice_id in response: {result}")

    print(f"    Voice uploaded. voice_id: {voice_id}")
    return voice_id


def split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            parts = re.split(r'(?<=,)\s+', sentence)
            for part in parts:
                if len(part) > max_chars:
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

    return [c for c in chunks if c]


def generate_with_deepinfra(text: str, voice_id: str, api_key: str) -> bytes:
    """Generate audio using DeepInfra inference endpoint with voice cloning."""
    import time

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                DEEPINFRA_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "voice_id": voice_id,
                },
                timeout=300,
            )
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10
                print(f"      Retry {attempt + 2}/{max_retries} in {wait_time}s: {e}")
                time.sleep(wait_time)
                continue
            raise

    if response.status_code != 200:
        raise RuntimeError(f"DeepInfra error {response.status_code}: {response.text}")

    result = response.json()
    audio_b64 = result.get("audio", "")

    if not audio_b64:
        raise RuntimeError(f"No audio in response. Keys: {list(result.keys())}")

    # Strip data URL prefix if present
    if audio_b64.startswith("data:"):
        audio_b64 = audio_b64.split(",", 1)[1]

    audio_data = base64.b64decode(audio_b64)
    print(f"      Got {len(audio_data)} bytes of audio")
    return audio_data


class AudioGenerator:
    """Generates audio from text using DeepInfra Chatterbox API with voice cloning."""

    def __init__(self, voice: str = None, speed: float = None, voice_sample: str = None):
        self._api_key = os.environ.get("DEEPINFRA_API_KEY")
        if not self._api_key:
            raise ValueError("DEEPINFRA_API_KEY environment variable not set")

        if voice_sample is None:
            project_root = Path(__file__).parent.parent
            self._voice_sample = project_root / DEFAULT_VOICE_SAMPLE
        else:
            self._voice_sample = Path(voice_sample)

        if not self._voice_sample.exists():
            raise FileNotFoundError(f"Voice sample not found: {self._voice_sample}")

        # Upload voice fresh each session (no caching - avoids cross-region issues)
        self._voice_id = upload_voice_to_deepinfra(self._voice_sample, self._api_key)

    def _sanitize_filename(self, text: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9\s-]", "", text[:50])
        safe = re.sub(r"\s+", "_", safe.strip())
        return safe.lower() or "audio"

    def generate(self, text: str, output_path: Path, title: str = "audio") -> Path:
        import shutil
        import subprocess
        import tempfile
        import time

        output_path.parent.mkdir(parents=True, exist_ok=True)

        chunks = split_into_chunks(text)
        print(f"    Generating audio in {len(chunks)} chunks via DeepInfra API...")

        with tempfile.TemporaryDirectory() as tmpdir:
            chunk_files = []
            for i, chunk in enumerate(chunks):
                print(f"    Chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                if i > 0:
                    time.sleep(2)
                audio_bytes = generate_with_deepinfra(chunk, self._voice_id, self._api_key)
                if audio_bytes:
                    chunk_path = Path(tmpdir) / f"chunk_{i:03d}.wav"
                    with open(chunk_path, 'wb') as f:
                        f.write(audio_bytes)
                    chunk_files.append(chunk_path)

            if not chunk_files:
                raise ValueError("No audio generated")

            mp3_path = output_path.with_suffix(".mp3")

            if len(chunk_files) == 1:
                # Single chunk: convert WAV to MP3
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", str(chunk_files[0]),
                     "-acodec", "libmp3lame", "-q:a", "2", str(mp3_path)],
                    capture_output=True, text=True, timeout=300,
                )
                if result.returncode == 0 and mp3_path.exists():
                    print(f"      Saved: {mp3_path}")
                    return mp3_path
            else:
                # Multiple chunks: concatenate and convert to MP3
                list_file = Path(tmpdir) / "chunks.txt"
                with open(list_file, 'w') as f:
                    for chunk_path in chunk_files:
                        f.write(f"file '{chunk_path}'\n")

                result = subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                     "-acodec", "libmp3lame", "-q:a", "2", str(mp3_path)],
                    capture_output=True, text=True, timeout=300,
                )
                if result.returncode == 0 and mp3_path.exists():
                    print(f"      Concatenated: {mp3_path}")
                    return mp3_path

            raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    def generate_episode(self, text: str, output_dir: Path, episode_id: str, title: str) -> Path:
        safe_title = self._sanitize_filename(title)
        filename = f"{episode_id}_{safe_title}"
        output_path = output_dir / f"{filename}.mp3"
        return self.generate(text, output_path, title)
