#!/usr/bin/env python3
"""TTS provider comparison script for OpenAI male voices.

Usage:
    uv run python scripts/test_tts.py

Requires environment variables:
    OPENAI_API_KEY - OpenAI API key

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


async def generate_openai(
    text: str,
    voice: str,
    api_key: str,
    output_path: Path,
    model: str = "tts-1-hd",
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

    openai_key = os.environ.get("OPENAI_API_KEY")

    if not openai_key:
        print("ERROR: OPENAI_API_KEY must be set")
        return 1

    print(f"Output directory: {output_dir}")
    print(f"\nTest text ({len(TEST_TEXT)} chars):")
    print(f"  {TEST_TEXT[:100]}...")
    print()

    results = []

    # OpenAI male voices (using tts-1-hd for best quality)
    # fable is often noted as having a British quality
    openai_voices = [
        ("echo", "Echo - deep male"),
        ("fable", "Fable - expressive male (often sounds British)"),
        ("onyx", "Onyx - deep authoritative male"),
    ]

    print("=== OpenAI Male Voices (tts-1-hd) ===")
    for voice, description in openai_voices:
        print(f"  {description}")
        output_path = output_dir / f"openai_{voice}.mp3"
        result = await generate_openai(
            TEST_TEXT, voice, openai_key, output_path, model="tts-1-hd"
        )
        results.append((voice, result))

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
    print("\nNote: OpenAI doesn't have explicit British accents.")
    print("'fable' is often noted as having a somewhat British quality.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
