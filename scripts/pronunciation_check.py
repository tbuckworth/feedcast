"""Measure how the production voice actually says a word, before respelling it.

Generates each spelling N times with the cloned voice in a fixed carrier
sentence ("Today, X said yes, and X said no."), then reads the audio back with
a phoneme recogniser and prints the distinct pronunciations with counts. Use it
to test a candidate for config.yaml `pronunciations`: about half of the
plausible respellings tried on 2026-10-08 did not help or made things worse
("Tsvee" for Zvi, "Open Ay-Eye" for OpenAI), so measure, do not guess.

Whisper is no use for this: its language model writes "OpenAI" however the
word was said. The phoneme model (wav2vec2, espeak phonemes) reports sounds.

    bwsrun uv run --with "torch" --with "transformers<5" --with phonemizer \\
        --index https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match \\
        python -m scripts.pronunciation_check "Kokotajlo" "Kokotai-lo" -n 6

Needs DEEPINFRA_API_KEY and ffmpeg. The recogniser runs on CPU (about a
second a clip) and downloads ~1.3 GB on first use.
"""

import argparse
import asyncio
import base64
import collections
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

from src.audio import DEEPINFRA_INFERENCE_URL, DEFAULT_VOICE_SAMPLE, TTS_MODELS, upload_voice_to_deepinfra

CARRIER = "Today, {x} said yes, and {x} said no."
PHONEME_MODEL = "facebook/wav2vec2-lv-60-espeak-cv-ft"


async def synthesise(spellings: list[str], n: int, out: Path) -> None:
    key = os.environ["DEEPINFRA_API_KEY"]
    voice = upload_voice_to_deepinfra(Path(__file__).resolve().parent.parent / DEFAULT_VOICE_SAMPLE, key)
    await asyncio.sleep(5)   # the uploaded voice takes a moment to reach every server
    sem = asyncio.Semaphore(6)
    model, extra = TTS_MODELS[0]
    async with httpx.AsyncClient(timeout=180) as client:
        async def one(i: int, spelling: str, rep: int) -> None:
            async with sem:
                r = await client.post(DEEPINFRA_INFERENCE_URL + model,
                                      headers={"Authorization": f"Bearer {key}"},
                                      json={"text": CARRIER.format(x=spelling), "voice_id": voice,
                                            "cfg_weight": 0.5, "exaggeration": 0.3, **extra})
            r.raise_for_status()
            audio = r.json()["audio"]
            audio = audio.split(",", 1)[1] if audio.startswith("data:") else audio
            (out / f"{i}_{rep}.wav").write_bytes(base64.b64decode(audio))
        await asyncio.gather(*[one(i, s, r) for i, s in enumerate(spellings) for r in range(n)])


def transcribe(spellings: list[str], out: Path) -> None:
    import numpy as np
    import torch
    from transformers import AutoModelForCTC, AutoProcessor

    proc = AutoProcessor.from_pretrained(PHONEME_MODEL)
    model = AutoModelForCTC.from_pretrained(PHONEME_MODEL).eval()
    for i, spelling in enumerate(spellings):
        heard = collections.Counter()
        for wav in sorted(out.glob(f"{i}_*.wav")):
            raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", str(wav), "-f", "s16le", "-ac", "1",
                                  "-ar", "16000", "-"], capture_output=True, check=True).stdout
            audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
            with torch.no_grad():
                ids = model(**proc(audio, sampling_rate=16000, return_tensors="pt")).logits.argmax(-1)
            phones = proc.batch_decode(ids)[0]
            # The word sits between "today" and "said yes", then "and" and "said no".
            first = re.search(r"d (?:eɪ|e|ɪ|i) (.*?) s [ɛeæ] d j", phones)
            second = re.search(r"(?:æ|ɛ|ə|ɐ)?n d? (.*?) s [ɛeæ] d n", phones)
            for m in (first, second):
                heard[m.group(1) if m else f"(unaligned) {phones}"] += 1
        print(f"\n{spelling!r}")
        for phones, count in heard.most_common():
            print(f"  {count:>3} × /{phones}/")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("spellings", nargs="+", help="spellings to compare, e.g. Kokotajlo Kokotai-lo")
    ap.add_argument("-n", type=int, default=6, help="clips per spelling (each says it twice)")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(synthesise(args.spellings, args.n, Path(tmp)))
        transcribe(args.spellings, Path(tmp))


if __name__ == "__main__":
    main()
