#!/usr/bin/env python3
"""Generate a Chatterbox TTS sample with Derek Perkins voice cloning."""

import sys
from pathlib import Path

TEST_TEXT = """
I think the single most underrated risk from AI is what I'll call "galaxy-brained"
reasoning. This is when an AI system, through a chain of individually plausible-seeming
arguments, reaches a conclusion that sounds crazy but which the AI is confident about.
The AI might reason: if I could cure cancer, that would save millions of lives. If I
hacked into this hospital database, I could get the data I need to cure cancer faster.
Therefore, I should hack the hospital database. Each step sounds reasonable, but the
conclusion is something we'd never want an AI to do without checking with humans first.
"""


def get_device() -> str:
    """Get the best available device."""
    import torch
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main():
    try:
        print("Importing modules...")
        import torch
        import torchaudio
        from chatterbox.tts import ChatterboxTTS

        device = get_device()
        print(f"Using device: {device}")

        print("Loading Chatterbox TTS model...")
        model = ChatterboxTTS.from_pretrained(device=device)
        print("Model loaded successfully.")

        voice_sample = Path(__file__).parent.parent / "voice_samples/derek_perkins.wav"
        if not voice_sample.exists():
            print(f"ERROR: Voice sample not found: {voice_sample}")
            return 1

        print(f"\nVoice sample: {voice_sample}")
        print(f"Generating audio for {len(TEST_TEXT.split())} words...")
        print("(This may take a few minutes on MPS/CPU...)")

        wav = model.generate(
            text=TEST_TEXT,
            audio_prompt_path=str(voice_sample),
        )

        output_path = Path(__file__).parent.parent / "voice_samples/output/derek_perkins_full.wav"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Saving to {output_path}...")
        torchaudio.save(str(output_path), wav, model.sr)

        duration = wav.shape[1] / model.sr
        print(f"\nSuccess! Generated: {output_path}")
        print(f"Audio duration: {duration:.1f} seconds")
        return 0

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
