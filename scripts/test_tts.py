#!/usr/bin/env python3
"""TTS voice comparison script, routed through OpenRouter.

Dev utility only — the pipeline itself uses DeepInfra Chatterbox, because
OpenRouter's speech models offer preset voices but no voice cloning, and
Feedcast needs the cloned Derek Perkins voice.

Usage:
    uv run python scripts/test_tts.py

Requires environment variables:
    OPENROUTER_API_KEY - OpenRouter API key

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


# OpenRouter mirrors OpenAI's /v1/audio/speech contract, so the request shape
# is unchanged from the original OpenAI version of this script — only the host,
# the key and the namespaced model id differ.
SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"
SPEECH_MODEL = "openai/gpt-audio"


async def generate_speech(
    text: str,
    voice: str,
    api_key: str,
    output_path: Path,
    model: str = SPEECH_MODEL,
) -> Path | None:
    """Generate audio via OpenRouter's speech endpoint."""
    print(f"  Generating {model} sample with voice: {voice}...")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            SPEECH_URL,
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
            print(f"    ERROR: OpenRouter returned {response.status_code}: {response.text[:200]}")
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

    api_key = os.environ.get("OPENROUTER_API_KEY")

    if not api_key:
        print("ERROR: OPENROUTER_API_KEY must be set")
        return 1

    print(f"Output directory: {output_dir}")
    print(f"\nTest text ({len(TEST_TEXT)} chars):")
    print(f"  {TEST_TEXT[:100]}...")
    print()

    results = []

    # Preset male voices exposed by the speech model
    voices = [
        ("echo", "Echo - deep male"),
        ("fable", "Fable - expressive male (often sounds British)"),
        ("onyx", "Onyx - deep authoritative male"),
    ]

    print(f"=== Male Voices ({SPEECH_MODEL}) ===")
    for voice, description in voices:
        print(f"  {description}")
        output_path = output_dir / f"{voice}.mp3"
        result = await generate_speech(TEST_TEXT, voice, api_key, output_path)
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
    print("\nNote: these are preset voices — no cloning. For the cloned")
    print("Derek Perkins voice the pipeline uses, see scripts/test_voice_cloning.sh.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
