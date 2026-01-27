"""Audio generation using DeepInfra Chatterbox-Turbo API with voice cloning."""

import base64
import hashlib
import json
import os
import re
from pathlib import Path

import requests

DEFAULT_VOICE_SAMPLE = "voice_samples/derek_perkins.wav"
MAX_CHUNK_CHARS = 1500  # Safe limit for Chatterbox TTS
VOICE_CACHE_FILE = ".voice_cache.json"

# DeepInfra API endpoints
DEEPINFRA_VOICE_UPLOAD_URL = "https://api.deepinfra.com/v1/voices/add"
DEEPINFRA_API_URL = "https://api.deepinfra.com/v1/inference/ResembleAI/chatterbox-turbo"


def _get_voice_file_hash(voice_path: Path) -> str:
    """Get SHA256 hash of voice file for cache key."""
    with open(voice_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def _load_voice_cache(cache_path: Path) -> dict:
    """Load voice cache from file."""
    if cache_path.exists():
        try:
            with open(cache_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_voice_cache(cache_path: Path, cache: dict) -> None:
    """Save voice cache to file."""
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)


def upload_voice_to_deepinfra(voice_path: Path, api_key: str, name: str = None) -> str:
    """Upload voice sample to DeepInfra and return voice_id.

    Args:
        voice_path: Path to the WAV voice sample file
        api_key: DeepInfra API key
        name: Optional name for the voice (defaults to filename)

    Returns:
        voice_id string from DeepInfra
    """
    if name is None:
        name = voice_path.stem

    print(f"    Uploading voice sample to DeepInfra: {voice_path.name}")

    with open(voice_path, "rb") as f:
        response = requests.post(
            DEEPINFRA_VOICE_UPLOAD_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"audio": (voice_path.name, f, "audio/wav")},
            data={"name": name, "description": f"Voice clone of {name}"},
            timeout=60,
        )

    if response.status_code != 200:
        raise RuntimeError(f"Failed to upload voice: {response.status_code} - {response.text}")

    result = response.json()
    voice_id = result.get("voice_id")

    if not voice_id:
        raise RuntimeError(f"No voice_id in response: {result}")

    print(f"    Voice uploaded successfully. voice_id: {voice_id}")
    return voice_id


def get_or_upload_voice(voice_path: Path, api_key: str, cache_dir: Path = None) -> str:
    """Get cached voice_id or upload voice and cache the result.

    Args:
        voice_path: Path to the WAV voice sample file
        api_key: DeepInfra API key
        cache_dir: Directory to store cache file (defaults to voice_path parent)

    Returns:
        voice_id string
    """
    if cache_dir is None:
        cache_dir = voice_path.parent

    cache_path = cache_dir / VOICE_CACHE_FILE
    cache = _load_voice_cache(cache_path)

    # Use file hash as cache key to detect if voice file changed
    file_hash = _get_voice_file_hash(voice_path)
    cache_key = f"{voice_path.name}:{file_hash}"

    if cache_key in cache:
        voice_id = cache[cache_key]
        print(f"    Using cached voice_id: {voice_id}")
        return voice_id

    # Upload voice and cache the result
    voice_id = upload_voice_to_deepinfra(voice_path, api_key, voice_path.stem)
    cache[cache_key] = voice_id
    _save_voice_cache(cache_path, cache)

    return voice_id


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


def generate_with_deepinfra(text: str, voice_id: str, api_key: str) -> bytes:
    """Generate audio using DeepInfra inference endpoint with a pre-uploaded voice.

    Args:
        text: Text to convert to speech
        voice_id: The voice_id from a previously uploaded voice sample
        api_key: DeepInfra API key

    Returns:
        WAV audio bytes
    """
    import time

    # Retry logic with longer timeout
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
                    "voice_id": voice_id,  # Use pre-uploaded voice
                },
                timeout=300,  # 5 minute timeout per chunk
            )
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10  # 10s, 20s, 30s
                print(f"      Connection error: {e}. Retrying in {wait_time}s ({attempt + 2}/{max_retries})...")
                time.sleep(wait_time)
                continue
            raise

    if response.status_code != 200:
        raise RuntimeError(f"DeepInfra API error {response.status_code}: {response.text}")

    # Parse JSON response
    result = response.json()
    audio_b64 = result.get("audio", "")

    if not audio_b64:
        raise RuntimeError(f"No audio in response. Keys: {list(result.keys())}")

    # Strip data URL prefix if present (format: data:audio/wav;base64,ACTUALDATA)
    if audio_b64.startswith("data:"):
        audio_b64 = audio_b64.split(",", 1)[1]

    # Decode base64
    audio_data = base64.b64decode(audio_b64)
    print(f"      Got {len(audio_data)} bytes of audio")

    # Verify we got valid WAV
    if audio_data[:4] == b'RIFF':
        print(f"      Valid WAV audio detected")
    else:
        print(f"      Audio header bytes: {audio_data[:16].hex()}")

    return audio_data


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

        # Get or upload voice and cache the voice_id
        self._voice_id = None  # Lazy initialization

    def _sanitize_filename(self, text: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9\s-]", "", text[:50])
        safe = re.sub(r"\s+", "_", safe.strip())
        return safe.lower() or "audio"

    def _ensure_voice_id(self) -> str:
        """Ensure voice_id is initialized, uploading voice if needed."""
        if self._voice_id is None:
            if not self._voice_sample.exists():
                raise FileNotFoundError(f"Voice sample not found: {self._voice_sample}")
            self._voice_id = get_or_upload_voice(
                self._voice_sample,
                self._api_key,
                cache_dir=self._voice_sample.parent,
            )
        return self._voice_id

    def generate(self, text: str, output_path: Path, title: str = "audio") -> Path:
        import subprocess
        import tempfile
        import time

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Ensure voice is uploaded and get voice_id
        voice_id = self._ensure_voice_id()

        # Split long text into chunks
        chunks = split_into_chunks(text)
        print(f"    Generating audio in {len(chunks)} chunks via DeepInfra API...")

        # Create temp directory for chunks
        with tempfile.TemporaryDirectory() as tmpdir:
            chunk_files = []
            for i, chunk in enumerate(chunks):
                print(f"    Chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                # Add delay between API calls to avoid rate limiting
                if i > 0:
                    time.sleep(2)
                audio_bytes = generate_with_deepinfra(chunk, voice_id, self._api_key)
                if audio_bytes:
                    # Save chunk as WAV (inference endpoint returns WAV)
                    chunk_path = Path(tmpdir) / f"chunk_{i:03d}.wav"
                    with open(chunk_path, 'wb') as f:
                        f.write(audio_bytes)
                    chunk_files.append(chunk_path)

            if not chunk_files:
                raise ValueError("No audio generated from text")

            mp3_path = output_path.with_suffix(".mp3")

            # Concatenate WAV files and convert to MP3
            if len(chunk_files) == 1:
                # Single chunk: just convert to MP3
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", str(chunk_files[0]),
                     "-acodec", "libmp3lame", "-q:a", "2", str(mp3_path)],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode == 0 and mp3_path.exists():
                    print(f"      Converted to MP3: {mp3_path}")
                    return mp3_path
            else:
                # Multiple chunks: concatenate and convert
                list_file = Path(tmpdir) / "chunks.txt"
                with open(list_file, 'w') as f:
                    for chunk_path in chunk_files:
                        f.write(f"file '{chunk_path}'\n")

                result = subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                     "-acodec", "libmp3lame", "-q:a", "2", str(mp3_path)],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode == 0 and mp3_path.exists():
                    print(f"      Concatenated and converted to MP3: {mp3_path}")
                    return mp3_path

            # Fallback: save as WAV
            wav_path = output_path.with_suffix(".wav")
            import shutil
            shutil.copy(chunk_files[0], wav_path)
            print(f"      Fallback: saved as WAV: {wav_path}")
            return wav_path

    def generate_episode(self, text: str, output_dir: Path, episode_id: str, title: str) -> Path:
        safe_title = self._sanitize_filename(title)
        filename = f"{episode_id}_{safe_title}"
        output_path = output_dir / f"{filename}.mp3"
        return self.generate(text, output_path, title)
