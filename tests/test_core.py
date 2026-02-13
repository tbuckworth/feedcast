"""Unit tests for pure functions — no API calls, no mocking."""

import hashlib
import os
import re
from datetime import datetime

# ContentProcessor.__init__ reads ANTHROPIC_API_KEY, set a dummy before import
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from src.audio import split_into_chunks
from src.feed import FeedGenerator, PodcastConfig
from src.main import generate_episode_id
from src.processor import ContentProcessor


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


# --- clean_html (src/processor.py) ---


class TestCleanHtml:
    def setup_method(self):
        self.processor = ContentProcessor.__new__(ContentProcessor)

    def test_removes_script_and_style(self):
        html = "<p>Hello</p><script>alert('x')</script><style>.x{}</style><p>World</p>"
        result = self.processor.clean_html(html)
        assert "alert" not in result
        assert ".x{}" not in result
        assert "Hello" in result
        assert "World" in result

    def test_collapses_whitespace(self):
        html = "<p>  Hello    World  </p>"
        result = self.processor.clean_html(html)
        assert "Hello" in result
        assert "World" in result
        # No runs of multiple spaces
        assert "    " not in result

    def test_empty_html(self):
        assert self.processor.clean_html("") == ""
        assert self.processor.clean_html("<div></div>") == ""

    def test_strips_nav_footer_header(self):
        html = "<nav>Menu</nav><p>Content</p><footer>Copyright</footer>"
        result = self.processor.clean_html(html)
        assert "Menu" not in result
        assert "Copyright" not in result
        assert "Content" in result

    def test_preserves_paragraph_breaks(self):
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        result = self.processor.clean_html(html)
        assert "First paragraph." in result
        assert "Second paragraph." in result


# --- _table_to_prose_simple (src/processor.py) ---


class TestTableToProseSimple:
    def setup_method(self):
        self.processor = ContentProcessor.__new__(ContentProcessor)

    def _make_table(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").find("table")

    def test_header_value_pairs(self):
        html = "<table><tr><th>Name</th><th>Score</th></tr><tr><td>Alice</td><td>95</td></tr></table>"
        result = self.processor._table_to_prose_simple(self._make_table(html))
        assert "Name: Alice" in result
        assert "Score: 95" in result

    def test_multi_row(self):
        html = """<table>
            <tr><th>City</th><th>Pop</th></tr>
            <tr><td>NYC</td><td>8M</td></tr>
            <tr><td>LA</td><td>4M</td></tr>
        </table>"""
        result = self.processor._table_to_prose_simple(self._make_table(html))
        assert "City: NYC" in result
        assert "City: LA" in result
        # Rows are joined by ". "
        assert ". " in result

    def test_empty_table(self):
        html = "<table></table>"
        result = self.processor._table_to_prose_simple(self._make_table(html))
        assert result == ""


# --- _format_duration (src/feed.py) ---


class TestFormatDuration:
    def setup_method(self):
        config = PodcastConfig(
            title="T", description="D", author="A",
            email="e@e.com", language="en", base_url="http://x",
        )
        self.gen = FeedGenerator(config)

    def test_zero(self):
        assert self.gen._format_duration(0) == "00:00:00"

    def test_minutes(self):
        assert self.gen._format_duration(125) == "00:02:05"

    def test_hours_minutes_seconds(self):
        assert self.gen._format_duration(3661) == "01:01:01"


# --- _format_rfc822 (src/feed.py) ---


class TestFormatRfc822:
    def setup_method(self):
        config = PodcastConfig(
            title="T", description="D", author="A",
            email="e@e.com", language="en", base_url="http://x",
        )
        self.gen = FeedGenerator(config)

    def test_known_datetime(self):
        dt = datetime(2025, 1, 15, 14, 30, 0)
        result = self.gen._format_rfc822(dt)
        assert result == "Wed, 15 Jan 2025 14:30:00 +0000"


# --- generate_episode_id (src/main.py) ---


class TestGenerateEpisodeId:
    def test_deterministic(self):
        assert generate_episode_id("foo") == generate_episode_id("foo")

    def test_12_char_hex(self):
        result = generate_episode_id("test-entry-id")
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_matches_sha256_prefix(self):
        entry_id = "https://example.com/post/123"
        expected = hashlib.sha256(entry_id.encode()).hexdigest()[:12]
        assert generate_episode_id(entry_id) == expected


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
    """Test the ACX skip_patterns against expected titles."""

    PATTERNS = [
        "^(Hidden )?Open Thread",
        "^Links [Ff]or \\w+ \\d{4}",
        "Classifieds",
        "^Meetups Everywhere",
        "^Mantic Monday",
        "^Highlights [Ff]rom [Tt]he [Cc]omments",
        "^ACX Survey$",
        "Contest Rules",
        "^Apply [Ff]or [Aa]n ACX Grant",
        "Forecasting Contest",
    ]

    def _should_skip(self, title: str) -> bool:
        return any(re.search(p, title, re.IGNORECASE) for p in self.PATTERNS)

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
