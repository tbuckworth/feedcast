"""Recover a post's full text when its feed only ships an excerpt.

Zvi Mowshowitz is read from ``podcast.lesswrong.com/users/zvi.rss`` — a
*podcast* feed, whose item body is the episode blurb plus a list of chapter
timestamps, not the post. Measured 2026-08-21: "AI #182: Pause For Reflection"
arrived as 2,820 characters of text against 99,411 in the actual post. Three
percent, and the tail of that three percent is a table of contents, so every
Zvi episode so far summarised a summary of a contents page. That is why the
narration sounded like it had not read the article: it had not.

The repair uses the same GraphQL markdown the maths filter already fetches
(``mathiness.fetch_lesswrong_markdown`` — see that module for why markdown and
not the rendered page), rendered to HTML so the rest of the pipeline runs
unchanged: tables still become prose, ``clean_html`` still strips the tags.

This is deliberately not Zvi-specific. Any LessWrong or Alignment Forum feed
can serve a partial body, and comparing against the real post is a cheap way to
notice. Author ``community-rss`` feeds measure at 93-95% of the post and are
left alone.
"""

import re
from typing import Optional

import markdown as _markdown

from .mathiness import fetch_lesswrong_markdown
from .monitor import FeedEntry

# Replace the feed's body only when the real post is materially longer. Markdown
# and RSS never agree exactly — footnotes, image alt text and link syntax all
# shift the count a few percent — so a small excess means "same post, different
# serialisation", not "the feed truncated it". Measured across the LessWrong
# author feeds: complete bodies land at 1.05-1.10x, Zvi's podcast feed at 30x.
MIN_GAIN = 1.2

_MD_EXTENSIONS = ["tables", "fenced_code"]


def markdown_to_html(md: str) -> str:
    """Render post markdown to HTML for the existing HTML pipeline."""
    return _markdown.markdown(md, extensions=_MD_EXTENSIONS)


def _visible_length(html: str) -> int:
    """Roughly how much text a reader would hear, ignoring markup."""
    text = re.sub(r"<[^>]+>", " ", html)
    return len(" ".join(text.split()))


def enrich_entry(entry: FeedEntry) -> Optional[tuple[int, int]]:
    """Swap in the full post text when the feed shipped an excerpt.

    Mutates ``entry.content`` in place and returns ``(before, after)`` visible
    character counts, or None when nothing was changed. Any failure is a None:
    a partial episode is better than a failed run, and the caller has no
    better option than the body it already had.
    """
    md = fetch_lesswrong_markdown(entry.link)
    if not md:
        return None

    html = markdown_to_html(md)
    before, after = _visible_length(entry.content), _visible_length(html)
    if after < before * MIN_GAIN:
        return None

    entry.content = html
    return before, after
