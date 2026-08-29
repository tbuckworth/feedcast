"""LessWrong Curated: curated when, written when.

The curated feed dates an item by its curation, which can trail publication by
weeks (Big-World Intuitions: posted 2026-07-30, curated 2026-08-21). The
freshness window has to key on the first, the email on the second.
"""

import asyncio
from datetime import datetime

import pytest
import yaml

from src.email_report import ReportEpisode, RunReport, build_html, build_text
from src.lesswrong import post_id, _parse
from src.main import _correct_publication_dates, _curated_date
from src.monitor import FeedEntry


class TestFeedChoice:

    def test_config_subscribes_to_curated_not_the_firehose(self):
        cfg = yaml.safe_load(open("config.yaml"))
        lw = [f for f in cfg["feeds"] if "lesswrong.com/feed.xml" in f["url"]
              and "userId" not in f["url"]]
        assert len(lw) == 1, "expected exactly one aggregate LessWrong feed"
        assert "view=curated-rss" in lw[0]["url"]
        assert "frontpage-rss" not in lw[0]["url"]

    def test_the_aggregate_feed_still_comes_last(self):
        """Author feeds must precede it or dedup drops the attribution."""
        cfg = yaml.safe_load(open("config.yaml"))
        names = [f["name"] for f in cfg["feeds"]]
        assert names[-1] == "LessWrong Curated"


class TestPostIdExtraction:

    def test_reads_the_id_out_of_a_post_url(self):
        assert post_id("https://www.lesswrong.com/posts/MhssYd2EN2HGfo7Jc/v-and-v") \
            == "MhssYd2EN2HGfo7Jc"

    def test_ignores_anything_that_is_not_a_lesswrong_post(self):
        assert post_id("https://www.astralcodexten.com/p/some-post") == ""
        assert post_id("") == ""

    def test_parses_lesswrongs_utc_stamps_to_naive_utc(self):
        assert _parse("2026-07-30T19:10:28.071Z") == datetime(2026, 7, 30, 19, 10, 28, 71000)
        assert _parse(None) is None
        assert _parse("not a date") is None


class TestDateCorrection:

    def _entry(self, feed_date, link="https://www.lesswrong.com/posts/abc123/x"):
        return FeedEntry(id="1", title="Big-World Intuitions", link=link, content="",
                         published=feed_date, author="A", feed_name="LessWrong Curated",
                         feed_date=feed_date)

    def test_a_late_curation_is_corrected_to_the_posting_date(self, monkeypatch):
        async def fake(link, client=None):
            return datetime(2026, 7, 30, 19, 10)
        monkeypatch.setattr("src.main.posted_at", fake)
        e = self._entry(datetime(2026, 8, 21, 18, 30))
        asyncio.run(_correct_publication_dates([e]))
        assert e.published == datetime(2026, 7, 30, 19, 10)
        assert e.feed_date == datetime(2026, 8, 21, 18, 30), "curation date must survive"

    def test_a_few_hours_of_lag_is_left_alone(self, monkeypatch):
        async def fake(link, client=None):
            return datetime(2026, 8, 25, 17, 50)
        monkeypatch.setattr("src.main.posted_at", fake)
        e = self._entry(datetime(2026, 8, 26, 0, 23))
        asyncio.run(_correct_publication_dates([e]))
        assert e.published == datetime(2026, 8, 26, 0, 23)

    def test_a_failed_lookup_leaves_the_feed_date_standing(self, monkeypatch):
        async def fake(link, client=None):
            return None
        monkeypatch.setattr("src.main.posted_at", fake)
        e = self._entry(datetime(2026, 8, 21, 18, 30))
        asyncio.run(_correct_publication_dates([e]))
        assert e.published == datetime(2026, 8, 21, 18, 30)


class TestReportShowsBothDates:

    def test_curation_is_shown_when_it_trails_publication(self):
        row = {"feed_date": datetime(2026, 8, 21, 18, 30).isoformat()}
        assert _curated_date(row, datetime(2026, 7, 30, 19, 10)) == datetime(2026, 8, 21, 18, 30)

    def test_curation_is_hidden_when_it_matches_publication(self):
        row = {"feed_date": datetime(2026, 8, 26, 0, 23).isoformat()}
        assert _curated_date(row, datetime(2026, 8, 25, 17, 50)) is None

    def test_rows_without_the_column_say_nothing(self):
        assert _curated_date({}, datetime(2026, 8, 26)) is None
        assert _curated_date({"feed_date": "nonsense"}, datetime(2026, 8, 26)) is None

    def test_the_email_explains_why_an_old_post_is_here(self):
        ep = ReportEpisode(
            title="Big-World Intuitions", author="Joe Carlsmith",
            feed_name="LessWrong Curated", link="https://example.com/p",
            audio_url="https://example.com/a.mp3", duration_seconds=600,
            published=datetime(2026, 7, 30), curated=datetime(2026, 8, 21))
        report = RunReport(episodes=[ep])
        html = build_html(report, datetime(2026, 8, 29))
        assert "30 Jul 2026" in html and "curated 21 Aug 2026" in html
        assert "30 Jul 2026" in build_text(report, datetime(2026, 8, 29))


class TestCrossFeedDuplicates:
    """A curated repost must not be narrated a second time.

    Zvi's "On Writing #3" reaches us from his own feed as guid
    f1c130ea-2d86-4ad6-bb79-fd6d4338c74e and from LessWrong Curated as
    rA6pqn6kz8NvHyznT, weeks apart, with an identical link.
    """

    LINK = "https://www.lesswrong.com/posts/rA6pqn6kz8NvHyznT/on-writing-3"

    def _xml(self, guid, when):
        return ("<?xml version='1.0'?><rss version='2.0'><channel><title>f</title>"
                f"<item><title>On Writing #3</title><link>{self.LINK}</link>"
                f"<guid>{guid}</guid><description>Body</description>"
                f"<pubDate>{when.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>"
                "</item></channel></rss>")

    def test_the_same_link_under_a_new_guid_is_skipped(self, tmp_path):
        from datetime import timedelta, timezone
        from src.monitor import FeedMonitor
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        m = FeedMonitor(tmp_path / "posts.db")

        first = m.fetch_feed(self._xml("f1c130ea", now - timedelta(hours=5)), "Zvi")
        assert len(first) == 1
        m.mark_processed(first[0], audio_file="a.mp3")

        again = m.fetch_feed(self._xml("rA6pqn6kz8NvHyznT", now - timedelta(hours=1)),
                             "LessWrong Curated")
        assert again == []
