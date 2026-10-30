"""Source bundles: what the writer saw is kept, and the state branch round-trips."""

import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from src.bundle import write_bundle, writer_bundle
from src.monitor import FeedEntry, FeedMonitor, episode_id

REPO = Path(__file__).resolve().parent.parent
STATE_SH = REPO / "scripts" / "state.sh"
PUBLISH_AUDIO_SH = REPO / "scripts" / "publish-audio.sh"


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
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
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
