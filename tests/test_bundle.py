"""Source bundles: what the writer saw is kept, the state branch round-trips,
and the CI scripts that commit and publish a run's files."""

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.bundle import (FIDELITY_CHECK, SYSTEM_PROMPT, WRITER_INPUT, WRITER_OUTPUT,
                        read_bundle, write_bundle, writer_bundle)
from src.monitor import FeedEntry, FeedMonitor, episode_id
from src.news import NewsAggregator
from src.processor import ContentProcessor
from tests.conftest import FakeApi

REPO = Path(__file__).resolve().parent.parent
STATE_SH = REPO / "scripts" / "state.sh"
PUBLISH_AUDIO_SH = REPO / "scripts" / "publish-audio.sh"
COMMIT_SH = REPO / "scripts" / "ci-commit-and-push.sh"
IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}


def test_bundle_keeps_prompt_input_and_output_verbatim():
    text = writer_bundle(title="On Writing #3", model="anthropic/claude-opus-4.6",
                         system_prompt="Summarise for audio.",
                         user_message="Title: On Writing #3\n\nContent:\nZvi says 45% of…",
                         response="Zvi argues that forty-five percent…")
    assert text.startswith("# On Writing #3\n")
    assert "Writer: anthropic/claude-opus-4.6" in text
    assert "## System prompt\n\nSummarise for audio." in text
    assert "## What the writer was given\n\nTitle: On Writing #3\n\nContent:\nZvi says 45% of…" in text
    assert text.rstrip().endswith("## What the writer wrote\n\nZvi argues that forty-five percent…")


# A briefing's input has ## headings of its own; only the bundle's split it.
BRIEFING_INPUT = ("Today is Friday, 30 October 2026.\n\n## Today's articles:\n"
                  "## Selected stories (full text where available)\n\n## AI\n"
                  "- [Lab blog] A model ships\n  URL: https://example.com/a\n  It shipped.")


def test_read_bundle_returns_each_section_as_written():
    sections = {SYSTEM_PROMPT: "Write a briefing.\n\n## Style\nPlain.",
                WRITER_INPUT: BRIEFING_INPUT,
                WRITER_OUTPUT: "  Good morning. A model shipped.",
                FIDELITY_CHECK: '- [unsupported, low] "shipped"'}
    text = writer_bundle(title="Daily briefing", model="claude-opus-5-5",
                         system_prompt=sections[SYSTEM_PROMPT], user_message=BRIEFING_INPUT,
                         response=sections[WRITER_OUTPUT] + "\n\n",
                         notes=sections[FIDELITY_CHECK])
    assert read_bundle(text) == sections


def test_read_bundle_leaves_out_a_section_the_bundle_lacks():
    text = writer_bundle(title="t", model="m", system_prompt="s", user_message="u",
                         response="", notes="  ")
    assert read_bundle(text) == {SYSTEM_PROMPT: "s", WRITER_INPUT: "u", WRITER_OUTPUT: ""}
    assert read_bundle("# Not a bundle\n\n## Something else\nx") == {}


# A written episode keeps its checked script, its bundle and its fidelity check.
# The writer and the checker are paid models: one fake Anthropic account answers
# both, in call order: the draft, the check, the revision, the re-check.
FLAG = {"verdict": "distorted", "severity": "high", "script_quote": "Zvi agrees",
        "source_quote": "Zvi disagrees", "explanation": "the stance is inverted"}
DRAFT = "Zvi agrees with the plan, and says so at length."
REVISED = "Zvi disagrees with the plan, and says so at length."
CHECKED = [DRAFT, json.dumps({"claims_total": 3, "flags": [FLAG]}), REVISED,
           json.dumps({"claims_total": 3, "flags": []})]
# The re-check's model reads the revision, so its credit is the checker's.
SONNET = {"model": "claude-sonnet-5-5", "route": "anthropic", "primary": "claude-sonnet-5-5",
          "backup": False}
FIDELITY = {"status": "revised", "claims_total": 3, "flags": [FLAG], "remaining": [],
            "revised": True, "note": "", "checker": SONNET}
FIDELITY_NOTES = (
    "Status: revised\nClaims: 3; flags: 1; material: 1\n\n"
    "Flags on the draft:\n"
    '- [distorted, high] "Zvi agrees" — the stance is inverted (source: "Zvi disagrees")\n\n'
    "Remaining after revision:\n- none\n\n"
    f"### Draft before revision\n\n{DRAFT}")
OPUS = {"model": "claude-opus-5-5", "route": "anthropic", "primary": "claude-opus-5-5",
        "backup": False}


def test_a_summary_keeps_its_checked_script_bundle_and_fidelity(routes):
    routes["anthropic"] = FakeApi(CHECKED)
    entry = FeedEntry(id="p", title="On Plans", link="https://e.com/p",
                      content="<p>Zvi disagrees with the plan.</p>",
                      published=datetime(2026, 10, 10), author="Zvi", feed_name="Zvi")
    processor = ContentProcessor("Summarise.", verify=True, auto_verbatim_limit=24000)

    assert asyncio.run(processor.summarize(entry)) == REVISED
    assert entry.fidelity == FIDELITY and entry.writer == OPUS
    assert entry.bundle.startswith("# On Plans\n\nWriter: claude-opus-5-5 via anthropic\n\n")
    assert read_bundle(entry.bundle) == {
        SYSTEM_PROMPT: "Summarise.",
        WRITER_INPUT: "Title: On Plans\nAuthor: Zvi\nPublished: 2026-10-10\n\n"
                      "Content:\nZvi disagrees with the plan.",
        WRITER_OUTPUT: REVISED,
        FIDELITY_CHECK: FIDELITY_NOTES}


def test_a_briefing_keeps_its_checked_script_bundle_and_fidelity(routes, monkeypatch):
    routes["anthropic"] = FakeApi(CHECKED)
    agg = NewsAggregator(sources=[], prompt="Brief.", lookback_hours=24, full_text_stories=0,
                         max_article_chars=6000, author="Feedcast Bot", verify=True)
    article = {"title": "A plan", "source": "BBC", "category": "politics",
               "summary": "Zvi disagrees with the plan.", "url": "https://e.com/plan",
               "published": datetime.now(timezone.utc)}
    # The news sources are RSS feeds on the network; one fetched article stands in.
    monkeypatch.setattr(agg, "fetch_all_sources", lambda: asyncio.sleep(0, [article]))

    entry = asyncio.run(agg.generate_briefing())

    today = datetime.now()
    assert entry.content == REVISED and entry.fidelity == FIDELITY and entry.writer == OPUS
    assert entry.bundle.startswith(f"# Daily News Briefing - {today:%Y-%m-%d}\n\n"
                                   "Writer: claude-opus-5-5 via anthropic\n\n")
    assert read_bundle(entry.bundle) == {
        SYSTEM_PROMPT: "Brief.",
        WRITER_INPUT: f"Today is {today:%A, %d %B %Y}. Use this date when you open the "
                      "briefing, not a date taken from any article.\n\n## Today's articles:\n"
                      "## POLITICS\n- [BBC] A plan\n  URL: https://e.com/plan\n"
                      "  Zvi disagrees with the plan.",
        WRITER_OUTPUT: REVISED,
        FIDELITY_CHECK: FIDELITY_NOTES}


def test_an_unchecked_script_keeps_a_bundle_without_a_fidelity_section(routes):
    routes["anthropic"] = FakeApi([DRAFT])
    entry = FeedEntry(id="p", title="On Plans", link="https://e.com/p", content="<p>Body.</p>",
                      published=datetime(2026, 10, 10), author="Zvi", feed_name="Zvi")
    processor = ContentProcessor("Summarise.", verify=False, auto_verbatim_limit=24000)

    assert asyncio.run(processor.summarize(entry)) == DRAFT
    assert entry.fidelity is None and entry.writer == OPUS
    assert read_bundle(entry.bundle)[WRITER_OUTPUT] == DRAFT
    assert FIDELITY_CHECK not in read_bundle(entry.bundle)


def test_bundle_file_is_named_by_episode_id(tmp_path):
    eid = episode_id("https://example.com/post")
    path = write_bundle(tmp_path / "sources", eid, "# x\n")
    assert path == tmp_path / "sources" / f"{eid}.md"
    assert len(eid) == 12 and path.read_text() == "# x\n"


def test_cleanup_deletes_the_bundle_with_the_episode(tmp_path):
    monitor = FeedMonitor(tmp_path / "posts.db")
    old = FeedEntry(id="old-post", title="Old", link="https://e.com/old", content="",
                    published=datetime.now() - timedelta(days=40), author="a", feed_name="f")
    new = FeedEntry(id="new-post", title="New", link="https://e.com/new", content="",
                    published=datetime.now(), author="a", feed_name="f")
    monitor.mark_processed(old, "old.mp3")
    monitor.mark_processed(new, "new.mp3")
    with sqlite3.connect(tmp_path / "posts.db") as conn:
        conn.execute("UPDATE processed_posts SET processed_at=? WHERE id='old-post'",
                     ((datetime.now() - timedelta(days=40)).isoformat(),))
    sources = tmp_path / "sources"
    write_bundle(sources, episode_id("old-post"), "old")
    write_bundle(sources, episode_id("new-post"), "new")

    removed = monitor.cleanup_old_entries(days=30, sources_dir=sources)

    assert removed == 1
    assert not (sources / f"{episode_id('old-post')}.md").exists()
    assert (sources / f"{episode_id('new-post')}.md").exists()


def _git(*args, cwd, **kw):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                          capture_output=True, **kw).stdout


def _clone_without_state(tmp_path):
    remote = tmp_path / "remote.git"
    _git("init", "--bare", "-q", str(remote), cwd=tmp_path)
    work = tmp_path / "work"
    _git("clone", "-q", str(remote), str(work), cwd=tmp_path)
    return work


def test_state_branch_round_trips_db_and_audio_without_history(tmp_path):
    """push replaces the branch with one parentless commit; pull restores the files."""
    work = _clone_without_state(tmp_path)
    remote = tmp_path / "remote.git"
    env = {**os.environ, **IDENTITY}
    (work / "README").write_text("main\n")
    (work / ".gitignore").write_text("data/posts.db\ndata/audio/\n")
    _git("add", ".", cwd=work); _git("commit", "-qm", "init", cwd=work, env=env)
    _git("push", "-q", "origin", "HEAD:main", cwd=work)
    script = STATE_SH

    (work / "data" / "audio").mkdir(parents=True)
    (work / "data" / "posts.db").write_bytes(b"db-v1")
    (work / "data" / "audio" / "a.mp3").write_bytes(b"mp3")
    (work / "data" / "audio" / "debug.wav").write_bytes(b"wav")  # never published
    subprocess.run([str(script), "push"], cwd=work, check=True, env=env, capture_output=True)
    (work / "data" / "posts.db").write_bytes(b"db-v2")
    subprocess.run([str(script), "push"], cwd=work, check=True, env=env, capture_output=True)

    # One commit, no parents, only the db and mp3 — and main's index untouched.
    assert _git("rev-list", "--count", "state", cwd=remote).strip() == "1"
    files = _git("ls-tree", "-r", "--name-only", "state", cwd=remote).split()
    assert files == ["data/audio/a.mp3", "data/posts.db"]
    assert _git("status", "--porcelain", cwd=work).strip() == ""

    fresh = tmp_path / "fresh"
    _git("clone", "-q", str(remote), str(fresh), cwd=tmp_path)
    out = subprocess.run([str(script), "pull"], cwd=fresh, check=True, env=env,
                         capture_output=True, text=True).stdout
    assert "restored" in out
    assert (fresh / "data" / "posts.db").read_bytes() == b"db-v2"
    assert (fresh / "data" / "audio" / "a.mp3").read_bytes() == b"mp3"
    assert not (fresh / "data" / "audio" / "debug.wav").exists()


def test_state_pull_starts_empty_only_when_the_branch_is_absent(tmp_path):
    work = _clone_without_state(tmp_path)
    out = subprocess.run([str(STATE_SH), "pull"], cwd=work,
                         check=True, capture_output=True, text=True).stdout
    assert "no 'state' branch" in out
    assert not (work / "data" / "posts.db").exists()


def test_state_pull_fails_when_the_remote_cannot_be_read(tmp_path):
    """An unreachable remote is not a missing branch: carrying on with an empty
    data/ would let the next push replace 30 days of episodes."""
    work = _clone_without_state(tmp_path)
    env = {**os.environ, "STATE_REMOTE": str(tmp_path / "no-such-remote.git")}
    run = subprocess.run([str(STATE_SH), "pull"], cwd=work,
                         env=env, capture_output=True, text=True)
    assert run.returncode != 0
    assert "starting with empty data/" not in run.stdout
    assert "::error::" in run.stdout + run.stderr


def _site(tmp_path, listed, restored):
    """A checkout after `state.sh pull`: feed.xml lists `listed`, data/audio holds `restored`."""
    items = "".join(
        f'<item><enclosure url="https://example.org/feedcast/audio/{name}" '
        f'type="audio/mpeg" length="3"/></item>' for name in listed)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "feed.xml").write_text(
        f'<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>')
    (tmp_path / "data" / "audio").mkdir(parents=True)
    for name in restored:
        (tmp_path / "data" / "audio" / name).write_bytes(b"mp3")
    return subprocess.run([str(PUBLISH_AUDIO_SH)], cwd=tmp_path,
                          capture_output=True, text=True)


def test_publish_audio_copies_every_listed_mp3_into_the_site(tmp_path):
    run = _site(tmp_path, ["a.mp3", "b.mp3"], ["a.mp3", "b.mp3"])
    assert run.returncode == 0, run.stdout + run.stderr
    assert "Copied 2 MP3s" in run.stdout
    assert sorted(p.name for p in (tmp_path / "output" / "audio").iterdir()) == ["a.mp3", "b.mp3"]


def test_publish_audio_fails_when_the_feed_lists_audio_the_state_lacks(tmp_path):
    run = _site(tmp_path, ["a.mp3", "b.mp3"], ["a.mp3"])
    assert run.returncode == 1
    assert "::error::feed.xml lists audio/b.mp3" in run.stdout


def _two_runs(tmp_path):
    """main on a local remote, and two checkouts of it: another run's and this run's.

    The checkouts carry the commit script and state.sh at their CI paths, and
    this run's has a database for `state.sh push` to publish.
    """
    env = {**os.environ, **IDENTITY}
    remote = tmp_path / "remote.git"
    _git("init", "--bare", "-q", "-b", "main", str(remote), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("clone", "-q", str(remote), str(seed), cwd=tmp_path)
    for path, text in {"output/feed.xml": "feed v0\n", "output/index.html": "index v0\n",
                       "data/sources/abc.md": "bundle\n",
                       ".gitignore": "data/posts.db\ndata/audio/\n"}.items():
        (seed / path).parent.mkdir(parents=True, exist_ok=True)
        (seed / path).write_text(text)
    (seed / "scripts").mkdir()
    for script in (COMMIT_SH, STATE_SH):
        shutil.copy2(script, seed / "scripts" / script.name)
    _git("add", ".", cwd=seed)
    _git("commit", "-qm", "init", cwd=seed, env=env)
    _git("push", "-q", "origin", "HEAD:main", cwd=seed)
    other, this = tmp_path / "other", tmp_path / "this"
    for clone in (other, this):
        _git("clone", "-q", str(remote), str(clone), cwd=tmp_path)
    (this / "data" / "audio").mkdir()
    (this / "data" / "audio" / "a.mp3").write_bytes(b"mp3")
    (this / "data" / "posts.db").write_bytes(b"db")
    return remote, other, this


def _other_run_pushes(other, path, text):
    (other / path).write_text(text)
    env = {**os.environ, **IDENTITY}
    _git("commit", "-qam", "the other run", cwd=other, env=env)
    _git("push", "-q", cwd=other)


def _commit_and_push(this, **env):
    env = {**os.environ, "PUSH_RETRY_DELAY_SECONDS": "0", **env}
    return subprocess.run([str(this / "scripts" / COMMIT_SH.name)], cwd=this, env=env,
                          capture_output=True, text=True, timeout=60)


def test_commit_step_names_the_files_a_conflicting_rebase_settled_for_this_run(tmp_path):
    """The merge fallback resolves every conflict in this run's favour; the run
    must say which files that overrode."""
    remote, other, this = _two_runs(tmp_path)
    _other_run_pushes(other, "output/feed.xml", "feed from the other run\n")
    (this / "output" / "feed.xml").write_text("feed from this run\n")

    run = _commit_and_push(this)

    assert run.returncode == 0, run.stdout + run.stderr
    (warning,) = [line for line in run.stdout.splitlines() if line.startswith("::warning")]
    assert "output/feed.xml" in warning and "output/index.html" not in warning
    assert _git("show", "main:output/feed.xml", cwd=remote) == "feed from this run\n"
    assert "the other run" in _git("log", "--format=%s", "main", cwd=remote)


def test_commit_step_rebases_quietly_when_nothing_conflicts(tmp_path):
    remote, other, this = _two_runs(tmp_path)
    _other_run_pushes(other, "output/index.html", "index from the other run\n")
    (this / "output" / "feed.xml").write_text("feed from this run\n")

    run = _commit_and_push(this)

    assert run.returncode == 0, run.stdout + run.stderr
    assert "::warning" not in run.stdout + run.stderr
    assert _git("show", "main:output/feed.xml", cwd=remote) == "feed from this run\n"
    assert _git("show", "main:output/index.html", cwd=remote) == "index from the other run\n"
    assert _git("rev-list", "--merges", "--count", "main", cwd=remote).strip() == "0"


def _remote_refuses(remote, branch, times):
    """Make the remote refuse the first `times` pushes to `branch`, as GitHub
    refused main on 2026-10-31 ("remote: fatal error in commit_refs")."""
    count = remote / f"refused-{branch}"
    count.write_text("0")
    hook = remote / "hooks" / "pre-receive"
    hook.write_text(f"""#!/bin/sh
while read old new ref; do
  if [ "$ref" = refs/heads/{branch} ]; then
    n=$(cat {count})
    if [ "$n" -lt {times} ]; then
      echo $((n + 1)) > {count}
      echo "fatal error in commit_refs" >&2
      exit 1
    fi
  fi
done
""")
    hook.chmod(0o755)
    # Local config beats a global core.hooksPath that would skip this hook.
    _git("config", "core.hooksPath", str(hook.parent), cwd=remote)
    return count


@pytest.mark.parametrize("branch", ["main", "state"])
def test_commit_step_retries_a_push_the_remote_refuses(tmp_path, branch):
    remote, _other, this = _two_runs(tmp_path)
    refused = _remote_refuses(remote, branch, times=2)
    (this / "output" / "feed.xml").write_text("feed from this run\n")

    run = _commit_and_push(this)

    assert run.returncode == 0, run.stdout + run.stderr
    assert refused.read_text().strip() == "2"
    warnings = [line for line in run.stdout.splitlines() if line.startswith("::warning")]
    assert len(warnings) == 2 and all("retrying" in w for w in warnings)
    assert _git("show", "main:output/feed.xml", cwd=remote) == "feed from this run\n"
    assert _git("show", "state:data/posts.db", cwd=remote) == "db"


def test_commit_step_fails_once_the_push_attempts_run_out(tmp_path):
    """A main that never accepts the push fails the step, so the deploy is
    skipped and the next trigger runs; the state branch has the run already."""
    remote, _other, this = _two_runs(tmp_path)
    refused = _remote_refuses(remote, "main", times=99)
    (this / "output" / "feed.xml").write_text("feed from this run\n")

    run = _commit_and_push(this, PUSH_ATTEMPTS="3")

    assert run.returncode != 0
    assert refused.read_text().strip() == "3"
    assert "::error title=Feedcast push::Pushing main failed 3 times" in run.stdout
    assert _git("show", "main:output/feed.xml", cwd=remote) == "feed v0\n"
    assert _git("show", "state:data/posts.db", cwd=remote) == "db"
