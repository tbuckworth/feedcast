"""Import AI's closing fiction through the real pipeline, with only paid APIs faked."""

import asyncio
from datetime import datetime

import pytest

from src.config import load_config
from src.main import Attempt, Workers, process_entry
from src.monitor import FeedEntry
from src.processor import ContentProcessor
from tests.conftest import FakeApi, needs_ffmpeg


def entry(content):
    return FeedEntry("issue", "Issue", "https://example.org/issue", content,
                     datetime(2026, 11, 23), "Jack Clark", "Import AI")


def section():
    return next(f for f in load_config().feeds if f.name == "Import AI").verbatim_section


@pytest.mark.parametrize("opening", [
    "<p>Tech Tales:</p><p><strong>The Visitor</strong><br>[Tomorrow]</p>",
    "<p><strong>Tech Tales:<br></strong><br><strong>The Visitor</strong><br>[Tomorrow]</p>",
    "<p>***</p><p><strong>The Visitor<br></strong><em>[Tomorrow]</em></p>",
])
@needs_ffmpeg
def test_story_follows_summary_without_going_through_a_language_model(
        opening, tmp_path, routes, tts, narrator, monkeypatch):
    # Uploading a cloned voice, the LLMs and the speech service are paid boundaries.
    monkeypatch.setattr("src.main.AudioGenerator", lambda **kw: narrator())
    w = Workers.from_config(load_config())
    routes["anthropic"] = FakeApi(["The news summary.", '{"flags":[]}'])
    routes["openrouter"] = FakeApi(["Summary of Issue by Jack Clark. The news summary."])
    routes["openai"] = FakeApi(["- News."])
    article = entry("<p>Research news.</p>" + opening +
                    "<p>“Come <em>here</em>,” she said.</p>"
                    "<p><strong>Things that inspired this story</strong>: Rain.</p>"
                    "<p>A separate news item.</p>")
    attempt = Attempt()
    _, path = asyncio.run(process_entry(article, "summarize", "Write a summary.",
                                        w.processor, w.audio_gen, w.normalizer,
                                        tmp_path, None, attempt))
    assert path.stat().st_size > 0
    assert "Research news." in routes["anthropic"].asked()[0]
    assert "A separate news item." in routes["anthropic"].asked()[0]
    for route in routes.values():
        assert all("The Visitor" not in text for text in route.asked())
    assert len(tts.texts) == 2
    assert "The news summary." in tts.texts[0]
    assert tts.texts[1].startswith(section().introduction)
    assert "The Visitor" in tts.texts[1] and "“Come here,” she said." in tts.texts[1]
    assert tts.texts[1].endswith("End of Issue.")
    assert "Rain." not in tts.texts[1]


@pytest.mark.parametrize("html", ["<p>A speech about science.</p>",
                                 "<p>Tech Tales:</p><p>Uncertain ending.</p>"])
def test_summary_only_when_no_complete_story(html):
    p = ContentProcessor("p", verify=False, auto_verbatim_limit=1000,
                         verbatim_sections={"Import AI": section()})
    p.client = FakeApi(["A summary."])
    text = asyncio.run(p.process(entry(html), "summarize"))
    assert text == "Summary of Issue by Jack Clark.\n\nA summary.\n\nEnd of Issue."
