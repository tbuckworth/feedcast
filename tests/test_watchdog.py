"""scripts/watchdog.py: when the morning watchdog launches an agent."""

import os
from datetime import UTC, date, datetime, time
from pathlib import Path

import httpx
import pytest
import yaml

from scripts import watchdog
from scripts.watchdog import Run, assess
from src.config import load_config
from src.feed import Episode, FeedGenerator

CFG = load_config().watchdog
WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / watchdog.WORKFLOW
DAY = date(2026, 11, 6)

BEFORE_ANY_RUN = time(5, 33)
EARLY = time(5, 40)
LATE = time(5, 56)
AFTER_STOP = time(8, 31)


def _run(status="completed", **jobs) -> Run:
    return Run(url="https://github.com/tbuckworth/feedcast/actions/runs/1", status=status,
               jobs={"guard": "success", "check-llm": "skipped", **jobs})


PUBLISHED = _run(update="success", **{"deploy / publish": "success"}, narrate="skipped")
NARRATING = _run("in_progress", update="success", **{"deploy / publish": "success"},
                 narrate=None)
UPDATING = _run("in_progress", update=None)
GUARDED = _run(update="skipped")


def test_the_settings_are_in_order():
    assert CFG.no_run_after < CFG.late_after < CFG.ready_by < CFG.stop_watching_at


def test_the_update_job_is_the_daily_workflows():
    """The watchdog reads the email from this job's conclusion: it fails when
    the email was not sent (test_workflow_dev_mode.py checks that step)."""
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    assert watchdog.UPDATE_JOB in jobs
    names = [step.get("name") for step in jobs[watchdog.UPDATE_JOB]["steps"]]
    assert "Fail the job if the report email was not sent" in names


def test_no_run_is_a_failure_only_after_the_dispatch_should_have_made_one():
    assert assess([], "", [], BEFORE_ANY_RUN, CFG).action == "wait"
    verdict = assess([], "", [], CFG.no_run_after, CFG)
    assert verdict.action == "launch" and "no run" in verdict.reason


@pytest.mark.parametrize("conclusion", sorted(watchdog.FAILED))
def test_a_failed_job_launches_at_once(conclusion):
    run = _run(update=conclusion)
    verdict = assess([run], "", [], EARLY, CFG)
    assert verdict.action == "launch"
    assert f"'update' of {run.url} ended {conclusion}" in verdict.reason


def test_a_failed_narration_launches_although_the_email_is_out():
    run = _run(update="success", **{"deploy / publish": "success"}, narrate="failure")
    assert assess([run], "", [], EARLY, CFG).action == "launch"


def test_a_slow_run_is_waited_for_until_late_after():
    assert assess([UPDATING], "", [], EARLY, CFG).action == "wait"
    verdict = assess([UPDATING], "", [], LATE, CFG)
    assert verdict.action == "launch"
    assert "the email has not gone out" in verdict.reason


def test_a_missing_briefing_is_late_even_with_the_email_out():
    problem = "today's briefing (news-briefing-2026-11-06) is not in the live feed"
    assert assess([PUBLISHED], problem, [], EARLY, CFG).action == "wait"
    verdict = assess([PUBLISHED], problem, [], LATE, CFG)
    assert verdict.action == "launch" and problem in verdict.reason
    assert "email" not in verdict.reason


def test_a_run_the_guard_stopped_has_not_sent_the_email():
    assert assess([GUARDED], "", [], LATE, CFG).action == "launch"


def test_a_long_narration_is_waited_for_until_stop_watching_at():
    """Posts read out in full cannot be ready by ready_by anyway."""
    assert assess([NARRATING], "", [], LATE, CFG).action == "wait"
    verdict = assess([NARRATING], "", [], AFTER_STOP, CFG)
    assert verdict.action == "launch" and "still going" in verdict.reason


def test_a_finished_run_with_every_episode_playing_is_healthy():
    assert assess([PUBLISHED], "", [], EARLY, CFG).action == "healthy"


def test_audio_that_does_not_answer_launches():
    broken = ["https://x/feedcast/audio/a.mp3 answers 404"]
    verdict = assess([PUBLISHED], "", broken, EARLY, CFG)
    assert verdict.action == "launch" and broken[0] in verdict.reason


def test_a_later_successful_run_does_not_hide_a_failed_one():
    assert assess([_run(update="failure"), PUBLISHED], "", [], EARLY, CFG).action == "launch"


def _feed(tmp_path, *, briefing: bool) -> str:
    config = load_config().podcast
    episodes = [Episode(id="https://www.lesswrong.com/posts/x/post", title="A post",
                        description="", audio_file="post.mp3",
                        published=datetime(2026, 11, 5, 18, 0, tzinfo=UTC), duration_seconds=60,
                        audio_bytes=1000)]
    if briefing:
        episodes.insert(0, Episode(id="news-briefing-2026-11-06", title="Briefing",
                                   description="", audio_file="briefing.mp3",
                                   published=datetime(2026, 11, 6, 5, 33, tzinfo=UTC),
                                   duration_seconds=300, audio_bytes=3000))
    out = tmp_path / "feed.xml"
    FeedGenerator(config, retention_days=30).generate(episodes, out)
    return out.read_text()


def _client(statuses: dict[str, int]) -> httpx.Client:
    """The live site, which a test cannot reach: each audio file's name ->
    the status it answers."""
    return httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(statuses[request.url.path.rsplit("/", 1)[-1]])))


def test_the_briefing_is_found_in_a_real_feed_and_its_audio_checked(tmp_path):
    items = watchdog.enclosures(_feed(tmp_path, briefing=True))
    assert watchdog.briefing_problem(_client({"briefing.mp3": 200}), items, DAY) == ""
    problem = watchdog.briefing_problem(_client({"briefing.mp3": 404}), items, DAY)
    assert problem.startswith("today's briefing audio answers 404")


def test_a_feed_without_todays_briefing_says_so(tmp_path):
    items = watchdog.enclosures(_feed(tmp_path, briefing=False))
    problem = watchdog.briefing_problem(_client({}), items, DAY)
    assert problem == "today's briefing (news-briefing-2026-11-06) is not in the live feed"


def test_broken_audio_lists_only_what_does_not_answer(tmp_path):
    items = watchdog.enclosures(_feed(tmp_path, briefing=True))
    broken = watchdog.broken_audio(_client({"briefing.mp3": 200, "post.mp3": 404}), items)
    assert len(broken) == 1 and "post.mp3" in broken[0] and "404" in broken[0]


def test_launch_writes_the_brief_and_starts_an_agent_on_this_checkout(tmp_path, monkeypatch):
    """agent-spawn starts a real agent, so a stand-in records what it was given."""
    bin_dir, args_log = tmp_path / "bin", tmp_path / "args"
    bin_dir.mkdir()
    spawn = bin_dir / "agent-spawn"
    spawn.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > {args_log}\n')
    spawn.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(watchdog, "BRIEF_DIR", tmp_path / "briefs")

    watchdog.launch("job 'update' ended failure", [_run(update="failure")], DAY, CFG,
                    "https://example.test/feed.xml")

    args = args_log.read_text().split("\n")
    brief = tmp_path / "briefs" / "brief-2026-11-06.md"
    assert args[:8] == ["--repo", str(watchdog.ROOT), "--branch", "watchdog-2026-11-06",
                        "--name", "feedcast-watchdog-2026-11-06", "--brief", str(brief)]
    text = brief.read_text()
    assert "What the watchdog saw: job 'update' ended failure" in text
    assert "- https://github.com/tbuckworth/feedcast/actions/runs/1 (completed): " \
           "guard success, check-llm skipped, update failure" in text
    assert f"Titus listens from {CFG.ready_by:%H:%M} ({CFG.timezone})" in text
    assert "https://example.test/feed.xml" in text
    assert "$" not in text


def test_a_failed_launch_fails_loudly(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "agent-spawn").write_text("#!/bin/bash\nexit 1\n")
    (bin_dir / "agent-spawn").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(watchdog, "BRIEF_DIR", tmp_path / "briefs")
    with pytest.raises(Exception, match="agent-spawn"):
        watchdog.launch("x", [], DAY, CFG, "https://example.test/feed.xml")
