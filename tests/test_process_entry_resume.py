"""A retried entry resumes at the stage that failed; it does not redo the writer.

The real ContentProcessor, TextNormalizer, AudioGenerator and digest run. Only
the paid APIs behind them are faked: the model routes (`routes`), and
DeepInfra's voice upload and TTS (`narrator`, `tts`). Which stages ran is read
off the requests those fakes saw.
"""

import asyncio
from datetime import datetime

import pytest

from src.main import Attempt, process_entry
from src.monitor import FeedEntry
from src.normalizer import TextNormalizer
from src.processor import ContentProcessor
from tests.conftest import FakeApi, needs_ffmpeg

pytestmark = needs_ffmpeg

SPOKEN = "Summary of T by A.\n\nScript with forty-five percent.\n\nEnd of T."
BULLET = "The script puts the figure at 45%, the post says."


def _entry():
    return FeedEntry(id="e1", title="T", link="https://x/t", content="<p>45%</p>",
                     published=datetime.now(), author="A", feed_name="F")


def _processor():
    return ContentProcessor("p", verify=False, auto_verbatim_limit=24000)


def test_second_attempt_skips_the_stages_that_already_produced_text(tmp_path, routes, narrator, tts):
    routes["anthropic"] = FakeApi(["Script with 45%."])          # the writer
    routes["openrouter"] = FakeApi([SPOKEN])                      # the normaliser
    routes["openai"] = FakeApi([f"- {BULLET}", f"- {BULLET}"])     # the digest, once per attempt
    audio, attempt = narrator(), Attempt()
    tts.fail_on.add("forty-five")

    with pytest.raises(RuntimeError, match="TTS chunks failed"):
        asyncio.run(process_entry(_entry(), "summarize", "p", _processor(), audio,
                                  TextNormalizer(), tmp_path, None, attempt))
    assert attempt.stage == "tts"
    assert "Script with 45%." in attempt.processed_text
    assert attempt.normalized_text == SPOKEN

    tts.fail_on.clear()
    entry, path = asyncio.run(process_entry(_entry(), "summarize", "p", _processor(), audio,
                                            TextNormalizer(), tmp_path, None, attempt))
    assert path.exists() and path.stat().st_size > 0 and entry.bullets == [BULLET]
    # One writer call and one normaliser call across both attempts; narrated twice.
    assert len(routes["anthropic"].calls) == 1 and len(routes["openrouter"].calls) == 1
    assert len(tts.texts) == 2 and all("forty-five percent" in t for t in tts.texts)
    # The first attempt's digest is cancelled with the failure; the retry's
    # bullets still come from the unspoken script, not the normalised one.
    assert routes["openai"].asked()[-1] == attempt.processed_text


def test_resume_from_a_stored_script_goes_straight_to_narration(tmp_path, routes, narrator, tts):
    routes["anthropic"] = FakeApi([])                 # the writer: not called
    routes["openrouter"] = FakeApi([])                # the normaliser: not called
    routes["openai"] = FakeApi([f"- {BULLET}"])
    attempt = Attempt(stage="tts", normalized_text="kept script", number=2)

    asyncio.run(process_entry(_entry(), "verbatim", "p", _processor(), narrator(),
                              TextNormalizer(), tmp_path, None, attempt))
    assert attempt.processed_text is None             # the post was not cleaned again
    assert routes["anthropic"].calls == [] and routes["openrouter"].calls == []
    assert tts.texts == ["kept script"]
    assert routes["openai"].asked() == ["kept script"]
    assert attempt.stage == "digest"


@pytest.mark.parametrize("row, stage", [
    ({"normalized_text": ""}, "process"),                                # failed_entries, no script
    ({"normalized_text": "spoken"}, "tts"),                              # failed_entries, script kept
    ({"processed_text": "written", "normalized_text": ""}, "normalize"),  # deferred, cleaned
    ({"processed_text": "written", "normalized_text": "spoken"}, "tts"),  # deferred, normalised
])
def test_a_stored_row_resumes_at_the_first_stage_without_a_script(row, stage):
    attempt = Attempt.from_row(row, number=2)
    assert (attempt.stage, attempt.number) == (stage, 2)
    assert attempt.processed_text == (row.get("processed_text") or None)
    assert attempt.normalized_text == (row["normalized_text"] or None)
