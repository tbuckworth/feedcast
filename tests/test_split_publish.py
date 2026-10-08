"""Summaries first, posts read out in full after: the two-publish run.

On 2026-09-26 a 113-chunk book review ran into the pipeline timeout and took
the day's briefing and summary down with it. The first pass now publishes and
emails everything a writer produced, and parks the verbatim posts in
deferred_entries; the narration pass narrates them and publishes again.
"""

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.main as main
from src.email_report import ReportEpisode, RunReport, build_html, build_text
from src.feed import Episode, FeedGenerator, PodcastConfig, episode_page_url
from src.main import Attempt, _build_run_report, _prepare_deferred, process_entry
from src.monitor import FeedEntry, FeedMonitor, episode_id
from src.processor import AUTO_VERBATIM_LIMIT, ContentProcessor

BASE = "https://tbuckworth.github.io/feedcast"


def _entry(i="acx-1", title="Does Georgism Work?", content="<p>Land.</p>", link=None):
    return FeedEntry(id=i, title=title, link=link or f"https://acx/{i}", content=content,
                     published=datetime(2026, 9, 24, 3, 0), author="Scott Alexander",
                     feed_name="Scott Alexander", authors=["Scott Alexander"],
                     feed_date=datetime(2026, 9, 24, 3, 0))


def _gen():
    return FeedGenerator(PodcastConfig(title="Feedcast", description="d", author="T",
                                       email="t@x", language="en-us", base_url=BASE))


@pytest.fixture
def monitor(tmp_path):
    return FeedMonitor(tmp_path / "posts.db")


class TestWhichPostsWait:

    def test_full_readings_wait_and_written_scripts_do_not(self):
        p = ContentProcessor("prompt")
        assert p.reads_verbatim(_entry(), "verbatim")
        assert not p.reads_verbatim(_entry(), "summarize")
        briefing = _entry("news-briefing-2026-10-08", "Daily News Briefing - 2026-10-08")
        assert not p.reads_verbatim(briefing, "verbatim")

    def test_auto_follows_the_same_length_rule_as_process(self):
        p = ContentProcessor("prompt")
        short = _entry(content=f"<p>{'word ' * 100}</p>")
        long = _entry(content=f"<p>{'x' * (AUTO_VERBATIM_LIMIT + 10)}</p>")
        assert p.reads_verbatim(short, "auto")
        assert not p.reads_verbatim(long, "auto")


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
        assert [e.id for e in monitor.fetch_feed(xml, "Scott Alexander")] == ["acx-1"]
        monitor.defer_entry(_entry(), "verbatim", "t", None, [])
        assert monitor.fetch_feed(xml, "Scott Alexander") == []


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


class _Normalizer:
    unnormalized_chars = 0
    def __init__(self, **kw):
        pass
    async def normalize_for_tts(self, text):
        return f"spoken: {text}"


class _Audio:
    fail = False
    def __init__(self, *a, **kw):
        pass
    async def generate_episode(self, text, audio_dir, ep_id, title, http_client):
        if _Audio.fail:
            raise RuntimeError("3 of 10 TTS chunks failed")
        path = Path(audio_dir) / f"{ep_id}.mp3"
        path.write_bytes(b"mp3")
        return path


class TestNarrationPass:

    @pytest.fixture
    def setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "AudioGenerator", _Audio)
        monkeypatch.setattr(main, "TextNormalizer", _Normalizer)
        async def no_digest(*a, **kw):
            raise AssertionError("bullets were written by the first pass")
        monkeypatch.setattr(main, "safe_bullets", no_digest)
        sent = []
        monkeypatch.setattr(main, "send_report",
                            lambda report, operator_only=False: sent.append((report, operator_only)))
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        _Audio.fail = False
        config = main.load_config(Path(__file__).resolve().parent.parent / "config.yaml")
        monitor = FeedMonitor(tmp_path / "posts.db")
        audio_dir, out = tmp_path / "audio", tmp_path / "output"
        audio_dir.mkdir()
        return config, monitor, audio_dir, out, sent

    def _narrate(self, setup):
        config, monitor, audio_dir, out, _ = setup
        asyncio.run(main._narrate_deferred(monitor, config, _gen(), audio_dir, out))

    def test_narrated_post_joins_the_feed_and_leaves_the_queue(self, setup):
        config, monitor, audio_dir, out, sent = setup
        monitor.defer_entry(_entry(), "verbatim", "Clean text.", None, ["b1"])
        self._narrate(setup)
        assert monitor.deferred_entries() == []
        row = monitor.get_entry("acx-1")
        assert row["audio_file"] == f"{episode_id('acx-1')}.mp3" and '"b1"' in row["bullets"]
        assert "<guid isPermaLink=\"false\">acx-1</guid>" in (out / "feed.xml").read_text()
        assert "<audio" in (out / "episodes" / f"{episode_id('acx-1')}.html").read_text()
        assert sent == []                       # the day's email already went out

    def test_failure_keeps_the_post_waiting_and_tells_only_the_operator(self, setup):
        config, monitor, audio_dir, out, sent = setup
        monitor.defer_entry(_entry(), "verbatim", "Clean text.", None, ["b1"])
        _Audio.fail = True
        self._narrate(setup)
        (row,) = monitor.deferred_entries()
        assert row["attempts"] == 1 and row["last_error"].startswith("tts:")
        assert row["normalized_text"] == "spoken: Clean text."    # retry skips straight to TTS
        assert monitor.get_entry("acx-1") is None
        (report, operator_only), = sent
        assert operator_only and "attempt 1 of 3, will retry next run" in report.failures[0][1]
        assert "failed on the last attempt" in \
               (out / "episodes" / f"{episode_id('acx-1')}.html").read_text()

    def test_a_post_whose_passes_keep_being_cut_off_is_given_up(self, setup):
        config, monitor, audio_dir, out, sent = setup
        monitor.defer_entry(_entry(), "verbatim", "Clean text.", None, [])
        for _ in range(3):            # three passes killed before they could record anything
            monitor.start_narration()
        self._narrate(setup)
        assert monitor.deferred_entries() == []
        (report, _), = sent
        assert "gave up after 3 attempts (the run was cut off)" in report.failures[0][1]

    def test_nothing_waiting_is_a_quick_no_op(self, setup, tmp_path, monkeypatch):
        out_file = tmp_path / "gh_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
        config, monitor, audio_dir, out, sent = setup
        self._narrate(setup)
        assert out_file.read_text() == "narrated=0\n" and not (out / "feed.xml").exists()


def test_deferred_post_keeps_its_first_pass_bullets(tmp_path, monkeypatch):
    async def no_digest(*a, **kw):
        raise AssertionError("must not digest again")
    monkeypatch.setattr(main, "safe_bullets", no_digest)
    e = _entry()
    e.bullets = ["from the first pass"]
    entry, _path = asyncio.run(process_entry(
        e, "verbatim", "p", None, _Audio(), _Normalizer(), tmp_path, None,
        Attempt(stage="normalize", processed_text="Clean text.")))
    assert entry.bullets == ["from the first pass"]


def test_prepare_cleans_and_digests_but_does_not_narrate(monkeypatch):
    digested = []
    async def fake_bullets(text, **kw):
        digested.append(text)
        return ["bullet"]
    monkeypatch.setattr(main, "safe_bullets", fake_bullets)

    class Processor:
        async def process(self, entry, mode, prompt, title=None):
            return f"Cleaned {entry.id}."

    fresh, resumed = _entry("a"), _entry("b")
    attempts = {"a": Attempt(), "b": Attempt(stage="tts", normalized_text="kept script")}
    out = asyncio.run(_prepare_deferred([(fresh, "verbatim", "p"), (resumed, "verbatim", "p")],
                                        attempts, Processor()))
    assert out[0].processed_text == "Cleaned a." and fresh.bullets == ["bullet"]
    assert out[1].processed_text is None and out[1].normalized_text == "kept script"
    assert digested == ["Cleaned a.", "kept script"]
