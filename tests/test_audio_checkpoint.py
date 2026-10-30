"""A retry narrates only the chunks that failed; the good ones stay on disk.

The real AudioGenerator runs, ffmpeg included. DeepInfra's TTS endpoint, a paid
network API, is faked: by `tts`, or by a test's own `fake_tts` where DeepInfra
misbehaves in a way `tts` does not cover. `narrator` fakes the voice upload the
constructor makes.
"""

import asyncio
import subprocess

import pytest

import src.audio as audio
from src import notices
from tests.conftest import needs_ffmpeg, silent_wav

pytestmark = needs_ffmpeg

# Three sentences, each long enough to be its own <=500-char chunk.
TEXT = " ".join(f"Sentence {i} " + "word " * 80 + "ends here." for i in range(3))


def test_failed_chunk_keeps_the_others_and_the_retry_only_redoes_it(tmp_path, narrator, tts):
    tts.fail_on.add("Sentence 1")
    g = narrator()
    out = tmp_path / "abc123def456_title.mp3"

    with pytest.raises(RuntimeError, match=r"1 of 3 TTS chunks failed \(2 kept for retry\)"):
        asyncio.run(g.generate(TEXT, out, http_client=None))
    work = tmp_path / ".partial" / "abc123def456_title"
    assert sorted(p.name for p in work.glob("*.wav")) == ["chunk_000.wav", "chunk_002.wav"]
    assert len(tts.texts) == 3

    tts.fail_on.clear()
    result = asyncio.run(g.generate(TEXT, out, http_client=None))
    assert result == out and out.stat().st_size > 0
    (retried,) = tts.texts[3:]                  # only the missing chunk was synthesised
    assert retried.startswith("Sentence 1")
    assert not work.exists()                    # checkpoints cleared once the MP3 exists


def test_a_busy_model_moves_the_rest_of_the_run_to_the_next_one(tmp_path, monkeypatch, narrator):
    # 2026-10-01: turbo answered 429 "Model busy" for hours; multilingual was up.
    models: list[str] = []

    async def fake_tts(text, voice_id, api_key, http_client, *, model, save_debug_wav=None, tag=""):
        models.append(model[0])
        if model[0].endswith("turbo"):
            raise audio.ModelBusy("DeepInfra rate limited after 5 retries")
        return silent_wav()

    monkeypatch.setattr(audio, "generate_with_deepinfra_async", fake_tts)
    g = narrator()
    out = tmp_path / "abc123def456_title.mp3"
    assert asyncio.run(g.generate(TEXT, out, http_client=None)) == out
    assert models.count("ResembleAI/chatterbox-multilingual") == 3
    (note,) = notices.report()
    assert "multilingual" in note
    # The next episode starts on multilingual and never tries turbo again.
    models.clear()
    asyncio.run(g.generate(TEXT, tmp_path / "fedcba654321_next.mp3", http_client=None))
    assert set(models) == {"ResembleAI/chatterbox-multilingual"}


def test_when_every_model_is_busy_the_chunk_fails(tmp_path, monkeypatch, narrator):
    async def fake_tts(text, voice_id, api_key, http_client, *, model, save_debug_wav=None, tag=""):
        raise audio.ModelBusy("busy")

    monkeypatch.setattr(audio, "generate_with_deepinfra_async", fake_tts)
    with pytest.raises(RuntimeError, match="3 of 3 TTS chunks failed"):
        asyncio.run(narrator().generate(TEXT, tmp_path / "abc123def456_t.mp3", http_client=None))


def test_an_empty_audio_chunk_fails_the_episode(tmp_path, monkeypatch, narrator):
    # One chunk comes back as zero bytes. It used to be left out of the MP3
    # without a word; now it fails like any other chunk, the rest kept for retry.
    async def fake_tts(text, voice_id, api_key, http_client, *, model, save_debug_wav=None, tag=""):
        return b"" if text.startswith("Sentence 1") else silent_wav()

    monkeypatch.setattr(audio, "generate_with_deepinfra_async", fake_tts)
    out = tmp_path / "abc123def456_title.mp3"
    with pytest.raises(RuntimeError, match=r"1 of 3 TTS chunks failed \(2 kept for retry\)"
                                           r".*chunk 2 of 3: no audio"):
        asyncio.run(narrator().generate(TEXT, out, http_client=None))
    assert not out.exists()


@pytest.mark.parametrize("text, seconds", [
    ("Just the one sentence.", 2.0 + 0.1),            # the lead-in, then the chunk
    (TEXT, 2.0 + 3 * 0.1 + 2 * 0.35),                 # a pause between chunks, none after
])
def test_the_mp3_is_the_lead_in_then_the_chunks_with_pauses_between(tmp_path, narrator, tts, text, seconds):
    # `tts` answers each chunk with 0.1 s of silence.
    out = tmp_path / "abc123def456_title.mp3"
    assert asyncio.run(narrator().generate(text, out, http_client=None)) == out
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
                           capture_output=True, text=True, check=True)
    # MP3 frames pad the end by up to a tenth of a second, well short of a pause.
    assert float(probe.stdout) == pytest.approx(seconds, abs=0.1)
