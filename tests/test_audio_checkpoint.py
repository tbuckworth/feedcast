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
    g._model = 0
    return g


def test_failed_chunk_keeps_the_others_and_the_retry_only_redoes_it(tmp_path, monkeypatch):
    calls: list[str] = []
    fail_on = {"Sentence 1"}

    async def fake_tts(text, voice_id, api_key, http_client, save_debug_wav=None, tag="", model=None):
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


def test_a_busy_model_moves_the_rest_of_the_run_to_the_next_one(tmp_path, monkeypatch):
    # 2026-10-01: turbo answered 429 "Model busy" for hours; multilingual was up.
    models: list[str] = []

    async def fake_tts(text, voice_id, api_key, http_client, save_debug_wav=None, tag="", model=None):
        models.append(model[0])
        if model[0].endswith("turbo"):
            raise audio.ModelBusy("DeepInfra rate limited after 5 retries")
        return _wav_bytes()

    monkeypatch.setattr(audio, "generate_with_deepinfra_async", fake_tts)
    monkeypatch.setattr(audio.llm, "fallback_log", [])
    g = _generator()
    out = tmp_path / "abc123def456_title.mp3"
    assert asyncio.run(g.generate(TEXT, out, "title", http_client=None)) == out
    assert models.count("ResembleAI/chatterbox-multilingual") == 3
    assert len(audio.llm.fallback_log) == 1 and "multilingual" in audio.llm.fallback_log[0]
    # The next episode starts on multilingual and never tries turbo again.
    models.clear()
    asyncio.run(g.generate(TEXT, tmp_path / "fedcba654321_next.mp3", "next", http_client=None))
    assert set(models) == {"ResembleAI/chatterbox-multilingual"}


def test_when_every_model_is_busy_the_chunk_fails(tmp_path, monkeypatch):
    async def fake_tts(text, voice_id, api_key, http_client, save_debug_wav=None, tag="", model=None):
        raise audio.ModelBusy("busy")

    monkeypatch.setattr(audio, "generate_with_deepinfra_async", fake_tts)
    monkeypatch.setattr(audio.llm, "fallback_log", [])
    with pytest.raises(RuntimeError, match="3 of 3 TTS chunks failed"):
        asyncio.run(_generator().generate(TEXT, tmp_path / "abc123def456_t.mp3", "t", http_client=None))
