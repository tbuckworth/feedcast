#!/usr/bin/env python3
"""Voice comparison script using Chatterbox TTS voice cloning.

This script generates audio samples from multiple narrator voices to help
select the best voice for the feedcast podcast.

Usage:
    uv run python scripts/compare_voices.py

Voice samples should be placed in voice_samples/ directory as WAV files.
Output will be saved to voice_samples/output/
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import torch
import torchaudio
from chatterbox.tts import ChatterboxTTS

# Sample text from Scott Alexander (Astral Codex Ten) - verbatim mode content
# First paragraph from a representative post
TEST_TEXT = """
I think the single most underrated risk from AI is what I'll call "galaxy-brained"
reasoning. This is when an AI system, through a chain of individually plausible-seeming
arguments, reaches a conclusion that sounds crazy but which the AI is confident about.
The AI might reason: if I could cure cancer, that would save millions of lives. If I
hacked into this hospital database, I could get the data I need to cure cancer faster.
Therefore, I should hack the hospital database. Each step sounds reasonable, but the
conclusion is something we'd never want an AI to do without checking with humans first.
"""

# Alternative shorter text for quick testing
SHORT_TEXT = """
The single most underrated risk from AI is galaxy-brained reasoning. This is when an AI,
through individually plausible arguments, reaches a conclusion that sounds crazy but which
the AI is confident about.
"""


def get_device() -> str:
    """Get the best available device."""
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(device: str) -> ChatterboxTTS:
    """Load the Chatterbox TTS model."""
    print(f"Loading Chatterbox TTS model on {device}...")
    model = ChatterboxTTS.from_pretrained(device=device)
    print("Model loaded successfully.")
    return model


def find_voice_samples(voice_dir: Path) -> list[Path]:
    """Find all voice sample WAV files in the directory."""
    samples = list(voice_dir.glob("*.wav"))
    # Exclude output directory samples
    samples = [s for s in samples if s.parent.name != "output"]
    return sorted(samples)


def generate_audio(
    model: ChatterboxTTS,
    text: str,
    voice_sample: Path,
    output_path: Path,
) -> Path:
    """Generate audio using voice cloning from the given sample."""
    print(f"  Generating audio with voice: {voice_sample.stem}...")

    # Generate audio with voice cloning
    wav = model.generate(
        text=text,
        audio_prompt_path=str(voice_sample),
    )

    # Save the output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(output_path), wav, model.sr)

    print(f"  Saved to: {output_path}")
    return output_path


def main():
    """Run voice comparison experiment."""
    # Setup paths
    project_root = Path(__file__).parent.parent
    voice_dir = project_root / "voice_samples"
    output_dir = voice_dir / "output"

    # Find voice samples
    voice_samples = find_voice_samples(voice_dir)

    if not voice_samples:
        print("No voice samples found in voice_samples/ directory.")
        print("\nPlease add WAV files (5-10 seconds of clean speech) for each voice:")
        print("  - attenborough.wav")
        print("  - pacey.wav")
        print("  - freeman.wav")
        print("  - jones.wav")
        print("  - coyote.wav")
        print("  - vance.wav")
        print("  - perkins.wav")
        print("  - fry.wav")
        print("\nSee the plan documentation for recommended sources.")
        return 1

    print(f"Found {len(voice_samples)} voice sample(s):")
    for sample in voice_samples:
        print(f"  - {sample.name}")
    print()

    # Load model
    device = get_device()
    model = load_model(device)

    # Use shorter text for faster iteration, full text for final comparison
    use_short = "--short" in sys.argv
    text = SHORT_TEXT if use_short else TEST_TEXT
    text_type = "short" if use_short else "full"

    print(f"\nGenerating {text_type} audio samples...")
    print(f"Text ({len(text.split())} words):")
    print(f"  {text[:100]}...")
    print()

    # Generate audio for each voice
    results = []
    for voice_sample in voice_samples:
        output_filename = f"{voice_sample.stem}_{text_type}.wav"
        output_path = output_dir / output_filename

        try:
            generated_path = generate_audio(model, text, voice_sample, output_path)
            results.append((voice_sample.stem, generated_path, "success"))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append((voice_sample.stem, None, str(e)))

    # Summary
    print("\n" + "=" * 60)
    print("VOICE COMPARISON RESULTS")
    print("=" * 60)

    successes = [(name, path) for name, path, status in results if status == "success"]
    failures = [(name, error) for name, _, error in results if error != "success"]

    if successes:
        print(f"\nSuccessfully generated {len(successes)} audio file(s):")
        for name, path in successes:
            print(f"  - {path}")

    if failures:
        print(f"\nFailed to generate {len(failures)} audio file(s):")
        for name, error in failures:
            print(f"  - {name}: {error}")

    print(f"\nOutput directory: {output_dir}")
    print("\nListen to each output and select your preferred voice!")
    print("Then update config.yaml with the chosen voice sample.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
