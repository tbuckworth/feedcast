"""Summaries first, posts read out in full after: the two-publish run.

On 2026-09-26 a 113-chunk book review ran into the pipeline timeout and took
the day's briefing and summary down with it. The first pass now publishes and
emails everything a writer produced, and parks the verbatim posts in
deferred_entries; the narration pass narrates them and publishes again.
"""

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import src.main as main
from src.config import PodcastMetaConfig, load_config
from src.email_report import ReportEpisode, RunReport, build_html, build_text
from src.feed import Episode, FeedGenerator, episode_page_url
from src.main import Attempt, _build_run_report, _prepare_deferred, process_entry
from src import notices
from src.monitor import FeedEntry, FeedMonitor, episode_id
from src.normalizer import TextNormalizer
from src.processor import ContentProcessor
from tests.conftest import FakeApi, needs_ffmpeg

BASE = "https://tbuckworth.github.io/feedcast"


def _entry(i="acx-1", title="Does Georgism Work?", content="<p>Land.</p>", link=None):
    return FeedEntry(id=i, title=title, link=link or f"https://acx/{i}", content=content,
                     published=datetime(2026, 9, 24, 3, 0), author="Scott Alexander",
                     feed_name="Scott Alexander", authors=["Scott Alexander"],
                     feed_date=datetime(2026, 9, 24, 3, 0))


def _gen():
    return FeedGenerator(PodcastMetaConfig(title="Feedcast", description="d", author="T",
                                           email="t@x", language="en-us", base_url=BASE,
                                           category="Technology"),
                         retention_days=30)


@pytest.fixture
def monitor(tmp_path):
    return FeedMonitor(tmp_path / "posts.db")


class TestWhichPostsWait:

    def test_full_readings_wait_and_written_scripts_do_not(self):
        p = ContentProcessor("prompt", verify=False, auto_verbatim_limit=24000)
        assert p.reads_verbatim(_entry(), "verbatim")
        assert not p.reads_verbatim(_entry(), "summarize")
        briefing = _entry("news-briefing-2026-10-08", "Daily News Briefing - 2026-10-08")
        assert not p.reads_verbatim(briefing, "verbatim")

    def test_auto_reads_in_full_up_to_the_configured_limit(self):
        p = ContentProcessor("prompt", verify=False, auto_verbatim_limit=1000)
        short = _entry(content=f"<p>{'word ' * 100}</p>")
        long = _entry(content=f"<p>{'x' * 1010}</p>")
        assert p.reads_verbatim(short, "auto")
        assert not p.reads_verbatim(long, "auto")

    def test_process_resolves_auto_by_the_same_rule(self, routes):
        # One rule decides both which publish a post goes out in and how
        # process() reads it, so the two cannot disagree: a briefing short
        # enough for auto to read in full is still summarised, as
        # reads_verbatim says, while a post as short is read out.
        routes["anthropic"] = FakeApi(["The summary."])
        p = ContentProcessor("prompt", verify=False, auto_verbatim_limit=1000)
        briefing = _entry("news-briefing-2026-10-08", "Daily News Briefing - 2026-10-08",
                          content="<p>Short news.</p>")
        post = _entry(content="<p>Short post.</p>")
        assert not p.reads_verbatim(briefing, "auto") and p.reads_verbatim(post, "auto")
        assert asyncio.run(p.process(briefing, "auto")).startswith("Summary of ")
        assert asyncio.run(p.process(post, "auto")).startswith("Does Georgism Work?. By ")
        assert len(routes["anthropic"].calls) == 1      # only the briefing went to the writer


class TestDeferredTable:

    def test_round_trip_keeps_the_post_and_its_script(self, monitor):
        e = _entry()
        monitor.defer_entry(e, "verbatim", "Clean text.", None, ["a bullet"])
        (row,) = monitor.deferred_entries()
        assert row["entry"] == e
        assert (row["mode"], row["processed_text"], row["normalized_text"]) == \
               ("verbatim", "Clean text.", "")
        assert row["bullets"] == ["a bullet"] and row["attempts"] == 0
        assert monitor.is_deferred(e.id) and monitor.is_deferred(link=e.link)
        assert not monitor.is_deferred("other") and not monitor.is_deferred(link="")

    def test_attempts_are_counted_before_narrating_and_survive_a_re_defer(self, monitor):
        monitor.defer_entry(_entry(), "verbatim", "t", None, [])
        monitor.start_narration()
        monitor.note_deferred_failure("acx-1", "tts: ReadError", "spoken script")
        # Deferring the same post again (a later first pass) keeps the count.
        monitor.defer_entry(_entry(), "verbatim", "t", None, [])
        (row,) = monitor.deferred_entries()
        assert row["attempts"] == 1
        monitor.note_deferred_failure("acx-1", "tts: boom")      # no script: keep the old one
        with sqlite3.connect(monitor.db_path) as conn:
            (kept,) = conn.execute("SELECT normalized_text FROM deferred_entries").fetchone()
        assert kept == "spoken script"
        monitor.drop_deferred("acx-1")
        assert monitor.deferred_entries() == []

    def test_a_waiting_post_does_not_come_back_as_new(self, monitor):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        xml = ("<?xml version='1.0'?><rss version='2.0'><channel><title>t</title>"
               "<item><title>Waiting</title><link>https://acx/acx-1</link>"
               f"<guid>acx-1</guid><pubDate>{(now - timedelta(hours=2)):%a, %d %b %Y %H:%M:%S} GMT"
               "</pubDate><description>b</description></item></channel></rss>")
        assert [e.id for e in monitor.fetch_feed(xml, "Scott Alexander", max_age_hours=48)] \
            == ["acx-1"]
        monitor.defer_entry(_entry(), "verbatim", "t", None, [])
        assert monitor.fetch_feed(xml, "Scott Alexander", max_age_hours=48) == []


class TestEpisodePages:

    def _ep(self, entry_id="sum-1"):
        return Episode(id=entry_id, title="AI #188", description="", audio_file="x_ai.mp3",
                       published=datetime(2026, 10, 2), duration_seconds=420,
                       link="https://lw/ai188", author="Zvi")

    def test_pending_page_promises_audio_and_ready_page_plays_it(self, monitor, tmp_path):
        gen, pages = _gen(), tmp_path / "episodes"
        monitor.defer_entry(_entry(), "verbatim", "t", None, [])
        gen.write_episode_pages([self._ep()], monitor.deferred_entries(), pages)
        waiting = (pages / f"{episode_id('acx-1')}.html").read_text()
        ready = (pages / f"{episode_id('sum-1')}.html").read_text()
        assert "being read out in full" in waiting and 'http-equiv="refresh"' in waiting
        assert "<audio" not in waiting and "https://acx/acx-1" in waiting
        assert '<audio controls preload="none" src="../audio/x_ai.mp3">' in ready
        assert "refresh" not in ready and "7 min" in ready
        assert episode_page_url(BASE, "acx-1") == f"{BASE}/episodes/{episode_id('acx-1')}.html"

    def test_failed_narration_says_so_and_narrated_posts_replace_the_waiting_page(self, monitor, tmp_path):
        gen, pages = _gen(), tmp_path / "episodes"
        monitor.defer_entry(_entry(), "verbatim", "t", None, [])
        monitor.note_deferred_failure("acx-1", "tts: boom")
        gen.write_episode_pages([], monitor.deferred_entries(), pages)
        assert "failed on the last attempt" in (pages / f"{episode_id('acx-1')}.html").read_text()
        # Narrated: the same URL now plays it, and pages of departed episodes go.
        (pages / "gone.html").write_text("old")
        gen.write_episode_pages([self._ep("acx-1")], [], pages)
        assert "<audio" in (pages / f"{episode_id('acx-1')}.html").read_text()
        assert not (pages / "gone.html").exists()


class TestEmail:

    def test_waiting_post_is_listed_with_its_bullets_and_page(self, monitor):
        monitor.defer_entry(_entry(), "verbatim", "t", None, ["Land value tax works"])
        report = _build_run_report([], [], set(), [], BASE, pending=monitor.deferred_entries())
        (ep,) = report.episodes
        assert ep.pending and ep.bullets == ["Land value tax works"]
        assert ep.audio_url == episode_page_url(BASE, "acx-1")
        html = build_html(report, datetime(2026, 9, 24))
        assert "Listen (narrating)" in html and "narrating now" in html
        assert "narrated after this email" in html
        text = build_text(report, datetime(2026, 9, 24))
        assert "still narrating" in text and "Land value tax works" in text

    def test_ordinary_episode_shows_its_duration_and_no_narrating_note(self):
        ep = ReportEpisode(title="t", author="a", feed_name="f", link="", audio_url="u.mp3",
                           duration_seconds=125)
        html = build_html(RunReport(episodes=[ep]), datetime(2026, 9, 24))
        assert "2 min 05 sec" in html and "narrated after this email" not in html


# What the fake normaliser model makes of "Clean text.", the deferred post's script.
SPOKEN = "Clean text, read aloud."


def _email_text(msg) -> str:
    return msg.get_body(("plain",)).get_content()


@needs_ffmpeg
class TestNarrationPass:
    """The real normaliser, narrator and email. Only the paid APIs behind them
    (`routes`, `narrator`, `tts`) and the mail server (`smtp`) are faked."""

    @pytest.fixture
    def setup(self, tmp_path, monkeypatch, routes, narrator, tts, smtp):
        # `narrator` is not called: it sets the key and fake upload for main's own AudioGenerator.
        routes["openrouter"] = FakeApi([SPOKEN])     # the normaliser
        routes["openai"] = FakeApi([])               # the digest: the first pass wrote the bullets
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        config = load_config()
        monitor = FeedMonitor(tmp_path / "posts.db")
        audio_dir, out = tmp_path / "audio", tmp_path / "output"
        audio_dir.mkdir()
        return config, monitor, audio_dir, out, smtp

    def _narrate(self, setup):
        config, monitor, audio_dir, out, _ = setup
        asyncio.run(main._narrate_deferred(monitor, config, _gen(), audio_dir, out))

    def test_narrated_post_joins_the_feed_and_leaves_the_queue(self, setup, routes, tts):
        config, monitor, audio_dir, out, sent = setup
        monitor.defer_entry(_entry(), "verbatim", "Clean text.", None, ["b1"])
        self._narrate(setup)
        assert monitor.deferred_entries() == []
        row = monitor.get_entry("acx-1")
        assert row["audio_file"] == f"{episode_id('acx-1')}_does_georgism_work.mp3"
        assert (audio_dir / row["audio_file"]).stat().st_size > 0 and tts.texts == [SPOKEN]
        assert '"b1"' in row["bullets"] and routes["openai"].calls == []   # not digested again
        assert "<guid isPermaLink=\"false\">acx-1</guid>" in (out / "feed.xml").read_text()
        assert "<audio" in (out / "episodes" / f"{episode_id('acx-1')}.html").read_text()
        assert sent == []                       # the day's email already went out

    def test_failure_keeps_the_post_waiting_and_tells_only_the_operator(self, setup, tts):
        config, monitor, audio_dir, out, sent = setup
        monitor.defer_entry(_entry(), "verbatim", "Clean text.", None, ["b1"])
        tts.fail_on.add(SPOKEN)
        self._narrate(setup)
        (row,) = monitor.deferred_entries()
        assert row["attempts"] == 1 and row["last_error"].startswith("tts:")
        assert row["normalized_text"] == SPOKEN    # retry skips straight to TTS
        assert monitor.get_entry("acx-1") is None
        (msg,) = sent
        assert msg["To"] == "operator@example.com" and msg["Bcc"] is None   # operator only
        assert "attempt 1 of 3, will retry next run" in _email_text(msg)
        assert "failed on the last attempt" in \
               (out / "episodes" / f"{episode_id('acx-1')}.html").read_text()

    def test_a_failure_email_that_was_not_sent_fails_the_job(self, setup, tts, tmp_path,
                                                             monkeypatch):
        _, monitor, *_ = setup
        monitor.defer_entry(_entry(), "verbatim", "Clean text.", None, ["b1"])
        tts.fail_on.add(SPOKEN)
        # The real send_report, with a recipient but no login: a failed send.
        monkeypatch.setenv("FEEDCAST_EMAIL_TO", "operator@example.com")
        monkeypatch.setenv("SMTP_USER", "")
        outputs = tmp_path / "github_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        self._narrate(setup)
        assert outputs.read_text() == "report_failed=true\n"

    def test_a_post_whose_passes_keep_being_cut_off_is_given_up(self, setup, monkeypatch,
                                                                 capsys):
        config, monitor, audio_dir, out, sent = setup
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monitor.defer_entry(_entry(), "verbatim", "Clean text.", None, [])
        for _ in range(3):            # three passes killed before they could record anything
            monitor.start_narration()
        self._narrate(setup)
        assert monitor.deferred_entries() == []
        (msg,) = sent
        why = "narration: gave up after 3 attempts (the run was cut off)"
        assert f"Failed:\n  - Does Georgism Work?: {why}\n\n" in _email_text(msg)
        # In the log and on the run's summary page, like every other give-up.
        log = capsys.readouterr().out
        assert f"Giving up on Does Georgism Work?: {why}" in log
        assert f"::warning title=Feedcast entry failed::Does Georgism Work? — {why}" in log

    def test_a_passage_narrated_as_written_is_reported_with_its_episode(
            self, setup, routes, monkeypatch, capsys):
        # Every normaliser model with a key returns nothing for the post
        # (Gemini on OpenRouter, then GPT-6.1 Sol; Haiku's account has none here).
        routes["openrouter"] = FakeApi(["<no-choices>"])
        routes["openai"] = FakeApi(["<no-choices>"])
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        config, monitor, audio_dir, out, sent = setup
        monitor.defer_entry(_entry(), "verbatim", "Clean text.", None, ["b1"])
        self._narrate(setup)
        assert monitor.get_entry("acx-1")["audio_file"]         # still narrated, as written
        msg = ("Does Georgism Work?: 11 chars narrated as written because every "
               "normaliser model refused them")
        assert notices.report() == [msg]
        assert f"::warning title=Feedcast normaliser::{msg}" in capsys.readouterr().out

    def test_nothing_waiting_is_a_quick_no_op(self, setup):
        config, monitor, audio_dir, out, sent = setup
        self._narrate(setup)
        assert not (out / "feed.xml").exists()


@needs_ffmpeg
def test_deferred_post_keeps_its_first_pass_bullets(tmp_path, routes, narrator, tts):
    # The real normaliser, narrator and digest; the paid APIs behind them are faked.
    routes["openrouter"] = FakeApi([SPOKEN])     # the normaliser
    routes["openai"] = FakeApi([])               # the digest, which must not run again
    e = _entry()
    e.bullets = ["from the first pass"]
    entry, _path = asyncio.run(process_entry(
        e, "verbatim", "p", None, narrator(), TextNormalizer(), tmp_path, None,
        Attempt(stage="normalize", processed_text="Clean text.")))
    assert entry.bullets == ["from the first pass"] and routes["openai"].calls == []


def test_prepare_cleans_and_digests_but_does_not_narrate(routes):
    # The digest's model is a paid API; this fake answers both posts' requests.
    bullet = "Land value tax is the one tax that does no harm, Scott argues."
    routes["openai"] = FakeApi([f"- {bullet}", f"- {bullet}"])
    fresh, resumed = _entry("a"), _entry("b")
    attempts = {"a": Attempt(), "b": Attempt(stage="tts", normalized_text="kept script")}
    processor = ContentProcessor("p", verify=False, auto_verbatim_limit=24000)
    out = asyncio.run(_prepare_deferred([(fresh, "verbatim", "p"), (resumed, "verbatim", "p")],
                                        attempts, processor))
    cleaned = out[0].processed_text
    assert "Land." in cleaned and "<p>" not in cleaned and fresh.bullets == [bullet]
    assert out[0].normalized_text is None                      # cleaned, not narrated
    assert out[1].processed_text is None and out[1].normalized_text == "kept script"
    digested = routes["openai"].asked()
    assert sorted(digested) == sorted([out[0].processed_text, "kept script"])
