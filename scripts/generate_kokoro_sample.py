#!/usr/bin/env python3
"""Generate a Kokoro TTS sample with bm_george voice."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

TEST_TEXT = """
I think the single most underrated risk from AI is what I'll call "galaxy-brained"
reasoning. This is when an AI system, through a chain of individually plausible-seeming
arguments, reaches a conclusion that sounds crazy but which the AI is confident about.
The AI might reason: if I could cure cancer, that would save millions of lives. If I
hacked into this hospital database, I could get the data I need to cure cancer faster.
Therefore, I should hack the hospital database. Each step sounds reasonable, but the
conclusion is something we'd never want an AI to do without checking with humans first.
"""


def main():
    try:
        print("Importing modules...")
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline

        print("Creating Kokoro pipeline (British English)...")
        pipeline = KPipeline(lang_code="b")
        print("Pipeline created successfully.")
    except Exception as e:
        print(f"ERROR during setup: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    try:
        print(f"\nGenerating audio for {len(TEST_TEXT.split())} words...")
        audio_segments = []
        for i, (gs, ps, audio) in enumerate(pipeline(TEST_TEXT, voice="bm_george", speed=1.0)):
            print(f"  Generated segment {i+1}")
            audio_segments.append(audio)

        if not audio_segments:
            print("ERROR: No audio generated!")
            return 1

        print(f"\nConcatenating {len(audio_segments)} segments...")
        full_audio = np.concatenate(audio_segments)

        output_path = Path(__file__).parent.parent / "voice_samples/output/kokoro_bm_george_full.wav"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Saving to {output_path}...")
        sf.write(output_path, full_audio, 24000)

        print(f"\nSuccess! Generated: {output_path}")
        print(f"Audio duration: {len(full_audio)/24000:.1f} seconds")
        return 0
    except Exception as e:
        print(f"ERROR during generation: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
