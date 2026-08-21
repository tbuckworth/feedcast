"""Tests for recovering full post text from excerpt-only feeds."""

import re
from datetime import datetime

import pytest

from src import fulltext
from src.fulltext import enrich_entry, markdown_to_html
from src.monitor import FeedEntry


def make_entry(content: str) -> FeedEntry:
    return FeedEntry(
        id="x",
        feed_name="Zvi Mowshowitz",
        title="AI #182",
        link="https://www.lesswrong.com/posts/JSZkzsi8cD4pW6ffA/ai-182",
        published=datetime(2026, 8, 20),
        content=content,
        author="Zvi",
    )


@pytest.fixture
def fake_markdown(monkeypatch):
    """Stand in for the GraphQL fetch so no test touches the network."""

    def install(md):
        monkeypatch.setattr(fulltext, "fetch_lesswrong_markdown", lambda link: md)

    return install


def test_replaces_a_podcast_blurb_with_the_post(fake_markdown):
    # The shape that caused this module to exist: the feed body is a teaser
    # plus a chapter list, and the post is two orders of magnitude longer.
    fake_markdown("The full post. " * 500)
    entry = make_entry("<p>Chapters: (01:16:32) The Incentives</p>")

    gain = enrich_entry(entry)

    assert gain.replaced and gain.reason == "replaced"
    assert gain.after > gain.before * 10
    assert "The full post." in entry.content


def test_leaves_a_complete_body_alone(fake_markdown):
    # An author feed that already carries the post: markdown and HTML differ by
    # a few percent of syntax, which must not read as a truncated feed.
    body = "Complete article text. " * 200
    fake_markdown(body)
    entry = make_entry(f"<p>{body}</p>")

    gain = enrich_entry(entry)

    assert not gain.replaced and gain.reason == "feed-complete"
    assert entry.content == f"<p>{body}</p>"


def test_non_lesswrong_entry_is_untouched(fake_markdown):
    fake_markdown(None)
    entry = make_entry("<p>short</p>")
    entry.link = "https://www.astralcodexten.com/p/something"

    gain = enrich_entry(entry)

    # Not a failure: Scott Alexander's feed carries the post and there is no
    # markdown to fetch. Reporting this as unreachable would cry wolf daily.
    assert gain.reason == "not-lesswrong"
    assert entry.content == "<p>short</p>"


def test_unreachable_markdown_is_distinguishable_from_a_complete_feed(fake_markdown):
    # The case that ships a blurb as an episode. It must not look like the
    # feed-complete case, which is the normal, fine outcome.
    fake_markdown(None)
    entry = make_entry("<p>Chapters: (01:16:32) The Incentives</p>")

    gain = enrich_entry(entry)

    assert gain.reason == "unreachable" and gain.is_failure
    assert entry.content == "<p>Chapters: (01:16:32) The Incentives</p>"


def test_markdown_tables_survive_as_html():
    # Tables must reach the pipeline as real <table> markup, or process_tables
    # cannot turn them into prose and the numbers are read as a wall of digits.
    html = markdown_to_html("| a | b |\n| --- | --- |\n| 1 | 2 |")

    assert "<table>" in html
    assert "<td>1</td>" in html


def test_markdown_links_keep_their_text_not_their_url():
    html = markdown_to_html("See [the risk report](https://example.com/x?r=67wny).")

    # clean_html later strips the tag, leaving the words a listener needs; the
    # raw markdown would have left the URL in the middle of the sentence.
    assert ">the risk report</a>" in html
    assert "67wny" not in re.sub(r"<[^>]+>", "", html)
