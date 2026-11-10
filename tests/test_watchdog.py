"""scripts/watchdog.py: when the morning watchdog launches an agent."""

import os
import re
import subprocess
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


def _spawn(tmp_path, monkeypatch, exit_status: int) -> Path:
    """A stand-in agent-spawn (the real one starts an agent) that records
    its arguments in the returned file and exits with `exit_status`. Briefs
    go to tmp_path/briefs."""
    bin_dir, args_log = tmp_path / "spawn-bin", tmp_path / "args"
    bin_dir.mkdir()
    spawn = bin_dir / "agent-spawn"
    spawn.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > {args_log}\nexit {exit_status}\n')
    spawn.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(watchdog, "BRIEF_DIR", tmp_path / "briefs")
    return args_log


def test_launch_writes_the_brief_and_starts_an_agent_on_this_checkout(tmp_path, monkeypatch):
    args_log = _spawn(tmp_path, monkeypatch, 0)

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


def test_the_briefs_recovery_steps_name_what_the_workflows_have():
    """The brief tells the agent what to do by the step that failed, so the
    steps, the dispatch input and the report it cites must exist. A deploy
    that was cancelled is recovered by a forced dev run, not a re-run
    (docs/publish-incident-2026-11-10.md)."""
    brief = watchdog.BRIEF_TEMPLATE.read_text()
    forced_run = f"gh workflow run {watchdog.WORKFLOW} --ref main -f force=true"
    (cancelled_deploy,) = [line for line in brief.splitlines()
                           if '"Deploy to GitHub Pages" step' in line]
    assert forced_run in cancelled_deploy
    assert "gh run rerun" not in cancelled_deploy

    wf = yaml.safe_load(WORKFLOW.read_text())
    # PyYAML reads the bare key `on` as the boolean True.
    assert "force" in wf[True]["workflow_dispatch"]["inputs"]
    assert '"Commit and push" failed' in brief
    assert "Commit and push" in [s.get("name") for s in wf["jobs"]["update"]["steps"]]
    publish = yaml.safe_load((WORKFLOW.parent / "publish-pages.yml").read_text())
    assert "Deploy to GitHub Pages" in [s.get("name")
                                        for s in publish["jobs"]["publish"]["steps"]]
    cited = re.findall(r"docs/[\w-]+\.md", brief)
    assert cited and all((watchdog.ROOT / doc).is_file() for doc in cited)


def test_a_failed_launch_fails_loudly(tmp_path, monkeypatch):
    _spawn(tmp_path, monkeypatch, 1)
    with pytest.raises(subprocess.CalledProcessError, match="agent-spawn"):
        watchdog.launch("x", [], DAY, CFG, "https://example.test/feed.xml")


def _gh(tmp_path, monkeypatch, runs: list[dict] | None) -> None:
    """A stand-in gh (the real one reads GitHub) that knows today's runs:
    each {"databaseId", "status", "url", "jobs": [{"name", "conclusion"}]},
    as the Actions API gives them. None makes every call fail, as gh does
    when GitHub does not answer."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"runs = {runs!r}\n"
        "if runs is None: sys.exit('gh: could not connect')\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['run', 'list']:\n"
        "    print(json.dumps([{k: r[k] for k in ('databaseId', 'status', 'url') if k in r} for r in runs]))\n"
        "else:\n"
        "    (run,) = [r for r in runs if f\"/runs/{r['databaseId']}/jobs\" in args[1]]\n"
        "    print(json.dumps({'jobs': run.get('jobs', [])}))\n")
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def _site(feed_xml: str, statuses: dict[str, int], heads: list[str]) -> httpx.Client:
    """The live site, which a test cannot reach: the feed, and each audio
    file's status. `heads` records which audio was asked for."""
    def answer(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if name == "feed.xml":
            return httpx.Response(200, text=feed_xml)
        heads.append(name)
        return httpx.Response(statuses[name])
    return httpx.Client(transport=httpx.MockTransport(answer))


FEED_URL = "https://example.test/feedcast/feed.xml"
JOBS_DONE = [{"name": "guard", "conclusion": "success"},
             {"name": "update", "conclusion": "success"},
             {"name": "deploy / publish", "conclusion": "success"}]


def test_a_look_reads_the_runs_and_the_feed(tmp_path, monkeypatch):
    _gh(tmp_path, monkeypatch, [{"databaseId": 7, "status": "completed",
                                 "url": "https://github.com/x/runs/7", "jobs": JOBS_DONE}])
    heads: list[str] = []
    client = _site(_feed(tmp_path, briefing=True), {"briefing.mp3": 200, "post.mp3": 200}, heads)
    verdict, runs = watchdog.look(client, FEED_URL, DAY, EARLY, CFG, True)
    assert verdict.action == "healthy"
    assert runs == [Run(url="https://github.com/x/runs/7", status="completed",
                        jobs={"guard": "success", "update": "success",
                              "deploy / publish": "success"})]
    assert sorted(heads) == ["briefing.mp3", "briefing.mp3", "post.mp3"]


def test_a_look_checks_every_episode_only_once_the_runs_have_finished(tmp_path, monkeypatch):
    jobs = JOBS_DONE + [{"name": "narrate", "conclusion": None}]
    _gh(tmp_path, monkeypatch, [{"databaseId": 7, "status": "in_progress",
                                 "url": "https://github.com/x/runs/7", "jobs": jobs}])
    heads: list[str] = []
    client = _site(_feed(tmp_path, briefing=True), {"briefing.mp3": 200}, heads)
    verdict, _ = watchdog.look(client, FEED_URL, DAY, EARLY, CFG, True)
    assert verdict.action == "wait" and heads == ["briefing.mp3"]


def test_a_look_without_a_briefing_expected_does_not_ask_for_one(tmp_path, monkeypatch):
    _gh(tmp_path, monkeypatch, [{"databaseId": 7, "status": "completed",
                                 "url": "https://github.com/x/runs/7", "jobs": JOBS_DONE}])
    heads: list[str] = []
    client = _site(_feed(tmp_path, briefing=False), {"post.mp3": 200}, heads)
    verdict, _ = watchdog.look(client, FEED_URL, DAY, EARLY, CFG, False)
    assert verdict.action == "healthy" and heads == ["post.mp3"]


def test_a_look_that_cannot_reach_github_waits_then_launches(tmp_path, monkeypatch):
    _gh(tmp_path, monkeypatch, None)
    client = _site("", {}, [])
    assert watchdog.look(client, FEED_URL, DAY, EARLY, CFG, True)[0].action == "wait"
    verdict, runs = watchdog.look(client, FEED_URL, DAY, LATE, CFG, True)
    assert verdict.action == "launch" and "could not read" in verdict.reason and runs == []


def test_a_look_that_cannot_reach_the_site_waits_then_launches(tmp_path, monkeypatch):
    _gh(tmp_path, monkeypatch, [])

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)
    client = httpx.Client(transport=httpx.MockTransport(refuse))
    assert watchdog.look(client, FEED_URL, DAY, EARLY, CFG, True)[0].action == "wait"
    verdict, _ = watchdog.look(client, FEED_URL, DAY, LATE, CFG, True)
    assert verdict.action == "launch" and "connection refused" in verdict.reason


def test_a_watchdog_that_fails_unexpectedly_launches_an_agent_then_fails(tmp_path, monkeypatch):
    """gh answering without a field the watchdog reads is an error look()
    does not expect; it fails before any request to the site."""
    _gh(tmp_path, monkeypatch, [{"databaseId": 7}])
    args_log = _spawn(tmp_path, monkeypatch, 0)
    with pytest.raises(KeyError):
        watchdog.main()
    assert "--brief" in args_log.read_text()
    (brief,) = (tmp_path / "briefs").iterdir()
    assert "What the watchdog saw: the watchdog itself failed: KeyError(" in brief.read_text()
