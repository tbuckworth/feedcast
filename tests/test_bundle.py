"""Source bundles: what the writer saw is kept, and the state branch round-trips."""

import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from src.bundle import write_bundle, writer_bundle
from src.monitor import FeedEntry, FeedMonitor, episode_id

REPO = Path(__file__).resolve().parent.parent


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


def test_state_branch_round_trips_db_and_audio_without_history(tmp_path):
    """push replaces the branch with one parentless commit; pull restores the files."""
    remote = tmp_path / "remote.git"
    _git("init", "--bare", "-q", str(remote), cwd=tmp_path)
    work = tmp_path / "work"
    _git("clone", "-q", str(remote), str(work), cwd=tmp_path)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    (work / "README").write_text("main\n")
    (work / ".gitignore").write_text("data/posts.db\ndata/audio/\n")
    _git("add", ".", cwd=work); _git("commit", "-qm", "init", cwd=work, env=env)
    _git("push", "-q", "origin", "HEAD:main", cwd=work)
    script = REPO / "scripts" / "state.sh"

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
