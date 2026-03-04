"""Extract article content from arbitrary URLs using trafilatura."""

import hashlib
import re
from datetime import datetime
from urllib.parse import urlparse

import trafilatura

from .monitor import FeedEntry


class ExtractionError(Exception):
    """Raised when content extraction fails or produces insufficient content."""


def _extract_title_from_html(html: str, sitename: str | None = None) -> str | None:
    """Extract title from og:title or <title> tag, stripping site name suffixes."""
    # Try og:title first (cleanest)
    og_match = re.search(
        r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if not og_match:
        og_match = re.search(
            r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:title["\']',
            html, re.IGNORECASE,
        )
    title = og_match.group(1).strip() if og_match else None

    # Fall back to <title> tag
    if not title:
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else None

    if not title:
        return None

    # Strip common site name suffixes: " — Site", " - Site", " | Site"
    for sep in [' — ', ' - ', ' | ']:
        if sep in title:
            parts = title.split(sep)
            # Take everything before the last separator (site name is usually last)
            candidate = sep.join(parts[:-1]).strip()
            if candidate:
                title = candidate
                break

    return title


def extract_article(url: str) -> dict:
    """Fetch a URL and extract article content + metadata.

    Returns dict with keys: text, title, author, date, sitename.
    Raises ExtractionError if extraction fails or content is too short.
    """
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ExtractionError(f"Failed to fetch URL: {url}")

    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    if not text or len(text) < 200:
        raise ExtractionError(
            f"Extracted content too short ({len(text) if text else 0} chars). "
            f"The page may be JS-rendered, paywalled, or empty."
        )

    metadata = trafilatura.extract_metadata(downloaded)
    sitename = (metadata.sitename if metadata and metadata.sitename else None) or urlparse(url).netloc
    author = (metadata.author if metadata and metadata.author else None) or urlparse(url).netloc

    # Title: prefer og:title / <title> tag over trafilatura metadata (which is unreliable for some sites)
    html_title = _extract_title_from_html(downloaded, sitename)
    traf_title = metadata.title if metadata and metadata.title else None
    title = html_title or traf_title or urlparse(url).path.split("/")[-1] or "Untitled"

    date = None
    if metadata and metadata.date:
        try:
            date = datetime.fromisoformat(metadata.date)
        except (ValueError, TypeError):
            pass

    return {
        "text": text,
        "title": title,
        "author": author,
        "date": date,
        "sitename": sitename,
    }


def url_to_entry_id(url: str) -> str:
    """Generate a stable entry ID from a URL."""
    return f"injected-{hashlib.sha256(url.encode()).hexdigest()[:16]}"


def url_to_feed_entry(url: str) -> FeedEntry:
    """Extract article from URL and return a FeedEntry.

    Raises ExtractionError on failure.
    """
    article = extract_article(url)
    entry_id = url_to_entry_id(url)
    domain = urlparse(url).netloc

    return FeedEntry(
        id=entry_id,
        title=article["title"],
        link=url,
        content=article["text"],
        published=datetime.now(),  # Always use now — article dates can be old, causing cleanup to delete fresh episodes
        author=article["author"],
        feed_name=domain,
    )
