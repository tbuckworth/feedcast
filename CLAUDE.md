# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Feedcast is an automated podcast generator. It monitors RSS feeds (primarily AI safety blogs on LessWrong and Astral Codex Ten), summarizes or cleans posts, generates audio via TTS with voice cloning, and publishes a valid RSS 2.0 podcast feed to GitHub Pages. It also produces a daily news briefing by aggregating articles from major news and AI sources, synthesizing them via Claude into a coherent audio briefing.

## Commands

```bash
# Install dependencies
uv sync

# Run the full pipeline (requires ANTHROPIC_API_KEY and DEEPINFRA_API_KEY in .env)
uv run python -m src.main

# Reprocess a specific entry
REPROCESS_ENTRY="<entry-id-or-url>" uv run python -m src.main

# Force verbatim mode when reprocessing
REPROCESS_ENTRY="<entry-id-or-url>" FORCE_VERBATIM=true uv run python -m src.main
```

System dependency: `ffmpeg` is required for audio concatenation and MP3 encoding.

## Architecture

The pipeline runs in three async phases orchestrated by `src/main.py`:

1. **Phase 1 — Parallel feed fetching**: All RSS feeds fetched concurrently via `asyncio.gather`. Author-specific feeds are listed before aggregate feeds in `config.yaml` so deduplication preserves author attribution (order matters). After dedup, a daily news briefing is generated (if configured) by `NewsAggregator`: it fetches news RSS sources, filters to recent articles, and synthesizes them via Claude into a single briefing entry.

2. **Phase 2 — Parallel content + audio**: For each new entry, `ContentProcessor` either summarizes via Claude (`claude-sonnet-4-20250514`) or cleans HTML for verbatim reading, then `AudioGenerator` chunks the text (max 500 chars, split at sentence boundaries), calls DeepInfra Chatterbox TTS with voice cloning for each chunk, and concatenates with ffmpeg. A semaphore (limit 10) controls TTS concurrency.

3. **Phase 3 — Sequential finalization**: Marks entries as processed in SQLite, generates `output/feed.xml`, and cleans up entries older than 30 days (including deleting associated audio files).

### Key modules

- **`src/monitor.py`** — `FeedMonitor`: RSS fetching with `feedparser`, SQLite-backed dedup tracking (`data/posts.db`, tables `processed_posts` and `news_briefings`). Supports `skip_patterns` per feed for title-based filtering. Stores recent news briefings for cross-day dedup.
- **`src/processor.py`** — `ContentProcessor`: HTML cleaning with BeautifulSoup, Claude API summarization. Auto mode uses 24,000 char threshold to decide summarize vs verbatim. Converts HTML tables to prose (small tables inline, large tables via Claude Haiku) before text extraction.
- **`src/normalizer.py`** — `TextNormalizer`: Claude Haiku-powered text normalization for TTS. Converts numbers, dates, percentages, currency, abbreviations, and special characters to spoken form. Handles long texts by splitting into paragraph batches.
- **`src/audio.py`** — `AudioGenerator`: Voice sample upload to DeepInfra (fresh each session), async TTS with retry/backoff for 429s, ffmpeg concatenation to MP3. Voice sample: `voice_samples/derek_perkins.wav`.
- **`src/feed.py`** — `FeedGenerator`: RSS 2.0 XML generation with iTunes namespace tags.
- **`src/news.py`** — `NewsAggregator`: Parallel RSS fetching of news sources, article filtering by recency (configurable lookback), Claude-powered synthesis into a daily briefing. Produces a date-keyed `FeedEntry` for idempotent daily processing. Accepts recent briefing context for cross-day dedup.

### Configuration

`config.yaml` defines podcast metadata, the default summarization prompt, the feed list, and the optional `news_briefing` section. Each feed has a `mode` (`summarize`, `verbatim`, or `auto`), optional custom prompt, and optional `skip_patterns` (list of regexes matched against entry titles to filter out non-article posts). The `news_briefing` section configures the daily briefing with `enabled`, `lookback_hours`, a synthesis `prompt`, and a list of `sources` (each with `name`, `url`, `category`).

### Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Claude API for summarization |
| `DEEPINFRA_API_KEY` | Yes | DeepInfra Chatterbox TTS API |
| `REPROCESS_ENTRY` | No | Entry ID/URL to reprocess |
| `FORCE_VERBATIM` | No | Force verbatim for reprocessed entry |
| `VOICE_UPLOAD_DELAY_SECONDS` | No | Delay after voice upload for cross-region replication (CI uses 5) |
| `SAVE_DEBUG_WAVS` | No | Save intermediate WAV chunks for debugging |

### CI/CD

GitHub Actions workflow (`.github/workflows/update-feed.yml`) runs daily at 6am UTC. It runs the pipeline, commits results, then deploys `output/` to GitHub Pages. Manual dispatch supports `entry_url` and `force_verbatim` inputs.

## Data Flow

```
RSS feeds → feedparser → skip_patterns filter → new entries (SQLite dedup)
    → table-to-prose conversion (small inline, large via Haiku)
    → Claude summarization OR HTML cleaning
    → TTS normalization (numbers/dates/symbols → spoken form via Haiku)
    → text chunks (≤500 chars, sentence boundaries)
    → DeepInfra TTS per chunk (voice-cloned WAVs)
    → ffmpeg concat → MP3
    → SQLite mark processed
    → RSS XML feed generation → GitHub Pages

News sources (RSS) → parallel fetch → filter last 48h
    → group by category → Claude synthesis (with recent briefing dedup context)
    → single briefing FeedEntry → same audio pipeline above
```
