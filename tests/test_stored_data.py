"""The database: columns added to old files, and JSON columns read back.

Rows written before a column existed hold '' there, which reads as nothing
stored. Anything else that is not the JSON the pipeline wrote is corrupt, and
raises naming the row: read as "nothing stored", it showed an episode without
its digest or fidelity check and nobody knew why.
"""

import os
import sqlite3
from datetime import datetime

import pytest

from src.monitor import FeedEntry, FeedMonitor, entry_from_row
from src.run_report import bullets_of, json_dict, stored_verdict

# processed_posts as it was before any migration, with every other table
# already in place, so opening the file needs only the ALTER TABLEs.
OLD_SCHEMA = """
CREATE TABLE processed_posts (id TEXT PRIMARY KEY, feed_name TEXT NOT NULL,
    title TEXT NOT NULL, link TEXT NOT NULL, published TEXT NOT NULL,
    processed_at TEXT NOT NULL, audio_file TEXT);
CREATE TABLE news_briefings (date TEXT PRIMARY KEY, briefing_text TEXT NOT NULL,
    created_at TEXT NOT NULL);
CREATE TABLE failed_entries (id TEXT PRIMARY KEY, link TEXT NOT NULL, feed_name TEXT NOT NULL,
    title TEXT NOT NULL, attempts INTEGER NOT NULL, last_error TEXT NOT NULL,
    first_failed_at TEXT NOT NULL, last_failed_at TEXT NOT NULL,
    normalized_text TEXT NOT NULL DEFAULT '');
CREATE TABLE deferred_entries (id TEXT PRIMARY KEY, link TEXT NOT NULL DEFAULT '',
    entry TEXT NOT NULL, mode TEXT NOT NULL, processed_text TEXT NOT NULL DEFAULT '',
    normalized_text TEXT NOT NULL DEFAULT '', bullets TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',
    deferred_at TEXT NOT NULL);
CREATE TABLE market_reports (market_key TEXT PRIMARY KEY, prob REAL NOT NULL,
    reported_at TEXT NOT NULL);
"""

ADDED = ["content", "author", "bullets", "maths", "feed_date", "fidelity", "writer"]


def _old_db(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(OLD_SCHEMA)


def _columns(path) -> list[str]:
    with sqlite3.connect(path) as conn:
        return [r[1] for r in conn.execute("PRAGMA table_info(processed_posts)")]


class TestMigrations:

    def test_an_old_file_gains_every_column_and_opens_again(self, tmp_path):
        db = tmp_path / "posts.db"
        _old_db(db)
        FeedMonitor(db)
        assert _columns(db)[-len(ADDED):] == ADDED
        FeedMonitor(db)            # every column there already: "duplicate column name"
        assert _columns(db)[-len(ADDED):] == ADDED

    @pytest.mark.skipif(os.geteuid() == 0, reason="root writes to a read-only file")
    def test_a_migration_that_fails_raises_instead_of_reading_as_done(self, tmp_path):
        """Every OperationalError used to read as "column already exists"."""
        db = tmp_path / "posts.db"
        _old_db(db)
        db.chmod(0o444)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            FeedMonitor(db)


class TestJsonColumns:

    ROW = {"id": "https://lw/p1"}

    def test_old_rows_read_as_nothing_stored(self):
        row = {**self.ROW, "bullets": "", "fidelity": "", "writer": "", "maths": ""}
        assert bullets_of(row) == [] and json_dict(row, "fidelity") is None
        assert json_dict(row, "writer") is None
        assert stored_verdict(row).source == "unrecorded"

    @pytest.mark.parametrize("read, column", [
        (bullets_of, "bullets"),
        (lambda row: json_dict(row, "fidelity"), "fidelity"),
        (lambda row: json_dict(row, "writer"), "writer"),
        (stored_verdict, "maths"),
    ])
    @pytest.mark.parametrize("stored", ['{"text": "cut off', '"a string"'])
    def test_corrupt_json_raises_naming_the_row(self, read, column, stored):
        with pytest.raises(ValueError, match=f"'https://lw/p1'.*{column}"):
            read({**self.ROW, column: stored})

    def test_a_waiting_post_with_corrupt_bullets_raises_naming_it(self, tmp_path):
        monitor = FeedMonitor(tmp_path / "posts.db")
        entry = FeedEntry(id="acx-1", title="Does Georgism Work?", link="https://acx/1",
                          content="<p>Land.</p>", published=datetime(2026, 9, 24),
                          author="Scott Alexander", feed_name="Scott Alexander")
        monitor.defer_entry(entry, "verbatim", "Clean text.", None, ["b1"])
        assert monitor.deferred_entries()[0]["bullets"] == ["b1"]
        with sqlite3.connect(monitor.db_path) as conn:
            conn.execute("UPDATE deferred_entries SET bullets = '[\"b1\"'")
        with pytest.raises(ValueError, match="'acx-1'.*bullets"):
            monitor.deferred_entries()


def test_a_stored_post_reads_back_as_the_post(tmp_path):
    monitor = FeedMonitor(tmp_path / "posts.db")
    entry = FeedEntry(id="acx-1", title="Does Georgism Work?", link="https://acx/1",
                      content="<p>Land.</p>", published=datetime(2026, 9, 24),
                      author="Scott Alexander", feed_name="ACX")
    monitor.mark_processed(entry, "a.mp3", content=entry.content)
    assert entry_from_row(monitor.get_entry("acx-1")) == entry
    # Rows written before the author column name the feed instead.
    assert entry_from_row({**monitor.get_entry("acx-1"), "author": ""}).author == "ACX"
