"""RSS feed monitoring with SQLite tracking."""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import feedparser


@dataclass
class FeedEntry:
    """Represents a single RSS feed entry."""

    id: str
    title: str
    link: str
    content: str
    published: datetime
    author: str
    feed_name: str


class FeedMonitor:
    """Monitors RSS feeds and tracks processed posts in SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_posts (
                    id TEXT PRIMARY KEY,
                    feed_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    link TEXT NOT NULL,
                    published TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    audio_file TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news_briefings (
                    date TEXT PRIMARY KEY,
                    briefing_text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # Migration: add content column if missing
            try:
                conn.execute("ALTER TABLE processed_posts ADD COLUMN content TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.commit()

    def is_processed(self, entry_id: str) -> bool:
        """Check if a post has already been processed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_posts WHERE id = ?", (entry_id,)
            )
            return cursor.fetchone() is not None

    def is_processed_by_link(self, link: str) -> bool:
        """Check if any entry with this link has been processed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_posts WHERE link = ?", (link,)
            )
            return cursor.fetchone() is not None

    def delete_entry(self, entry_id: str) -> bool:
        """Delete an entry from the database. Returns True if deleted."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM processed_posts WHERE id = ? OR link = ?",
                (entry_id, entry_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def mark_processed(
        self, entry: FeedEntry, audio_file: Optional[str] = None,
        content: Optional[str] = None,
    ) -> None:
        """Mark a post as processed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_posts
                (id, feed_name, title, link, published, processed_at, audio_file, content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.feed_name,
                    entry.title,
                    entry.link,
                    entry.published.isoformat(),
                    datetime.now().isoformat(),
                    audio_file,
                    content or "",
                ),
            )
            conn.commit()

    def get_processed_entries(self) -> list[dict]:
        """Get all processed entries."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM processed_posts
                ORDER BY published DESC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def fetch_feed(self, url: str, feed_name: str, skip_patterns: list[str] | None = None) -> list[FeedEntry]:
        """Fetch and parse an RSS feed, returning new entries."""
        feed = feedparser.parse(url)
        entries = []

        for entry in feed.entries:
            entry_id = entry.get("id") or entry.get("link", "")

            # Skip entries matching title patterns (e.g. ACX open threads)
            title = entry.get("title", "Untitled")
            if skip_patterns and any(re.search(p, title, re.IGNORECASE) for p in skip_patterns):
                continue

            if self.is_processed(entry_id):
                continue

            # Extract content - try different fields
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                content = entry.summary
            elif hasattr(entry, "description"):
                content = entry.description

            # Parse published date
            published = datetime.now()
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])

            author = entry.get("author", feed_name)

            entries.append(
                FeedEntry(
                    id=entry_id,
                    title=entry.get("title", "Untitled"),
                    link=entry.get("link", ""),
                    content=content,
                    published=published,
                    author=author,
                    feed_name=feed_name,
                )
            )

        # Sort by published date (oldest first for processing)
        entries.sort(key=lambda e: e.published)
        return entries

    def store_news_briefing(self, date: str, text: str) -> None:
        """Store a news briefing for dedup across days."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO news_briefings (date, briefing_text, created_at)
                VALUES (?, ?, ?)
                """,
                (date, text, datetime.now().isoformat()),
            )
            conn.commit()

    def get_recent_briefings(self, days: int = 5) -> list[dict]:
        """Get recent news briefings for dedup context."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT date, briefing_text FROM news_briefings WHERE date >= ? ORDER BY date DESC",
                (cutoff,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def cleanup_old_briefings(self, days: int = 7) -> int:
        """Remove news briefings older than specified days. Returns count removed."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM news_briefings WHERE date < ?", (cutoff,)
            )
            conn.commit()
            return cursor.rowcount

    def cleanup_old_entries(
        self, days: int = 30, audio_dir: Optional[Path] = None,
        transcript_dir: Optional[Path] = None,
    ) -> int:
        """Remove entries added more than `days` ago and their audio/transcript files. Returns count removed.

        Retention is keyed on `processed_at` (when the episode was added to the
        podcast), NOT `published` (the original post date). Keying on `published`
        would delete a freshly-added episode whose source post is older than the
        cutoff — its audio gets generated, listed in the feed, then immediately
        deleted in the same run, leaving a 404 enclosure.
        """
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
        cutoff_date = datetime.fromtimestamp(cutoff).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            # Delete associated files before removing DB rows
            if audio_dir or transcript_dir:
                cursor = conn.execute(
                    "SELECT id, audio_file FROM processed_posts WHERE processed_at < ?",
                    (cutoff_date,),
                )
                for entry_id, audio_file in cursor.fetchall():
                    if audio_dir and audio_file:
                        path = audio_dir / audio_file
                        if path.exists():
                            path.unlink()
                    if transcript_dir:
                        txt_path = transcript_dir / f"{entry_id}.txt"
                        if txt_path.exists():
                            txt_path.unlink()

            cursor = conn.execute(
                "DELETE FROM processed_posts WHERE processed_at < ?", (cutoff_date,)
            )
            conn.commit()
            return cursor.rowcount
