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

The database (`data/posts.db`) and MP3s (`data/audio/`) are gitignored on main and live on the orphan `state` branch: run `scripts/state.sh pull` before the pipeline locally, and `scripts/state.sh push` only to publish. CI does both.

## Architecture

The pipeline runs in three async phases orchestrated by `src/main.py`:

1. **Phase 1 — Parallel feed fetching** (skipped in inject mode): All RSS feeds fetched concurrently via `asyncio.gather`. Author-specific feeds are listed before aggregate feeds in `config.yaml` so deduplication preserves author attribution (order matters). After dedup, a daily news briefing is generated (if configured) by `NewsAggregator`: it fetches news RSS sources, filters to recent articles, and synthesizes them via Gemini Flash (OpenRouter) into a single briefing entry.

   **Inject mode** (`INJECT_URL`): Skips Phase 1 entirely. Uses trafilatura to fetch and extract content from any arbitrary URL, then feeds it into Phases 2 and 3. Re-injecting the same URL deletes the previous entry.

2. **Phase 2 — Parallel content + audio**: For each new entry, `ContentProcessor` either summarizes via Gemini 3 Flash (OpenRouter) or cleans HTML for verbatim reading, then `AudioGenerator` chunks the text (max 500 chars, split at sentence boundaries), calls DeepInfra Chatterbox TTS with voice cloning for each chunk, and concatenates with ffmpeg. A semaphore (limit 5) controls TTS concurrency. Finished chunk WAVs are kept under `data/audio/.partial/<episode>/` until the MP3 exists, so a retry synthesises only the chunks that failed; TTS retries open a fresh connection with jittered backoff.

3. **Phase 3 — Sequential finalization**: Marks entries as processed in SQLite, generates `output/feed.xml`, and cleans up entries older than 30 days (including deleting associated audio files). For every episode a writer model produced (summaries and the briefing), the exact prompt and reply are saved to `data/sources/<episode-id>.md` (`src/bundle.py`) and deleted by the same cleanup. In inject mode, sends a push notification via ntfy.sh on success or failure. An entry that fails gets a serial second pass in the same run (`Attempt` in `src/main.py` records the stage reached and the texts produced, so it resumes rather than restarts), and is then queued in `failed_entries` with its normalised script; later runs retry it regardless of the age window, straight from narration, up to `FeedMonitor.MAX_ATTEMPTS` (3). Failures are logged with stage and traceback and surfaced as GitHub `::warning` annotations.

   **Two publishes per run** (`FEEDCAST_PASS`; unset runs everything in one pass, as locally). `first`: the briefing and the summaries are narrated, published and emailed. Posts read out in full (`ContentProcessor.reads_verbatim`: verbatim feeds, and auto posts under 24k chars) are cleaned and digested, then parked in the `deferred_entries` table. The email lists them with their bullets and a "Listen (narrating)" link to `output/episodes/<episode-id>.html`. That page says the audio is coming, refreshes itself, and plays the episode once it exists (`FeedGenerator.write_episode_pages`, which writes a page for every feed episode). `narrate`: narrates the parked posts, adds them to the feed, and publishes again. It mails only on failure, and only `FEEDCAST_EMAIL_TO`. Attempts are counted before narrating (`start_narration`), so a pass the job timeout kills still uses up an attempt; the post is retried by the next run's narrate job, up to `MAX_ATTEMPTS`. A parked post is invisible to `fetch_feed`, so it never comes back as new. Inject and reprocess runs are single-pass. Why: on 2026-09-26 a 113-chunk book review ran into the 90-minute timeout and took the day's briefing and summary down with it. On slow-TTS days the summaries also waited 10–20 minutes behind the verbatim chunks in the shared narration queue.

### Key modules

- **`src/monitor.py`** — `FeedMonitor`: RSS fetching with `feedparser`, plus `warn_if_dead()`, which every feed fetch runs through — `feedparser.parse()` never raises, so a 404 or a DNS failure arrives as an empty feed and reads as "nobody posted".  SQLite-backed dedup tracking (`data/posts.db`, tables `processed_posts` and `news_briefings`). Supports `skip_patterns` per feed for title-based filtering. Stores recent news briefings for cross-day dedup. `is_processed_by_link()` provides link-based dedup for injected URLs.
- **`src/extractor.py`** — `url_to_feed_entry()`: Fetches any URL via trafilatura, extracts article text + metadata (title, author, date). Entry IDs use `injected-{sha256(url)[:16]}` format. Rejects content under 200 chars (quality gate for JS-rendered/paywalled pages).
- **`src/llm.py`** — every model call goes through `complete(role, messages, ...)`. Four roles, each an ordered list of `(route, model)` targets; a failed or empty call falls through to the next target, the switch is logged, and the email ends with a "Model fallbacks this run" section (`RunReport.notices`). Routes are the three billable accounts, all spoken to with the OpenAI SDK: `openrouter` (`OPENROUTER_API_KEY`), `openai` (`OPENAI_API_KEY`; needs `max_completion_tokens`, rejects `temperature`), `anthropic` (`ANTHROPIC_API_KEY`, the OpenAI-compatible endpoint, which ignores effort and rejects any temperature on Sonnet 5 / Opus 5.5; a call that sets an effort goes to the native Messages API via the `anthropic` SDK instead). An unset key skips that route. Since 2026-09-22 OpenRouter refuses every Claude model on the Arrow key (403 "violation of provider Terms Of Service"), so the Claude roles go to Anthropic direct first, with OpenRouter as the backup. **writer** = Claude Opus 5.5 at effort low, Anthropic direct (backups: Opus 5.5 via OpenRouter, Opus 4.6 direct, GPT-6.1 Sol at effort low direct and via OpenRouter): summaries, the briefing, story selection, table prose, the revision. Replaced Opus 4.6 on 2026-09-27 (`scripts/model_upgrade_test.py`): shorter, more carefully attributed briefings, ~7% dearer a month because its tokenizer counts ~1.46x the tokens. **checker** = Claude Sonnet 5, Anthropic direct (backups: via OpenRouter, Sonnet 4.6, Gemini 3 Flash, then GPT-6.1 Sol direct). **bullets** = GPT-5.6 Sol on OpenAI direct with reasoning off (backups: Sol via OpenRouter, Opus 5.5 direct): the email digest, chosen 2026-09-16 after a side-by-side. **normalizer** = Gemini 3 Flash via OpenRouter: only transforms text for TTS, ~47% of all tokens (backups: Claude Haiku 5.5 direct, then GPT-6.1 Sol direct; until 2026-10-10 it had no backup, and OpenRouter running out of credit failed every episode). Every role has a target off OpenRouter (a test enforces it). GPT-6.1 Sol rejects `reasoning_effort: none`, so its targets carry `min_effort="low"` and a request for reasoning off is sent as low. An account-level refusal (`account_failure()`: 401/402, or credit/quota/billing wording on 400/403/429; not OpenRouter's Claude-only 403 or a plain rate limit) puts the route in `dead_routes`, and every later call that run skips it. `fallback_notices()` is what the email shows: one headline per dead account, repeats collapsed. `Completion.credit()` records who wrote a script (`FeedEntry.writer`, `processed_posts.writer`); the email prints a small "Written by …" line under each written episode, amber with "(backup: … was unavailable)" when a different model from the primary wrote it. `completion_text()` is the one place a completion's text is read: OpenRouter reports a provider failure as a 200 with `choices=None`; it raises `EmptyCompletion` instead of a bare `TypeError`. `client=` pins a call to a given client with no fallback (tests); that client is assumed to be OpenRouter's and gets `pinned_target(role)`. `MODEL_WRITER` etc. name each role's primary model.
- **`src/mathiness.py`** — `assess()`: decides whether a post is too mathematical to follow by ear. Scores LaTeX density per 1000 words against `maths_filter.threshold_per_1k`. Fetches the LessWrong/Alignment Forum **markdown** via GraphQL, because RSS and the rendered page both strip MathJax — formulas otherwise arrive as holes. Flagged posts get no audio and are linked in the email instead.
- **`src/fulltext.py`** — `enrich_entry()`: swaps a feed's excerpt for the real post. Zvi's feed is `podcast.lesswrong.com/users/zvi.rss`, a *podcast* feed whose body is an episode blurb plus a chapter list — measured at 3% of the article — so summaries were written from a table of contents. Refetches the GraphQL markdown (cached, shared with `mathiness.py`) and renders it to HTML so the rest of the pipeline is unchanged. Only replaces when the post is at least `MIN_GAIN` (1.2x) longer in visible text, which leaves the author `community-rss` feeds alone.
- **`src/processor.py`** — `ContentProcessor`: HTML cleaning with BeautifulSoup, LLM summarization through the writer role (Opus 5.5). Auto mode uses 24,000 char threshold to decide summarize vs verbatim. Converts HTML tables to prose (small tables inline, large tables via the LLM) before text extraction.
- **`src/normalizer.py`** — `respell()` applies config.yaml `pronunciations` (word → spelling the voice says right) in code after normalisation, to the spoken text only. Every entry is measured with `scripts/pronunciation_check.py` (TTS N times, then a phoneme recogniser); about half the plausible respellings tried in testing didn't help. Code beat both LLM routes: Gemini improvising respellings was inconsistent run to run, and Opus respelling while writing leaked into the email, transcripts and fidelity check. IPA input does not work (Chatterbox reads the symbols as letters). Intros and outros use `processor.spoken_title()`, which drops a "by <author>" tail (Zvi's titles end "by Zvi").
- **`src/normalizer.py`** — `TextNormalizer`: On an `EmptyCompletion` a batch is halved and each side retried, by paragraph, then by sentence, down to the passage the model will not take, which is then narrated as written (counted in `unnormalized_chars`). Gemini 3 Flash-powered text normalization for TTS. Converts numbers, dates, percentages, currency, abbreviations, and special characters to spoken form. Handles long texts by splitting into paragraph batches.
- **`src/audio.py`** — `AudioGenerator`: Voice sample upload to DeepInfra (fresh each session), async TTS with retry/backoff for 429s, ffmpeg concatenation to MP3. Models in `TTS_MODELS` order: Chatterbox Turbo, then Chatterbox Multilingual (same price, same uploaded voice). A model still answering 429 after the retries moves the rest of the run to the next one and adds a line to the email's fallback section; on 2026-10-01 turbo said "Model busy" for hours and the run produced no audio. Voice sample: `voice_samples/derek_perkins.wav`.
- **`src/feed.py`** — `FeedGenerator`: RSS 2.0 XML generation with iTunes namespace tags. Episode durations come from `ffprobe`, enclosure lengths from the file size. Item descriptions and `<itunes:author>` carry the post's author(s). The channel declares a WebSub hub (`podcast.hub_url`, default Google's `pubsubhubbub.appspot.com`) and CI pings it after every Pages deploy: Pocket Casts fetches feeds server-side, and polled this small private feed only every few hours — the episode email arrived while the app still showed yesterday (2026-09-15). A hub notification reaches it in about a minute. Non-URL guids carry `isPermaLink="false"`.
- **`src/digest.py`** — `safe_bullets()`: the email's two-level digest of each episode — 4-6 headline bullets, each with 1-4 indented sub-bullets carrying the figures, names and caveats, so the email says what the audio says. Written by the **bullets** role from the spoken script *after* the fidelity check, never from the source (bullets are unchecked; the source is where an invented story would come from). The briefing's bullets carry per-bullet `Source →` links drawn only from the 12 selected articles (`FeedEntry.sources`), not every headline: the full list once let the digest lift a story the briefing never told. Takes the script *before* TTS normalisation, because bullets are read: they want "45%", not "forty-five percent". Never raises. Stored as JSON in `processed_posts.bullets`: strings, or `{"text", "url"?, "sub"?}`. Fired concurrently with TTS in `process_entry`.
- **`src/email_report.py`** — `send_report()`: HTML + plain-text run report emailed over SMTP when the pipeline finishes. Covers the day's news briefing and each new episode as nested bullets (falling back to the full briefing text if the digest failed), author, source link and audio link; any failures; any source that returned nothing (`dead_sources` — a 404 feed produces an empty parse, not an error, so this is the only symptom); model fallbacks; and the past week's other episodes. Fidelity: a bullet matching one of the checker's remaining complaints is tinted and numbered (`flag_marks`, matched by shared words), and one "Checked against source" section at the foot lists every complaint with its script and source quotes (`number_notes`, `checker_notes`). Silently skipped when the SMTP env vars are unset, and never raises.
- **`src/verify.py`** — Second-model fidelity check: Sonnet 5 reads each written script against its source, flags contradicted/distorted/unsupported claims, the writer revises once, the checker re-reads. Never raises. Result stored per episode (`fidelity` column) and shown in the email; `fidelity_summary()` states the draft's flag count and what remains after the one revision, never a subtraction (the re-check can raise flags the first pass did not, which printed "-1 corrected" on 2026-09-16).
- **`src/markets.py`** — prediction markets in the briefing (`prediction_markets` in config.yaml). `MarketScout.build()` runs between story selection and writing, never raises, and is bounded at 240s. **Story context:** two small checker calls (search queries, then which candidate markets are really about each story) over Polymarket `public-search`, Manifold `search-markets` and the configured Kalshi AI series (Kalshi has no search, so they are matched by shared words). Each matched market's odds a week before the story, the day before it and now are appended to that story in the writer's input. **Moves:** Polymarket events tagged ai/openai/anthropic plus the Kalshi series are scanned for 24h moves (`MarketRules`, from a 30-day backtest: ≥15 points; a volume floor; not closing within 7 days; not ending within 2% of an edge; no leaderboards or benchmark debuts; a topic whitelist; IPO and boardroom markets only at ≥20). Moves on a market already attached to a story are dropped, as is one reported in the last week (`market_reports` table) unless it has moved another 15. Each remaining move gets a cause from Sonnet 5 with Anthropic's server-side web search (`find_cause`, ~5s, $10 per 1,000 searches). The writer gets extra instructions only on days with market data, so other days send the same message as before; moves become a closing "On the prediction markets," segment. Market URLs join `FeedEntry.sources`, so digest bullets can link them. Manifold is play money, so it gives context only and never counts as a move.
- **`src/market_charts.py`** — `render_chart()`: a 30-day PNG of a market's odds with the story marked, for the prediction-markets trial email (`_send_markets_trial` in main.py). That email is the day's email plus charts under the bullets that link their stories, sent to `FEEDCAST_MARKETS_TRIAL_TO` (Titus and Jason) as "[DEV - Prediction Markets]", only on days the briefing used a market.
- **`src/news.py`** — `NewsAggregator`: Parallel RSS fetching of news sources, article filtering by recency (configurable lookback), Opus 5.5-powered synthesis into a daily briefing. Produces a date-keyed `FeedEntry` for idempotent daily processing. Accepts recent briefing context for cross-day dedup.

### Configuration

`config.yaml` defines podcast metadata, the default summarization prompt, the feed list, the `maths_filter` section (`enabled`, `threshold_per_1k` — LaTeX matches per 1000 words above which a post is linked rather than narrated; recalibrate it whenever `_PATTERNS` in `mathiness.py` changes, since the two are coupled), and the optional `news_briefing` section. Each feed has a `mode` (`summarize`, `verbatim`, or `auto`), optional custom prompt, and optional `skip_patterns` (list of regexes matched against entry titles to filter out non-article posts). The `news_briefing` section configures the daily briefing with `enabled`, `lookback_hours`, a synthesis `prompt`, and a list of `sources` (each with `name`, `url`, `category`).

### Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter: the normaliser (Gemini 3 Flash) and the backup route for the Claude roles |
| `OPENAI_API_KEY` | No | OpenAI direct: GPT-5.6 Sol writes email bullets and backs up the writer when Claude is unavailable |
| `ANTHROPIC_API_KEY` | No | Anthropic direct: primary route for the writer (Opus 5.5) and checker (Sonnet 5). All three LLM keys are the ARROW_* accounts |
| `DEEPINFRA_API_KEY` | Yes | DeepInfra Chatterbox TTS API |
| `REPROCESS_ENTRY` | No | Entry ID/URL to reprocess |
| `FORCE_VERBATIM` | No | Force verbatim for reprocessed entry |
| `INJECT_URL` | No | Arbitrary URL to extract and process as a new episode (skips RSS fetching) |
| `INJECT_MODE` | No | Processing mode for injected URL: `auto` (default), `summarize`, or `verbatim` |
| `NTFY_TOPIC` | No | ntfy.sh topic for push notifications on inject success/failure (e.g. `feedcast-titus`) |
| `VOICE_UPLOAD_DELAY_SECONDS` | No | Delay after voice upload for cross-region replication (CI uses 5) |
| `FEEDCAST_TEST_RUN` | No | Dev run: publish as normal but email only `FEEDCAST_EMAIL_TO`, subject tagged `[DEV]`, no BCC. CI sets it for every hand-dispatched run unless `notify_list` is ticked |
| `SAVE_DEBUG_WAVS` | No | Save intermediate WAV chunks for debugging |
| `RESEND_REPORT` | No | Re-send the last run's email and nothing else. Backfills missing bullet digests, publishes nothing, generates no audio. Mail credentials only exist in CI, so this is how you re-send after a template change |
| `LLM_TIMEOUT_SECONDS` | No | Per-request timeout for OpenRouter calls (default 180, 3 retries) |
| `FEEDCAST_EMAIL_TO` | No | Recipient of the HTML run report. Unset disables the email entirely |
| `SMTP_USER` | No | SMTP username (the sending Gmail address) |
| `GMAIL_APP_PASSWORD` | No | Google App Password. `SMTP_PASSWORD` is accepted as an alias |
| `SMTP_HOST` | No | SMTP server (default `smtp.gmail.com`) |
| `SMTP_PORT` | No | SMTP port (default 587 STARTTLS; 465 switches to implicit TLS) |
| `FEEDCAST_EMAIL_FROM` | No | From address (defaults to `SMTP_USER`) |
| `PREVIEW_BRIEFING` | No | Write a fresh briefing (markets and fidelity check included) and email it plus the markets trial email; publishes and records nothing. The briefing is made once a day, so this is the only way to see a change to it the same day. CI input `preview_briefing` (a dev run: emails go to `FEEDCAST_EMAIL_TO` only) |
| `FEEDCAST_MARKETS_TRIAL_TO` | No | Recipients of the prediction-markets trial email with charts (comma-separated). Unset: no trial email |
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

GitHub Actions workflow (`.github/workflows/update-feed.yml`) is scheduled daily at 03:43 UTC; the desktop cron backstop dispatches at 05:30 Europe/London. The `update` job runs the first pass (`FEEDCAST_PASS=first`) and commits (`scripts/ci-commit-and-push.sh`). `deploy` then publishes `output/` to GitHub Pages. In parallel, `narrate` runs the narration pass when the first pass deferred anything (its `deferred` output), and `deploy-narrated` publishes again. Both deploys call the reusable `.github/workflows/publish-pages.yml`, each with its own artifact name. That workflow waits until the live `feed.xml` is byte-identical to the committed one (the Pages CDN caches for 10 minutes), then sends a WebSub publish ping to the hub the feed declares. The narrate step is `continue-on-error`, so a failed or timed-out narration still commits its attempt count and the episode pages. Manual dispatch supports `entry_url`, `force_verbatim`, `inject_url`, `inject_mode`, `resend_report` and `preview_briefing` inputs. `llm_smoke_test=true` runs only short synthetic LLM checks with the real CI keys: no email, audio, state changes, or publishing. Run it locally with `bwsrun uv run python -m scripts.check_llm`. A `concurrency` group (`feedcast-pipeline`) prevents race conditions between scheduled and injected runs. The commit step uses `git pull --rebase` to handle sequential runs cleanly.

## Data Flow

```
RSS feeds → feedparser → skip_patterns filter → new entries (SQLite dedup)
    → maths filter (LessWrong markdown via GraphQL; too mathematical → link in
      email, no audio, recorded with a NULL audio_file so it never recurs)
    → full-text recovery (excerpt-only feeds refetched as markdown → HTML)
    → table-to-prose conversion (small inline, large via Gemini 2.5 Flash)
    → Gemini 3 Flash summarization OR HTML cleaning
    → TTS normalization (numbers/dates/symbols → spoken form via Gemini 2.5 Flash)
    → text chunks (≤500 chars, sentence boundaries)
    → DeepInfra TTS per chunk (voice-cloned WAVs)
    → ffmpeg concat → MP3   (two-level bullet digest by GPT-5.6 Sol runs in parallel, for the email)
    → SQLite mark processed
    → RSS XML feed generation → GitHub Pages

News sources (RSS) → parallel fetch → filter to lookback_hours (24)
    → group by category → Opus 5.5 synthesis (with recent briefing dedup context)
    → single briefing FeedEntry → same audio pipeline above

Injected URL (via Chrome extension / Android PWA / CLI)
    → Cloudflare Worker (auth + rate limit) → GitHub Actions workflow_dispatch
    → trafilatura fetch + extract (200-char quality gate)
    → same audio pipeline above (skips Phase 1 RSS fetching)
    → ntfy.sh push notification on completion
```
