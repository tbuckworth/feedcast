"""A retried entry resumes at the stage that failed; it does not redo the writer."""

import asyncio
from datetime import datetime
from pathlib import Path

import src.main as main
from src.main import Attempt, process_entry
from src.monitor import FeedEntry


def _entry():
    return FeedEntry(id="e1", title="T", link="https://x/t", content="<p>45%</p>",
                     published=datetime.now(), author="A", feed_name="F")


class Processor:
    calls = 0
    async def process(self, entry, mode, prompt, title=None):
        Processor.calls += 1
        return "Script with 45%."


class Normalizer:
    calls = 0
    unnormalized_chars = 0
    async def normalize_for_tts(self, text):
        Normalizer.calls += 1
        return "Script with forty-five percent."


class Audio:
    def __init__(self, fail_first: bool):
        self.fail_first, self.calls = fail_first, 0
    async def generate_episode(self, text, audio_dir, episode_id, title, http_client):
        self.calls += 1
        if self.fail_first:
            self.fail_first = False
            raise RuntimeError("3 of 10 TTS chunks failed")
        p = Path(audio_dir) / f"{episode_id}.mp3"
        p.write_bytes(b"mp3")
        return p


def _run(coro):
    return asyncio.run(coro)


def test_second_attempt_skips_the_stages_that_already_produced_text(tmp_path, monkeypatch):
    digested = []
    async def fake_bullets(text, **kw):
        digested.append(text)
        return ["a bullet"]
    monkeypatch.setattr(main, "safe_bullets", fake_bullets)
    Processor.calls = Normalizer.calls = 0
    audio, attempt = Audio(fail_first=True), Attempt()

    try:
        _run(process_entry(_entry(), "summarize", "p", Processor(), audio, Normalizer(),
                           tmp_path, None, attempt))
        raise AssertionError("first attempt should fail at tts")
    except RuntimeError:
        pass
    assert attempt.stage == "tts"
    assert attempt.processed_text == "Script with 45%."
    assert attempt.normalized_text == "Script with forty-five percent."

    entry, path = _run(process_entry(_entry(), "summarize", "p", Processor(), audio, Normalizer(),
                                     tmp_path, None, attempt))
    assert path.exists() and entry.bullets == ["a bullet"]
    assert (Processor.calls, Normalizer.calls, audio.calls) == (1, 1, 2)
    # The first attempt's digest is cancelled with the failure; the retry's
    # bullets still come from the unspoken script, not the normalised one.
    assert digested[-1] == "Script with 45%."


def test_resume_from_a_stored_script_goes_straight_to_narration(tmp_path, monkeypatch):
    digested = []
    async def fake_bullets(text, **kw):
        digested.append(text)
        return []
    monkeypatch.setattr(main, "safe_bullets", fake_bullets)
    Processor.calls = Normalizer.calls = 0
    audio = Audio(fail_first=False)
    attempt = Attempt(stage="tts", normalized_text="kept script", number=2)

    _run(process_entry(_entry(), "verbatim", "p", Processor(), audio, Normalizer(),
                       tmp_path, None, attempt))
    assert (Processor.calls, Normalizer.calls, audio.calls) == (0, 0, 1)
    assert digested == ["kept script"]
    assert attempt.stage == "digest"
