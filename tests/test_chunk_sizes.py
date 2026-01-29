"""Test TTS quality at different input lengths.

Sends the SAME passage at increasing character counts to DeepInfra
Chatterbox as single TTS calls (no chunking), so you can listen and
hear exactly where quality starts to degrade.

Outputs: data/chunk_size_test/sample_{N}chars.wav for each size.

Run via GHA workflow 'test-chunk-sizes.yml' (needs DEEPINFRA_API_KEY).
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from src.audio import generate_with_deepinfra_async, upload_voice_to_deepinfra
import os

# A representative podcast-style passage (~2500 chars of natural prose).
# Deliberately includes varied sentence lengths, technical terms, and
# conversational cadence — typical of what the pipeline actually generates.
SAMPLE_TEXT = (
    "Scott Adams appreciated these considerations earlier and more deeply than "
    "most people. His genius was in finding the humor not just in bad bosses, "
    "but in the entire enterprise of white-collar work. The cubicle became his "
    "canvas, the pointy-haired boss his muse. Every strip was a small act of "
    "rebellion against the absurdity of corporate life. "
    "When your father came home every day looking haggard and worn out, you "
    "understood on some level that work was a kind of suffering. But Dilbert "
    "showed that it was also a kind of comedy. The meetings that could have been "
    "emails, the mission statements that meant nothing, the org charts that "
    "changed every quarter. All of it was material. "
    "The niche that became Dilbert was office humor. In the eighties and nineties, "
    "saying that you hated your job was considered a form of social bonding. "
    "You could be that guy, proudly boasting to your date about how you were too "
    "smart for your company. There was a support group for people like you. It was "
    "called everybody, and they met at the bar. "
    "This was more than just comedy. It was a worldview. The idea that the world "
    "is run by idiots, and the smart people are stuck in cubicles, resonated with "
    "millions of engineers and programmers. Dilbert gave them permission to feel "
    "superior without having to actually do anything about it. "
    "If humor, like religion, is an opiate of the masses, then Adams was the "
    "most successful drug dealer of the nineties. His strips were syndicated in "
    "over two thousand newspapers. His books sold millions. He became, against "
    "all odds, exactly what Dilbert could never be: successful. "
    "Wally is brilliant but lazy, so he at least enjoys a fool's paradise. "
    "Dogbert, an inveterate scammer with a passing resemblance to a certain "
    "former president, rules through sheer audacity. Alice has anger management "
    "issues that would get her fired at any real company. And the pointy-haired "
    "boss remains blissfully ignorant of his own incompetence. "
    "The question that Adams never quite answered was whether Dilbert himself "
    "was complicit in the system. He complained endlessly but never left. He saw "
    "the absurdity but kept showing up. Was that wisdom or cowardice? Perhaps "
    "it was just realism. Most people cannot simply quit and start a company. "
    "The mortgage needs paying, the kids need braces, and the health insurance "
    "comes from the employer. Dilbert understood this. His rebellion was internal, "
    "expressed through eye rolls and sarcastic comments that his boss never "
    "noticed. In the end, he was all of us."
)

# Character counts to test — from well-below the current limit to way above.
CHUNK_SIZES = [200, 350, 500, 650, 800, 1000, 1250, 1500, 2000]


def truncate_at_word(text: str, max_chars: int) -> str:
    """Truncate text at a word boundary, not mid-word."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Find last space
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        return truncated[:last_space].rstrip(".,;:!? ")
    return truncated


async def main():
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        print("ERROR: DEEPINFRA_API_KEY not set")
        sys.exit(1)

    project_root = Path(__file__).parent.parent
    voice_path = project_root / "voice_samples" / "derek_perkins.wav"
    output_dir = project_root / "data" / "chunk_size_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Total sample text: {len(SAMPLE_TEXT)} chars")
    print(f"Testing sizes: {CHUNK_SIZES}")
    print()

    # Upload voice
    voice_id = upload_voice_to_deepinfra(voice_path, api_key)
    print()

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        for size in CHUNK_SIZES:
            text = truncate_at_word(SAMPLE_TEXT, size)
            actual_len = len(text)
            out_path = output_dir / f"sample_{size}chars_actual{actual_len}.wav"

            print(f"--- {size} chars (actual: {actual_len}) ---")
            print(f"  Text: {text[:80]!r}...")
            print(f"  Ends: ...{text[-60:]!r}")

            try:
                audio_data = await generate_with_deepinfra_async(
                    text, voice_id, api_key, client, save_debug_wav=out_path,
                )
                print(f"  OK: {len(audio_data)} bytes -> {out_path.name}")
            except Exception as e:
                print(f"  FAILED: {type(e).__name__}: {e}")

            print()

    print("Done. Listen to files in data/chunk_size_test/")
    print("Compare samples to find where quality degrades.")


if __name__ == "__main__":
    asyncio.run(main())
