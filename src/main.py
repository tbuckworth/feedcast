"""Main entry point for feedcast pipeline."""

import asyncio
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel

from .audio import AudioGenerator
from .extractor import ExtractionError, url_to_feed_entry
from .feed import FeedGenerator, PodcastConfig
from .monitor import FeedEntry, FeedMonitor
from .news import NewsAggregator
from .normalizer import TextNormalizer
from .processor import ContentProcessor


class FeedConfig(BaseModel):
    """Configuration for a single feed."""

    name: str
    url: str
    mode: Literal["summarize", "verbatim", "auto"] = "auto"
    prompt: str | None = None
    skip_patterns: list[str] | None = None


class TTSConfig(BaseModel):
    """TTS configuration."""

    voice: str = "bm_george"
    speed: float = 1.0


class PodcastMetaConfig(BaseModel):
    """Podcast metadata configuration."""

    title: str
    description: str
    author: str
    email: str
    language: str = "en-us"
    base_url: str
    image_url: str | None = None


class NewsSource(BaseModel):
    """A single news RSS source for the daily briefing."""

    name: str
    url: str
    category: str


class NewsBriefingConfig(BaseModel):
    """Configuration for the daily news briefing."""

    enabled: bool = True
    lookback_hours: int = 48
    prompt: str
    sources: list[NewsSource]


class Config(BaseModel):
    """Full application configuration."""

    podcast: PodcastMetaConfig
    tts: TTSConfig
    default_prompt: str
    feeds: list[FeedConfig]
    news_briefing: NewsBriefingConfig | None = None


def load_config(config_path: Path) -> Config:
    """Load configuration from YAML file."""
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return Config(**data)


def generate_episode_id(entry_id: str) -> str:
    """Generate a short, unique episode ID from entry ID."""
    return hashlib.sha256(entry_id.encode()).hexdigest()[:12]


async def process_entry(
    entry: FeedEntry, mode: str, prompt: str,
    processor: ContentProcessor, audio_gen: AudioGenerator,
    normalizer: TextNormalizer,
    audio_dir: Path, http_client: httpx.AsyncClient,
) -> tuple[FeedEntry, Path]:
    """Process one entry: content → audio. Runs concurrently with other entries."""
    print(f"\n  Processing: {entry.title}")
    processed_text = await processor.process(entry, mode, prompt, title=entry.title)
    print(f"    Processed text: {len(processed_text)} chars")
    processed_text = await normalizer.normalize_for_tts(processed_text)
    print(f"    Normalized text: {len(processed_text)} chars")

    episode_id = generate_episode_id(entry.id)
    audio_path = await audio_gen.generate_episode(
        processed_text, audio_dir, episode_id, entry.title, http_client,
    )
    print(f"    Generated audio: {audio_path.name}")
    return (entry, audio_path)


async def async_main(config_path: Path | None = None) -> None:
    """Run the feedcast pipeline with parallel processing."""
    # Determine paths
    project_root = Path(__file__).parent.parent
    config_path = config_path or project_root / "config.yaml"
    db_path = project_root / "data" / "posts.db"
    audio_dir = project_root / "data" / "audio"
    output_dir = project_root / "output"

    # Check for reprocess request
    reprocess_entry = os.environ.get("REPROCESS_ENTRY", "").strip()
    if reprocess_entry:
        print(f"Reprocess requested for: {reprocess_entry}")

    # Check for force-verbatim override
    force_verbatim = os.environ.get("FORCE_VERBATIM", "").strip().lower() in ("true", "1", "yes")
    if force_verbatim:
        if not reprocess_entry:
            print("Warning: FORCE_VERBATIM is set but no REPROCESS_ENTRY specified — flag will have no effect")
        else:
            print(f"Force verbatim enabled for: {reprocess_entry}")

    # Check for URL injection (arbitrary URL processing)
    inject_url = os.environ.get("INJECT_URL", "").strip()
    inject_mode = os.environ.get("INJECT_MODE", "auto").strip().lower()
    if inject_url:
        print(f"URL injection requested: {inject_url} (mode: {inject_mode})")

    # Load configuration
    print(f"Loading configuration from {config_path}")
    config = load_config(config_path)

    # Initialize components
    monitor = FeedMonitor(db_path)

    # Handle reprocess request - delete entry so it gets picked up again
    if reprocess_entry:
        if monitor.delete_entry(reprocess_entry):
            print(f"  Deleted entry from database, will reprocess")
        else:
            print(f"  Entry not found in database (may be new)")

    processor = ContentProcessor(config.default_prompt)
    normalizer = TextNormalizer()
    audio_gen = AudioGenerator(voice=config.tts.voice, speed=config.tts.speed)
    podcast_config = PodcastConfig(
        title=config.podcast.title,
        description=config.podcast.description,
        author=config.podcast.author,
        email=config.podcast.email,
        language=config.podcast.language,
        base_url=config.podcast.base_url,
        image_url=config.podcast.image_url,
    )
    feed_gen = FeedGenerator(podcast_config)

    entries_to_process: list[tuple[FeedEntry, str, str]] = []
    briefing_entry = None

    if inject_url:
        # INJECT MODE: Skip Phase 1, extract content from arbitrary URL
        print(f"\nInjecting URL (skipping RSS feeds)...")
        try:
            entry = await asyncio.to_thread(url_to_feed_entry, inject_url)
        except ExtractionError as e:
            print(f"  Extraction failed: {e}")
            ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
            if ntfy_topic:
                await _send_ntfy_error(ntfy_topic, inject_url, str(e))
            raise
        print(f"  Extracted: {entry.title} ({len(entry.content)} chars)")

        # Dedup: check both entry ID and link
        if monitor.is_processed(entry.id) or monitor.is_processed_by_link(inject_url):
            print(f"  URL already processed, deleting for re-injection...")
            monitor.delete_entry(entry.id)

        entries_to_process = [(entry, inject_mode, config.default_prompt)]
    else:
        # NORMAL MODE: Phase 1 — Parallel feed fetching
        print(f"\nPhase 1: Fetching {len(config.feeds)} feeds in parallel...")

        async def fetch_one(fc: FeedConfig) -> tuple[FeedConfig, list[FeedEntry]]:
            print(f"  Fetching: {fc.name} ({fc.url})")
            entries = await asyncio.to_thread(monitor.fetch_feed, fc.url, fc.name, fc.skip_patterns)
            print(f"  {fc.name}: {len(entries)} new entries")
            return (fc, entries)

        feed_results = await asyncio.gather(*[fetch_one(fc) for fc in config.feeds])

        # Deduplicate — gather preserves config order, so author feeds win
        seen_ids: set[str] = set()
        for feed_config, entries in feed_results:
            if not entries:
                continue
            entry = entries[-1]  # most recent only
            if entry.id in seen_ids:
                print(f"  Skipping duplicate: {entry.title}")
                continue
            seen_ids.add(entry.id)
            mode = feed_config.mode
            if force_verbatim and reprocess_entry and (
                entry.id == reprocess_entry or entry.link == reprocess_entry
            ):
                print(f"    Overriding mode to verbatim (force_verbatim)")
                mode = "verbatim"
            prompt = feed_config.prompt or config.default_prompt
            entries_to_process.append((entry, mode, prompt))

        # Generate daily news briefing if configured
        if config.news_briefing and config.news_briefing.enabled:
            recent_briefings = monitor.get_recent_briefings(5)
            aggregator = NewsAggregator(
                sources=[s.model_dump() for s in config.news_briefing.sources],
                prompt=config.news_briefing.prompt,
                lookback_hours=config.news_briefing.lookback_hours,
                recent_briefings=recent_briefings,
            )
            briefing_entry = await aggregator.generate_briefing()
            if briefing_entry and not monitor.is_processed(briefing_entry.id):
                entries_to_process.insert(0, (briefing_entry, "verbatim", config.default_prompt))
            elif briefing_entry:
                print(f"  News briefing already processed today")

    print(f"\n{len(entries_to_process)} entries to process")

    if not entries_to_process:
        print("No new entries to process.")
    else:
        # PHASE 2: Parallel processing (content + audio)
        print(f"\nPhase 2: Processing {len(entries_to_process)} entries in parallel...")

        # Configure connection limits to avoid ReadError issues with concurrent TTS requests
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0), limits=limits) as http_client:
            tasks = [
                process_entry(e, m, p, processor, audio_gen, normalizer, audio_dir, http_client)
                for e, m, p in entries_to_process
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # PHASE 3: Sequential finalization
        print(f"\nPhase 3: Finalizing...")
        new_episodes = 0
        for result in results:
            if isinstance(result, Exception):
                print(f"  Error processing entry: {type(result).__name__}: {result!r}")
                continue
            entry, audio_path = result
            monitor.mark_processed(entry, audio_path.name, content=entry.content)
            # Store news briefing text for future dedup context
            if entry.id.startswith("news-briefing-") and briefing_entry:
                today = datetime.now().strftime("%Y-%m-%d")
                monitor.store_news_briefing(today, briefing_entry.content)
            new_episodes += 1

        print(f"  {new_episodes} new episodes created")

    # Generate podcast feed
    print(f"\nGenerating podcast feed...")
    transcript_dir = output_dir / "transcripts"
    db_entries = monitor.get_processed_entries()
    episodes = feed_gen.load_episodes_from_db(db_entries, audio_dir, transcript_dir)
    feed_path = output_dir / "feed.xml"
    feed_gen.generate(episodes, feed_path)
    print(f"  Generated feed with {len(episodes)} episodes: {feed_path}")

    # Cleanup old entries (optional)
    removed = monitor.cleanup_old_entries(days=30, audio_dir=audio_dir, transcript_dir=transcript_dir)
    if removed:
        print(f"  Cleaned up {removed} old entries")
    removed_briefings = monitor.cleanup_old_briefings(days=7)
    if removed_briefings:
        print(f"  Cleaned up {removed_briefings} old news briefings")

    # Send ntfy notification for injected URLs
    if inject_url:
        ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
        if ntfy_topic:
            await _send_ntfy(ntfy_topic, inject_url, entries_to_process)

    print(f"\nPipeline complete.")


async def _send_ntfy(
    topic: str, url: str, entries: list[tuple[FeedEntry, str, str]],
) -> None:
    """Send ntfy push notification about injection result."""
    try:
        if entries:
            title = entries[0][0].title
            message = f"New episode: {title}"
            tags = "white_check_mark"
        else:
            message = f"No new content from: {url}"
            tags = "warning"
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://ntfy.sh/{topic}",
                content=message,
                headers={"Title": "Feedcast", "Tags": tags},
            )
    except Exception as e:
        print(f"  ntfy notification failed: {e}")


async def _send_ntfy_error(topic: str, url: str, error: str) -> None:
    """Send ntfy push notification about injection failure."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://ntfy.sh/{topic}",
                content=f"Failed to process: {url}\n{error}",
                headers={"Title": "Feedcast", "Tags": "x"},
            )
    except Exception as e:
        print(f"  ntfy notification failed: {e}")


def main(config_path: Path | None = None) -> None:
    """Run the feedcast pipeline."""
    asyncio.run(async_main(config_path))


if __name__ == "__main__":
    main()
