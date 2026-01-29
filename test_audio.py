"""Test DeepInfra TTS endpoints to find working audio generation."""
import base64
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
import requests

load_dotenv()

# Old inference endpoint (broken - returns corrupted base64)
INFERENCE_API_URL = "https://api.deepinfra.com/v1/inference/ResembleAI/chatterbox-turbo"

# OpenAI-compatible endpoint (should return raw binary audio)
OPENAI_API_URL = "https://api.deepinfra.com/v1/openai/audio/speech"

VOICE_SAMPLE = "voice_samples/derek_perkins.wav"


def test_openai_endpoint(api_key: str):
    """Test the OpenAI-compatible TTS endpoint."""
    print(f"\n{'='*60}")
    print("Testing OpenAI-compatible endpoint (raw binary response)")
    print(f"URL: {OPENAI_API_URL}")
    print('='*60)

    response = requests.post(
        OPENAI_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "ResembleAI/chatterbox-turbo",
            "input": "Hello, this is a test of the OpenAI compatible endpoint.",
            "voice": "aria",  # Standard voice - voice cloning may require different approach
            "response_format": "mp3",
        },
        timeout=120,
    )

    print(f"Status: {response.status_code}")
    content_type = response.headers.get("content-type", "")
    print(f"Content-Type: {content_type}")

    if response.status_code != 200:
        print(f"Error: {response.text[:500]}")
        return None

    audio_data = response.content
    print(f"Response size: {len(audio_data)} bytes")
    print(f"First 16 bytes (hex): {audio_data[:16].hex()}")

    # Check for MP3 header (ID3 tag or MPEG audio frame sync 0xFF 0xF*)
    if audio_data[:3] == b'ID3' or (len(audio_data) >= 2 and audio_data[0] == 0xff and (audio_data[1] & 0xe0) == 0xe0):
        print("SUCCESS: Detected MP3 format!")
    elif audio_data[:4] == b'RIFF':
        print("Detected WAV format")
    elif audio_data[:4] == b'fLaC':
        print("Detected FLAC format")
    else:
        print(f"Unknown format - first bytes: {audio_data[:4]}")

    # Save it
    out_file = "test_openai_endpoint.mp3"
    Path(out_file).write_bytes(audio_data)
    print(f"Saved: {out_file}")

    # Try ffprobe
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", out_file],
        capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout:
        print(f"ffprobe:\n{result.stdout[:500]}")
    else:
        print(f"ffprobe failed: {result.stderr[:200]}")

    return audio_data


def test_openai_with_voice_clone(api_key: str, voice_b64: str):
    """Test OpenAI endpoint with voice cloning via audio_prompt."""
    print(f"\n{'='*60}")
    print("Testing OpenAI endpoint with voice cloning (audio_prompt)")
    print('='*60)

    response = requests.post(
        OPENAI_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "ResembleAI/chatterbox-turbo",
            "input": "Hello, this is a test with voice cloning.",
            "voice": "custom",
            "audio_prompt": voice_b64,  # Pass voice sample as base64
            "response_format": "mp3",
        },
        timeout=120,
    )

    print(f"Status: {response.status_code}")
    content_type = response.headers.get("content-type", "")
    print(f"Content-Type: {content_type}")

    if response.status_code != 200:
        print(f"Error: {response.text[:500]}")
        return None

    audio_data = response.content
    print(f"Response size: {len(audio_data)} bytes")
    print(f"First 16 bytes (hex): {audio_data[:16].hex()}")

    # Check for MP3 header (ID3 tag or MPEG audio frame sync 0xFF 0xF*)
    if audio_data[:3] == b'ID3' or (len(audio_data) >= 2 and audio_data[0] == 0xff and (audio_data[1] & 0xe0) == 0xe0):
        print("SUCCESS: Detected MP3 format!")
    elif audio_data[:4] == b'RIFF':
        print("Detected WAV format")
    else:
        print(f"Unknown format - first bytes: {audio_data[:4]}")

    # Save it
    out_file = "test_openai_voice_clone.mp3"
    Path(out_file).write_bytes(audio_data)
    print(f"Saved: {out_file}")

    # Verify with ffprobe
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", out_file],
        capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout:
        print(f"ffprobe:\n{result.stdout[:500]}")

    return audio_data


def test_inference_endpoint(api_key: str, voice_b64: str, fmt: str):
    """Test the old inference endpoint (for comparison)."""
    print(f"\n{'='*60}")
    print(f"Testing inference endpoint with output_format: {fmt}")
    print(f"URL: {INFERENCE_API_URL}")
    print('='*60)

    response = requests.post(
        INFERENCE_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "text": "Hello, this is a test.",
            "audio_prompt": voice_b64,
            "output_format": fmt,
        },
        timeout=120,
    )

    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Error: {response.text[:200]}")
        return None

    content_type = response.headers.get("content-type", "")
    print(f"Content-Type: {content_type}")

    if "json" in content_type:
        result = response.json()
        print(f"JSON keys: {list(result.keys())}")
        print(f"Returned output_format: {result.get('output_format')}")
        if "audio" in result:
            audio_b64 = result["audio"]
            padding = len(audio_b64) % 4
            if padding:
                audio_b64 += "=" * (4 - padding)
            audio_data = base64.b64decode(audio_b64)
        else:
            print("No audio key")
            return None
    else:
        audio_data = response.content

    print(f"Audio bytes: {len(audio_data)}")
    print(f"First 16 bytes (hex): {audio_data[:16].hex()}")

    # Save it
    out_file = f"test_inference_{fmt}.bin"
    Path(out_file).write_bytes(audio_data)
    print(f"Saved: {out_file}")

    return audio_data


def test_audio():
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        print("Set DEEPINFRA_API_KEY environment variable")
        return

    # Load voice sample
    voice_b64 = None
    if Path(VOICE_SAMPLE).exists():
        with open(VOICE_SAMPLE, "rb") as f:
            voice_b64 = base64.b64encode(f.read()).decode()
        print(f"Loaded voice sample: {VOICE_SAMPLE}")
    else:
        print(f"Voice sample not found: {VOICE_SAMPLE}")

    # Test 1: OpenAI endpoint with standard voice (should work)
    result1 = test_openai_endpoint(api_key)

    # Test 2: OpenAI endpoint with voice cloning (if voice sample available)
    if voice_b64:
        result2 = test_openai_with_voice_clone(api_key, voice_b64)

        # Test 3: Old inference endpoint (for comparison)
        print("\n\n--- Testing old inference endpoint for comparison ---")
        test_inference_endpoint(api_key, voice_b64, "mp3")

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print("Try playing the generated files:")
    print("  afplay test_openai_endpoint.mp3")
    if voice_b64:
        print("  afplay test_openai_voice_clone.mp3")


if __name__ == "__main__":
    test_audio()
