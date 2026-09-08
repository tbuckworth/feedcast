"""A retry narrates only the chunks that failed; the good ones stay on disk."""

import asyncio
import io
import shutil
import wave

import pytest

import src.audio as audio
from src.audio import AudioGenerator

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

# Three sentences, each long enough to be its own <=500-char chunk.
TEXT = " ".join(f"Sentence {i} " + "word " * 80 + "ends here." for i in range(3))


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b"\0\0" * 2400)   # 0.1 s of silence
    return buf.getvalue()


def _generator() -> AudioGenerator:
    g = AudioGenerator.__new__(AudioGenerator)
    g._voice_id, g._api_key = "v", "k"
    g._semaphore = asyncio.Semaphore(5)
    return g


def test_failed_chunk_keeps_the_others_and_the_retry_only_redoes_it(tmp_path, monkeypatch):
    calls: list[str] = []
    fail_on = {"Sentence 1"}

    async def fake_tts(text, voice_id, api_key, http_client, save_debug_wav=None, tag=""):
        calls.append(text[:10])
        if any(text.startswith(f) for f in fail_on):
            raise audio.httpx.ReadError("")
        return _wav_bytes()

    monkeypatch.setattr(audio, "generate_with_deepinfra_async", fake_tts)
    g = _generator()
    out = tmp_path / "abc123def456_title.mp3"

    with pytest.raises(RuntimeError, match=r"1 of 3 TTS chunks failed \(2 kept for retry\)"):
        asyncio.run(g.generate(TEXT, out, "title", http_client=None))
    work = tmp_path / ".partial" / "abc123def456_title"
    assert sorted(p.name for p in work.glob("*.wav")) == ["chunk_000.wav", "chunk_002.wav"]
    assert len(calls) == 3

    fail_on.clear()
    result = asyncio.run(g.generate(TEXT, out, "title", http_client=None))
    assert result == out and out.stat().st_size > 0
    assert calls[3:] == ["Sentence 1"]          # only the missing chunk was synthesised
    assert not work.exists()                    # checkpoints cleared once the MP3 exists
