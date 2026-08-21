"""Main entry point for feedcast pipeline."""

import asyncio
import hashlib
import os
import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel

from .audio import AudioGenerator
from .email_report import LinkedPost, ReportEpisode, RunReport, send_report
from .extractor import ExtractionError, url_to_feed_entry
from .feed import Episode, FeedGenerator, PodcastConfig
from .fulltext import enrich_entry
from .mathiness import MathsVerdict, assess
from .monitor import FeedEntry, FeedMonitor
from .news import NewsAggregator
from .normalizer import TextNormalizer
from .processor import ContentProcessor

# feedparser.parse(url) fetches through urllib, which blocks forever on a
# stalled server — a single unresponsive feed would hang the whole run until
# CI killed it. feedparser 6.x exposes no timeout argument, so bound it at the
# socket layer. Only affects blocking sockets; asyncio/httpx are unaffected.
socket.setdefaulttimeout(30)


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


class MathsFilterConfig(BaseModel):
    """Skip audio for posts that are too mathematical to follow by ear."""

    enabled: bool = True
    threshold_per_1k: float = 8.0


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
    maths_filter: MathsFilterConfig = MathsFilterConfig()


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

        # return_exceptions: one unreachable or slow feed must not abort the run.
        # feedparser raises (rather than setting bozo) on a socket timeout.
        raw_results = await asyncio.gather(
            *[fetch_one(fc) for fc in config.feeds],
            return_exceptions=True,
        )
        feed_results = []
        for fc, result in zip(config.feeds, raw_results):
            if isinstance(result, BaseException):
                print(f"  Warning: failed to fetch {fc.name}: {result!r}")
                continue
            feed_results.append(result)

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

    # Maths filter: posts built on real mathematics are linked, not narrated.
    # Bypassed for inject and reprocess — both are explicit "I want this one"
    # requests. Reprocess especially: it deletes the row first, so filtering a
    # reprocessed post would re-insert it with a NULL audio_file and silently
    # drop an already-published episode out of feed.xml, unrecoverably.
    maths_skipped: list[tuple[FeedEntry, MathsVerdict]] = []
    if (config.maths_filter.enabled and not inject_url and not reprocess_entry
            and entries_to_process):
        print(f"\nChecking {len(entries_to_process)} entries for maths density...")
        candidates = [
            (i, e) for i, (e, _m, _p) in enumerate(entries_to_process)
            if not e.id.startswith("news-briefing-")
        ]
        verdicts = await asyncio.gather(
            *[asyncio.to_thread(assess, e.link, e.content,
                                config.maths_filter.threshold_per_1k)
              for _i, e in candidates],
            return_exceptions=True,
        )
        drop: set[int] = set()
        for (idx, entry), verdict in zip(candidates, verdicts):
            if isinstance(verdict, BaseException):
                print(f"  Maths check failed for {entry.title}: {verdict!r} — keeping")
                continue
            if verdict.is_heavy:
                print(f"  Too mathematical for audio ({verdict.score}/1k via "
                      f"{verdict.source}): {entry.title}")
                drop.add(idx)
                maths_skipped.append((entry, verdict))
        if drop:
            entries_to_process = [
                t for i, t in enumerate(entries_to_process) if i not in drop
            ]

    # Some feeds ship an excerpt rather than the post. Zvi's is a podcast feed
    # whose body is a blurb plus a chapter list — three percent of the article —
    # so the summariser was working from a table of contents. Pull the real text
    # before anything reads it. Runs after the maths filter so posts about to be
    # dropped are not fetched twice, and in reprocess mode too, which is usually
    # someone asking for a bad episode to be done again.
    if entries_to_process and not inject_url:
        enrichable = [e for e, _m, _p in entries_to_process
                      if not e.id.startswith("news-briefing-")]
        gains = await asyncio.gather(
            *[asyncio.to_thread(enrich_entry, e) for e in enrichable],
            return_exceptions=True,
        )
        for entry, gain in zip(enrichable, gains):
            if isinstance(gain, BaseException):
                print(f"  Full-text fetch failed for {entry.title}: {gain!r} — using feed body")
            elif gain.replaced:
                print(f"  Recovered full text: {entry.title} "
                      f"({gain.before:,} -> {gain.after:,} chars)")
            elif gain.is_failure:
                # Silence here is how a three-percent blurb ships as an episode.
                print(f"  WARNING: could not reach the full text of {entry.title} — "
                      f"narrating the feed body ({gain.before:,} chars), which may "
                      f"be an excerpt")

    print(f"\n{len(entries_to_process)} entries to process")

    new_entry_ids: set[str] = set()
    failures: list[tuple[str, str]] = []

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
        # gather() preserves input order, so zipping recovers which entry each
        # exception came from — the report needs to name what failed.
        for (submitted, _mode, _prompt), result in zip(entries_to_process, results):
            if isinstance(result, BaseException):
                print(f"  Error processing {submitted.title}: {type(result).__name__}: {result!r}")
                failures.append((submitted.title, f"{type(result).__name__}: {result}"))
                continue
            entry, audio_path = result
            monitor.mark_processed(entry, audio_path.name, content=entry.content)
            new_entry_ids.add(entry.id)
            # Store news briefing text for future dedup context
            if entry.id.startswith("news-briefing-") and briefing_entry:
                today = datetime.now().strftime("%Y-%m-%d")
                monitor.store_news_briefing(today, briefing_entry.content)
            new_episodes += 1

        print(f"  {new_episodes} new episodes created")

    # Record the maths-skipped posts with no audio file. This dedups them so they
    # are not re-detected daily, and the feed generator already skips any entry
    # without audio, so they never appear as a broken episode.
    for entry, _verdict in maths_skipped:
        monitor.mark_processed(entry, None, content=entry.content)

    # Cleanup old entries BEFORE generating the feed, so the feed never
    # references audio/transcripts that cleanup deletes in this same run
    # (otherwise the deployed feed.xml advertises 404 enclosures).
    transcript_dir = output_dir / "transcripts"
    removed = monitor.cleanup_old_entries(days=30, audio_dir=audio_dir, transcript_dir=transcript_dir)
    if removed:
        print(f"  Cleaned up {removed} old entries")
    removed_briefings = monitor.cleanup_old_briefings(days=7)
    if removed_briefings:
        print(f"  Cleaned up {removed_briefings} old news briefings")

    # Generate podcast feed
    print(f"\nGenerating podcast feed...")
    db_entries = monitor.get_processed_entries()
    episodes = feed_gen.load_episodes_from_db(db_entries, audio_dir, transcript_dir)
    feed_path = output_dir / "feed.xml"
    feed_gen.generate(episodes, feed_path)
    print(f"  Generated feed with {len(episodes)} episodes: {feed_path}")

    # Email the run report. Skipped silently when the SMTP vars are unset.
    if new_entry_ids or failures or maths_skipped or _email_always():
        report = _build_run_report(
            episodes, db_entries, new_entry_ids, failures, config.podcast.base_url,
            maths_skipped,
        )
        send_report(report)
    else:
        print("  Nothing new — email report skipped (set FEEDCAST_EMAIL_ALWAYS=true to send anyway)")

    # Send ntfy notification for injected URLs
    if inject_url:
        ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
        if ntfy_topic:
            await _send_ntfy(ntfy_topic, inject_url, entries_to_process)

    print(f"\nPipeline complete.")


def _email_always() -> bool:
    """Whether to email even on a run that produced nothing."""
    return os.environ.get("FEEDCAST_EMAIL_ALWAYS", "").strip().lower() in ("true", "1", "yes")


def _build_run_report(
    episodes: list[Episode], db_entries: list[dict], new_entry_ids: set[str],
    failures: list[tuple[str, str]], base_url: str,
    maths_skipped: list[tuple[FeedEntry, MathsVerdict]] | None = None,
) -> RunReport:
    """Assemble the emailed report from this run's episodes and the feed."""
    db_by_id = {d["id"]: d for d in db_entries}
    cutoff = datetime.now() - timedelta(days=7)

    def to_report(ep: Episode) -> ReportEpisode:
        row = db_by_id.get(ep.id, {})
        is_briefing = ep.id.startswith("news-briefing-")
        feed_name = row.get("feed_name", "")
        author = (row.get("author") or "").strip() or feed_name
        return ReportEpisode(
            title=ep.title,
            author="" if is_briefing else author,
            feed_name=feed_name,
            link=ep.link or "",
            audio_url=f"{base_url}/audio/{ep.audio_file}",
            duration_seconds=ep.duration_seconds,
            is_briefing=is_briefing,
            briefing_text=(row.get("content") or "") if is_briefing else "",
        )

    ordered = sorted(episodes, key=lambda e: e.published, reverse=True)
    return RunReport(
        episodes=[to_report(e) for e in ordered if e.id in new_entry_ids],
        recent=[
            to_report(e) for e in ordered
            if e.id not in new_entry_ids and e.published >= cutoff
        ][:12],
        failures=failures,
        linked=[
            LinkedPost(title=e.title, author=e.author, feed_name=e.feed_name,
                       link=e.link, maths_score=v.score, source=v.source)
            for e, v in (maths_skipped or [])
        ],
        feed_url=f"{base_url}/feed.xml",
        site_url=base_url,
        total_in_feed=len(episodes),
    )


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
