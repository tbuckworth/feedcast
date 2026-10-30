"""What the site's pages say and how they are styled, pinned.

Taken from the pages as they stood before the index and episode pages were
given one template (2026-10-30). The comparison is of what a reader gets, the
text, links, head and style rules, not of the bytes, so moving a line of the
template does not fail it and changing a word or a colour does.
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime

import pytest
from bs4 import BeautifulSoup

from src.config import PodcastMetaConfig
from src.feed import Episode, FeedGenerator
from src.monitor import FeedEntry, FeedMonitor, episode_id

BASE = "https://tbuckworth.github.io/feedcast"


def _view(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    refresh = soup.find("meta", attrs={"http-equiv": "refresh"})
    alternate = soup.find("link", rel="alternate")
    audio = soup.find("audio")
    return {
        "lang": soup.html["lang"],
        "viewport": soup.find("meta", attrs={"name": "viewport"})["content"],
        "title": soup.title.string,
        "refresh": refresh["content"] if refresh else None,
        "alternate": alternate["href"] if alternate else None,
        "text": " ".join(soup.body.get_text(" ").split()),
        "links": [(a.get_text(" ", strip=True), a["href"]) for a in soup.body.find_all("a")],
        "audio": audio["src"] if audio else None,
        "css": {sel.strip(): rules
                for sel, rules in re.findall(r"([^{}]+)\{([^}]*)\}", soup.style.string)},
    }


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """Every page the site has, written once: the database setup is slow."""
    tmp_path = tmp_path_factory.mktemp("site")
    gen = FeedGenerator(PodcastMetaConfig(title="Feedcast", description="AI safety, read aloud.",
                                          author="T", email="t@x", language="en-us",
                                          base_url=BASE, category="Technology"),
                        retention_days=30)
    episodes = [
        Episode(id="https://lw/ai188", title="AI #188 & more", description="",
                audio_file="a_ai.mp3", published=datetime(2026, 10, 2), duration_seconds=420,
                link="https://lw/ai188", author="Zvi"),
        # ffprobe could not read it: no duration.
        Episode(id="news-briefing-2026-10-03", title="Daily News Briefing - 2026-10-03",
                description="", audio_file="b.mp3", published=datetime(2026, 10, 3),
                duration_seconds=0, transcript_url=f"{BASE}/transcripts/b.txt"),
    ]
    monitor = FeedMonitor(tmp_path / "posts.db")
    for i, title in [("acx-1", "Does Georgism Work?"), ("acx-2", "Book Review: Genji")]:
        monitor.defer_entry(
            FeedEntry(id=i, title=title, link=f"https://acx/{i}", content="<p>x</p>",
                      published=datetime(2026, 10, 4), author="Scott Alexander",
                      feed_name="Scott Alexander", authors=["Scott Alexander"],
                      feed_date=datetime(2026, 10, 4)),
            "verbatim", "t", None, [])
    monitor.note_deferred_failure("acx-2", "tts: boom")
    gen.write_index(episodes, tmp_path / "index.html")
    gen.write_episode_pages(episodes, monitor.deferred_entries(), tmp_path / "episodes")
    gen.generate(episodes, tmp_path / "feed.xml")

    def page(entry_id: str | None = None) -> dict:
        path = (tmp_path / "index.html" if entry_id is None
                else tmp_path / "episodes" / f"{episode_id(entry_id)}.html")
        return _view(path.read_text(encoding="utf-8"))

    page.feed = (tmp_path / "feed.xml").read_text(encoding="utf-8")
    return page


BODY_CSS = ("margin:0;padding:32px 20px 60px;background:#f5f7f6;color:#1b2024;"
            "font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif")

EPISODE_CSS = {
    "body": BODY_CSS,
    "main": "max-width:680px;margin:0 auto",
    "h1": "font-size:24px;line-height:1.3;margin:0 0 6px",
    ".m": "color:#66717a;font-size:13px;margin:0 0 22px",
    "a": "color:#1f6f78",
    "audio": "width:100%;margin:6px 0 14px",
    ".note": "background:#fff;border-left:3px solid #1f6f78;padding:12px 16px;margin:0 0 18px",
}

FOOTER = [("Feedcast", "../"), ("RSS feed", "../feed.xml")]


def test_index_page(site):
    assert site() == {
        "lang": "en-us",
        "viewport": "width=device-width,initial-scale=1",
        "title": "Feedcast",
        "refresh": None,
        "alternate": "feed.xml",
        # An unreadable duration still shows as "1 min" here, though not on its own page.
        "text": ("Feedcast AI safety, read aloud. Subscribe (RSS) Send a URL "
                 "Daily News Briefing - 2026-10-03 03 Oct 2026 · 1 min "
                 "AI #188 & more 02 Oct 2026 · 7 min · Zvi · source "
                 "2 episodes in the feed. Episodes are kept for 30 days."),
        "links": [("Subscribe (RSS)", "feed.xml"), ("Send a URL", "app/"),
                  ("Daily News Briefing - 2026-10-03", "audio/b.mp3"),
                  ("AI #188 & more", "audio/a_ai.mp3"), ("source", "https://lw/ai188")],
        "audio": None,
        "css": {
            "body": BODY_CSS,
            "main": "max-width:680px;margin:0 auto",
            "h1": "font-size:26px;margin:0 0 6px",
            "p": "color:#66717a;margin:0 0 18px",
            ".sub a": ("display:inline-block;background:#1f6f78;color:#fff;text-decoration:none;"
                       "padding:8px 14px;border-radius:4px;margin:0 8px 8px 0"),
            "ul": "list-style:none;padding:0;margin:26px 0 0",
            "li": "padding:12px 0;border-top:1px solid #d9e0de",
            "li a": "color:#1b2024;text-decoration:none;font-weight:600",
            "li a:hover": "text-decoration:underline",
            ".m": "display:block;font-size:13px;color:#66717a;margin-top:3px",
            ".m a": "color:#1f6f78;font-weight:400",
        },
    }


def test_page_of_a_narrated_episode(site):
    assert site("https://lw/ai188") == {
        "lang": "en-us",
        "viewport": "width=device-width,initial-scale=1",
        "title": "AI #188 & more · Feedcast",
        "refresh": None,
        "alternate": None,
        "text": ("AI #188 & more Zvi · 02 Oct 2026 · 7 min "
                 "Download the MP3 · Read the original Feedcast · RSS feed"),
        "links": [("Download the MP3", "../audio/a_ai.mp3"),
                  ("Read the original", "https://lw/ai188"), *FOOTER],
        "audio": "../audio/a_ai.mp3",
        "css": EPISODE_CSS,
    }
    briefing = site("news-briefing-2026-10-03")
    assert briefing["text"] == ("Daily News Briefing - 2026-10-03 03 Oct 2026 "
                                "Download the MP3 Feedcast · RSS feed")
    assert briefing["links"] == [("Download the MP3", "../audio/b.mp3"), *FOOTER]
    assert briefing["css"] == EPISODE_CSS


def test_pages_of_episodes_still_being_narrated(site):
    waiting, failed = site("acx-1"), site("acx-2")
    assert waiting == {
        "lang": "en-us",
        "viewport": "width=device-width,initial-scale=1",
        "title": "Does Georgism Work? · Feedcast",
        "refresh": "120",
        "alternate": None,
        "text": ("Does Georgism Work? Scott Alexander · 04 Oct 2026 This post is being read out "
                 "in full, which takes longer than the summaries. It will appear in the podcast "
                 "feed shortly, usually within half an hour. This page updates itself and will "
                 "play the episode once it is ready. Read the original Feedcast · RSS feed"),
        "links": [("Read the original", "https://acx/acx-1"), *FOOTER],
        "audio": None,
        "css": EPISODE_CSS,
    }
    assert failed["text"] == (
        "Book Review: Genji Scott Alexander · 04 Oct 2026 Narration failed on the last attempt. "
        "It will be tried again on the next run, and this page will play the episode once it "
        "works. Read the original Feedcast · RSS feed")
    assert failed["refresh"] == "120" and failed["css"] == EPISODE_CSS


def test_feed_declares_its_namespaces(site):
    assert ('xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"' in site.feed
            and 'xmlns:atom="http://www.w3.org/2005/Atom"' in site.feed
            and 'xmlns:podcast="https://podcastindex.org/namespace/1.0"' in site.feed)
    channel = ET.fromstring(site.feed.encode()).find("channel")
    assert channel.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text == "T"
    (transcript,) = channel.iter("{https://podcastindex.org/namespace/1.0}transcript")
    assert transcript.get("url") == f"{BASE}/transcripts/b.txt"
