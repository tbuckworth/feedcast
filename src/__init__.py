"""Feedcast: RSS feeds and a daily news briefing, narrated as a podcast.

`python -m src.main` runs the pipeline in three phases:

1. Collect. Fetch every feed in config.yaml in parallel and take each feed's
   newest unseen entry within `max_age_hours`, deduplicating by id and by link
   in config order. Add the entries that failed on earlier runs (table
   `failed_entries`, found again with the age cutoff off, up to
   `FeedMonitor.MAX_ATTEMPTS` attempts) and write the day's news briefing.
   Then link rather than narrate posts too mathematical to follow by ear, and
   replace excerpt-only feed bodies with the full post. An injected URL
   (`INJECT_URL`) replaces this phase with one page extracted from the web.
2. Make episodes, concurrently. The writer role summarises a post and the
   checker role reads the summary against its source, or the post is cleaned
   to be read in full. The normalizer role rewrites the script for speech,
   and text-to-speech (TTS) narrates it in chunks that ffmpeg joins into an
   MP3. Meanwhile the bullets role digests the script for the email. An entry
   that fails is retried once, serially, from the stage that failed; if it
   fails again, a feed entry is queued in `failed_entries`.
3. Publish. Record the episodes in data/posts.db, delete episodes older than
   `retention_days` with their audio, transcripts and source records, write
   output/, push an injection's outcome to ntfy.sh, and email the run report.

`FEEDCAST_PASS` splits a run into two publishes, so that a long reading cannot
delay the briefing and the summaries. `first` publishes the briefing and the
summaries and sends the email; posts read out in full
(`ContentProcessor.reads_verbatim`) are only cleaned and digested, listed in
the email with a link to their episode page, and parked in table
`deferred_entries`. `narrate` narrates the parked posts and publishes again,
emailing only `FEEDCAST_EMAIL_TO` and only on failure. Inject and reprocess
runs are always one pass.

The modules, roughly in the order a run uses them:

- config: the schema of config.yaml, and loading it.
- env: on/off switches read from the environment.
- monitor: feed fetching, and the SQLite database (data/posts.db) that holds the run state.
- lesswrong: a LessWrong or Alignment Forum post's markdown and posting date, over GraphQL.
- extractor: an article's text and metadata from any URL, for injected URLs.
- news: the daily news briefing, from the configured news sources.
- markets: prediction-market odds and big moves for the briefing.
- mathiness: whether a post is too mathematical to follow by ear.
- fulltext: a post's full text when its feed ships only an excerpt.
- html_text: plain text from HTML, and small tables as prose, with no model calls.
- processor: an entry's script, written by the writer role or cleaned to be read in full.
- verify: the fidelity check of a written script against its source, and its one revision.
- llm: the model roles, their fallbacks, and every model call.
- notices: what a run fell back on or skipped, for the email.
- normalizer: a script rewritten for speech, then respelled where the voice errs.
- chunking: cutting text at natural breaks to fit a length limit.
- audio: narration with DeepInfra's Chatterbox TTS in a cloned voice, joined into an MP3.
- digest: the email's two-level bullet digest of each episode.
- bundle: the per-episode record of what the writer saw and wrote, under data/sources/.
- feed: feed.xml, the site's index and episode pages, and the briefings' transcripts.
- market_charts: price charts of the markets the briefing's digest cites, for the email.
- run_report: the run report, assembled from what the run did and the rows it stored.
- email_report: the run report email.
- main: the entry point; runs the pipeline.
"""
