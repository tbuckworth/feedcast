"""Feedcast: RSS feeds and a daily news briefing, narrated as a podcast.

`python -m src.main` runs the pipeline; AGENTS.md describes a run's phases and
passes. The modules, roughly in the order a run uses them:

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
- email_report: the run report email.
- main: the entry point; runs the pipeline.
"""
