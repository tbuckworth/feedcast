"""Launch a Feedcast agent when the morning's email or episodes are not out.

The desktop crontab runs this through scripts/cron-watchdog.sh a few minutes
after scripts/cron-backstop.sh dispatches the daily run. Every
`watchdog.poll_seconds` it reads today's runs of the daily workflow (through
gh) and the live feed, and it stops at the first of these:

- Healthy: a run's update job succeeded, so it published and sent the email.
  Today's briefing is in the live feed and its audio answers. Every run has
  finished, and every episode's audio answers.
- Launch: a job of today's runs failed, no run started by `no_run_after`, the
  email or the briefing's audio was not out by `late_after`, a run was still
  going at `stop_watching_at`, or an episode's audio does not answer. It
  writes a brief from scripts/watchdog_brief.md to logs/watchdog/ and starts
  an agent on this checkout with agent-spawn.

A look that fails (GitHub or the site not answering) is logged and retried at
the next poll; one that still fails at `late_after` is itself a launch, and so
is an error the watchdog does not expect. A day whose news gave no briefing
launches an agent too. Settings: `watchdog` in config.yaml.

    uv run python -m scripts.watchdog
"""

import json
import logging
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime
from datetime import time as clock
from string import Template
from typing import Literal
from zoneinfo import ZoneInfo

import httpx

from src.config import ROOT, WatchdogConfig, load_config
from src.feed import feed_url
from src.monitor import briefing_id

log = logging.getLogger("watchdog")

# The daily workflow, and its job that publishes and sends the email. That
# job succeeds only when both happened (update-feed.yml).
WORKFLOW = "update-feed.yml"
UPDATE_JOB = "update"
# Job conclusions GitHub reports for a job that did not do its work. A job
# the guard skipped concludes "skipped", which is not a failure.
FAILED = {"failure", "cancelled", "timed_out", "startup_failure"}
BRIEF_TEMPLATE = ROOT / "scripts" / "watchdog_brief.md"
BRIEF_DIR = ROOT / "logs" / "watchdog"


@dataclass(frozen=True)
class Run:
    """One run of the daily workflow, as GitHub reports it."""

    url: str
    # queued, in_progress or completed.
    status: str
    # Job name -> conclusion; None while the job has not finished.
    jobs: dict[str, str | None]


@dataclass(frozen=True)
class Verdict:
    action: Literal["wait", "healthy", "launch"]
    reason: str


def assess(runs: list[Run], briefing_problem: str, broken_audio: list[str],
           now: clock, cfg: WatchdogConfig) -> Verdict:
    """Decide from one look at today's runs and the live feed.

    `briefing_problem` is "" when today's briefing is live (or none is
    expected) and otherwise says what is wrong with it. `broken_audio` lists
    the episodes whose audio does not answer; it is checked only once every
    run has finished, so it is [] before then.
    """
    failed = [f"job {name!r} of {run.url} ended {conclusion}"
              for run in runs for name, conclusion in run.jobs.items()
              if conclusion in FAILED]
    if failed:
        return Verdict("launch", "; ".join(failed))
    if not runs:
        if now >= cfg.no_run_after:
            return Verdict("launch", f"no run of {WORKFLOW} has started today "
                                     f"(none by {cfg.no_run_after:%H:%M})")
        return Verdict("wait", "no run yet")
    emailed = any(run.jobs.get(UPDATE_JOB) == "success" for run in runs)
    if emailed and not briefing_problem:
        if any(run.status != "completed" for run in runs):
            if now >= cfg.stop_watching_at:
                return Verdict("launch", "the email and the briefing are out, but a run "
                                         f"is still going at {cfg.stop_watching_at:%H:%M}: "
                               + ", ".join(r.url for r in runs if r.status != "completed"))
            return Verdict("wait", "the email and the briefing are out; a run is still going")
        if broken_audio:
            return Verdict("launch", "episodes in the live feed whose audio does not answer: "
                           + "; ".join(broken_audio))
        return Verdict("healthy", "the email and every episode are out")
    missing = ([] if emailed else ["the email has not gone out (no update job has succeeded)"]
               ) + ([briefing_problem] if briefing_problem else [])
    if now >= cfg.late_after:
        return Verdict("launch", f"at {cfg.late_after:%H:%M} " + " and ".join(missing))
    return Verdict("wait", "; ".join(missing))


def _gh_json(*args: str) -> object:
    """Run gh in this checkout, so that {owner}/{repo} is its origin."""
    out = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True,
                         check=True, timeout=60).stdout
    return json.loads(out)


def todays_runs(day: date) -> list[Run]:
    """Runs of the daily workflow created on `day` (UTC), with their jobs."""
    listed = _gh_json("run", "list", "--workflow", WORKFLOW, "--created", day.isoformat(),
                      "--limit", "20", "--json", "databaseId,status,url")
    runs = []
    for run in listed:
        jobs = _gh_json("api", f"repos/{{owner}}/{{repo}}/actions/runs/{run['databaseId']}/jobs")
        runs.append(Run(url=run["url"], status=run["status"],
                        jobs={job["name"]: job["conclusion"] for job in jobs["jobs"]}))
    return runs


def enclosures(feed_xml: str) -> dict[str, str]:
    """Each item's guid -> the URL of its audio."""
    channel = ET.fromstring(feed_xml).find("channel")
    return {item.findtext("guid"): item.find("enclosure").get("url")
            for item in channel.findall("item")}


def audio_status(client: httpx.Client, url: str) -> int:
    return client.head(url, follow_redirects=True).status_code


def briefing_problem(client: httpx.Client, items: dict[str, str], day: date) -> str:
    """What is wrong with today's briefing in the live feed; "" if nothing."""
    url = items.get(briefing_id(day.isoformat()))
    if url is None:
        return f"today's briefing ({briefing_id(day.isoformat())}) is not in the live feed"
    status = audio_status(client, url)
    return "" if status == 200 else f"today's briefing audio answers {status}: {url}"


def broken_audio(client: httpx.Client, items: dict[str, str]) -> list[str]:
    statuses = {guid: audio_status(client, url) for guid, url in items.items()}
    return [f"{guid} ({items[guid]}) answers {status}"
            for guid, status in statuses.items() if status != 200]


def launch(reason: str, runs: list[Run], day: date, cfg: WatchdogConfig, live_feed: str) -> None:
    """Write the brief and start an agent on this checkout."""
    BRIEF_DIR.mkdir(parents=True, exist_ok=True)
    brief = BRIEF_DIR / f"brief-{day}.md"
    run_lines = [f"- {run.url} ({run.status}): "
                 + ", ".join(f"{name} {conclusion or 'running'}"
                             for name, conclusion in run.jobs.items())
                 for run in runs]
    brief.write_text(Template(BRIEF_TEMPLATE.read_text()).substitute(
        date=day.isoformat(), reason=reason, runs="\n".join(run_lines) or "- none",
        ready_by=f"{cfg.ready_by:%H:%M}", timezone=cfg.timezone, feed_url=live_feed))
    command = ["agent-spawn", "--repo", str(ROOT), "--branch", f"watchdog-{day}",
               "--name", f"feedcast-watchdog-{day}", "--brief", str(brief)]
    log.warning("Launching an agent: %s", reason)
    log.info("Running %s", " ".join(command))
    subprocess.run(command, check=True, timeout=600)


def look(client: httpx.Client, live_feed: str, day: date, now: clock, cfg: WatchdogConfig,
         briefing_expected: bool) -> tuple[Verdict, list[Run]]:
    """One look at today's runs and the live feed, and what to do about them.

    A look that fails (GitHub or the site not answering) waits for the next
    poll, and from `late_after` on it is itself a launch.
    """
    try:
        runs = todays_runs(day)
        # The query string gets past the site's 10-minute cache.
        feed = client.get(live_feed, params={"watchdog": int(time.time())})
        feed.raise_for_status()
        items = enclosures(feed.text)
        problem = briefing_problem(client, items, day) if briefing_expected else ""
        done = bool(runs) and all(run.status == "completed" for run in runs)
        broken = broken_audio(client, items) if done else []
    except (subprocess.SubprocessError, httpx.HTTPError, ET.ParseError,
            json.JSONDecodeError) as error:
        log.warning("Could not read the runs or the live feed: %s", error)
        reason = f"the watchdog could not read the runs or the live feed: {error}"
        return Verdict("launch" if now >= cfg.late_after else "wait", reason), []
    return assess(runs, problem, broken, now, cfg), runs


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config()
    cfg = config.watchdog
    url = feed_url(config.podcast.base_url)
    with httpx.Client(timeout=30) as client:
        while True:
            day = datetime.now(UTC).date()
            now = datetime.now(ZoneInfo(cfg.timezone)).time()
            try:
                verdict, runs = look(client, url, day, now, cfg, config.briefing_enabled)
            except Exception as error:
                # A watchdog that dies unseen is the failure it exists to
                # prevent: launch, then fail as loudly as before.
                log.exception("The watchdog failed")
                launch(f"the watchdog itself failed: {error!r}", [], day, cfg, url)
                raise
            log.info("%s: %s", verdict.action, verdict.reason)
            if verdict.action == "healthy":
                return 0
            if verdict.action == "launch":
                launch(verdict.reason, runs, day, cfg, url)
                return 0
            time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
