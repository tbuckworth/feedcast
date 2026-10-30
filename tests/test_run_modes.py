"""What async_main does in each of its modes, end to end.

Each test runs the pipeline on the scratch repository of the `pipeline`
fixture (tests/conftest.py) and checks what the run leaves behind: the
database, the files under data/ and output/, the report it emailed and how it
sent it, the step outputs it hands the workflow, the ntfy pushes, and the log
lines someone reading the run's log goes by. test_publish.py covers the
published site in detail and test_pipeline_failures.py the failure paths.
"""

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.config import load_config
from src.email_report import LinkedPost, RunReport
from src.extractor import ExtractionError, url_to_entry_id
from src.monitor import FeedEntry, briefing_id, episode_id
from tests.conftest import BULLET, Model, item, needs_ffmpeg

# The real narrator joins its chunks with ffmpeg, and the feed reads each MP3 with ffprobe.
pytestmark = needs_ffmpeg

BASE = load_config().podcast.base_url
TODAY = f"{datetime.now():%Y-%m-%d}"
BRIEFING = briefing_id(TODAY)
BRIEFING_TITLE = f"Daily News Briefing - {TODAY}"
SCRIPT = "Friday's briefing. Parliament passed a land tax."
SUMMARY = "Zvi argues that land value taxes work."

FULL = "https://acx.example/georgism"            # read out in full
SUMMARISED = "https://zvi.example/land"          # summarised
MATHS = "https://proofs.example/fixed-point"     # too mathematical to narrate
LW = "https://www.lesswrong.com/posts/AAAAAAAAAAAAAAAAA/on-land"
LATEX = " ".join(["Then $x^2 = y_1$ holds."] * 12)


def writer(messages) -> str:
    """The writer: a summary when it is handed a post, the day's briefing otherwise."""
    return SUMMARY if messages[-1]["content"].startswith("Title: ") else SCRIPT


@pytest.fixture
def day(pipeline, routes):
    """A news briefing, a post to summarise, one read out in full, and one of formulas."""
    pipeline.news(item("Land tax passes", "https://bbc.example/land"))
    routes["anthropic"] = Model(writer)
    pipeline.feed("Scott", item("Does Georgism Work?", FULL))
    pipeline.feed("Zvi", item("On Land", SUMMARISED), mode="summarize")
    pipeline.feed("Proofs", item("A Fixed Point", MATHS, body=LATEX))
    return pipeline


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    """The file GitHub Actions reads step outputs from."""
    path = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))
    return path


def mp3(entry_id: str, title: str) -> str:
    """The file the narrator saves an episode as: its id, then its title made safe."""
    return f"{episode_id(entry_id)}_{title}.mp3"


def _run(pipeline, **env) -> RunReport | None:
    """Run the pipeline once; the report it emailed, or None if it sent none."""
    before = len(pipeline.reports)
    pipeline.run(**env)
    return pipeline.reports[-1] if len(pipeline.reports) > before else None


def _posts(pipeline) -> dict[str, dict]:
    """processed_posts, by id."""
    with sqlite3.connect(pipeline.monitor.db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM processed_posts")}


def _logged_in_order(log: str, *lines: str | re.Pattern) -> None:
    """Each of `lines` is a whole line of `log` (a pattern matches one), in this order."""
    out, at = log.splitlines(), 0
    for line in lines:
        hits = [i for i, got in enumerate(out[at:], at)
                if (line.fullmatch(got) if isinstance(line, re.Pattern) else got == line)]
        assert hits, f"not logged after line {at}: {line!r}"
        at = hits[0] + 1


def lesswrong(posted: datetime, markdown: str):
    """LessWrong's GraphQL: the post was written at `posted`, and reads as `markdown`."""
    def answer(request: httpx.Request) -> httpx.Response:
        if "postedAt" in json.loads(request.content)["query"]:
            result = {"postedAt": f"{posted:%Y-%m-%dT%H:%M:%S}.000Z"}
        else:
            result = {"contents": {"markdown": markdown}}
        return httpx.Response(200, json={"data": {"post": {"result": result}}})
    return answer


class TestFirstPass:

    def test_it_narrates_what_was_written_parks_full_readings_and_links_the_maths(
            self, day, outputs, capsys):
        report = _run(day, FEEDCAST_PASS="first")
        log = capsys.readouterr().out
        posts = _posts(day)

        # The briefing and the summary are episodes; the maths post is
        # recorded without audio, so it is never picked up again.
        assert {i: r["audio_file"] for i, r in posts.items()} == {
            BRIEFING: mp3(BRIEFING, f"daily_news_briefing_-_{TODAY}"),
            SUMMARISED: mp3(SUMMARISED, "on_land"),
            MATHS: None}
        assert json.loads(posts[SUMMARISED]["bullets"]) == [BULLET]
        assert json.loads(posts[SUMMARISED]["writer"])["model"]
        verdict = json.loads(posts[MATHS]["maths"])
        assert (verdict["hits"], verdict["source"]) == (12, "rss")
        # The post read out in full waits for the narration pass, cleaned and digested.
        (parked,) = day.monitor.deferred_entries()
        assert (parked["id"], parked["mode"], parked["attempts"]) == (FULL, "verbatim", 0)
        assert "By Scott." in parked["processed_text"]
        assert parked["processed_text"].endswith("End of Does Georgism Work?.")
        assert parked["normalized_text"] == "" and parked["bullets"] == [BULLET]
        assert day.monitor.pending_failures() == []
        # Tomorrow's briefing is written knowing what today's said.
        assert [b["briefing_text"] for b in day.monitor.get_recent_briefings()] == [SCRIPT]
        # The writer's prompt and reply, kept for each episode a model wrote.
        assert sorted(p.name for p in (day.root / "data" / "sources").iterdir()) == sorted(
            [f"{episode_id(BRIEFING)}.md", f"{episode_id(SUMMARISED)}.md"])
        assert outputs.read_text() == "deferred=1\n"

        assert day.sent_with == [{"images": {}}]
        assert [(e.title, e.pending, e.bullets) for e in report.episodes] == [
            (BRIEFING_TITLE, False, [BULLET]),
            ("On Land", False, [BULLET]),
            ("Does Georgism Work?", True, [BULLET])]
        assert report.episodes[0].briefing_text == SCRIPT
        assert report.linked == [LinkedPost(title="A Fixed Point", author="Proofs",
                                            feed_name="Proofs", link=MATHS,
                                            maths_score=verdict["score"], source="rss")]
        assert (report.failures, report.dead_sources, report.recent, report.notices,
                report.charts) == ([], [], [], [], [])
        assert report.total_in_feed == 2

        _logged_in_order(
            log,
            f"Loading configuration from {day.root / 'config.yaml'}",
            "Phase 1: Fetching 3 feeds in parallel...",
            "  Only entries published in the last 48h are eligible",
            f"  Fetching: Scott ({day.root / 'feeds' / 'Scott.xml'})",
            "  Scott: 1 new entries",
            "  Zvi: 1 new entries",
            "  Proofs: 1 new entries",
            "  Synthesizing briefing via LLM...",
            "Checking 4 entries for maths density...",
            f"  Too mathematical for audio ({verdict['score']}/1k via rss): A Fixed Point",
            "Narrating after the first publish: Does Georgism Work?",
            "2 entries to process",
            "Phase 2: Processing 2 entries in parallel...",
            "Phase 3: Finalizing...",
            "  2 new episodes created",
            "Generating podcast feed...",
            f"  Generated feed with 2 episodes: {day.root / 'output' / 'feed.xml'}",
            "Pipeline complete.")

    def test_the_narration_pass_publishes_the_parked_post_and_emails_nobody(
            self, day, outputs, capsys):
        day.run(FEEDCAST_PASS="first")
        (parked,) = day.monitor.deferred_entries()
        outputs.unlink()
        capsys.readouterr()

        assert day.run(FEEDCAST_PASS="narrate") is None   # the day's email went out already
        log = capsys.readouterr().out
        posts = _posts(day)
        assert posts[FULL]["audio_file"] == mp3(FULL, "does_georgism_work")
        assert json.loads(posts[FULL]["bullets"]) == [BULLET]   # the first pass's digest
        assert day.monitor.deferred_entries() == [] and day.monitor.pending_failures() == []
        assert not outputs.exists()
        _logged_in_order(
            log,
            f"Loading configuration from {day.root / 'config.yaml'}",
            "Narration pass: 1 post read out in full",
            "  Processing: Does Georgism Work?",
            f"    Resuming with the script from an earlier attempt "
            f"({len(parked['processed_text'])} chars)",
            "  1 narrated",
            f"  Generated feed with 3 episodes: {day.root / 'output' / 'feed.xml'}")
        assert "Phase 1: " not in log and "Pipeline complete." not in log


class TestInjection:

    def test_an_injected_post_is_narrated_in_one_pass_without_the_feed_stages(
            self, pipeline, outputs, capsys):
        """Not deferred, not checked for maths, not swapped for LessWrong's text."""
        pipeline.answer = lambda request: httpx.Response(
            200 if request.url.host == "ntfy.sh" else 502)
        report = _run(pipeline, INJECT_URL=LW, INJECT_MODE="verbatim", FEEDCAST_PASS="first",
                      NTFY_TOPIC="feedcast-test")
        log = capsys.readouterr().out
        entry_id = url_to_entry_id(LW)
        posts = _posts(pipeline)
        assert list(posts) == [entry_id]
        assert posts[entry_id]["audio_file"] == mp3(entry_id, "land")
        assert pipeline.monitor.deferred_entries() == []
        assert [r.url.host for r in pipeline.requests] == ["ntfy.sh"]
        assert outputs.read_text() == "deferred=0\n"
        assert [e.title for e in report.episodes] == ["Land"]
        (push,) = pipeline.ntfy()
        assert push.content.decode() == "New episode: Land"
        _logged_in_order(
            log,
            f"URL injection requested: {LW} (mode: verbatim)",
            f"Loading configuration from {pipeline.root / 'config.yaml'}",
            "Injecting URL (skipping RSS feeds)...",
            f"  Extracted: Land ({len(posts[entry_id]['content'])} chars)",
            "1 entries to process",
            "Phase 2: Processing 1 entries in parallel...",
            "  1 new episodes created",
            "Pipeline complete.")
        assert "Phase 1: " not in log and "maths density" not in log

    def test_a_page_that_cannot_be_read_pushes_why_and_fails_the_run(
            self, pipeline, monkeypatch, capsys):
        # trafilatura's download of the page, over the network, comes back empty.
        monkeypatch.setattr("src.extractor.trafilatura.fetch_url", lambda url: None)
        pipeline.answer = lambda request: httpx.Response(200)
        with pytest.raises(ExtractionError, match="Failed to fetch URL"):
            pipeline.run(INJECT_URL=LW, NTFY_TOPIC="feedcast-test")
        (push,) = pipeline.ntfy()
        assert push.headers["Tags"] == "x"
        assert push.content.decode() == f"Failed to process: {LW}\nFailed to fetch URL: {LW}"
        assert pipeline.reports == [] and _posts(pipeline) == {}
        assert not (pipeline.root / "output").exists()
        _logged_in_order(capsys.readouterr().out,
                         f"URL injection requested: {LW} (mode: auto)",
                         f"  Extraction failed: Failed to fetch URL: {LW}")


class TestReprocess:

    @pytest.mark.parametrize("hours_ago, found", [
        (240, ["  Zvi: 0 new entries", "  Reprocessing: On Land (Zvi, mode verbatim)"]),
        (1, ["  Zvi: 1 new entries", "    Overriding mode to verbatim (force_verbatim)"]),
    ])
    def test_a_reprocess_narrates_the_post_again_in_one_pass(
            self, pipeline, routes, outputs, capsys, hours_ago, found):
        """Found inside the window or out of it; full text, no maths filter, no deferral."""
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        posted = now - timedelta(days=12)
        pipeline.monitor.mark_processed(
            FeedEntry(id=LW, title="On Land", link=LW, content="<p>Old.</p>",
                      published=posted, author="Zvi", feed_name="Zvi"), "old.mp3")
        pipeline.feed("Zvi", item("On Land", LW, hours_ago=hours_ago), mode="summarize")
        routes["anthropic"] = Model(writer)
        pipeline.answer = lesswrong(posted, LATEX)

        report = _run(pipeline, REPROCESS_ENTRY=LW, FORCE_VERBATIM="true", FEEDCAST_PASS="first")
        log = capsys.readouterr().out
        row = _posts(pipeline)[LW]
        assert row["audio_file"] == mp3(LW, "on_land")
        assert "x^2" in row["content"]                     # LessWrong's text, formulas and all
        assert routes["anthropic"].calls == []             # read out, not summarised
        assert pipeline.monitor.deferred_entries() == []
        assert outputs.read_text() == "deferred=0\n"
        (episode,) = report.episodes
        assert (episode.title, episode.published) == ("On Land", posted)
        assert episode.surfaced.date() == (now - timedelta(hours=hours_ago)).date()
        assert report.linked == []
        _logged_in_order(
            log,
            f"Reprocess requested for: {LW}",
            f"Force verbatim enabled for: {LW}",
            f"Loading configuration from {pipeline.root / 'config.yaml'}",
            "  Deleted entry from database, will reprocess",
            "Phase 1: Fetching 1 feeds in parallel...",
            *found,
            f"    On Land: posted {posted:%Y-%m-%d}, "
            f"in feed {now - timedelta(hours=hours_ago):%Y-%m-%d}",
            re.compile(r"  Recovered full text: On Land \([\d,]+ -> [\d,]+ chars\)"),
            "1 entries to process",
            "  1 new episodes created",
            "Pipeline complete.")
        assert "maths density" not in log


class TestResend:

    def test_a_resend_emails_the_latest_day_again_and_changes_nothing_else(
            self, day, outputs, capsys):
        first = _run(day, FEEDCAST_PASS="first")
        outputs.unlink()
        # An episode from before the digest column: the resend digests it.
        day.monitor.set_bullets(SUMMARISED, [])
        capsys.readouterr()

        report = _run(day, RESEND_REPORT="true")
        log = capsys.readouterr().out
        assert day.sent_with[-1] == {}
        # The day's episodes and the linked post; the parked post is not listed.
        assert [(e.title, e.bullets) for e in report.episodes] == [
            (BRIEFING_TITLE, [BULLET]), ("On Land", [BULLET])]
        assert report.linked == first.linked
        assert (report.failures, report.recent, report.dead_sources, report.charts) == \
            ([], [], [], [])
        assert json.loads(_posts(day)[SUMMARISED]["bullets"]) == [BULLET]
        assert len(day.monitor.deferred_entries()) == 1
        assert not outputs.exists()
        _logged_in_order(log,
                         f"Re-sending the report for {TODAY} (3 entries)",
                         "  Backfilling digests for 1 entries...",
                         "    1 bullets: On Land")
        assert "Phase 1: " not in log and "Pipeline complete." not in log

    def test_an_empty_database_has_nothing_to_resend(self, pipeline, capsys):
        assert pipeline.run(RESEND_REPORT="true") is None
        assert "Nothing in the database to report on." in capsys.readouterr().out.splitlines()


def test_a_preview_emails_a_fresh_briefing_and_records_nothing(day, capsys):
    report = _run(day, PREVIEW_BRIEFING="true")
    assert day.sent_with == [{"subject_tag": "[Preview]", "images": {}}]
    assert [(e.title, e.bullets, e.briefing_text) for e in report.episodes] == [
        (f"Preview: {BRIEFING_TITLE}", [BULLET], ""), ("Full script", [], SCRIPT)]
    assert (report.feed_url, report.site_url, report.charts) == (f"{BASE}/feed.xml", BASE, [])
    assert _posts(day) == {} and day.monitor.get_recent_briefings() == []
    assert day.monitor.deferred_entries() == []
    assert not (day.root / "output").exists() and not (day.root / "data" / "sources").exists()
    assert "Phase 1: " not in capsys.readouterr().out


def test_a_post_that_failed_on_an_earlier_run_goes_straight_to_narration(
        pipeline, routes, capsys):
    """Its normalised script was kept, so neither the writer nor the normaliser runs."""
    three_days = datetime.now() - timedelta(days=3)
    pipeline.monitor.record_failure(
        FeedEntry(id=FULL, title="Does Georgism Work?", link=FULL, content="<p>Land.</p>",
                  published=three_days, author="Scott", feed_name="Scott"),
        "tts: ReadError", "Spoken script about land.")
    pipeline.feed("Scott", item("Does Georgism Work?", FULL, hours_ago=72))
    report = _run(pipeline)
    assert routes["openrouter"].calls == []
    assert [e.title for e in report.episodes] == ["Does Georgism Work?"]
    assert _posts(pipeline)[FULL]["audio_file"] == mp3(FULL, "does_georgism_work")
    assert pipeline.monitor.pending_failures() == []
    _logged_in_order(
        capsys.readouterr().out,
        "  Scott: 0 new entries",
        "  Retrying from an earlier run: Does Georgism Work? "
        "(attempt 2 of 3, script kept — straight to narration)",
        "1 entries to process",
        "    Resuming with the normalised script from an earlier attempt (25 chars)",
        "  1 new episodes created")


def test_an_entry_that_fails_twice_is_queued_and_annotated(pipeline, monkeypatch, tts,
                                                           capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    tts.fail_on.add("land value taxes")      # DeepInfra drops the post's one chunk
    pipeline.feed("Scott", item("Does Georgism Work?", FULL))
    report = _run(pipeline)
    error = ("tts: RuntimeError: 1 of 1 TTS chunks failed (0 kept for retry): "
             "ReadError: connection dropped")
    why = f"{error} — attempt 1 of 3, will retry next run"
    assert report.failures == [("Does Georgism Work?", why)]
    assert report.episodes == []
    (queued,) = pipeline.monitor.pending_failures()
    assert (queued["id"], queued["attempts"], queued["last_error"]) == (FULL, 1, error)
    assert queued["normalized_text"]                      # tomorrow starts at narration
    _logged_in_order(
        capsys.readouterr().out,
        "  Second pass: retrying 1 failed entry serially...",
        f"    Does Georgism Work?: failed at {error}",
        "Phase 3: Finalizing...",
        f"  Error processing Does Georgism Work? at {error}",
        f"::warning title=Feedcast entry failed::Does Georgism Work? — {why}",
        "  0 new episodes created",
        "Pipeline complete.")


@pytest.mark.parametrize("always", [False, True])
def test_a_run_with_nothing_new_emails_only_when_told_to(pipeline, outputs, capsys, always):
    pipeline.monitor.mark_processed(
        FeedEntry(id=FULL, title="Does Georgism Work?", link=FULL, content="<p>Land.</p>",
                  published=datetime.now(), author="Scott", feed_name="Scott"), "old.mp3")
    pipeline.feed("Scott", item("Does Georgism Work?", FULL))
    report = _run(pipeline, **({"FEEDCAST_EMAIL_ALWAYS": "true"} if always else {}))
    log = capsys.readouterr().out
    assert outputs.read_text() == "deferred=0\n"
    _logged_in_order(log, "0 entries to process", "No new entries to process.",
                     "Generating podcast feed...", "Pipeline complete.")
    skipped = ("  Nothing new — email report skipped "
               "(set FEEDCAST_EMAIL_ALWAYS=true to send anyway)")
    if always:
        assert report.episodes == [] and report.failures == []
        assert skipped not in log.splitlines()
    else:
        assert report is None and skipped in log.splitlines()


@pytest.mark.parametrize("mode", [{"REPROCESS_ENTRY": LW}, {"RESEND_REPORT": "true"}])
def test_an_unknown_pass_stops_the_run_before_it_changes_anything(pipeline, mode):
    """A mistyped FEEDCAST_PASS is refused before a reprocess sets its post aside."""
    pipeline.monitor.mark_processed(
        FeedEntry(id=LW, title="On Land", link=LW, content="<p>Old.</p>",
                  published=datetime(2026, 10, 1), author="Zvi", feed_name="Zvi"), "old.mp3")
    with pytest.raises(ValueError):
        pipeline.run(FEEDCAST_PASS="narration", **mode)
    assert LW in _posts(pipeline)
