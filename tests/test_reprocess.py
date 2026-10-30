"""Reprocessing an old entry must not delete it, and the site root must exist."""

from datetime import datetime, timedelta

from src.config import PodcastMetaConfig
from src.feed import Episode, FeedGenerator
from src.monitor import FeedEntry, FeedMonitor


def _entry(i="old-post"):
    return FeedEntry(id=i, title="Old post", link="https://e.com/old", content="<p>x</p>",
                     published=datetime.now() - timedelta(days=10), author="a", feed_name="f")


def test_get_and_restore_round_trip(tmp_path):
    monitor = FeedMonitor(tmp_path / "posts.db")
    monitor.mark_processed(_entry(), "old.mp3", content="<p>x</p>")
    row = monitor.get_entry(link="https://e.com/old")
    assert row and row["id"] == "old-post" and row["audio_file"] == "old.mp3"
    assert monitor.get_entry("nope") is None
    assert monitor.get_entry("https://e.com/old") is None    # a link is not an id

    assert monitor.delete_entry("old-post")
    assert monitor.get_entry("old-post") is None
    monitor.restore_entry(row)
    back = monitor.get_entry("old-post")
    assert back == row                                       # processed_at untouched too
    assert monitor.is_processed("old-post")


def test_a_post_is_found_by_its_id_or_its_link_and_never_by_an_empty_one(tmp_path):
    """One signature for every lookup: processed_posts as deferred_entries."""
    monitor = FeedMonitor(tmp_path / "posts.db")
    monitor.mark_processed(_entry(), "old.mp3")
    briefing = FeedEntry(id="news-briefing-2026-10-30", title="Briefing", link="",
                         content="", published=datetime.now(), author="", feed_name="News")
    monitor.mark_processed(briefing, "b.mp3")
    assert monitor.is_processed("old-post") and monitor.is_processed(link="https://e.com/old")
    assert monitor.is_processed("nope", link="https://e.com/old")
    assert not monitor.is_processed(link="") and not monitor.is_processed()
    # Re-injecting a URL: the earlier copy is deleted by id, or by link under a feed's id.
    assert monitor.delete_entry(entry_id="injected-1", link="https://e.com/old") == [
        ("old-post", "Old post")]
    assert monitor.delete_entry(link="") == []
    assert monitor.is_processed("news-briefing-2026-10-30")


def test_index_page_lists_episodes_and_links_the_feed(tmp_path):
    gen = FeedGenerator(PodcastMetaConfig(title="Feedcast", description="AI safety, read aloud.",
                                          author="T", email="t@x", language="en-us",
                                          base_url="https://tbuckworth.github.io/feedcast",
                                          category="Technology"),
                        retention_days=14)
    eps = [Episode(id="a", title="On Writing #3", description="", audio_file="a.mp3",
                   published=datetime(2026, 8, 26), duration_seconds=1500,
                   link="https://lw/x", author="Zvi"),
           Episode(id="b", title="Daily News Briefing - 2026-09-02", description="",
                   audio_file="b.mp3", published=datetime(2026, 9, 2), duration_seconds=300)]
    out = tmp_path / "site" / "index.html"
    gen.write_index(eps, out)
    html = out.read_text()
    assert html.index("Daily News Briefing") < html.index("On Writing #3")   # newest first
    assert 'href="feed.xml"' in html and 'href="audio/a.mp3"' in html
    assert "25 min" in html and "Zvi" in html and 'href="https://lw/x"' in html
    assert "<script" not in html
    assert "Episodes are kept for 14 days." in html   # the configured retention
