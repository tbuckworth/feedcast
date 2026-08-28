# Feedcast

An automated podcast generator that monitors RSS feeds, summarizes or reads posts verbatim, generates voice-cloned audio via TTS, and publishes a podcast RSS feed to GitHub Pages. Also produces a daily news briefing and accepts arbitrary URLs from a Chrome extension or Android share menu.

**Live feed:** [tbuckworth.github.io/feedcast/feed.xml](https://tbuckworth.github.io/feedcast/feed.xml)

## What It Does

- Monitors AI safety blogs (LessWrong, Astral Codex Ten, Alignment Forum) and selected authors
- Summarizes long posts via Gemini Flash or reads shorter ones verbatim
- Generates voice-cloned audio using DeepInfra Chatterbox TTS
- Produces a daily news briefing from BBC, Reuters, Ars Technica, TechCrunch, and AI lab blogs
- Accepts any URL from a Chrome extension or Android share menu, extracts the article, and turns it into a podcast episode
- Publishes a valid RSS 2.0 podcast feed with iTunes tags to GitHub Pages

## Architecture

```
                              ┌─────────────────────────────────────────────────────────────┐
 Scheduled (daily 6am UTC) ──▶│  RSS Feeds ──▶ dedup ──▶ summarize/verbatim ──▶ TTS ──▶ MP3 │
                              │  News Sources ──▶ synthesize briefing ──────▶ TTS ──▶ MP3   │
 Chrome Extension ──┐         │                                                             │──▶ feed.xml ──▶ GitHub Pages
 Android PWA Share ──┼──▶ Worker ──▶ GHA ──▶│  trafilatura extract ──▶ process ──▶ TTS ──▶ MP3   │
 CLI (INJECT_URL) ──┘         │                                              ──▶ ntfy push  │
                              └─────────────────────────────────────────────────────────────┘
```

### Pipeline Phases

1. **Phase 1 — Feed fetching** (skipped for injected URLs): Fetches all RSS feeds in parallel. Author-specific feeds are listed before aggregate feeds in `config.yaml` so deduplication preserves author attribution. News briefing is generated from news RSS sources via Gemini Flash.

2. **Phase 2 — Content + audio**: For each entry, the content is summarized (Gemini 3 Flash) or cleaned for verbatim reading, normalized for TTS (numbers/dates/symbols to spoken form via Gemini 2.5 Flash), chunked (max 500 chars at sentence boundaries), converted to speech via DeepInfra Chatterbox TTS with voice cloning, and concatenated to MP3 with ffmpeg.

3. **Phase 3 — Finalization**: Entries marked as processed in SQLite, `feed.xml` generated, old entries cleaned up (30 days). For injected URLs, a push notification is sent via ntfy.sh.

## Setup

### Prerequisites

- Python 3.11–3.12
- [uv](https://github.com/astral-sh/uv) package manager
- `ffmpeg` (for audio concatenation and MP3 encoding)

### Installation

```bash
git clone https://github.com/tbuckworth/feedcast.git
cd feedcast
uv sync
```

### Environment Variables

Create a `.env` file:

```bash
OPENROUTER_API_KEY=your_key    # Required — LLM calls (Gemini Flash via OpenRouter)
DEEPINFRA_API_KEY=your_key     # Required — DeepInfra Chatterbox TTS
```

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API for LLM calls (Gemini Flash) |
| `DEEPINFRA_API_KEY` | Yes | DeepInfra Chatterbox TTS API |
| `REPROCESS_ENTRY` | No | Entry ID/URL to reprocess from RSS feeds |
| `FORCE_VERBATIM` | No | Force verbatim mode when reprocessing |
| `INJECT_URL` | No | Any URL to extract and process as a podcast episode |
| `INJECT_MODE` | No | Mode for injected URL: `auto` (default), `summarize`, or `verbatim` |
| `NTFY_TOPIC` | No | ntfy.sh topic for push notifications on inject success/failure |
| `VOICE_UPLOAD_DELAY_SECONDS` | No | Delay after voice upload for cross-region replication (CI uses 5) |
| `SAVE_DEBUG_WAVS` | No | Save intermediate WAV chunks for debugging |
| `LLM_TIMEOUT_SECONDS` | No | Per-request timeout for OpenRouter calls (default 180, 3 retries) |
| `FEEDCAST_EMAIL_TO` | No | Recipient of the HTML run report. Unset disables the email entirely |
| `FEEDCAST_EMAIL_BCC` | No | Extra recipients, comma-separated, blind-copied so they stay hidden from each other |
| `SMTP_USER` | No | SMTP username (the sending Gmail address) |
| `GMAIL_APP_PASSWORD` | No | Google App Password. `SMTP_PASSWORD` is accepted as an alias |
| `SMTP_HOST` | No | SMTP server (default `smtp.gmail.com`) |
| `SMTP_PORT` | No | SMTP port (default 587 STARTTLS; 465 switches to implicit TLS) |
| `FEEDCAST_EMAIL_FROM` | No | From address (defaults to `SMTP_USER`) |
| `FEEDCAST_EMAIL_ALWAYS` | No | Send the report even when a run produced nothing new |

### Configuration

Edit `config.yaml` to configure podcast metadata, feeds, and the news briefing:

```yaml
feeds:
  - name: "Blog Name"
    url: "https://example.com/feed"
    mode: "auto"           # auto, summarize, or verbatim
    prompt: null            # null = use default_prompt
    skip_patterns:          # optional regex filters on titles
      - "^Open Thread"

news_briefing:
  enabled: true
  lookback_hours: 24
  prompt: "..."
  sources:
    - { name: "BBC World", url: "https://feeds.bbci.co.uk/news/world/rss.xml", category: "geopolitics" }
```

**Mode behavior:**
- `summarize` — LLM summary (~300-450 words, 2-3 min audio)
- `verbatim` — Full text cleaned for TTS
- `auto` — Verbatim if under 24,000 chars, summarize otherwise

## Usage

### Run the Full Pipeline

```bash
uv run python -m src.main
```

### Reprocess a Specific RSS Entry

```bash
REPROCESS_ENTRY="https://lesswrong.com/posts/..." uv run python -m src.main
REPROCESS_ENTRY="https://lesswrong.com/posts/..." FORCE_VERBATIM=true uv run python -m src.main
```

### Inject Any URL

```bash
INJECT_URL="https://example.com/article" uv run python -m src.main
INJECT_URL="https://example.com/article" INJECT_MODE="summarize" uv run python -m src.main
```

This skips RSS fetching, extracts the article via trafilatura, and processes it through the normal audio pipeline.

## Send Any URL (Chrome Extension + Android)

The inject system lets you send any URL to feedcast from your browser or phone:

```
[Chrome Extension] ──┐
                     ├──▶ Cloudflare Worker ──▶ GitHub Actions ──▶ Pipeline ──▶ feed.xml
[Android PWA]      ──┘    (auth + rate limit)   (workflow_dispatch)
```

### Cloudflare Worker

Auth proxy that validates a bearer token, rate limits (20 requests/hour), and triggers GitHub Actions.

```bash
cd worker
npm install
npx wrangler login
npx wrangler deploy

# Set secrets
npx wrangler secret put FEEDCAST_TOKEN    # shared auth token for clients
npx wrangler secret put GITHUB_PAT        # GitHub PAT with actions:write scope
npx wrangler secret put GITHUB_REPO       # e.g. tbuckworth/feedcast
```

### Chrome Extension

1. Go to `chrome://extensions/` and enable Developer Mode
2. Click **Load unpacked** and select the `chrome-extension/` folder
3. Click the extension icon, go to **Settings**, enter your Worker URL and auth token
4. Navigate to any article, click the extension, pick a mode, and hit **Send to Podcast**

### Android (PWA Share Target)

1. Visit `https://tbuckworth.github.io/feedcast/app/` on your phone
2. **Add to Home Screen** when prompted
3. Open the app, expand Settings, enter Worker URL and auth token
4. From any app: **Share** > **Feedcast** > pick mode > **Send to Podcast**

### Push Notifications

The pipeline sends notifications via [ntfy.sh](https://ntfy.sh) when injected URLs finish processing.

1. Add `NTFY_TOPIC` as a GitHub Actions secret (e.g. `feedcast-titus`)
2. Install the ntfy app ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/app/ntfy/id1625396347))
3. Subscribe to your topic

## CI/CD

GitHub Actions workflow (`.github/workflows/update-feed.yml`) runs daily at 03:43 UTC:

1. Fetches feeds, processes new entries, generates audio
2. Commits results to the repo
3. Deploys `output/` to GitHub Pages

**Manual dispatch** supports:
- `entry_url` — reprocess a specific RSS entry
- `force_verbatim` — force verbatim mode
- `inject_url` — process any arbitrary URL
- `inject_mode` — auto/summarize/verbatim

A concurrency group prevents race conditions between scheduled and on-demand runs.

**Scheduled runs are best-effort.** GitHub delivers `schedule:` late under load —
hours late on 27 and 28 Aug 2026 — and sometimes not at all. Two mitigations:
the cron sits off the congested top of the hour, and `scripts/cron-backstop.sh`
runs from the desktop crontab a couple of hours later, dispatching the workflow
only when no run exists for that UTC day. A redundant dispatch is harmless: the
concurrency group queues it, and a run with nothing new publishes nothing and
sends no email.

**GitHub Secrets required:**
- `OPENROUTER_API_KEY`
- `DEEPINFRA_API_KEY`
- `NTFY_TOPIC` (optional, for push notifications)

## Project Structure

```
feedcast/
├── src/
│   ├── main.py           # Pipeline orchestration (3 phases)
│   ├── monitor.py        # RSS fetching + SQLite dedup tracking
│   ├── extractor.py      # Arbitrary URL extraction via trafilatura
│   ├── processor.py      # Content processing (summarize/verbatim)
│   ├── normalizer.py     # TTS text normalization (numbers, dates, symbols)
│   ├── audio.py          # Voice-cloned TTS generation + ffmpeg concat
│   ├── feed.py           # RSS 2.0 XML generation
│   ├── llm.py            # OpenRouter client + model constants
│   └── news.py           # Daily news briefing aggregation
├── worker/
│   ├── src/index.ts      # Cloudflare Worker (auth proxy)
│   ├── wrangler.toml     # Worker configuration
│   └── package.json      # Worker dependencies
├── chrome-extension/
│   ├── manifest.json     # Manifest V3
│   ├── popup.html/js     # Extension popup UI
│   └── options.html/js   # Settings page
├── output/
│   ├── feed.xml          # Generated podcast feed
│   ├── transcripts/      # Episode transcripts
│   └── app/              # PWA share target for Android
├── config.yaml           # Feed + news briefing configuration
├── data/
│   ├── posts.db          # SQLite — processed posts + news briefings
│   └── audio/            # Generated MP3 files
├── voice_samples/        # TTS voice clone source audio
└── .github/workflows/    # GitHub Actions (daily + on-demand)
```

## Known Limitations

- **JS-rendered pages**: trafilatura fetches static HTML only. SPAs or heavy client-rendered pages may fail the 200-char quality gate.
- **Paywalled content**: If you're logged in on your browser but the server can't access the page, extraction fails.
- **No real-time status**: Injected URLs return "queued" immediately; you get a ntfy notification 3-8 minutes later when processing completes.
- **Podcast app polling**: Even after an episode is published, your podcast app may take up to an hour to poll the feed.

## License

MIT
