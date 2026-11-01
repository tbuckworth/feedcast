"""People are named where the source names them, and never where it does not.

On 1 Nov 2026 the briefing called Alex Turner "a former Google DeepMind safety
researcher": his Alignment Forum post spoke in the first person, the
briefing's input carried no byline, and the writer may add no name from
memory. Titus wants every researcher named, because he may know them. So the
byline reaches the writer, LessWrong usernames become full names, and every
prompt that writes about people says to name them and never to guess.
"""

import asyncio
from datetime import datetime, timezone

import httpx
import yaml

from src import digest, lesswrong, news, processor, verify
from src.config import CONFIG_PATH
from src.monitor import FeedEntry
from src.news import NewsAggregator
from src.processor import ContentProcessor
from tests.conftest import FakeApi

AF = "https://www.alignmentforum.org/posts/RHxaRkarGp9snWoKY/explaining-ai-might"


def _answers(monkeypatch, answer) -> list[str]:
    """Send LessWrong's GraphQL requests to `answer`; the hosts asked, in order."""
    asked: list[str] = []
    real = httpx.AsyncClient

    def handle(request):
        asked.append(request.url.host)
        return answer(request)
    monkeypatch.setattr(lesswrong.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handle), **kw))
    return asked


def _users(*users: dict) -> httpx.Response:
    first, *rest = users
    return httpx.Response(200, json={"data": {"post": {"result": {
        "user": first, "coauthors": rest}}}})


class TestAuthorNames:

    def test_a_username_comes_back_with_the_full_name(self, monkeypatch):
        asked = _answers(monkeypatch, lambda r: _users(
            {"displayName": "TurnTrout", "fullName": "Alex Turner"}))
        assert asyncio.run(lesswrong.author_names(AF)) == ["Alex Turner (TurnTrout)"]
        assert asked == ["www.alignmentforum.org"]

    def test_coauthors_are_named_too_and_a_bare_username_stays(self, monkeypatch):
        _answers(monkeypatch, lambda r: _users(
            {"displayName": "TurnTrout", "fullName": "Alex Turner"},
            {"displayName": "Buck", "fullName": ""},
            {"displayName": "Owain Evans", "fullName": "Owain Evans"}))
        assert asyncio.run(lesswrong.author_names(AF)) == [
            "Alex Turner (TurnTrout)", "Buck", "Owain Evans"]

    def test_no_full_name_on_the_profile_leaves_the_feeds_name(self, monkeypatch):
        """Zvi's feed says "Zvi Mowshowitz" and his profile only "Zvi"."""
        _answers(monkeypatch, lambda r: _users({"displayName": "Zvi", "fullName": None}))
        assert asyncio.run(lesswrong.author_names(AF)) is None

    def test_a_failed_lookup_leaves_the_feeds_name(self, monkeypatch, capsys):
        _answers(monkeypatch, lambda r: httpx.Response(502))
        assert asyncio.run(lesswrong.author_names(AF)) is None
        assert "author lookup for RHxaRkarGp9snWoKY failed" in capsys.readouterr().out

    def test_other_sites_are_not_asked(self, monkeypatch):
        asked = _answers(monkeypatch, lambda r: httpx.Response(500))
        assert asyncio.run(lesswrong.author_names("https://techcrunch.com/2026/x")) is None
        assert asked == []


def _agg() -> NewsAggregator:
    return NewsAggregator(sources=[], prompt="Write.", lookback_hours=24, full_text_stories=12,
                          max_article_chars=6000, author="Feedcast Bot", verify=False)


class TestBriefingBylines:

    def test_a_news_feeds_byline_is_kept(self, monkeypatch, tmp_path):
        now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        path = tmp_path / "af.xml"
        path.write_text(
            "<?xml version='1.0'?><rss version='2.0' "
            "xmlns:dc='http://purl.org/dc/elements/1.1/'><channel><title>AF</title>"
            f"<item><title>Explaining</title><link>{AF}</link><dc:creator>TurnTrout</dc:creator>"
            f"<description>I gave a talk.</description><pubDate>{now}</pubDate></item>"
            f"<item><title>Unsigned</title><link>https://bbc.example/1</link>"
            f"<description>Body.</description><pubDate>{now}</pubDate></item>"
            "</channel></rss>")
        agg = _agg()
        agg.sources = [{"name": "Alignment Forum", "url": str(path), "category": "ai_safety"}]
        signed, unsigned = asyncio.run(agg.fetch_all_sources())
        assert signed["authors"] == ["TurnTrout"] and unsigned["authors"] == []

    def test_the_writer_sees_the_full_name_after_the_url(self, monkeypatch):
        _answers(monkeypatch, lambda r: _users(
            {"displayName": "TurnTrout", "fullName": "Alex Turner"}))
        art = {"title": "Explaining", "source": "Alignment Forum", "category": "ai_safety",
               "summary": "Until June, my job at Google DeepMind...", "url": AF,
               "authors": ["TurnTrout"], "published": datetime.now(timezone.utc)}
        unsigned = {**art, "url": "https://bbc.example/1", "authors": []}
        agg = _agg()
        asyncio.run(agg.resolve_bylines([art, unsigned]))
        text = agg._format_articles_for_prompt([art, unsigned])
        assert (f"- [Alignment Forum] Explaining\n  URL: {AF}\n  By: Alex Turner (TurnTrout)\n"
                "  Until June") in text
        # No byline, no By: line. URL straight after the title is what
        # scripts/model_upgrade_test.py parses the selected stories by.
        assert "- [Alignment Forum] Explaining\n  URL: https://bbc.example/1\n  Until" in text

    def test_generate_briefing_resolves_the_selected_stories_bylines(self, monkeypatch):
        asked = []

        async def names(link):
            asked.append(link)
            return ["Alex Turner (TurnTrout)"] if link == AF else None
        monkeypatch.setattr(news, "author_names", names)
        monkeypatch.setattr(news, "extract_article", lambda url: {"text": "FULL"})
        arts = [{"title": f"S{i}", "source": "AF", "category": "ai_safety", "summary": "b",
                 "url": AF if i == 0 else f"https://e.example/{i}", "authors": ["TurnTrout"],
                 "published": datetime.now(timezone.utc)} for i in range(3)]
        agg = _agg()
        agg.full_text_stories = 2
        agg.client = client = FakeApi([f'["{AF}", "https://e.example/1"]',
                                       "Here is your daily news briefing."])
        monkeypatch.setattr(agg, "fetch_all_sources", lambda: asyncio.sleep(0, arts))
        asyncio.run(agg.generate_briefing())
        assert asked == [AF, "https://e.example/1"]          # the selected stories only
        assert "By: Alex Turner (TurnTrout)" in client.calls[1]["messages"][1]["content"]


def test_a_summary_writer_is_given_the_full_name(monkeypatch):
    async def names(link):
        return ["Alex Turner (TurnTrout)"]
    monkeypatch.setattr(processor, "author_names", names)
    seen = []

    async def write(system, user, **kw):
        seen.append(user)
        return verify.Written(text="Summary.", writer={}, fidelity=None, bundle="")
    monkeypatch.setattr(processor, "write_checked", write)
    entry = FeedEntry(id="x", title="Explaining", link=AF, content="<p>I gave a talk.</p>",
                      published=datetime(2026, 11, 1), author="TurnTrout",
                      feed_name="LessWrong Curated", authors=["TurnTrout"])
    p = ContentProcessor("Summarise.", verify=False, auto_verbatim_limit=24000)
    asyncio.run(p.summarize(entry))
    assert seen[0].startswith("Title: Explaining\nAuthor: Alex Turner (TurnTrout)\n")
    assert entry.author == "TurnTrout"      # the episode's credit is the feed's, as before


class TestPrompts:
    """Every prompt that writes about people says to name them and never to guess."""

    def test_both_writer_prompts_name_people_and_never_guess(self):
        cfg = yaml.safe_load(CONFIG_PATH.read_text())
        prompts = {"default_prompt": cfg["default_prompt"],
                   "news_briefing": cfg["news_briefing"]["prompt"]}
        prompts |= {f["name"]: f["prompt"] for f in cfg["feeds"] if f.get("prompt")}
        for name, prompt in prompts.items():
            flat = " ".join(prompt.split())
            assert "Naming people" in flat, name
            assert '"an AI safety researcher, [their full name],' in flat, name
            assert "do not supply one, however sure you are who it is" in flat, name
        assert '"By:" line' in " ".join(prompts["news_briefing"].split())

    def test_the_digest_keeps_names_and_adds_none(self):
        assert "Keep every person's name the script gives" in digest.PROMPT
        assert "Never add a name the script does not give" in digest.PROMPT

    def test_the_checker_flags_a_name_the_source_does_not_give(self):
        assert ("A person's name the source does not give (in its text or its Author or By "
                "line) is unsupported and high severity") in verify.CHECK_PROMPT

