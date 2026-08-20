# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Feedcast is an automated podcast generator. It monitors RSS feeds (primarily AI safety blogs on LessWrong and Astral Codex Ten), summarizes or cleans posts, generates audio via TTS with voice cloning, and publishes a valid RSS 2.0 podcast feed to GitHub Pages. It also produces a daily news briefing by aggregating articles from major news and AI sources, synthesizing them via LLM (Gemini Flash via OpenRouter) into a coherent audio briefing.

## Commands

```bash
# Install dependencies
uv sync

# Run the full pipeline (requires OPENROUTER_API_KEY and DEEPINFRA_API_KEY in .env)
uv run python -m src.main

# Reprocess a specific entry
REPROCESS_ENTRY="<entry-id-or-url>" uv run python -m src.main

# Force verbatim mode when reprocessing
REPROCESS_ENTRY="<entry-id-or-url>" FORCE_VERBATIM=true uv run python -m src.main

# Inject an arbitrary URL (any webpage, not just RSS feeds)
INJECT_URL="https://example.com/article" INJECT_MODE="auto" uv run python -m src.main
```

System dependency: `ffmpeg` is required for audio concatenation and MP3 encoding.

## Architecture

The pipeline runs in three async phases orchestrated by `src/main.py`:

1. **Phase 1 — Parallel feed fetching** (skipped in inject mode): All RSS feeds fetched concurrently via `asyncio.gather`. Author-specific feeds are listed before aggregate feeds in `config.yaml` so deduplication preserves author attribution (order matters). After dedup, a daily news briefing is generated (if configured) by `NewsAggregator`: it fetches news RSS sources, filters to recent articles, and synthesizes them via Gemini Flash (OpenRouter) into a single briefing entry.

   **Inject mode** (`INJECT_URL`): Skips Phase 1 entirely. Uses trafilatura to fetch and extract content from any arbitrary URL, then feeds it into Phases 2 and 3. Re-injecting the same URL deletes the previous entry.

2. **Phase 2 — Parallel content + audio**: For each new entry, `ContentProcessor` either summarizes via Gemini 3 Flash (OpenRouter) or cleans HTML for verbatim reading, then `AudioGenerator` chunks the text (max 500 chars, split at sentence boundaries), calls DeepInfra Chatterbox TTS with voice cloning for each chunk, and concatenates with ffmpeg. A semaphore (limit 10) controls TTS concurrency.

3. **Phase 3 — Sequential finalization**: Marks entries as processed in SQLite, generates `output/feed.xml`, and cleans up entries older than 30 days (including deleting associated audio files). In inject mode, sends a push notification via ntfy.sh on success or failure.

### Key modules

- **`src/monitor.py`** — `FeedMonitor`: RSS fetching with `feedparser`, SQLite-backed dedup tracking (`data/posts.db`, tables `processed_posts` and `news_briefings`). Supports `skip_patterns` per feed for title-based filtering. Stores recent news briefings for cross-day dedup. `is_processed_by_link()` provides link-based dedup for injected URLs.
- **`src/extractor.py`** — `url_to_feed_entry()`: Fetches any URL via trafilatura, extracts article text + metadata (title, author, date). Entry IDs use `injected-{sha256(url)[:16]}` format. Rejects content under 200 chars (quality gate for JS-rendered/paywalled pages).
- **`src/llm.py`** — OpenRouter client factory (`get_client()`) and two role-named model constants. `MODEL_WRITER` (**Claude Opus 4.6**) produces prose a person listens to: summaries, the daily briefing, table descriptions. `MODEL_NORMALIZER` (**Gemini 3 Flash**) only transforms text for TTS and writes nothing — it is ~47% of all tokens, and a reasoning model is not better at "preserve all other text exactly as-is". `MODEL_STRONG`/`MODEL_CHEAP` remain as aliases of `MODEL_WRITER`. All LLM calls use the OpenAI SDK against OpenRouter.
- **`src/mathiness.py`** — `assess()`: decides whether a post is too mathematical to follow by ear. Scores LaTeX density per 1000 words against `maths_filter.threshold_per_1k`. Fetches the LessWrong/Alignment Forum **markdown** via GraphQL, because RSS and the rendered page both strip MathJax — formulas otherwise arrive as holes. Flagged posts get no audio and are linked in the email instead.
- **`src/processor.py`** — `ContentProcessor`: HTML cleaning with BeautifulSoup, LLM summarization via Opus 4.6. Auto mode uses 24,000 char threshold to decide summarize vs verbatim. Converts HTML tables to prose (small tables inline, large tables via the LLM) before text extraction.
- **`src/normalizer.py`** — `TextNormalizer`: Gemini 3 Flash-powered text normalization for TTS. Converts numbers, dates, percentages, currency, abbreviations, and special characters to spoken form. Handles long texts by splitting into paragraph batches.
- **`src/audio.py`** — `AudioGenerator`: Voice sample upload to DeepInfra (fresh each session), async TTS with retry/backoff for 429s, ffmpeg concatenation to MP3. Voice sample: `voice_samples/derek_perkins.wav`.
- **`src/feed.py`** — `FeedGenerator`: RSS 2.0 XML generation with iTunes namespace tags. Episode durations come from `ffprobe`. Item descriptions and `<itunes:author>` carry the post's author(s).
- **`src/email_report.py`** — `send_report()`: HTML + plain-text run report emailed over SMTP when the pipeline finishes. Covers the day's news briefing in full, each new episode with author, source link and audio link, any failures, and the past week's other episodes. Silently skipped when the SMTP env vars are unset, and never raises.
- **`src/news.py`** — `NewsAggregator`: Parallel RSS fetching of news sources, article filtering by recency (configurable lookback), Opus 4.6-powered synthesis into a daily briefing. Produces a date-keyed `FeedEntry` for idempotent daily processing. Accepts recent briefing context for cross-day dedup.

### Configuration

`config.yaml` defines podcast metadata, the default summarization prompt, the feed list, the `maths_filter` section (`enabled`, `threshold_per_1k` — LaTeX matches per 1000 words above which a post is linked rather than narrated; recalibrate it whenever `_PATTERNS` in `mathiness.py` changes, since the two are coupled), and the optional `news_briefing` section. Each feed has a `mode` (`summarize`, `verbatim`, or `auto`), optional custom prompt, and optional `skip_patterns` (list of regexes matched against entry titles to filter out non-article posts). The `news_briefing` section configures the daily briefing with `enabled`, `lookback_hours`, a synthesis `prompt`, and a list of `sources` (each with `name`, `url`, `category`).

### Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API for LLM calls (Gemini Flash) |
| `DEEPINFRA_API_KEY` | Yes | DeepInfra Chatterbox TTS API |
| `REPROCESS_ENTRY` | No | Entry ID/URL to reprocess |
| `FORCE_VERBATIM` | No | Force verbatim for reprocessed entry |
| `INJECT_URL` | No | Arbitrary URL to extract and process as a new episode (skips RSS fetching) |
| `INJECT_MODE` | No | Processing mode for injected URL: `auto` (default), `summarize`, or `verbatim` |
| `NTFY_TOPIC` | No | ntfy.sh topic for push notifications on inject success/failure (e.g. `feedcast-titus`) |
| `VOICE_UPLOAD_DELAY_SECONDS` | No | Delay after voice upload for cross-region replication (CI uses 5) |
| `SAVE_DEBUG_WAVS` | No | Save intermediate WAV chunks for debugging |
| `LLM_TIMEOUT_SECONDS` | No | Per-request timeout for OpenRouter calls (default 180, 3 retries) |
| `FEEDCAST_EMAIL_TO` | No | Recipient of the HTML run report. Unset disables the email entirely |
| `SMTP_USER` | No | SMTP username (the sending Gmail address) |
| `GMAIL_APP_PASSWORD` | No | Google App Password. `SMTP_PASSWORD` is accepted as an alias |
| `SMTP_HOST` | No | SMTP server (default `smtp.gmail.com`) |
| `SMTP_PORT` | No | SMTP port (default 587 STARTTLS; 465 switches to implicit TLS) |
| `FEEDCAST_EMAIL_FROM` | No | From address (defaults to `SMTP_USER`) |
| `FEEDCAST_EMAIL_ALWAYS` | No | Send the report even when a run produced nothing new |

### URL Injection (Send Any URL)

The inject system allows sending any URL to feedcast from a browser or phone:

```
[Chrome Extension]  ──┐
                      ├──▶ [Cloudflare Worker] ──▶ [GitHub Actions] ──▶ [Pipeline] ──▶ feed.xml
[Android PWA Share] ──┘   (auth + rate limit)      (workflow_dispatch)
```

- **Cloudflare Worker** (`worker/`): Auth proxy at `https://feedcast-worker.feedcast-worker.workers.dev`. Validates bearer token, rate limits (20/hr), triggers GHA `workflow_dispatch` with `inject_url`/`inject_mode` inputs. Secrets: `FEEDCAST_TOKEN`, `GITHUB_PAT`, `GITHUB_REPO`.
- **Chrome Extension** (`chrome-extension/`): Manifest V3. Click on any page → pick mode → Send. Settings store Worker URL + token in `chrome.storage.sync`. Load unpacked from `chrome://extensions/`.
- **PWA Share Target** (`output/app/`): Installable PWA hosted on GitHub Pages. On Android, appears in the Share menu after "Add to Home Screen". Auth token stored in `localStorage`.
- **Notifications**: Pipeline sends push notifications via ntfy.sh (`NTFY_TOPIC` secret). Install the ntfy app and subscribe to the topic.

### CI/CD

GitHub Actions workflow (`.github/workflows/update-feed.yml`) runs daily at 6am UTC. It runs the pipeline, commits results, then deploys `output/` to GitHub Pages. Manual dispatch supports `entry_url`, `force_verbatim`, `inject_url`, and `inject_mode` inputs. A `concurrency` group (`feedcast-pipeline`) prevents race conditions between scheduled and injected runs. The commit step uses `git pull --rebase` to handle sequential runs cleanly.

## Data Flow

```
RSS feeds → feedparser → skip_patterns filter → new entries (SQLite dedup)
    → maths filter (LessWrong markdown via GraphQL; too mathematical → link in
      email, no audio, recorded with a NULL audio_file so it never recurs)
    → table-to-prose conversion (small inline, large via Gemini 2.5 Flash)
    → Gemini 3 Flash summarization OR HTML cleaning
    → TTS normalization (numbers/dates/symbols → spoken form via Gemini 2.5 Flash)
    → text chunks (≤500 chars, sentence boundaries)
    → DeepInfra TTS per chunk (voice-cloned WAVs)
    → ffmpeg concat → MP3
    → SQLite mark processed
    → RSS XML feed generation → GitHub Pages

News sources (RSS) → parallel fetch → filter last 48h
    → group by category → Gemini 3 Flash synthesis (with recent briefing dedup context)
    → single briefing FeedEntry → same audio pipeline above

Injected URL (via Chrome extension / Android PWA / CLI)
    → Cloudflare Worker (auth + rate limit) → GitHub Actions workflow_dispatch
    → trafilatura fetch + extract (200-char quality gate)
    → same audio pipeline above (skips Phase 1 RSS fetching)
    → ntfy.sh push notification on completion
```
