"""Tests for the maths filter that keeps equation-heavy posts out of the audio."""

import pytest

from src.email_report import LinkedPost, RunReport, build_html, build_text
from src.mathiness import (
    DEFAULT_THRESHOLD, MathsVerdict, assess, lesswrong_post_id, maths_score,
)
from datetime import datetime

PROSE = " ".join(["the model was trained on a large corpus of text"] * 40)
MATHS = " ".join([r"we define $f(x) = \lim_{t\to\infty} \phi(x,t)$ where $\phi$ is"] * 40)


class TestMathsScore:
    def test_prose_scores_zero(self):
        hits, score = maths_score(PROSE)
        assert hits == 0 and score == 0.0

    def test_latex_is_counted(self):
        hits, score = maths_score(MATHS)
        assert hits > 0 and score > DEFAULT_THRESHOLD

    def test_empty_text(self):
        assert maths_score("") == (0, 0.0)

    def test_score_is_density_not_volume(self):
        """A long prose post must not out-score a short dense one."""
        _, dense = maths_score(r"$a=b$ $c=d$ $e=f$")
        _, diluted = maths_score(r"$a=b$ " + PROSE * 5)
        assert dense > diluted


class TestPostId:
    def test_extracts_lesswrong_id(self):
        assert lesswrong_post_id(
            "https://www.lesswrong.com/posts/MgYCraoxMwfWwgWa5/an-anytime-algorithm"
        ) == "MgYCraoxMwfWwgWa5"

    def test_extracts_alignment_forum_id(self):
        assert lesswrong_post_id(
            "https://www.alignmentforum.org/posts/QBuJ3suRZxrrxSTtv/does-diffusiongemma"
        ) == "QBuJ3suRZxrrxSTtv"

    def test_other_hosts_ignored(self):
        assert lesswrong_post_id("https://www.astralcodexten.com/p/some-post") is None

    def test_empty_link(self):
        assert lesswrong_post_id("") is None


class TestAssess:
    def test_falls_back_to_supplied_text_off_lesswrong(self, monkeypatch):
        monkeypatch.setattr("src.mathiness.fetch_lesswrong_markdown", lambda *a, **k: None)
        v = assess("https://example.com/post", MATHS)
        assert v.is_heavy and v.source == "rss"

    def test_prose_is_not_flagged(self, monkeypatch):
        monkeypatch.setattr("src.mathiness.fetch_lesswrong_markdown", lambda *a, **k: None)
        assert assess("https://example.com/post", PROSE).is_heavy is False

    def test_markdown_wins_over_stripped_rss(self, monkeypatch):
        """The whole point: RSS has the maths stripped, markdown does not."""
        monkeypatch.setattr("src.mathiness.fetch_lesswrong_markdown", lambda *a, **k: MATHS)
        v = assess("https://www.lesswrong.com/posts/abcdefghijklmnopq/x", PROSE)
        assert v.is_heavy and v.source == "markdown"

    def test_threshold_is_respected(self, monkeypatch):
        monkeypatch.setattr("src.mathiness.fetch_lesswrong_markdown", lambda *a, **k: None)
        assert assess("https://x.com/p", MATHS, threshold=10_000.0).is_heavy is False

    def test_network_failure_does_not_raise(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("down")
        monkeypatch.setattr("httpx.post", boom)
        v = assess("https://www.lesswrong.com/posts/abcdefghijklmnopq/x", PROSE)
        assert v.source == "rss" and v.is_heavy is False


class TestLinkedInEmail:
    def _report(self):
        return RunReport(episodes=[], linked=[LinkedPost(
            title="An anytime algorithm for mixing the computable measures",
            author="Cole Wyeth", feed_name="LessWrong Frontpage",
            link="https://www.lesswrong.com/posts/MgYCraoxMwfWwgWa5/x",
            maths_score=129.7, source="markdown")])

    def test_html_lists_the_post_and_links_it(self):
        html = build_html(self._report(), datetime(2026, 8, 20))
        assert "An anytime algorithm" in html
        assert "MgYCraoxMwfWwgWa5" in html
        assert "Linked, not narrated" in html
        assert "129.7 maths matches per 1000 words" in html

    def test_text_lists_the_post(self):
        txt = build_text(self._report(), datetime(2026, 8, 20))
        assert "Linked, not narrated" in txt
        assert "MgYCraoxMwfWwgWa5" in txt

    def test_subject_reflects_a_linked_only_run(self, monkeypatch):
        sent = {}

        class Fake:
            def __init__(s, *a, **k): pass
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def starttls(s, context=None): pass
            def login(s, *a): pass
            def send_message(s, m): sent["subject"] = m["Subject"]

        monkeypatch.setattr("smtplib.SMTP", Fake)
        monkeypatch.setenv("FEEDCAST_EMAIL_TO", "r@example.com")
        monkeypatch.setenv("SMTP_USER", "s@example.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
        from src.email_report import send_report
        send_report(self._report(), datetime(2026, 8, 20))
        assert "1 linked, no audio" in sent["subject"]


class TestFalsePositiveGuards:
    """A false positive here silently deletes a post, so these matter more
    than the false negatives they trade against."""

    @pytest.fixture(autouse=True)
    def _no_network(self, monkeypatch):
        monkeypatch.setattr("src.mathiness.fetch_lesswrong_markdown", lambda *a, **k: None)

    def test_currency_is_not_mathematics(self):
        """'raised $10M at a $1B valuation' must not read as an equation."""
        money = ("The startup raised $10M at a $1B valuation. "
                 "It later raised $25M at a $3B valuation. ") * 3
        hits, _ = maths_score(money)
        assert hits == 0
        assert assess("https://example.com/p", money).is_heavy is False

    def test_real_latex_still_counted_alongside_currency(self):
        mixed = (r"They raised $10M. We define $f(x) = \lim_{t\to\infty}\phi(x,t)$ "
                 r"where $\phi$ is bounded and $\sum_i p_i = 1$. ") * 8
        assert assess("https://example.com/p", mixed).is_heavy is True

    def test_short_post_needs_real_volume_not_just_density(self):
        """Two matches in a short post clears the density bar but must not fire."""
        from src.mathiness import MIN_HITS
        short = r"We set $a = b$ and $c = d$. " + "filler words here " * 20
        hits, score = maths_score(short)
        assert hits < MIN_HITS
        assert score >= DEFAULT_THRESHOLD, "density alone would have flagged it"
        assert assess("https://example.com/p", short).is_heavy is False

    def test_threshold_and_min_hits_both_required(self):
        from src.mathiness import MIN_HITS
        dense_enough = r"$a = b$ " * (MIN_HITS + 2) + "word " * 50
        assert assess("https://example.com/p", dense_enough).is_heavy is True


class TestLinkedRowEscaping:
    def test_separator_is_not_double_escaped(self):
        """escape() around the whole joined string yields a literal &middot;."""
        r = RunReport(linked=[LinkedPost("T", "Ada", "LessWrong", "https://x/p", 13.5, "markdown")])
        html = build_html(r, datetime(2026, 8, 20))
        assert "&amp;middot;" not in html
        assert "&middot;" in html

    def test_hostile_author_still_escaped(self):
        r = RunReport(linked=[LinkedPost("T", "A & <b>B</b>", "Feed", "https://x/p", 13.5, "md")])
        html = build_html(r, datetime(2026, 8, 20))
        assert "<b>" not in html
        assert "A &amp; &lt;b&gt;B&lt;/b&gt;" in html
