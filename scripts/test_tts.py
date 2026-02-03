#!/usr/bin/env python3
"""TTS provider comparison script for ElevenLabs and OpenAI.

This script generates audio samples from both TTS providers to help
select the best one for the feedcast podcast.

Usage:
    uv run python scripts/test_tts.py

Requires environment variables:
    ELEVENLABS_API_KEY - ElevenLabs API key
    OPENAI_API_KEY - OpenAI API key (optional, will skip if not set)

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


async def generate_openai(
    text: str,
    voice: str,
    api_key: str,
    output_path: Path,
    model: str = "tts-1",
) -> Path | None:
    """Generate audio using OpenAI TTS API."""
    print(f"  Generating OpenAI {model} sample with voice: {voice}...")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": text,
                "voice": voice,
                "response_format": "mp3",
            },
        )

        if response.status_code != 200:
            print(f"    ERROR: OpenAI returned {response.status_code}: {response.text[:200]}")
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
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not elevenlabs_key and not openai_key:
        print("ERROR: At least one of ELEVENLABS_API_KEY or OPENAI_API_KEY must be set")
        return 1

    print(f"Output directory: {output_dir}")
    print(f"\nTest text ({len(TEST_TEXT)} chars):")
    print(f"  {TEST_TEXT[:100]}...")
    print()

    results = []

    # ElevenLabs voices to test
    # Daniel - British, steady broadcaster voice
    elevenlabs_voices = [
        ("onwK4e9ZLuTAKqWW03F9", "daniel"),  # Daniel - British steady broadcaster
        ("pqHfZKP75CvOlQylNhV4", "bill"),    # Bill - American narrator
    ]

    if elevenlabs_key:
        print("=== ElevenLabs ===")
        for voice_id, voice_name in elevenlabs_voices:
            output_path = output_dir / f"elevenlabs_{voice_name}.mp3"
            result = await generate_elevenlabs(
                TEST_TEXT, voice_id, voice_name, elevenlabs_key, output_path
            )
            results.append(("ElevenLabs", voice_name, result))
    else:
        print("Skipping ElevenLabs (ELEVENLABS_API_KEY not set)")

    # OpenAI voices to test
    # British-sounding options: echo, fable, onyx
    openai_voices = ["echo", "fable", "onyx"]

    if openai_key:
        print("\n=== OpenAI ===")
        for voice in openai_voices:
            # Test both tts-1 and tts-1-hd
            for model in ["tts-1", "tts-1-hd"]:
                output_path = output_dir / f"openai_{model}_{voice}.mp3"
                result = await generate_openai(
                    TEST_TEXT, voice, openai_key, output_path, model
                )
                results.append(("OpenAI", f"{model}/{voice}", result))
    else:
        print("\nSkipping OpenAI (OPENAI_API_KEY not set)")

    # Summary
    print("\n" + "=" * 60)
    print("TTS COMPARISON RESULTS")
    print("=" * 60)

    successes = [(provider, voice, path) for provider, voice, path in results if path]
    failures = [(provider, voice) for provider, voice, path in results if not path]

    if successes:
        print(f"\nSuccessfully generated {len(successes)} audio file(s):")
        for provider, voice, path in successes:
            print(f"  - {provider} ({voice}): {path.name}")

    if failures:
        print(f"\nFailed to generate {len(failures)} audio file(s):")
        for provider, voice in failures:
            print(f"  - {provider} ({voice})")

    print(f"\nOutput directory: {output_dir}")
    print("\nListen to each output and select your preferred voice!")
    print("\nMonthly cost estimates (~180k chars/month):")
    print("  - ElevenLabs Starter: ~$20+ (60k chars included)")
    print("  - OpenAI tts-1: ~$2.70")
    print("  - OpenAI tts-1-hd: ~$5.40")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
