"""RSS feed monitoring with SQLite tracking."""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import feedparser


MAX_AUTHORS = 5

# Only narrate what was published recently. Dedup by id alone is not enough:
# a feed that changes its guids, moves host, or is added to config.yaml
# presents its whole archive as unseen, and the pipeline happily worked
# through it one post per run (250 Zvi items back to Sep 2025, 2026-08-29).
# A date cutoff makes that structurally impossible rather than merely unlikely.
DEFAULT_MAX_AGE_HOURS = 48.0


def format_authors(authors: list[str]) -> str:
    """Render an author list for speech and display: 'A', 'A and B', 'A, B and C'."""
    shown = authors[:MAX_AUTHORS]
    if not shown:
        return ""
    if len(authors) > MAX_AUTHORS:
        return ", ".join(shown) + " and others"
    if len(shown) == 1:
        return shown[0]
    return ", ".join(shown[:-1]) + " and " + shown[-1]


def extract_authors(entry, feed_name: str) -> list[str]:
    """Pull every author name off a feedparser entry, in order.

    feedparser exposes `authors` as a list of dicts for feeds that publish
    several (LessWrong currently emits exactly one per post, but co-authored
    posts and other feeds do not). Fall back to the single `author` string,
    then to the feed name so an episode is never attributed to nobody.

    Deliberately does NOT truncate: capping is a rendering decision that
    belongs to format_authors, which needs the true count to know whether to
    say "and others". Truncating here would silently drop co-authors instead.
    """
    names: list[str] = []
    for a in entry.get("authors") or []:
        name = (a.get("name") or "").strip() if isinstance(a, dict) else str(a).strip()
        if name and name not in names:
            names.append(name)
    if not names:
        single = (entry.get("author") or "").strip()
        if single:
            names = [single]
    return names or [feed_name]


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
    authors: list[str] = field(default_factory=list)
    # Read-not-heard digest for the email. Filled in during Phase 2. Each item
    # is either a plain string or {"text": ..., "url": ...} when the bullet can
    # be traced to one source article (the news briefing).
    bullets: list = field(default_factory=list)
    # The articles a synthesised entry was built from: {"title", "url",
    # "source"}. Empty for ordinary posts, which are their own source.
    sources: list[dict] = field(default_factory=list)
    # The date the item carried in the feed, which decides whether it is new
    # to us. Equal to `published` everywhere except LessWrong Curated, where
    # the feed dates an item by its curation and `published` is corrected to
    # the real posting date.
    feed_date: Optional[datetime] = None


def warn_if_dead(feed, name: str, url: str) -> bool:
    """Say so when a feed returns nothing, and report True if it did.

    feedparser never raises: a 404, a DNS failure or an HTML error page all
    come back as a parsed feed with zero entries, so `except` blocks around it
    are dead code. Without this check a source that dies is indistinguishable
    from an author who simply did not post — which is how three of the news
    sources went months contributing nothing.
    """
    if feed.entries:
        return False
    status = getattr(feed, "status", None)
    reason = getattr(feed, "bozo_exception", None) or "no items"
    print(f"  WARNING: {name} returned no entries "
          f"(HTTP {status}) — {reason} <{url}>")
    return True


class FeedMonitor:
    """Monitors RSS feeds and tracks processed posts in SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        # Feeds that returned nothing this run, for the email. A source can
        # die quietly for months otherwise — the run just looks uneventful.
        self.dead_feeds: list[str] = []
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
            # Migration: add author column if missing. Rows written before this
            # column existed keep '', and readers fall back to the feed name.
            try:
                conn.execute("ALTER TABLE processed_posts ADD COLUMN author TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists
            # Migration: bullet digest for the email, stored as a JSON array.
            # Older rows keep '' and simply render without bullets.
            try:
                conn.execute("ALTER TABLE processed_posts ADD COLUMN bullets TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists
            # Migration: the maths verdict that caused a post to be linked
            # rather than narrated, as JSON. Recorded at the moment of the
            # decision so a later report states what was decided, rather than
            # re-deriving a score that can disagree with it.
            try:
                conn.execute("ALTER TABLE processed_posts ADD COLUMN maths TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists
            # Migration: the date the feed gave the item, kept apart from the
            # publication date so a curated post can be new to us in August
            # and still say it was written in July.
            try:
                conn.execute("ALTER TABLE processed_posts ADD COLUMN feed_date TEXT DEFAULT ''")
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
        content: Optional[str] = None, maths: Optional[dict] = None,
    ) -> None:
        """Mark a post as processed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_posts
                (id, feed_name, title, link, published, processed_at, audio_file, content, author, bullets, maths, feed_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    entry.author or "",
                    json.dumps(entry.bullets) if entry.bullets else "",
                    json.dumps(maths) if maths else "",
                    entry.feed_date.isoformat() if entry.feed_date else "",
                ),
            )
            conn.commit()

    def set_bullets(self, entry_id: str, bullets: list[str]) -> None:
        """Attach a digest to an existing row without touching anything else.

        mark_processed would work but rewrites processed_at, which would make a
        backfilled old episode look like it was published today.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE processed_posts SET bullets = ? WHERE id = ?",
                         (json.dumps(bullets) if bullets else "", entry_id))
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

    def fetch_feed(self, url: str, feed_name: str, skip_patterns: list[str] | None = None,
                   max_age_hours: float | None = DEFAULT_MAX_AGE_HOURS) -> list[FeedEntry]:
        """Fetch and parse an RSS feed, returning new entries newer than the cutoff.

        `max_age_hours=None` disables the cutoff, which only reprocessing an
        old post on purpose should ever want.
        """
        feed = feedparser.parse(url)
        if warn_if_dead(feed, feed_name, url) and feed_name not in self.dead_feeds:
            self.dead_feeds.append(feed_name)
        entries = []
        # feedparser hands back naive UTC, so the cutoff must be naive UTC too.
        # datetime.now() here silently skewed the window by the machine's UTC
        # offset — an hour narrower on the BST desktop than in CI.
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff = (now_utc - timedelta(hours=max_age_hours)
                  if max_age_hours is not None else None)
        stale = undated = already = 0

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
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])

            if cutoff is not None:
                # An undated entry cannot be shown to be recent, and the whole
                # point of the cutoff is that nothing old slips through. Count
                # it so a feed that stops publishing dates is visible rather
                # than silently empty.
                if published is None:
                    undated += 1
                    continue
                if published < cutoff:
                    stale += 1
                    continue
            elif published is None:
                published = now_utc

            # The same post reaches us under different guids: an author feed
            # and LessWrong Curated carry identical links weeks apart (Zvi's
            # "On Writing #3" — guid f1c130ea… there, rA6pqn6kz8NvHyznT here).
            # Without this the curated copy is narrated a second time.
            link = entry.get("link", "")
            if link and self.is_processed_by_link(link):
                already += 1
                continue

            authors = extract_authors(entry, feed_name)
            author = format_authors(authors)

            entries.append(
                FeedEntry(
                    id=entry_id,
                    title=entry.get("title", "Untitled"),
                    link=link,
                    content=content,
                    published=published,
                    author=author,
                    feed_name=feed_name,
                    authors=authors,
                    feed_date=published,
                )
            )

        if stale or undated or already:
            detail = ", ".join(filter(None, [
                f"{stale} older than {max_age_hours:g}h" if stale else "",
                f"{undated} with no date" if undated else "",
                f"{already} already narrated under another feed" if already else "",
            ]))
            print(f"  {feed_name}: skipped {detail}")

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
