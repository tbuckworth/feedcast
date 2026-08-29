"""The 48-hour window, and the source links on briefing bullets.

The window exists because of a real incident: on 2026-08-29 the Zvi feed
presented 250 items back to September 2025 as unseen, and the pipeline
narrated its way through the archive one post per run.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.digest import parse_bullets
from src.email_report import (ReportEpisode, RunReport, build_html, build_text,
                              bullet_parts, format_published)
from src.monitor import DEFAULT_MAX_AGE_HOURS, FeedMonitor


def rfc822(when: datetime) -> str:
    return when.strftime("%a, %d %b %Y %H:%M:%S GMT")


def feed_xml(*items: tuple[str, datetime | None]) -> str:
    """A minimal RSS document; a None date means the item publishes no date."""
    entries = []
    for title, when in items:
        date = f"<pubDate>{rfc822(when)}</pubDate>" if when else ""
        entries.append(
            f"<item><title>{title}</title>"
            f"<link>https://example.com/{title.replace(' ', '-')}</link>"
            f"<guid>https://example.com/{title.replace(' ', '-')}</guid>"
            f"<description>Body of {title}</description>{date}</item>"
        )
    return ("<?xml version='1.0'?><rss version='2.0'><channel>"
            "<title>Test feed</title>" + "".join(entries) + "</channel></rss>")


@pytest.fixture
def monitor(tmp_path):
    return FeedMonitor(tmp_path / "posts.db")


class TestFreshnessWindow:

    def _now(self):
        # feedparser reports UTC; fetch_feed compares against a naive local
        # clock, so build the fixtures the same way it reads them.
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def test_recent_entries_survive(self, monitor):
        xml = feed_xml(("Fresh", self._now() - timedelta(hours=3)))
        entries = monitor.fetch_feed(xml, "Test")
        assert [e.title for e in entries] == ["Fresh"]

    def test_the_archive_is_not_narrated(self, monitor):
        """The incident in one test: one new post, 250 old ones."""
        items = [("Fresh", self._now() - timedelta(hours=6))]
        items += [(f"Old {i}", self._now() - timedelta(days=30 + i)) for i in range(250)]
        entries = monitor.fetch_feed(feed_xml(*items), "Zvi Mowshowitz")
        assert [e.title for e in entries] == ["Fresh"]

    def test_the_boundary_is_the_max_age(self, monitor):
        xml = feed_xml(("JustInside", self._now() - timedelta(hours=47)),
                       ("JustOutside", self._now() - timedelta(hours=49)))
        entries = monitor.fetch_feed(xml, "Test")
        assert [e.title for e in entries] == ["JustInside"]

    def test_an_undated_entry_is_not_assumed_fresh(self, monitor):
        """Undated entries used to inherit datetime.now() and always pass."""
        xml = feed_xml(("Undated", None), ("Fresh", self._now() - timedelta(hours=1)))
        entries = monitor.fetch_feed(xml, "Test")
        assert [e.title for e in entries] == ["Fresh"]

    def test_cutoff_can_be_disabled_for_a_deliberate_backfill(self, monitor):
        xml = feed_xml(("Ancient", self._now() - timedelta(days=400)))
        entries = monitor.fetch_feed(xml, "Test", max_age_hours=None)
        assert [e.title for e in entries] == ["Ancient"]

    def test_a_custom_window_is_honoured(self, monitor):
        xml = feed_xml(("SixHoursOld", self._now() - timedelta(hours=6)))
        assert monitor.fetch_feed(xml, "Test", max_age_hours=3) == []
        assert len(monitor.fetch_feed(xml, "Test", max_age_hours=12)) == 1

    def test_default_window_is_two_days(self):
        assert DEFAULT_MAX_AGE_HOURS == 48.0

    def test_the_window_does_not_override_dedup(self, monitor):
        """Fresh but already processed is still processed."""
        xml = feed_xml(("Fresh", self._now() - timedelta(hours=2)))
        entry = monitor.fetch_feed(xml, "Test")[0]
        monitor.mark_processed(entry, audio_file="a.mp3")
        assert monitor.fetch_feed(xml, "Test") == []


class TestBulletSources:

    ALLOWED = {"https://news.example.com/chips", "https://news.example.com/moscow"}

    def test_a_supplied_url_is_attached(self):
        raw = ("OpenAI unveiled a custom inference chip. || https://news.example.com/chips\n"
               "The CIA director visited Moscow. || https://news.example.com/moscow")
        bullets = parse_bullets(raw, self.ALLOWED)
        assert [bullet_parts(b) for b in bullets] == [
            ("OpenAI unveiled a custom inference chip.", "https://news.example.com/chips"),
            ("The CIA director visited Moscow.", "https://news.example.com/moscow"),
        ]

    def test_an_invented_url_is_dropped_not_shown(self):
        """A confident wrong link is worse than no link."""
        raw = "OpenAI unveiled a custom inference chip. || https://invented.example.com/x"
        (text, url), = map(bullet_parts, parse_bullets(raw, self.ALLOWED))
        assert text == "OpenAI unveiled a custom inference chip."
        assert url == ""

    def test_none_means_no_single_source(self):
        raw = "A theme running across several stories today. || none"
        (text, url), = map(bullet_parts, parse_bullets(raw, self.ALLOWED))
        assert text == "A theme running across several stories today."
        assert url == ""

    def test_without_sources_bullets_stay_plain_strings(self):
        raw = "A claim with a specific number in it, namely 42 percent."
        assert parse_bullets(raw) == [raw]

    def test_old_string_bullets_still_render(self):
        assert bullet_parts("plain") == ("plain", "")


class TestReportShowsDates:

    def _ep(self, **kw):
        base = dict(title="A Post", author="Ada Lovelace", feed_name="LessWrong",
                    link="https://example.com/post", audio_url="https://example.com/a.mp3",
                    duration_seconds=245, published=datetime(2026, 8, 27, 9, 30))
        base.update(kw)
        return ReportEpisode(**base)

    def test_html_states_when_the_source_was_published(self):
        html = build_html(RunReport(episodes=[self._ep()]), datetime(2026, 8, 29))
        assert "27 Aug 2026" in html

    def test_text_states_it_too(self):
        txt = build_text(RunReport(episodes=[self._ep()]), datetime(2026, 8, 29))
        assert "27 Aug 2026" in txt

    def test_an_unknown_date_is_simply_absent(self):
        html = build_html(RunReport(episodes=[self._ep(published=None)]), datetime(2026, 8, 29))
        assert "Ada Lovelace" in html
        assert format_published(None) == ""

    def test_the_weekly_list_is_dated(self):
        html = build_html(RunReport(recent=[self._ep(title="Older")]), datetime(2026, 8, 29))
        assert "Older" in html and "27 Aug 2026" in html

    def test_a_linked_bullet_renders_as_a_link(self):
        ep = self._ep(is_briefing=True, author="", bullets=[
            {"text": "OpenAI unveiled a custom inference chip.",
             "url": "https://news.example.com/chips"}])
        html = build_html(RunReport(episodes=[ep]), datetime(2026, 8, 29))
        assert 'href="https://news.example.com/chips"' in html
        txt = build_text(RunReport(episodes=[ep]), datetime(2026, 8, 29))
        assert "https://news.example.com/chips" in txt

    def test_a_bullet_url_is_escaped(self):
        ep = self._ep(bullets=[{"text": "Claim.", "url": 'https://x.example/"onmouseover=alert(1)'}])
        html = build_html(RunReport(episodes=[ep]), datetime(2026, 8, 29))
        assert '"onmouseover' not in html
