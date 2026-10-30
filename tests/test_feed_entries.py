"""A feed entry's date and body, read the same way by the feed monitor and the
news briefing (src/monitor.py `entry_published`, `entry_body`)."""

from datetime import datetime
from types import SimpleNamespace

import feedparser

from src.monitor import entry_body, entry_published

RSS = """<?xml version='1.0'?><rss version='2.0'><channel><title>t</title>
<item><title>Dated</title><pubDate>Fri, 30 Oct 2026 04:05:06 GMT</pubDate>
<description>The body.</description></item>
<item><title>Bare</title></item>
</channel></rss>"""

ATOM = """<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'><title>t</title>
<entry><title>Updated only</title><updated>2026-10-29T23:00:00+01:00</updated>
<summary>Atom summary.</summary></entry>
<entry><title>Both</title><published>2026-10-01T00:00:00Z</published>
<updated>2026-10-20T00:00:00Z</updated></entry>
</feed>"""


def test_published_is_the_publication_time_else_the_update_time_in_naive_utc():
    dated, bare = feedparser.parse(RSS).entries
    updated_only, both = feedparser.parse(ATOM).entries
    assert entry_published(dated) == datetime(2026, 10, 30, 4, 5, 6)
    assert entry_published(updated_only) == datetime(2026, 10, 29, 22, 0)
    assert entry_published(both) == datetime(2026, 10, 1)
    assert entry_published(bare) is None


def test_body_is_the_summary_else_the_description_else_nothing():
    dated, bare = feedparser.parse(RSS).entries
    updated_only, _ = feedparser.parse(ATOM).entries
    assert entry_body(dated) == "The body."
    assert entry_body(updated_only) == "Atom summary."
    assert entry_body(bare) == ""
    # feedparser files an RSS description under `summary`; an entry object
    # that carries only a description is read from it.
    assert entry_body(SimpleNamespace(description="Described.")) == "Described."
