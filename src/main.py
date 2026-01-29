"""Main entry point for feedcast pipeline."""

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel

from .audio import AudioGenerator
from .feed import FeedGenerator, PodcastConfig
from .monitor import FeedEntry, FeedMonitor
from .processor import ContentProcessor


class FeedConfig(BaseModel):
    """Configuration for a single feed."""

    name: str
    url: str
    mode: Literal["summarize", "verbatim", "auto"] = "auto"
    prompt: str | None = None


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


class Config(BaseModel):
    """Full application configuration."""

    podcast: PodcastMetaConfig
    tts: TTSConfig
    default_prompt: str
    feeds: list[FeedConfig]


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
    audio_dir: Path, http_client: httpx.AsyncClient,
) -> tuple[FeedEntry, Path]:
    """Process one entry: content → audio. Runs concurrently with other entries."""
    print(f"\n  Processing: {entry.title}")
    processed_text = await processor.process(entry, mode, prompt)
    print(f"    Processed text: {len(processed_text)} chars")

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

    # PHASE 1: Parallel feed fetching
    print(f"\nPhase 1: Fetching {len(config.feeds)} feeds in parallel...")

    async def fetch_one(fc: FeedConfig) -> tuple[FeedConfig, list[FeedEntry]]:
        print(f"  Fetching: {fc.name} ({fc.url})")
        entries = await asyncio.to_thread(monitor.fetch_feed, fc.url, fc.name)
        print(f"  {fc.name}: {len(entries)} new entries")
        return (fc, entries)

    feed_results = await asyncio.gather(*[fetch_one(fc) for fc in config.feeds])

    # Deduplicate — gather preserves config order, so author feeds win
    seen_ids: set[str] = set()
    entries_to_process: list[tuple[FeedEntry, str, str]] = []
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

    print(f"\n{len(entries_to_process)} entries to process")

    if not entries_to_process:
        print("No new entries to process.")
    else:
        # PHASE 2: Parallel processing (content + audio)
        print(f"\nPhase 2: Processing {len(entries_to_process)} entries in parallel...")

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as http_client:
            tasks = [
                process_entry(e, m, p, processor, audio_gen, audio_dir, http_client)
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
            monitor.mark_processed(entry, audio_path.name)
            new_episodes += 1

        print(f"  {new_episodes} new episodes created")

    # Generate podcast feed
    print(f"\nGenerating podcast feed...")
    db_entries = monitor.get_processed_entries()
    episodes = feed_gen.load_episodes_from_db(db_entries, audio_dir)
    feed_path = output_dir / "feed.xml"
    feed_gen.generate(episodes, feed_path)
    print(f"  Generated feed with {len(episodes)} episodes: {feed_path}")

    # Cleanup old entries (optional)
    removed = monitor.cleanup_old_entries(days=30)
    if removed:
        print(f"  Cleaned up {removed} old entries")

    print(f"\nPipeline complete.")


def main(config_path: Path | None = None) -> None:
    """Run the feedcast pipeline."""
    asyncio.run(async_main(config_path))


if __name__ == "__main__":
    main()
