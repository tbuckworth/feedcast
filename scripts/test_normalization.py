"""A/B test for TTS text normalization.

Generates before/after audio samples to compare raw vs. normalized text.
Outputs pairs of WAV files to data/normalization_test/.

Requires DEEPINFRA_API_KEY and OPENROUTER_API_KEY env vars.
"""

import asyncio
import sys
from pathlib import Path

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.audio import generate_with_deepinfra_async, upload_voice_to_deepinfra, DEFAULT_VOICE_SAMPLE
from src.normalizer import TextNormalizer

TEST_CASES = {
    "dates_iso": "The paper was published on 2026-02-07 and revised on 2026-03-15.",
    "dates_us": "The meeting is scheduled for 02/14/2026 and the deadline is 12/31/2026.",
    "dates_relative": "On Jan 3rd, 2025, the 1st version was released. The 23rd revision came on Nov 2nd.",
    "large_numbers": "The model has 175,000,000,000 parameters and was trained on 1.4 trillion tokens over 34 days.",
    "decimals": "The loss decreased from 3.14159 to 0.0042, a 99.87% improvement.",
    "currency": "OpenAI raised $6.6B at a $157B valuation. The compute cost was $100M.",
    "percentages": "The accuracy improved from 78.3% to 94.7%, while the false positive rate dropped to 0.2%.",
    "abbreviations": "The model (e.g. GPT-4) uses RLHF, i.e. reinforcement learning from human feedback, etc.",
    "mixed_content": (
        "On 2026-01-15, Anthropic released Claude 4.5 with 2x the context window. "
        "The benchmark scores improved by 23.4% vs. the previous version. "
        "Training cost approx. $50M over 90 days on 10,000 H100 GPUs. "
        "See https://anthropic.com/research for details."
    ),
    "date_pronunciation": (
        "The events of September 11th, 2001 changed the world. "
        "By 2024-06-15, 23 years had passed. "
        "The 1st amendment was ratified on 12/15/1791."
    ),
}


async def main():
    api_key = __import__("os").environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        print("Error: DEEPINFRA_API_KEY not set")
        sys.exit(1)

    output_dir = Path(__file__).parent.parent / "data" / "normalization_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Upload voice
    project_root = Path(__file__).parent.parent
    voice_path = project_root / DEFAULT_VOICE_SAMPLE
    print(f"Uploading voice sample: {voice_path.name}")
    voice_id = upload_voice_to_deepinfra(voice_path, api_key)

    normalizer = TextNormalizer()

    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0), limits=limits) as client:
        for name, text in TEST_CASES.items():
            print(f"\n{'='*60}")
            print(f"Test: {name}")
            print(f"Raw:        {text[:100]}...")

            # Normalize
            normalized = await normalizer.normalize_for_tts(text)
            print(f"Normalized: {normalized[:100]}...")

            # Generate raw audio
            print(f"  Generating raw audio...")
            raw_audio = await generate_with_deepinfra_async(
                text, voice_id, api_key, client,
                save_debug_wav=output_dir / f"raw_{name}.wav",
            )

            # Generate normalized audio
            print(f"  Generating normalized audio...")
            norm_audio = await generate_with_deepinfra_async(
                normalized, voice_id, api_key, client,
                save_debug_wav=output_dir / f"normalized_{name}.wav",
            )

            print(f"  Saved: raw_{name}.wav ({len(raw_audio)} bytes)")
            print(f"  Saved: normalized_{name}.wav ({len(norm_audio)} bytes)")

    print(f"\n{'='*60}")
    print(f"All test files saved to: {output_dir}")
    print(f"Compare raw_*.wav vs normalized_*.wav for each test case.")


if __name__ == "__main__":
    asyncio.run(main())
