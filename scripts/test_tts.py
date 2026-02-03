#!/usr/bin/env python3
"""TTS provider comparison script for ElevenLabs British male voices.

This script generates audio samples from ElevenLabs British male voices
to help select the best one for the feedcast podcast.

Usage:
    uv run python scripts/test_tts.py

Requires environment variables:
    ELEVENLABS_API_KEY - ElevenLabs API key

Output will be saved to voice_samples/tts_comparison/
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx

# Sample text - representative podcast content
TEST_TEXT = """
I think the single most underrated risk from AI is what I'll call "galaxy-brained"
reasoning. This is when an AI system, through a chain of individually plausible-seeming
arguments, reaches a conclusion that sounds crazy but which the AI is confident about.
The AI might reason: if I could cure cancer, that would save millions of lives. If I
hacked into this hospital database, I could get the data I need to cure cancer faster.
Therefore, I should hack the hospital database. Each step sounds reasonable, but the
conclusion is something we'd never want an AI to do without checking with humans first.
""".strip()


async def generate_elevenlabs(
    text: str,
    voice_id: str,
    voice_name: str,
    api_key: str,
    output_path: Path,
) -> Path | None:
    """Generate audio using ElevenLabs API."""
    print(f"  Generating ElevenLabs sample with voice: {voice_name}...")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            url,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
            },
        )

        if response.status_code != 200:
            print(f"    ERROR: ElevenLabs returned {response.status_code}: {response.text[:200]}")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)

        print(f"    Saved: {output_path}")
        return output_path


async def main():
    """Run TTS provider comparison."""
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "voice_samples" / "tts_comparison"

    elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY")

    if not elevenlabs_key:
        print("ERROR: ELEVENLABS_API_KEY must be set")
        return 1

    print(f"Output directory: {output_dir}")
    print(f"\nTest text ({len(TEST_TEXT)} chars):")
    print(f"  {TEST_TEXT[:100]}...")
    print()

    results = []

    # ElevenLabs British male voices
    elevenlabs_voices = [
        ("onwK4e9ZLuTAKqWW03F9", "daniel"),   # Daniel - British, deep, authoritative broadcaster
        ("JBFqnCBsd6RMkjVDRZzb", "george"),   # George - British, warm, middle-aged narrator
        ("N2lVS1w4EtoT3dr4eOWO", "callum"),   # Callum - British, hoarse, mature
        ("TX3LPaxmHKxFdv7VOQHJ", "liam"),     # Liam - British, young, articulate
        ("iP95p4xoKVk53GoZ742B", "chris"),    # Chris - British, casual, middle-aged
    ]

    print("=== ElevenLabs British Male Voices ===")
    for voice_id, voice_name in elevenlabs_voices:
        output_path = output_dir / f"elevenlabs_{voice_name}.mp3"
        result = await generate_elevenlabs(
            TEST_TEXT, voice_id, voice_name, elevenlabs_key, output_path
        )
        results.append((voice_name, result))

    # Summary
    print("\n" + "=" * 60)
    print("TTS COMPARISON RESULTS")
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
    print("\nListen to each output and select your preferred voice!")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
