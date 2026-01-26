"""Main entry point for feedcast pipeline."""

import hashlib
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from .audio import AudioGenerator
from .feed import FeedGenerator, PodcastConfig
from .monitor import FeedMonitor
from .processor import ContentProcessor


class FeedConfig(BaseModel):
    """Configuration for a single feed."""

    name: str
    url: str
    mode: str = "summarize"
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


def main(config_path: Path | None = None) -> None:
    """Run the feedcast pipeline."""
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

    # Process each configured feed
    new_episodes = 0
    for feed_config in config.feeds:
        print(f"\nProcessing feed: {feed_config.name}")
        print(f"  URL: {feed_config.url}")
        print(f"  Mode: {feed_config.mode}")

        try:

            entries = monitor.fetch_feed(feed_config.url, feed_config.name)
            print(f"  Found {len(entries)} new entries")

            # Only process the most recent entry per feed per run
            if entries:
                entries = [entries[-1]]
                print(f"  Processing most recent entry only")

            for entry in entries:
                print(f"\n  Processing: {entry.title}")

                try:
                    # Process content
                    prompt = feed_config.prompt or config.default_prompt
                    processed_text = processor.process(
                        entry, feed_config.mode, prompt
                    )
                    print(f"    Processed text: {len(processed_text)} chars")

                    # Generate audio
                    episode_id = generate_episode_id(entry.id)
                    audio_path = audio_gen.generate_episode(
                        processed_text, audio_dir, episode_id, entry.title
                    )
                    print(f"    Generated audio: {audio_path.name}")

                    # Mark as processed
                    monitor.mark_processed(entry, audio_path.name)
                    new_episodes += 1

                except Exception as e:
                    print(f"    Error processing entry: {e}")
                    continue

        except Exception as e:
            print(f"  Error fetching feed: {e}")
            continue

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

    print(f"\nPipeline complete. {new_episodes} new episodes created.")


if __name__ == "__main__":
    main()
