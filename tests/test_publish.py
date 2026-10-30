"""What a run publishes: the site under output/, written from the database.

Each pass of a split run publishes the whole site: feed.xml, the index, a page
per episode (a waiting page for a post still being narrated) and the
briefing's transcript. A resend re-sends the email and publishes nothing.
These run async_main on the scratch repository of the `pipeline` fixture.
"""

import shutil
import xml.etree.ElementTree as ET
from datetime import datetime

import pytest

from src.config import load_config
from src.feed import episode_page_url
from src.markets import MarketContext, MarketScout
from src.monitor import episode_id
from tests.conftest import Model, item, needs_ffmpeg

# The real narrator joins its chunks with ffmpeg, and the feed reads each MP3 with ffprobe.
pytestmark = needs_ffmpeg

BASE = load_config().podcast.base_url
POST = "https://acx.example/georgism"
TODAY = f"{datetime.now():%Y-%m-%d}"
BRIEFING = f"news-briefing-{TODAY}"
SCRIPT = "Friday's briefing. Parliament passed a land tax."
TRANSCRIPT = f"transcripts/{BRIEFING}.txt"


@pytest.fixture
def day(pipeline, monkeypatch, routes, tmp_path):
    """A day with a news briefing and one post that is read out in full."""
    news = pipeline.root / "news.xml"
    news.write_text("<?xml version='1.0'?><rss version='2.0'><channel><title>BBC</title>"
                    + item("Land tax passes", "https://bbc.example/land") + "</channel></rss>")
    pipeline.briefing_sources = [{"name": "BBC", "url": str(news), "category": "politics"}]
    routes["anthropic"] = Model(lambda m: SCRIPT)      # the writer

    async def no_markets(self, selected):   # Polymarket and Kalshi, over the network
        return MarketContext()
    monkeypatch.setattr(MarketScout, "_build", no_markets)
    pipeline.feed("Scott", item("Does Georgism Work?", POST))
    return pipeline


def _site(pipeline) -> dict[str, str]:
    """Every file under output/, by its path there."""
    out = pipeline.root / "output"
    return {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(out.rglob("*")) if p.is_file()}


def _mp3(pipeline, entry_id: str) -> str:
    """The name of the MP3 the narrator wrote for an entry under data/audio."""
    (path,) = (pipeline.root / "data" / "audio").glob(f"{episode_id(entry_id)}_*.mp3")
    return path.name


def _items(feed: str) -> dict[str, tuple[str, str | None]]:
    """Each feed item's guid -> its enclosure URL and its transcript URL, if any."""
    items = {}
    for it in ET.fromstring(feed.encode()).find("channel").findall("item"):
        transcript = it.find("{https://podcastindex.org/namespace/1.0}transcript")
        items[it.findtext("guid")] = (it.find("enclosure").get("url"),
                                      None if transcript is None else transcript.get("url"))
    return items


def _self_link(feed: str) -> str:
    channel = ET.fromstring(feed.encode()).find("channel")
    return channel.find("{http://www.w3.org/2005/Atom}link[@rel='self']").get("href")


def test_the_first_pass_publishes_the_briefing_and_a_page_for_the_waiting_post(
        day, monkeypatch, tmp_path):
    outputs = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    email = day.run(FEEDCAST_PASS="first")
    site = _site(day)
    assert sorted(site) == sorted([
        f"episodes/{episode_id(BRIEFING)}.html", f"episodes/{episode_id(POST)}.html",
        "feed.xml", "index.html", TRANSCRIPT])
    assert _self_link(site["feed.xml"]) == f"{BASE}/feed.xml"
    assert _items(site["feed.xml"]) == {
        BRIEFING: (f"{BASE}/audio/{_mp3(day, BRIEFING)}", f"{BASE}/{TRANSCRIPT}")}
    assert site[TRANSCRIPT] == SCRIPT
    assert "<audio" in site[f"episodes/{episode_id(BRIEFING)}.html"]
    assert "being read out in full" in site[f"episodes/{episode_id(POST)}.html"]
    assert f"Daily News Briefing - {TODAY}" in site["index.html"]
    assert outputs.read_text() == "deferred=1\n"     # the narration job has work

    # The email links what was published.
    assert email.splitlines()[-1] == f"{BASE}/feed.xml"
    assert f"\n  Audio:  {BASE}/audio/{_mp3(day, BRIEFING)}\n" in email
    assert f"\n  Audio:  {episode_page_url(BASE, POST)} (still narrating;" in email


def test_the_narration_pass_publishes_the_post_into_the_same_site(day):
    day.run(FEEDCAST_PASS="first")
    first = _site(day)
    day.run(FEEDCAST_PASS="narrate")
    site = _site(day)
    assert sorted(site) == sorted(first)
    assert _items(site["feed.xml"]) == {
        BRIEFING: (f"{BASE}/audio/{_mp3(day, BRIEFING)}", f"{BASE}/{TRANSCRIPT}"),
        POST: (f"{BASE}/audio/{_mp3(day, POST)}", None)}
    assert site[TRANSCRIPT] == first[TRANSCRIPT]
    assert site[f"episodes/{episode_id(BRIEFING)}.html"] == \
        first[f"episodes/{episode_id(BRIEFING)}.html"]
    assert "<audio" in site[f"episodes/{episode_id(POST)}.html"]
    assert "Does Georgism Work?" in site["index.html"]


def test_a_resend_publishes_nothing(day):
    """It used to rewrite the transcripts: they were written while the episodes were read."""
    day.run(FEEDCAST_PASS="first")
    shutil.rmtree(day.root / "output")
    email = day.run(RESEND_REPORT="true")
    assert [line for line in email.splitlines() if line.startswith("* ")] == [
        f"* Daily News Briefing - {TODAY}"]
    assert not (day.root / "output").exists()
