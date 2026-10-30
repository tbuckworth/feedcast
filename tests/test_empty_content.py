"""An empty post fails its episode instead of publishing junk.

Before, a post whose content cleaned to nothing was narrated as "Summary of
<title>. No content available for: <title>. End of <title>." when summarised,
and as just its intro and outro when read in full.
"""

import asyncio
from datetime import datetime

import pytest

from src.main import Attempt, process_entry
from src.monitor import FeedEntry
from src.processor import ContentProcessor
from tests.conftest import FakeApi


def _entry(content: str, entry_id: str = "acx-1") -> FeedEntry:
    return FeedEntry(id=entry_id, title="Does Georgism Work?", link="https://acx/1",
                     content=content, published=datetime(2026, 10, 30), author="Scott Alexander",
                     feed_name="Scott Alexander")


@pytest.mark.parametrize("mode", ["summarize", "verbatim", "auto"])
@pytest.mark.parametrize("content", ["", "<p> </p>", "<script>var x = 1;</script>"])
def test_an_empty_post_fails_instead_of_being_narrated(routes, mode, content):
    routes["anthropic"] = FakeApi(["A summary of nothing."])
    processor = ContentProcessor("Summarise.", verify=False, auto_verbatim_limit=24000)
    with pytest.raises(ValueError, match="no content to narrate in 'Does Georgism Work\\?'"):
        asyncio.run(processor.process(_entry(content), mode))
    assert routes["anthropic"].calls == []          # nothing was sent to the writer


def test_an_empty_briefing_fails_too(routes):
    processor = ContentProcessor("Summarise.", verify=False, auto_verbatim_limit=24000)
    with pytest.raises(ValueError, match="no content to narrate"):
        asyncio.run(processor.process(_entry("", "news-briefing-2026-10-30"), "verbatim"))


def test_an_empty_post_fails_its_entry_at_the_process_stage(tmp_path):
    processor = ContentProcessor("Summarise.", verify=False, auto_verbatim_limit=24000)
    attempt = Attempt()
    with pytest.raises(ValueError, match="no content to narrate"):
        # Normaliser and narrator are never reached, so None stands in for both.
        asyncio.run(process_entry(_entry("<p></p>"), "verbatim", "p", processor, None, None,
                                  tmp_path, None, attempt))
    assert attempt.stage == "process" and attempt.processed_text is None


def test_a_post_with_text_is_still_read_out(routes):
    processor = ContentProcessor("Summarise.", verify=False, auto_verbatim_limit=24000)
    text = asyncio.run(processor.process(_entry("<p>Land value taxes work.</p>"), "verbatim"))
    assert "Land value taxes work." in text

