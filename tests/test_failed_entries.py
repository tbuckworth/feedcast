"""A failed entry is owed MAX_ATTEMPTS tries, and its best script survives them."""

import sqlite3
from datetime import datetime, timedelta

from src.monitor import FeedEntry, FeedMonitor


def _entry(i="p1"):
    return FeedEntry(id=i, title="An Alien Mind", link="https://lw/p1", content="<p>x</p>",
                     published=datetime.now(), author="Zvi", feed_name="Zvi Mowshowitz")


def test_record_then_clear(tmp_path):
    m = FeedMonitor(tmp_path / "posts.db")
    assert m.pending_failures() == []
    assert m.record_failure(_entry(), "tts: ReadError") == 1
    (row,) = m.pending_failures()
    assert row["id"] == "p1" and row["attempts"] == 1 and row["last_error"] == "tts: ReadError"
    assert row["feed_name"] == "Zvi Mowshowitz" and row["normalized_text"] == ""
    m.clear_failure("p1")
    assert m.pending_failures() == []


def test_gives_up_after_max_attempts_and_keeps_the_script(tmp_path):
    m = FeedMonitor(tmp_path / "posts.db")
    m.record_failure(_entry(), "tts: boom")
    assert m.record_failure(_entry(), "tts: boom", normalized_text="the script") == 2
    # A later attempt failing *earlier* in the pipeline must not erase it.
    assert m.record_failure(_entry(), "process: EmptyCompletion") == 3
    assert m.pending_failures() == []          # MAX_ATTEMPTS reached
    with sqlite3.connect(m.db_path) as conn:
        text, first, last = conn.execute(
            "SELECT normalized_text, first_failed_at, last_failed_at FROM failed_entries").fetchone()
    assert text == "the script" and first <= last


def test_pending_is_oldest_first_and_prune_forgets_old_rows(tmp_path):
    m = FeedMonitor(tmp_path / "posts.db")
    m.record_failure(_entry("new"), "x")
    m.record_failure(_entry("old"), "x")
    with sqlite3.connect(m.db_path) as conn:
        conn.execute("UPDATE failed_entries SET first_failed_at = ? WHERE id = 'old'",
                     ((datetime.now() - timedelta(days=40)).isoformat(),))
    assert [r["id"] for r in m.pending_failures()] == ["old", "new"]
    assert m.prune_failures(days=30) == 1
    assert [r["id"] for r in m.pending_failures()] == ["new"]
