# Feedcast

Feedcast turns RSS feeds into a podcast. Each day it picks up new posts from the feeds in `config.yaml`, has a language model summarise each one or reads it out in full, narrates the result in a cloned voice with a text-to-speech (TTS) model, and publishes a podcast RSS feed on GitHub Pages. It also writes and narrates a daily news briefing, and turns any web page sent from a browser extension or an Android phone into an episode. After each run it emails a report (the daily email) with a bullet digest of every new episode.

**Live feed:** [tbuckworth.github.io/feedcast/feed.xml](https://tbuckworth.github.io/feedcast/feed.xml)

## How it works

```
 Daily schedule, 03:43 UTC ──────────────────────┐
 Chrome extension ──┐                            ▼
 Android web app ───┴──▶ Cloudflare Worker ──▶ GitHub Actions ──▶ python -m src.main ◀── a local run

 python -m src.main:
   RSS feeds ──▶ new posts ──▶ summarise or clean ──┐
   News sources ──▶ write the briefing ─────────────┼──▶ normalise ──▶ TTS ──▶ MP3
   Injected URL ──▶ extract the article ────────────┘
   ──▶ feed.xml on GitHub Pages, the daily email, and an ntfy push for an injected URL
```

Language models do the work in roles, which `ROLES` in `src/llm.py` defines: the **writer** writes the summaries and the briefing, the **checker** reads each written script against its source and the writer corrects what it flags, the **bullets** role writes the email's digest, and the **normalizer** rewrites a script for speech ("45%" becomes "forty-five percent"). Each role tries an ordered list of models across the API accounts and moves to the next when one fails; the module's docstring says why each model was chosen. The email names the model that wrote each summary and briefing, and lists every fallback.

The `src/__init__.py` docstring describes a run in detail, including its two publishes.

## Setup

You need Python 3.11 or 3.12, [uv](https://github.com/astral-sh/uv), and `ffmpeg` with `ffprobe`.

```bash
git clone https://github.com/tbuckworth/feedcast.git
cd feedcast
uv sync
```

The pipeline reads its API keys from the environment; nothing loads a `.env` file. On the desktop, `bwsrun` supplies them from the secrets vault under the names `.bws-profile` gives, and every command below that calls a model or DeepInfra runs under it.

## Running locally

The database (`data/posts.db`) and the MP3s (`data/audio/`) live on the orphan `state` branch, not on `main`. Restore them before any run:

```bash
scripts/state.sh pull                    # restore data/posts.db and data/audio/
bwsrun uv run python -m src.main         # one run: fetch, write, narrate, write output/
scripts/state.sh push                    # only to publish this run's database and MP3s
```

Environment variables choose other kinds of run:

```bash
REPROCESS_ENTRY="<entry id or URL>" bwsrun uv run python -m src.main
REPROCESS_ENTRY="<entry id or URL>" FORCE_VERBATIM=true bwsrun uv run python -m src.main
INJECT_URL="https://example.com/article" INJECT_MODE=summarize bwsrun uv run python -m src.main
bwsrun uv run python -m scripts.check_llm   # a short live call through each LLM role
```

An injected URL skips the feeds: the page is fetched and its article extracted with trafilatura, then processed like a post.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | The three LLM accounts. A role skips any account whose key is unset and falls back to the next; `ROLES` in `src/llm.py` says which models each account serves. Every role needs at least one of its accounts |
| `DEEPINFRA_API_KEY` | DeepInfra, for TTS. Required by any run that narrates |
| `REPROCESS_ENTRY` | Entry id or URL to make again: its episode is deleted and the post found in its feed with the age cutoff off. If the post cannot be found, the old episode is kept |
| `FORCE_VERBATIM` | With `REPROCESS_ENTRY`, read the post in full |
| `INJECT_URL` | Any URL, to extract and narrate as an episode instead of reading the feeds. Injecting a URL again replaces its episode |
| `INJECT_MODE` | Mode for `INJECT_URL`: `auto` (default), `summarize` or `verbatim` |
| `NTFY_TOPIC` | ntfy.sh topic that gets a push when an injected URL is published or fails |
| `FEEDCAST_PASS` | `first` or `narrate`: one of a run's two publishes (`src/__init__.py`). Unset runs everything in one pass; any other value stops the run |
| `RESEND_REPORT` | Re-send the last run's email, digesting any episode that has no bullets. Reads no feeds, and narrates and publishes nothing |
| `PREVIEW_BRIEFING` | Write a fresh briefing, prediction markets and fidelity check included, and email it with its charts. Publishes and records nothing |
| `FEEDCAST_EMAIL_TO` | Recipient of the email. Unset turns the email off; set, the SMTP credentials must be too, or the send fails, and in CI so does the job (after it publishes) |
| `FEEDCAST_EMAIL_BCC` | Further recipients, comma-separated, blind-copied |
| `FEEDCAST_EMAIL_FROM` | From address (default `SMTP_USER`) |
| `FEEDCAST_EMAIL_ALWAYS` | Send the email even when a run produced nothing |
| `FEEDCAST_TEST_RUN` | Dev run: publish as normal, but email only `FEEDCAST_EMAIL_TO`, with `[DEV]` in the subject |
| `SMTP_USER` | SMTP username (the sending Gmail address) |
| `GMAIL_APP_PASSWORD` | SMTP password, a Google app password; `SMTP_PASSWORD` is an alias |
| `SMTP_HOST`, `SMTP_PORT` | SMTP server (default `smtp.gmail.com`) and port (default 587, STARTTLS; 465 uses implicit TLS) |
| `LLM_TIMEOUT_SECONDS` | Timeout of each LLM request, on every account (default 180); the SDKs retry a failed request up to 3 times |
| `VOICE_UPLOAD_DELAY_SECONDS` | Seconds to wait after uploading the voice sample, for DeepInfra to replicate it (default 0; CI uses 5) |
| `SAVE_DEBUG_WAVS` | Keep every TTS chunk's WAV under `data/audio/debug_wavs/` |
| `STATE_REMOTE`, `STATE_BRANCH` | Remote and branch `scripts/state.sh` uses (default `origin`, `state`) |
| `FEEDCAST_REPO`, `FEEDCAST_WORKFLOW` | Repository and workflow `scripts/cron-backstop.sh` dispatches (default `tbuckworth/feedcast`, `update-feed.yml`) |

On/off variables count as on when set to `true`, `1` or `yes`. In CI, the `env:` blocks in `.github/workflows/update-feed.yml` set the pipeline's variables from the repository's secrets and variables.

## Configuration

`config.yaml` holds every pipeline setting, and its comments explain each one. Loading refuses an unknown key (`src/config.py`).

| Key | What it sets |
|-----|--------------|
| `podcast` | Feed metadata, the site's `base_url`, and the WebSub `hub_url` that apps are told to subscribe to |
| `default_prompt` | The writer's instructions for a summary, for a feed with no `prompt` of its own |
| `max_age_hours` | How recent an unseen post must be to be narrated; `null` turns the cutoff off |
| `retention_days` | How long an episode stays in the feed, and a failure in the retry queue |
| `auto_verbatim_limit` | Characters up to which an `auto` feed's post is read in full rather than summarised |
| `feeds` | The feeds: `name`, `url`, `mode` (`summarize`, `verbatim` or `auto`), optional `prompt`, and optional `skip_patterns` (regular expressions; a post whose title matches one is skipped) |
| `fidelity_check` | Whether the checker reads each written script against its source |
| `maths_filter` | Whether posts too mathematical to follow by ear are linked in the email instead of narrated, and the threshold |
| `tts.voice_sample` | The recording the voice is cloned from |
| `pronunciations` | Words the voice gets wrong, mapped to spellings it says right; applied to the audio only |
| `prediction_markets` | Prediction-market odds on the briefing's stories and a segment on big unexplained moves (`src/markets.py`) |
| `news_briefing` | The daily briefing: `enabled`, `lookback_hours`, how many stories the writer reads in full (`full_text_stories`, each capped at `max_article_chars`), its `prompt`, and its `sources` |

## CI

`.github/workflows/update-feed.yml` runs the pipeline daily at 03:43 UTC. GitHub's schedule can fire hours late or not at all, so `scripts/cron-backstop.sh`, run by the desktop crontab at 05:30 Europe/London, dispatches the workflow when no run exists for the UTC day.

One run publishes per UTC day: the `guard` job stops a run when another run that day has already published, so the backstop and a late scheduled run do not both email. A hand run, one dispatched with any input the workflow's `ON_DEMAND` expression names, is not guarded, and is a dev run (`FEEDCAST_TEST_RUN`) unless `notify_list` is ticked. Runs queue behind one another in the `feedcast-pipeline` concurrency group.

| Dispatch input | Effect |
|----------------|--------|
| `entry_url` | Reprocess this entry (`REPROCESS_ENTRY`) |
| `force_verbatim` | With `entry_url`, read the post in full |
| `inject_url`, `inject_mode` | Narrate this page (`INJECT_URL`, `INJECT_MODE`) |
| `resend_report` | Re-send the last run's email only |
| `preview_briefing` | Write and email a fresh briefing; publish nothing |
| `force` | Run even if today's run has already published |
| `notify_list` | Email the BCC list from a hand run too |
| `llm_smoke_test` | Only run `scripts/check_llm.py` with the CI keys: no email, audio, state change or publishing |

## Send any URL (Chrome extension and Android)

A web page reaches the pipeline through a Cloudflare Worker, which checks a bearer token, allows 20 requests an hour, and dispatches the workflow with `inject_url` and `inject_mode`.

### Cloudflare Worker

```bash
cd worker
npm install
npx wrangler login
npx wrangler deploy
npx wrangler secret put FEEDCAST_TOKEN    # shared auth token for clients
npx wrangler secret put GITHUB_PAT        # GitHub token with actions:write scope
npx wrangler secret put GITHUB_REPO       # e.g. tbuckworth/feedcast
```

### Chrome extension

1. Go to `chrome://extensions/` and enable Developer Mode.
2. Click **Load unpacked** and select the `chrome-extension/` folder.
3. Open the extension's **Settings** and enter the Worker URL and auth token.
4. On any article, click the extension, pick a mode, and click **Send to Podcast**.

### Android

The share target is a progressive web app (PWA): a web page that Android can install like an app, after which it appears in the Share menu.

1. Visit `https://tbuckworth.github.io/feedcast/app/` on the phone and choose **Add to Home Screen**.
2. Open the app, expand **Settings**, and enter the Worker URL and auth token.
3. From any app: **Share** > **Feedcast** > pick a mode > **Send to Podcast**.

### Push notifications

When `NTFY_TOPIC` is set (in CI, as a repository secret), the pipeline pushes each injected URL's outcome to that [ntfy.sh](https://ntfy.sh) topic. Subscribe to the topic in the ntfy app ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy), [iOS](https://apps.apple.com/app/ntfy/id1625396347)).

## Known limitations

- trafilatura fetches static HTML only, so a page rendered by JavaScript, or one behind a paywall or login, usually fails extraction (under 200 characters of text is refused).
- The Worker answers "queued" at once; the outcome arrives later as an ntfy push.

## License

MIT
