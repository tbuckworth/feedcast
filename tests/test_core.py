"""Unit tests that make no network calls: the one model call, the briefing
writer's, is answered by a recording fake."""

import asyncio
import hashlib
import subprocess
from datetime import datetime

import pytest

from src.audio import split_into_chunks
from src.config import PodcastMetaConfig, load_config
from src.feed import FeedGenerator
from src.env import env_flag
from src.html_text import clean_html, small_table_to_prose
from src.monitor import FeedMonitor, briefing_id, episode_id, is_briefing
from src.news import PREVIOUS_BRIEFINGS_HEADER, NewsAggregator
from tests.conftest import FakeApi, feed_xml, needs_ffmpeg, silent_mp3


# --- split_into_chunks (src/audio.py) ---


class TestSplitIntoChunks:
    def test_short_text_single_chunk(self):
        text = "Hello world. This is a test."
        chunks = split_into_chunks(text, max_chars=500)
        assert chunks == [text]

    def test_splits_at_sentence_boundary(self):
        s1 = "First sentence here."
        s2 = "Second sentence here."
        text = f"{s1} {s2}"
        chunks = split_into_chunks(text, max_chars=25)
        assert chunks == [s1, s2]

    def test_comma_fallback_for_long_sentence(self):
        # Single sentence longer than max_chars, with commas
        text = "Alpha bravo charlie, delta echo foxtrot, golf hotel india."
        chunks = split_into_chunks(text, max_chars=30)
        assert len(chunks) > 1
        # All chunks should fit in the limit (or be single comma-parts)
        for chunk in chunks:
            assert len(chunk) <= 30 or "," not in chunk

    def test_hard_split_for_long_word(self):
        text = "A" * 600
        chunks = split_into_chunks(text, max_chars=500)
        assert len(chunks) == 2
        assert chunks[0] == "A" * 500
        assert chunks[1] == "A" * 100

    def test_empty_input(self):
        assert split_into_chunks("") == []

    def test_whitespace_only(self):
        assert split_into_chunks("   ") == []

    def test_no_chunk_exceeds_limit_on_normal_text(self):
        text = ". ".join([f"Sentence number {i} with some filler words" for i in range(20)])
        chunks = split_into_chunks(text, max_chars=100)
        for chunk in chunks:
            assert len(chunk) <= 100


# --- clean_html (src/html_text.py) ---


class TestCleanHtml:
    def test_removes_script_and_style(self):
        html = "<p>Hello</p><script>alert('x')</script><style>.x{}</style><p>World</p>"
        result = clean_html(html)
        assert "alert" not in result
        assert ".x{}" not in result
        assert "Hello" in result
        assert "World" in result

    def test_collapses_whitespace(self):
        html = "<p>  Hello    World  </p>"
        result = clean_html(html)
        assert "Hello" in result
        assert "World" in result
        # No runs of multiple spaces
        assert "    " not in result

    def test_empty_html(self):
        assert clean_html("") == ""
        assert clean_html("<div></div>") == ""

    def test_strips_nav_footer_header(self):
        html = "<nav>Menu</nav><p>Content</p><footer>Copyright</footer>"
        result = clean_html(html)
        assert "Menu" not in result
        assert "Copyright" not in result
        assert "Content" in result

    def test_preserves_paragraph_breaks(self):
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        result = clean_html(html)
        assert "First paragraph." in result
        assert "Second paragraph." in result


# --- small_table_to_prose (src/html_text.py) ---


class TestTableToProseSimple:
    def _make_table(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").find("table")

    def test_header_value_pairs(self):
        html = "<table><tr><th>Name</th><th>Score</th></tr><tr><td>Alice</td><td>95</td></tr></table>"
        result = small_table_to_prose(self._make_table(html))
        assert "Name: Alice" in result
        assert "Score: 95" in result

    def test_multi_row(self):
        html = """<table>
            <tr><th>City</th><th>Pop</th></tr>
            <tr><td>NYC</td><td>8M</td></tr>
            <tr><td>LA</td><td>4M</td></tr>
        </table>"""
        result = small_table_to_prose(self._make_table(html))
        assert "City: NYC" in result
        assert "City: LA" in result
        # Rows are joined by ". "
        assert ". " in result

    def test_empty_table(self):
        html = "<table></table>"
        result = small_table_to_prose(self._make_table(html))
        assert result == ""


# --- _format_duration (src/feed.py) ---


class TestFormatDuration:
    def setup_method(self):
        config = PodcastMetaConfig(
            title="T", description="D", author="A",
            email="e@e.com", language="en", base_url="http://x", category="Technology",
        )
        self.gen = FeedGenerator(config, retention_days=30)

    def test_zero(self):
        assert self.gen._format_duration(0) == "00:00:00"

    def test_minutes(self):
        assert self.gen._format_duration(125) == "00:02:05"

    def test_hours_minutes_seconds(self):
        assert self.gen._format_duration(3661) == "01:01:01"


# --- _format_rfc822 (src/feed.py) ---


class TestFormatRfc822:
    def setup_method(self):
        config = PodcastMetaConfig(
            title="T", description="D", author="A",
            email="e@e.com", language="en", base_url="http://x", category="Technology",
        )
        self.gen = FeedGenerator(config, retention_days=30)

    def test_known_datetime(self):
        dt = datetime(2025, 1, 15, 14, 30, 0)
        result = self.gen._format_rfc822(dt)
        assert result == "Wed, 15 Jan 2025 14:30:00 +0000"


# --- episode_id (src/monitor.py) ---


class TestEpisodeId:
    def test_deterministic(self):
        assert episode_id("foo") == episode_id("foo")

    def test_12_char_hex(self):
        result = episode_id("test-entry-id")
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_matches_sha256_prefix(self):
        entry_id = "https://example.com/post/123"
        expected = hashlib.sha256(entry_id.encode()).hexdigest()[:12]
        assert episode_id(entry_id) == expected


# --- briefing_id, is_briefing (src/monitor.py) ---


def test_a_briefing_is_known_by_the_id_it_was_given():
    assert briefing_id("2026-10-30") == "news-briefing-2026-10-30"
    assert is_briefing(briefing_id("2026-10-30"))
    assert not is_briefing("https://www.astralcodexten.com/p/news-briefing-2026-10-30")


# --- env_flag (src/env.py) ---


@pytest.mark.parametrize("value, on", [
    ("true", True), (" TRUE ", True), ("1", True), ("Yes", True),
    ("false", False), ("0", False), ("", False), ("on", False),
])
def test_env_flag_reads_true_1_and_yes_as_on(monkeypatch, value, on):
    monkeypatch.setenv("FEEDCAST_FLAG", value)
    assert env_flag("FEEDCAST_FLAG") is on


def test_an_unset_env_flag_is_off(monkeypatch):
    monkeypatch.delenv("FEEDCAST_FLAG", raising=False)
    assert env_flag("FEEDCAST_FLAG") is False


# --- _build_briefing_description (src/feed.py) ---


class TestBuildBriefingDescription:
    def test_skips_opener_extracts_bullets(self):
        content = (
            "Here is your daily news briefing for February 13, 2026.\n\n"
            "The European Union announced new AI regulations today. These rules "
            "will affect major tech companies.\n\n"
            "OpenAI released a new model called GPT-5. The model shows significant "
            "improvements in reasoning.\n\n"
            "Markets rallied on positive economic data. The S&P 500 rose two percent."
        )
        result = FeedGenerator._build_briefing_description("Daily News Briefing", content)
        assert result.startswith("Daily News Briefing\n\nTopics covered:\n")
        assert "- The European Union announced new AI regulations today" in result
        assert "- OpenAI released a new model called GPT-5" in result
        assert "- Markets rallied on positive economic data" in result
        # Opener should not appear as a bullet
        assert "Here is your daily" not in result.split("Topics covered:")[1]

    def test_handles_short_content(self):
        result = FeedGenerator._build_briefing_description("Title", "Just one paragraph.")
        assert result == "Title"

    def test_max_six_bullets(self):
        paragraphs = ["Opener paragraph."] + [f"Topic {i} happened. More details." for i in range(10)]
        content = "\n\n".join(paragraphs)
        result = FeedGenerator._build_briefing_description("Title", content)
        bullet_count = result.count("\n- ")
        assert bullet_count == 6

    def test_empty_content(self):
        result = FeedGenerator._build_briefing_description("Title", "")
        assert result == "Title"


# --- Skip patterns (regex matching from config) ---


class TestSkipPatterns:
    """config.yaml's ACX skip_patterns, run through the real feed filter."""

    @pytest.fixture(autouse=True, scope="class")
    def _acx(self, request, tmp_path_factory):
        # One database for the class: fetch_feed only reads it.
        (request.cls.acx,) = [f for f in load_config().feeds if f.name == "Scott Alexander"]
        request.cls.monitor = FeedMonitor(tmp_path_factory.mktemp("acx") / "posts.db")

    def _should_skip(self, title: str) -> bool:
        # An undated item and no age window: only the skip patterns are under test.
        kept = self.monitor.fetch_feed(feed_xml((title, None)), self.acx.name,
                                       self.acx.skip_patterns, max_age_hours=None)
        return not kept

    def test_skips_open_threads(self):
        assert self._should_skip("Open Thread 350")
        assert self._should_skip("Hidden Open Thread 350")

    def test_skips_links_posts(self):
        assert self._should_skip("Links for January 2026")
        assert self._should_skip("Links For February 2026")

    def test_skips_classifieds(self):
        assert self._should_skip("ACX Classifieds")

    def test_skips_meetups(self):
        assert self._should_skip("Meetups Everywhere Fall 2026")

    def test_skips_mantic_monday(self):
        assert self._should_skip("Mantic Monday 2/10/26")

    def test_skips_highlights(self):
        assert self._should_skip("Highlights From The Comments On AI Risk")
        assert self._should_skip("Highlights from the Comments on Prediction Markets")

    def test_passes_normal_articles(self):
        assert not self._should_skip("Why AI Safety Matters")
        assert not self._should_skip("Book Review: The Alignment Problem")
        assert not self._should_skip("My Model Of AI Doom")


# --- News briefing dedup prompt construction (src/news.py) ---


class TestNewsBriefingDedup:
    """Test that dedup context is correctly included in the synthesis prompt."""

    def _make_aggregator(self, recent_briefings=None):
        return NewsAggregator(
            sources=[],
            prompt="Test prompt",
            lookback_hours=24,
            full_text_stories=12,
            max_article_chars=6000,
            author="Feedcast Bot",
            verify=False,
            recent_briefings=recent_briefings,
        )

    def _writer_input(self, agg, articles: str) -> str:
        """Run the real synthesize_briefing; return the user message the writer got.

        The writer is a paid model, so a pinned fake client answers and records.
        """
        agg.client = FakeApi(["Briefing."])
        asyncio.run(agg.synthesize_briefing(articles))
        (msg,) = agg.client.asked()
        return msg

    def test_no_dedup_context_when_empty(self):
        agg = self._make_aggregator(recent_briefings=[])
        articles = "## AI NEWS\n- [Source] Some headline\n  Summary text"
        msg = self._writer_input(agg, articles)
        assert PREVIOUS_BRIEFINGS_HEADER not in msg and "Previous briefings" not in msg
        assert f"## Today's articles:\n{articles}" in msg

    def test_dedup_context_included_with_recent_briefings(self):
        briefings = [
            {"date": "2026-02-18", "briefing_text": "Yesterday EU announced new AI rules."},
            {"date": "2026-02-17", "briefing_text": "OpenAI released GPT-5 two days ago."},
        ]
        agg = self._make_aggregator(recent_briefings=briefings)
        msg = self._writer_input(agg, "## AI NEWS\n- [Source] Some headline")

        assert PREVIOUS_BRIEFINGS_HEADER in msg
        assert "do NOT repeat stories" in msg
        assert "### 2026-02-18\nYesterday EU announced new AI rules." in msg
        assert "### 2026-02-17\nOpenAI released GPT-5 two days ago." in msg
        assert "## Today's articles:\n## AI NEWS" in msg
        assert msg.index(PREVIOUS_BRIEFINGS_HEADER) < msg.index("## Today's articles:")

    def test_format_articles_groups_by_category(self):
        agg = self._make_aggregator()
        articles = [
            {"title": "AI Rule", "source": "BBC", "category": "ai_safety", "summary": "New rules"},
            {"title": "Markets Up", "source": "Reuters", "category": "economics", "summary": "Stocks rose"},
            {"title": "Model Release", "source": "Verge", "category": "ai_safety", "summary": "New model"},
        ]
        formatted = agg._format_articles_for_prompt(articles)
        assert "## AI SAFETY" in formatted
        assert "## ECONOMICS" in formatted
        # ai_safety items grouped together
        ai_section_start = formatted.index("## AI SAFETY")
        econ_section_start = formatted.index("## ECONOMICS")
        assert formatted.index("AI Rule", ai_section_start) < econ_section_start
        assert formatted.index("Model Release", ai_section_start) < econ_section_start


# --- generate (src/feed.py): what podcast crawlers need ---


class TestGenerateFeedForCrawlers:
    """Pocket Casts showed nothing for episodes the email linked (2026-09-15).

    Its server polls a small private feed on its own schedule; a WebSub hub
    declared in the feed and pinged by CI is what makes it fetch straight away.
    The rest is hygiene the feed validator flagged: a non-URL guid must say it
    is not a permalink, and enclosures should carry their real byte length.
    """

    def _feed(self, tmp_path, **cfg):
        import xml.etree.ElementTree as ET
        config = PodcastMetaConfig(**{
            "title": "T", "description": "D", "author": "A", "email": "e@e.com",
            "language": "en", "base_url": "https://x.test/pod", "category": "Technology",
            "hub_url": "https://pubsubhubbub.appspot.com/", **cfg,
        })
        from src.feed import Episode
        eps = [
            Episode(id="news-briefing-2026-09-15", title="Briefing", description="",
                    audio_file="b.mp3", published=datetime(2026, 9, 15, 4, 34),
                    duration_seconds=308, audio_bytes=2927229),
            Episode(id="https://www.astralcodexten.com/p/king-ludd", title="King Ludd",
                    description="", audio_file="k.mp3", published=datetime(2026, 9, 14),
                    duration_seconds=1216, link="https://www.astralcodexten.com/p/king-ludd"),
        ]
        out = tmp_path / "feed.xml"
        FeedGenerator(config, retention_days=30).generate(eps, out)
        return ET.parse(out).getroot().find("channel"), out.read_text()

    ATOM = "{http://www.w3.org/2005/Atom}link"

    def test_declares_the_websub_hub_next_to_the_self_link(self, tmp_path):
        channel, text = self._feed(tmp_path)
        links = {l.get("rel"): l.get("href") for l in channel.findall(self.ATOM)}
        assert links["self"] == "https://x.test/pod/feed.xml"
        assert links["hub"] == "https://pubsubhubbub.appspot.com/"
        # The CI ping step extracts the hub from the serialised XML with grep.
        assert '<atom:link href="https://pubsubhubbub.appspot.com/" rel="hub" />' in text

    def test_the_itunes_category_is_the_configured_one(self, tmp_path):
        channel, _ = self._feed(tmp_path, category="News")
        (category,) = channel.findall("{http://www.itunes.com/dtds/podcast-1.0.dtd}category")
        assert category.get("text") == "News"

    def test_hub_is_configurable_and_omittable(self, tmp_path):
        channel, _ = self._feed(tmp_path, hub_url="https://hub.example/")
        assert [l.get("href") for l in channel.findall(self.ATOM) if l.get("rel") == "hub"] \
            == ["https://hub.example/"]
        channel, _ = self._feed(tmp_path, hub_url="")
        assert [l for l in channel.findall(self.ATOM) if l.get("rel") == "hub"] == []

    def test_last_build_date_is_present_and_rfc822(self, tmp_path):
        channel, _ = self._feed(tmp_path)
        lbd = channel.findtext("lastBuildDate")
        assert lbd and lbd.endswith("+0000")
        from email.utils import parsedate_to_datetime
        assert parsedate_to_datetime(lbd).year >= 2026

    def test_non_url_guid_says_it_is_not_a_permalink(self, tmp_path):
        channel, _ = self._feed(tmp_path)
        guids = {i.findtext("guid"): i.find("guid").get("isPermaLink") for i in channel.findall("item")}
        assert guids["news-briefing-2026-09-15"] == "false"
        assert guids["https://www.astralcodexten.com/p/king-ludd"] is None   # a real permalink

    def test_enclosure_length_is_the_audio_size(self, tmp_path):
        channel, _ = self._feed(tmp_path)
        lengths = {i.findtext("title"): i.find("enclosure").get("length") for i in channel.findall("item")}
        assert lengths == {"Briefing": "2927229", "King Ludd": "0"}

    @needs_ffmpeg
    def test_load_episodes_reads_the_audio_size(self, tmp_path):
        config = PodcastMetaConfig(title="T", description="D", author="A", email="e@e.com",
                                   language="en", base_url="https://x.test/pod",
                                   category="Technology")
        (tmp_path / "a.mp3").write_bytes(silent_mp3())
        eps = FeedGenerator(config, retention_days=30).load_episodes_from_db(
            [self._row("a.mp3")], tmp_path)
        assert eps[0].audio_bytes == len(silent_mp3()) and eps[0].duration_seconds == 2

    @staticmethod
    def _row(audio_file: str, entry_id: str = "a") -> dict:
        return {"id": entry_id, "title": "A", "audio_file": audio_file,
                "published": "2026-09-15T04:00:00", "feed_name": "Zvi", "author": "Zvi",
                "link": None, "content": ""}

    def _gen(self):
        return FeedGenerator(PodcastMetaConfig(
            title="T", description="D", author="A", email="e@e.com", language="en",
            base_url="https://x.test/pod", category="Technology"), retention_days=30)

    @needs_ffmpeg
    def test_an_mp3_ffprobe_cannot_read_fails_the_feed(self, tmp_path):
        """It used to publish as a 00:00:00 episode with no error anywhere."""
        (tmp_path / "a.mp3").write_bytes(b"\0" * 1234)
        with pytest.raises(subprocess.CalledProcessError):
            self._gen().load_episodes_from_db([self._row("a.mp3")], tmp_path)

    @needs_ffmpeg
    def test_a_row_whose_mp3_is_missing_is_named_in_the_log(self, tmp_path, capsys):
        (tmp_path / "a.mp3").write_bytes(silent_mp3())
        eps = self._gen().load_episodes_from_db(
            [self._row("a.mp3"), self._row("gone.mp3", entry_id="https://lw/gone")], tmp_path)
        assert [e.id for e in eps] == ["a"]
        assert "WARNING: https://lw/gone (A): gone.mp3 is missing" in capsys.readouterr().out
