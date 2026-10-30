"""LessWrong Curated: curated when, written when.

The curated feed dates an item by its curation, which can trail publication by
weeks (Big-World Intuitions: posted 2026-07-30, curated 2026-08-21). The
freshness window has to key on the first, the email on the second.
"""

import asyncio
from datetime import datetime

import httpx
import yaml

from src import lesswrong, notices
from src.config import CONFIG_PATH
from src.email_report import ReportEpisode, RunReport, build_html, build_text
from src.lesswrong import _parse, lesswrong_post_id, posted_at
from src.main import (_build_run_report, _correct_publication_dates, _stored_feed_date,
                      _surfaced_date)
from src.monitor import FeedEntry


def _lesswrong_answers(monkeypatch, answer) -> None:
    """Send the date lookup's GraphQL request to `answer` instead of the network."""
    real = httpx.AsyncClient
    monkeypatch.setattr(lesswrong.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(answer), **kw))


class TestFeedChoice:

    def test_config_subscribes_to_curated_not_the_firehose(self):
        cfg = yaml.safe_load(CONFIG_PATH.read_text())
        lw = [f for f in cfg["feeds"] if "lesswrong.com/feed.xml" in f["url"]
              and "userId" not in f["url"]]
        assert len(lw) == 1, "expected exactly one aggregate LessWrong feed"
        assert "view=curated-rss" in lw[0]["url"]
        assert "frontpage-rss" not in lw[0]["url"]

    def test_the_aggregate_feed_still_comes_last(self):
        """Author feeds must precede it or dedup drops the attribution."""
        cfg = yaml.safe_load(CONFIG_PATH.read_text())
        names = [f["name"] for f in cfg["feeds"]]
        assert names[-1] == "LessWrong Curated"


class TestPostIdExtraction:

    def test_reads_the_id_out_of_a_post_url(self):
        assert lesswrong_post_id("https://www.lesswrong.com/posts/MhssYd2EN2HGfo7Jc/v-and-v") \
            == "MhssYd2EN2HGfo7Jc"

    def test_ignores_anything_that_is_not_a_lesswrong_post(self):
        assert lesswrong_post_id("https://www.astralcodexten.com/p/some-post") is None
        assert lesswrong_post_id("") is None

    def test_parses_lesswrongs_utc_stamps_to_naive_utc(self):
        assert _parse("2026-07-30T19:10:28.071Z") == datetime(2026, 7, 30, 19, 10, 28, 71000)
        assert _parse(None) is None
        assert _parse("not a date") is None


    def test_an_alignment_forum_post_is_dated_by_its_own_site(self, monkeypatch):
        """The date lookup once knew only lesswrong.com URLs, so Alignment
        Forum posts kept their curation date as their release date."""
        asked = []

        def answer(request):
            asked.append(request.url.host)
            return httpx.Response(200, json={"data": {"post": {"result": {
                "postedAt": "2026-07-30T19:10:28.071Z"}}}})

        _lesswrong_answers(monkeypatch, answer)
        link = "https://www.alignmentforum.org/posts/MhssYd2EN2HGfo7Jc/v-and-v"
        assert asyncio.run(posted_at(link)) == datetime(2026, 7, 30, 19, 10, 28, 71000)
        assert asked == ["www.alignmentforum.org"]

    @staticmethod
    def _ask(monkeypatch, answer):
        _lesswrong_answers(monkeypatch, answer)
        return asyncio.run(posted_at("https://www.lesswrong.com/posts/MhssYd2EN2HGfo7Jc/v-and-v"))

    def test_a_graphql_error_payload_is_named_with_the_post_and_the_errors(self, monkeypatch,
                                                                           capsys):
        """It used to return None in silence: the email then called the
        curation date the release date and nobody knew."""
        errors = [{"message": "Post not found"}]
        assert self._ask(monkeypatch, lambda request: httpx.Response(
            200, json={"errors": errors, "data": {"post": None}})) is None
        (note,) = notices.report()
        assert note.startswith("LessWrong date lookup for MhssYd2EN2HGfo7Jc failed")
        assert "Post not found" in note and note.endswith("the feed's date stands")
        assert note in capsys.readouterr().out

    def test_a_failed_request_is_named_too(self, monkeypatch):
        assert self._ask(monkeypatch, lambda request: httpx.Response(502)) is None
        (note,) = notices.report()
        assert note.startswith(
            "LessWrong date lookup for MhssYd2EN2HGfo7Jc failed (HTTPStatusError")


class TestDateCorrection:

    def _entry(self, feed_date, link="https://www.lesswrong.com/posts/abc123/x"):
        return FeedEntry(id="1", title="Big-World Intuitions", link=link, content="",
                         published=feed_date, author="A", feed_name="LessWrong Curated",
                         feed_date=feed_date)

    def test_a_late_curation_is_corrected_to_the_posting_date(self, monkeypatch):
        async def fake(link):
            return datetime(2026, 7, 30, 19, 10)
        monkeypatch.setattr("src.main.posted_at", fake)
        e = self._entry(datetime(2026, 8, 21, 18, 30))
        asyncio.run(_correct_publication_dates([e]))
        assert e.published == datetime(2026, 7, 30, 19, 10)
        assert e.feed_date == datetime(2026, 8, 21, 18, 30), "curation date must survive"

    def test_a_few_hours_of_lag_is_left_alone(self, monkeypatch):
        async def fake(link):
            return datetime(2026, 8, 25, 17, 50)
        monkeypatch.setattr("src.main.posted_at", fake)
        e = self._entry(datetime(2026, 8, 26, 0, 23))
        asyncio.run(_correct_publication_dates([e]))
        assert e.published == datetime(2026, 8, 26, 0, 23)

    def test_a_failed_lookup_leaves_the_feed_date_standing(self, monkeypatch):
        async def fake(link):
            return None
        monkeypatch.setattr("src.main.posted_at", fake)
        e = self._entry(datetime(2026, 8, 21, 18, 30))
        asyncio.run(_correct_publication_dates([e]))
        assert e.published == datetime(2026, 8, 21, 18, 30)


class TestReportShowsBothDates:

    def test_the_feed_date_is_shown_when_it_trails_publication(self):
        assert _surfaced_date(datetime(2026, 8, 21, 18, 30), datetime(2026, 7, 30, 19, 10)) \
            == datetime(2026, 8, 21, 18, 30)

    def test_the_feed_date_is_hidden_when_it_matches_publication(self):
        assert _surfaced_date(datetime(2026, 8, 26, 0, 23), datetime(2026, 8, 25, 17, 50)) is None

    def test_rows_without_the_column_say_nothing(self):
        assert _stored_feed_date({"feed_date": "2026-08-21T18:30:00"}) == \
            datetime(2026, 8, 21, 18, 30)
        assert _stored_feed_date({}) is None
        assert _stored_feed_date({"feed_date": "nonsense"}) is None
        assert _surfaced_date(None, datetime(2026, 8, 26)) is None

    def test_a_post_waiting_for_narration_shows_both_dates_too(self):
        e = FeedEntry(id="1", title="Big-World Intuitions", link="https://example.com/p",
                      content="", published=datetime(2026, 7, 30), author="Joe Carlsmith",
                      feed_name="LessWrong Curated", feed_date=datetime(2026, 8, 21))
        report = _build_run_report([], [], set(), [], "https://x", pending=[{"entry": e}])
        assert report.episodes[0].surfaced == datetime(2026, 8, 21)

    def test_the_email_explains_why_an_old_post_is_here(self):
        """Any LessWrong post can carry a feed date, not only a curated one: the
        label says "in feed" (it said "curated" until 2026-10-30)."""
        ep = ReportEpisode(
            title="Big-World Intuitions", author="Joe Carlsmith",
            feed_name="LessWrong Curated", link="https://example.com/p",
            audio_url="https://example.com/a.mp3", duration_seconds=600,
            published=datetime(2026, 7, 30), surfaced=datetime(2026, 8, 21))
        report = RunReport(episodes=[ep])
        html = build_html(report, datetime(2026, 8, 29))
        text = build_text(report, datetime(2026, 8, 29))
        assert "30 Jul 2026" in html and "in feed 21 Aug 2026" in html
        assert "30 Jul 2026" in text and "in feed 21 Aug 2026" in text
        assert "curated 21 Aug" not in html + text


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

        first = m.fetch_feed(self._xml("f1c130ea", now - timedelta(hours=5)), "Zvi",
                             max_age_hours=48)
        assert len(first) == 1
        m.mark_processed(first[0], audio_file="a.mp3")

        again = m.fetch_feed(self._xml("rA6pqn6kz8NvHyznT", now - timedelta(hours=1)),
                             "LessWrong Curated", max_age_hours=48)
        assert again == []
