"""Two-call briefing: choose stories from blurbs, write from their full text."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from src import news
from src.news import NewsAggregator


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies); self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.replies.pop(0)))])


def _articles(n):
    return [{"title": f"Story {i}", "source": "BBC World", "category": "geopolitics",
             "summary": f"Blurb {i}", "published": datetime.now(timezone.utc),
             "url": f"https://example.com/{i}"} for i in range(n)]


def _agg(client, **kw):
    agg = NewsAggregator(sources=[], prompt="Write the briefing.", verify=False, **kw)
    agg.client = client
    return agg


def test_selection_keeps_only_known_urls_in_order_and_caps_n():
    client = FakeClient(['Here you go: ["https://example.com/3", "https://evil.example/x", '
                         '"https://example.com/1", "https://example.com/3", "https://example.com/0"]'])
    agg = _agg(client, full_text_stories=2)
    chosen = asyncio.run(agg.select_stories(_articles(5)))
    assert [a["url"] for a in chosen] == ["https://example.com/3", "https://example.com/1"]
    assert "Pick the 2 most worth covering" in client.calls[0]["messages"][0]["content"]


def test_few_articles_skip_the_selection_call():
    client = FakeClient([])
    agg = _agg(client, full_text_stories=12)
    assert len(asyncio.run(agg.select_stories(_articles(4)))) == 4 and client.calls == []
    assert asyncio.run(_agg(client, full_text_stories=0).select_stories(_articles(4))) == []


def test_unparseable_selection_falls_back_to_blurbs():
    agg = _agg(FakeClient(["I cannot decide."]), full_text_stories=2)
    assert asyncio.run(agg.select_stories(_articles(5))) == []


def test_full_text_fetch_caps_length_and_keeps_blurb_on_failure(monkeypatch):
    def fake_extract(url):
        if url.endswith("/1"):
            raise news.extract_article.__globals__["ExtractionError"]("paywall")
        return {"text": "Full article text. " * 100}
    monkeypatch.setattr(news, "extract_article", fake_extract)
    agg = _agg(FakeClient([]), max_article_chars=50)
    arts = _articles(2)
    got = asyncio.run(agg.fetch_full_text(arts))
    assert got == 1
    assert len(arts[0]["text"]) == 50 and "text" not in arts[1]


def test_writer_input_has_full_text_for_chosen_and_headlines_for_the_rest():
    agg = _agg(FakeClient([]))
    arts = _articles(3)
    arts[0]["text"] = "THE FULL TEXT OF STORY 0"
    formatted = agg._format_briefing_input(arts, [arts[0]])
    assert "## Selected stories" in formatted and "THE FULL TEXT OF STORY 0" in formatted
    assert "Blurb 0" not in formatted
    assert "## Other headlines" in formatted and "Story 1" in formatted and "Blurb 1" not in formatted
    # No selection: exactly the old blurb listing.
    assert agg._format_briefing_input(arts, []) == agg._format_articles_for_prompt(arts)


def test_generate_briefing_wires_select_fetch_write(monkeypatch):
    arts = _articles(3)
    client = FakeClient(['["https://example.com/2"]', "Here is your daily news briefing."])
    agg = _agg(client, full_text_stories=1)

    async def fake_fetch_all():
        return arts
    monkeypatch.setattr(agg, "fetch_all_sources", fake_fetch_all)
    monkeypatch.setattr(news, "extract_article", lambda url: {"text": "FULL 2"})

    entry = asyncio.run(agg.generate_briefing())
    assert entry.content == "Here is your daily news briefing."
    writer_input = client.calls[1]["messages"][1]["content"]
    assert "FULL 2" in writer_input and "Story 0" in writer_input and "Blurb 0" not in writer_input
    assert "FULL 2" in entry.bundle and entry.fidelity is None
    assert len(entry.sources) == 3  # digest can still cite any article
