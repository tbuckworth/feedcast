#!/usr/bin/env python3
"""Test DeepInfra Kokoro-82M TTS with British male voices.

Tests whether Kokoro can handle 600+ chars without chunking.

Usage:
    uv run python scripts/test_kokoro.py

Requires: DEEPINFRA_API_KEY in environment
"""

import asyncio
import base64
import os
import sys
from pathlib import Path

import httpx

KOKORO_API_URL = "https://api.deepinfra.com/v1/inference/hexgrad/Kokoro-82M"

# Same 602-char test text - NO CHUNKING to test Kokoro's limits
TEST_TEXT = """
I think the single most underrated risk from AI is what I'll call "galaxy-brained"
reasoning. This is when an AI system, through a chain of individually plausible-seeming
arguments, reaches a conclusion that sounds crazy but which the AI is confident about.
The AI might reason: if I could cure cancer, that would save millions of lives. If I
hacked into this hospital database, I could get the data I need to cure cancer faster.
Therefore, I should hack the hospital database. Each step sounds reasonable, but the
conclusion is something we'd never want an AI to do without checking with humans first.
""".strip()


async def generate_kokoro(
    text: str,
    voice: str,
    api_key: str,
    output_path: Path,
) -> Path | None:
    """Generate audio using DeepInfra Kokoro-82M API."""
    print(f"  Generating Kokoro sample with voice: {voice}...")
    print(f"    Text length: {len(text)} chars (testing without chunking)")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            KOKORO_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "output_format": "wav",
                "preset_voice": voice,
            },
        )

        if response.status_code != 200:
            print(f"    ERROR: Kokoro returned {response.status_code}: {response.text[:300]}")
            return None

        result = response.json()

        # Extract audio from response
        audio_b64 = result.get("audio", "")
        if not audio_b64:
            print(f"    ERROR: No audio in response. Keys: {list(result.keys())}")
            return None

        # Strip data URL prefix if present
        if audio_b64.startswith("data:"):
            audio_b64 = audio_b64.split(",", 1)[1]

        audio_data = base64.b64decode(audio_b64)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(audio_data)

        print(f"    Saved: {output_path} ({len(audio_data)} bytes)")
        return output_path


async def main():
    """Run Kokoro TTS test."""
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "voice_samples" / "tts_comparison"

    api_key = os.environ.get("DEEPINFRA_API_KEY")

    if not api_key:
        print("ERROR: DEEPINFRA_API_KEY must be set")
        return 1

    print(f"Output directory: {output_dir}")
    print(f"\nTest text ({len(TEST_TEXT)} chars) - sending WITHOUT chunking:")
    print(f"  {TEST_TEXT[:100]}...")
    print()

    results = []

    # British male voices from Kokoro
    kokoro_voices = [
        ("bm_daniel", "Daniel - British male"),
        ("bm_fable", "Fable - British male (Quality B)"),
        ("bm_george", "George - British male (Quality B)"),
        ("bm_lewis", "Lewis - British male"),
    ]

    print("=== DeepInfra Kokoro-82M British Male Voices ===")
    for voice, description in kokoro_voices:
        print(f"  {description}")
        output_path = output_dir / f"kokoro_{voice}.wav"
        result = await generate_kokoro(TEST_TEXT, voice, api_key, output_path)
        results.append((voice, result))

    # Summary
    print("\n" + "=" * 60)
    print("KOKORO TTS RESULTS")
    print("=" * 60)

    successes = [(name, path) for name, path in results if path]
    failures = [name for name, path in results if not path]

    if successes:
        print(f"\nSuccessfully generated {len(successes)} audio file(s):")
        for name, path in successes:
            print(f"  - {name}: {path.name}")

    if failures:
        print(f"\nFailed to generate {len(failures)} audio file(s):")
        for name in failures:
            print(f"  - {name}")

    print(f"\nOutput directory: {output_dir}")
    print(f"\nKokoro pricing: ~$0.80 per million characters")
    print("Compare with current DeepInfra Chatterbox which required 500-char chunking.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
