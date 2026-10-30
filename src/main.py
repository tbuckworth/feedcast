"""Main entry point for feedcast pipeline."""

import asyncio
import os
import socket
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

from .audio import AudioGenerator
from .bundle import write_bundle
from .config import CONFIG_PATH, ROOT, Config, FeedConfig, load_config
from .digest import safe_bullets
from .email_report import RunReport, send_report
from .env import env_flag
from .extractor import ExtractionError, url_to_feed_entry
from .feed import Episode, FeedGenerator
from .fulltext import enrich_entry
from .html_text import clean_html
from .lesswrong import posted_at
from . import notices
from .market_charts import charts_for_report
from .markets import MarketRules, MarketScout
from .mathiness import MathsVerdict, assess
from .monitor import (FeedEntry, FeedMonitor, briefing_id, entry_from_row, episode_id,
                      is_briefing)
from .news import NewsAggregator
from .normalizer import TextNormalizer
from .processor import ContentProcessor
from .run_report import (build_run_report, failure_report, preview_report, stored_verdict,
                         surfaced_date)

# feedparser.parse(url) fetches through urllib, which blocks forever on a
# stalled server, so a single unresponsive feed would hang the whole run until
# CI killed it. feedparser 6.x exposes no timeout argument, so bound it at the
# socket layer. Only affects blocking sockets; asyncio/httpx are unaffected.
socket.setdefaulttimeout(30)


@dataclass
class Attempt:
    """How far one entry got, so a retry resumes there instead of starting over.

    The stages are the writer's work (`process`), TTS normalisation
    (`normalize`), narration (`tts`) and the bullet digest (`digest`). A failure
    names its stage in the log and the email. A later attempt skips any stage
    that already produced text, and the normalised script is kept in the
    database so a retry on another day goes straight to narration (the
    summary, its fidelity check and the normalisation are the expensive part).
    """
    stage: str = "process"
    processed_text: str | None = None
    normalized_text: str | None = None
    number: int = 1  # attempt count across runs, for the report

    @classmethod
    def from_row(cls, row: dict, number: int) -> "Attempt":
        """Resume from the scripts a stored row kept, at the first stage with none.

        A failed_entries row keeps the normalised script; a deferred_entries
        row the written one too. Rows store '' for a script they do not have.
        """
        processed = row.get("processed_text") or None
        normalized = row.get("normalized_text") or None
        stage = "tts" if normalized else "normalize" if processed else "process"
        return cls(stage=stage, processed_text=processed, normalized_text=normalized,
                   number=number)


async def process_entry(
    entry: FeedEntry, mode: str, prompt: str,
    processor: ContentProcessor, audio_gen: AudioGenerator,
    normalizer: TextNormalizer,
    audio_dir: Path, http_client: httpx.AsyncClient,
    attempt: Attempt | None = None,
) -> tuple[FeedEntry, Path]:
    """Process one entry: content → audio. Runs concurrently with other entries."""
    attempt = attempt if attempt is not None else Attempt()
    print(f"\n  Processing: {entry.title}")

    if attempt.normalized_text is None and attempt.processed_text is None:
        attempt.stage = "process"
        attempt.processed_text = await processor.process(entry, mode, prompt)
        print(f"    Processed text: {len(attempt.processed_text)} chars")
    elif attempt.processed_text is not None:
        print(f"    Resuming with the script from an earlier attempt "
              f"({len(attempt.processed_text)} chars)")

    # Digest the script before normalisation, because bullets are read and
    # want "45%", not the "forty-five percent" a voice needs. It runs alongside
    # the audio, which takes minutes to the digest's seconds.
    # A retry that only has the normalised script digests that instead: spoken
    # numbers in the bullets beat no episode. A post the first pass deferred
    # arrives with its bullets already written (and already emailed).
    digest_task = asyncio.create_task(
        _same(entry.bullets) if entry.bullets else
        safe_bullets(attempt.processed_text or attempt.normalized_text or "",
                     is_briefing=is_briefing(entry.id),
                     label=entry.title,
                     sources=entry.sources)
    )

    # Everything from here to the finished MP3 sits inside the guard.
    # Normalisation raises loudly on a truncated completion, and an escape
    # there would leave the digest in flight into Phase 3 and the loop closing
    # on a pending task.
    try:
        if attempt.normalized_text is None:
            attempt.stage = "normalize"
            attempt.normalized_text = await normalizer.normalize_for_tts(
                attempt.processed_text, label=entry.title)
            print(f"    Normalized text: {len(attempt.normalized_text)} chars")
        else:
            print(f"    Resuming with the normalised script from an earlier attempt "
                  f"({len(attempt.normalized_text)} chars)")

        attempt.stage = "tts"
        audio_path = await audio_gen.generate_episode(
            attempt.normalized_text, audio_dir, episode_id(entry.id), entry.title, http_client,
        )
    except BaseException:
        digest_task.cancel()
        raise
    print(f"    Generated audio: {audio_path.name}")

    attempt.stage = "digest"
    entry.bullets = await digest_task
    print(f"    Digest: {len(entry.bullets)} bullets")
    return (entry, audio_path)


async def _same(value):
    return value


@dataclass
class Workers:
    """What Phase 2 runs each entry through: the writer, the normaliser and the narrator."""

    processor: ContentProcessor
    normalizer: TextNormalizer
    audio_gen: AudioGenerator

    @classmethod
    def from_config(cls, config: Config) -> "Workers":
        """As config.yaml sets them up, the narrator with the voice it names.

        Constructing the narrator demands a DeepInfra key and uploads the
        voice sample, so a run that makes no audio builds none of these.
        """
        return cls(
            processor=ContentProcessor(config.default_prompt, verify=config.fidelity_check,
                                       auto_verbatim_limit=config.auto_verbatim_limit),
            normalizer=TextNormalizer(respellings=config.pronunciations),
            audio_gen=AudioGenerator(voice_sample=config.tts.voice_path),
        )


async def _run_entries(
    items: list[tuple[FeedEntry, str, str]], attempts: dict[str, Attempt],
    workers: Workers, audio_dir: Path,
) -> list:
    """Run process_entry over `items` concurrently, then retry failures serially.

    Returns one result per item, in order: (entry, audio_path) or the
    exception. The second pass resumes each failure at the stage that failed
    and reuses the TTS chunks already on disk, on a fresh connection pool, so
    a transient failure, such as a few dropped DeepInfra connections, costs
    minutes here rather than a day.
    """
    # Configure connection limits to avoid ReadError issues with concurrent TTS requests
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

    async def run_all(batch, concurrently: bool) -> list:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0), limits=limits) as http_client:
            coros = [
                process_entry(e, m, p, workers.processor, workers.audio_gen,
                              workers.normalizer, audio_dir, http_client, attempts[e.id])
                for e, m, p in batch
            ]
            if concurrently:
                return await asyncio.gather(*coros, return_exceptions=True)
            out = []
            for coro in coros:
                try:
                    out.append(await coro)
                except Exception as exc:
                    out.append(exc)
            return out

    results = await run_all(items, concurrently=True)
    retry = [(item, r) for item, r in zip(items, results) if isinstance(r, BaseException)]
    if retry:
        print(f"\n  Second pass: retrying {len(retry)} failed "
              f"{'entry' if len(retry) == 1 else 'entries'} serially...")
        for (submitted, _m, _p), exc in retry:
            print(f"    {submitted.title}: failed at {attempts[submitted.id].stage}: "
                  f"{type(exc).__name__}: {exc}")
        second = await run_all([item for item, _ in retry], concurrently=False)
        second_by_id = {item[0].id: r for (item, _), r in zip(retry, second)}
        results = [second_by_id.get(e.id, r) for (e, _m, _p), r in zip(items, results)]
    return results


async def _prepare_deferred(
    items: list[tuple[FeedEntry, str, str]], attempts: dict[str, Attempt],
    processor: ContentProcessor,
) -> list:
    """Everything a verbatim post needs before narration, for the first email.

    Cleaning the post takes seconds and the bullets one model call, so both
    happen in the first pass: the email lists the post with its digest while
    the slow part, narration, waits for the second. Returns, per item, the
    Attempt with its script filled in, or the exception.
    """
    async def one(entry: FeedEntry, mode: str, prompt: str) -> Attempt:
        attempt = attempts[entry.id]
        if attempt.normalized_text is None and attempt.processed_text is None:
            attempt.stage = "process"
            attempt.processed_text = await processor.process(entry, mode, prompt)
        attempt.stage = "digest"
        entry.bullets = await safe_bullets(
            attempt.processed_text or attempt.normalized_text or "",
            is_briefing=False, label=entry.title)
        return attempt

    return await asyncio.gather(*[one(e, m, p) for e, m, p in items], return_exceptions=True)


async def _backfill_bullets(monitor: FeedMonitor, rows: list[dict]) -> list[tuple[str, str]]:
    """Digest rows that predate the bullets column, in parallel.

    Returns (title, why) for each row whose digest could not be made, for the
    email's failures.

    Digests the post's own text rather than the spoken script, because scripts
    are not kept for anything but the briefing. For a summarised post that
    means bullets drawn from the whole article instead of from its 450-word
    summary, which is if anything the better source. It does mean running
    the full-text recovery first, or a Zvi post would be digested from the
    three-percent podcast blurb.
    """
    # Skip rows with no audio: those are the maths-linked posts, and the email
    # renders them as a link and a score, with nowhere to put bullets.
    todo = [r for r in rows if r["audio_file"] and not (r.get("bullets") or "")]
    if not todo:
        return []
    print(f"  Backfilling digests for {len(todo)} entries...")

    async def one(row: dict) -> None:
        briefing = is_briefing(row["id"])
        if briefing:
            text = row["content"] or ""
        else:
            entry = entry_from_row(row)
            gain = await asyncio.to_thread(enrich_entry, entry)
            if gain.replaced:
                print(f"    Recovered full text for {entry.title} "
                      f"({gain.before:,} -> {gain.after:,})")
            text = clean_html(entry.content)
        bullets = await safe_bullets(text, is_briefing=briefing, label=row["title"])
        monitor.set_bullets(row["id"], bullets)
        print(f"    {len(bullets)} bullets: {row['title'][:56]}")

    results = await asyncio.gather(*[one(r) for r in todo], return_exceptions=True)
    failures = []
    for row, result in zip(todo, results):
        # safe_bullets catches its own API failures; anything arriving here is
        # something else (a malformed published date, or LessWrong down for
        # the full-text recovery) and would otherwise ship a bulletless
        # episode on a run reporting success.
        if isinstance(result, BaseException):
            why = f"digest backfill: {type(result).__name__}: {result}"
            print(f"    Backfill failed for {row['title'][:56]}: {why}")
            failures.append((row["title"], why))
    return failures


async def _resend_report(monitor: FeedMonitor, config, feed_gen: FeedGenerator,
                         audio_dir: Path) -> None:
    """Rebuild and re-send the most recent run's email. Publishes nothing.

    Exists because the mail credentials only live in CI, so re-sending after a
    template change means asking the pipeline to do it. Deliberately does not
    fetch, process, generate audio, write anything under output/ or run cleanup.
    """
    db_entries = monitor.get_processed_entries()
    if not db_entries:
        print("Nothing in the database to report on.")
        return

    latest = max(d["processed_at"][:10] for d in db_entries)
    todays = [d for d in db_entries if d["processed_at"][:10] == latest]
    print(f"Re-sending the report for {latest} ({len(todays)} entries)")

    failures = await _backfill_bullets(monitor, todays)
    db_entries = monitor.get_processed_entries()   # reread, now with bullets

    # A row with no audio is a post the maths filter linked instead of
    # narrating. Report the verdict that was recorded at the time, not a fresh
    # one: re-deriving it can disagree with the decision it is explaining, and
    # would need the GraphQL fetch again, which can fail.
    linked: list[tuple[FeedEntry, MathsVerdict]] = []
    for row in todays:
        if row["audio_file"]:
            continue
        linked.append((entry_from_row(row), stored_verdict(row)))

    episodes = feed_gen.load_episodes_from_db(db_entries, audio_dir)
    new_ids = {d["id"] for d in todays if d["audio_file"]}
    report = build_run_report(episodes, db_entries, new_ids, failures,
                              config.podcast.base_url, linked)
    _email(report)


@dataclass(frozen=True)
class RunOptions:
    """What this run was asked to do, read from the environment once.

    The workflow sets these from its inputs; unset, a run is the daily one
    in a single pass. The properties are the gates the stages go by.
    """

    reprocess_entry: str   # REPROCESS_ENTRY: a post's id or URL, to narrate again
    force_verbatim: bool   # FORCE_VERBATIM: read that post out in full
    inject_url: str        # INJECT_URL: a web page to narrate instead of the feeds
    inject_mode: str       # INJECT_MODE: auto, summarize or verbatim
    resend: bool           # RESEND_REPORT
    preview: bool          # PREVIEW_BRIEFING
    run_pass: str          # FEEDCAST_PASS: "all", "first" or "narrate" (_run_pass)
    email_always: bool     # FEEDCAST_EMAIL_ALWAYS
    ntfy_topic: str        # NTFY_TOPIC

    @classmethod
    def from_env(cls) -> "RunOptions":
        """Read the options. An unknown FEEDCAST_PASS raises (_run_pass)."""
        return cls(
            reprocess_entry=os.environ.get("REPROCESS_ENTRY", "").strip(),
            force_verbatim=env_flag("FORCE_VERBATIM"),
            inject_url=os.environ.get("INJECT_URL", "").strip(),
            inject_mode=os.environ.get("INJECT_MODE", "auto").strip().lower(),
            resend=env_flag("RESEND_REPORT"),
            preview=env_flag("PREVIEW_BRIEFING"),
            run_pass=_run_pass(),
            email_always=env_flag("FEEDCAST_EMAIL_ALWAYS"),
            ntfy_topic=os.environ.get("NTFY_TOPIC", "").strip(),
        )

    @property
    def asks_for_one_post(self) -> bool:
        """An inject or a reprocess: one episode, asked for by name."""
        return bool(self.inject_url or self.reprocess_entry)

    @property
    def filters_maths(self) -> bool:
        """Whether posts built on real mathematics are linked rather than narrated.

        Not for inject and reprocess, both explicit "I want this one"
        requests. Reprocess especially: it deletes the row first, so filtering
        a reprocessed post would re-insert it with a NULL audio_file and
        silently drop an already-published episode out of feed.xml,
        unrecoverably.
        """
        return not self.asks_for_one_post

    @property
    def recovers_full_text(self) -> bool:
        """Whether a feed's excerpt is swapped for the whole post (fulltext.py).

        Not for an injected URL, whose text was extracted from the page itself.
        A reprocess does, as it is usually someone asking for a bad episode to
        be done again.
        """
        return not self.inject_url

    @property
    def defers_full_readings(self) -> bool:
        """Whether posts read out in full wait for the narration pass.

        Only in the first pass of a split run. Inject and reprocess runs are
        one episode each and stay in a single pass.
        """
        return self.run_pass == "first" and not self.asks_for_one_post

    @property
    def pushes(self) -> bool:
        """Whether an injection's outcome is pushed to ntfy.sh."""
        return bool(self.inject_url and self.ntfy_topic)

    def forces_verbatim(self, entry: FeedEntry) -> bool:
        """Whether `entry` is the post a reprocess asked to have read out in full."""
        return (self.force_verbatim and bool(self.reprocess_entry)
                and self.reprocess_entry in (entry.id, entry.link))


@dataclass
class Run:
    """What the stages of one run share: what it was asked, its database, what it has so far."""

    options: RunOptions
    config: Config
    root: Path
    monitor: FeedMonitor
    # (entry, mode, prompt) for each entry this run narrates, in order.
    entries: list[tuple[FeedEntry, str, str]] = field(default_factory=list)
    # The same for the posts read out in full that wait for the narration pass.
    deferring: list[tuple[FeedEntry, str, str]] = field(default_factory=list)
    # How far each entry has got. One that failed on an earlier run resumes
    # part-way through.
    attempts: dict[str, Attempt] = field(default_factory=dict)
    briefing: FeedEntry | None = None
    # For the email.
    failures: list[tuple[str, str]] = field(default_factory=list)   # (title, why)
    dead_sources: list[str] = field(default_factory=list)
    maths_skipped: list[tuple[FeedEntry, MathsVerdict]] = field(default_factory=list)
    new_ids: set[str] = field(default_factory=set)

    @property
    def audio_dir(self) -> Path:
        return self.root / "data" / "audio"

    @property
    def sources_dir(self) -> Path:
        return self.root / "data" / "sources"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def feed_gen(self) -> FeedGenerator:
        return FeedGenerator(self.config.podcast, retention_days=self.config.retention_days)

    def has(self, entry_id: str) -> bool:
        """Whether this run already narrates the entry with this id."""
        return any(e.id == entry_id for e, _m, _p in self.entries)

    def add(self, entry: FeedEntry, feed: FeedConfig, mode: str) -> None:
        """Narrate a feed's entry this run, in `mode`, with the feed's prompt."""
        self.entries.append((entry, mode, feed.prompt or self.config.default_prompt))

    def can_retry(self, entry: FeedEntry) -> bool:
        """Whether a failed entry is queued for the next run.

        Only feed entries can be found again tomorrow. A briefing is
        regenerated daily anyway, and an injected URL has ntfy.
        """
        return (entry.feed_name in {fc.name for fc in self.config.feeds}
                and not is_briefing(entry.id))


async def async_main(config_path: Path | None = None) -> None:
    """Run the feedcast pipeline: one stage after another, sharing a Run."""
    options = RunOptions.from_env()
    _announce(options)
    run = _open_run(options, config_path or CONFIG_PATH)
    replaced = _set_aside_reprocessed(run) if options.reprocess_entry else None

    # Before the TTS setup: constructing AudioGenerator demands a DeepInfra key
    # and uploads the voice sample, and a resend makes no audio at all.
    if options.resend:
        await _resend_report(run.monitor, run.config, run.feed_gen, run.audio_dir)
        return
    if options.run_pass == "narrate":
        await _narrate_deferred(run.monitor, run.config, run.feed_gen, run.audio_dir,
                                run.output_dir)
        return
    if options.preview:
        await _preview_briefing(run.monitor, run.config)
        return
    workers = Workers.from_config(run.config)

    if options.inject_url:
        await _inject(run)
    else:
        fetched = await _fetch_new_entries(run)
        _take_newest(run, fetched)
        if options.reprocess_entry:
            await _find_reprocessed(run, replaced)
        await _requeue_failures(run)
        await _correct_publication_dates([e for e, _m, _p in run.entries])
        await _add_briefing(run)
        # The feeds that returned nothing, to whichever fetch above.
        run.dead_sources += run.monitor.dead_feeds
    if options.filters_maths:
        await _filter_maths(run)
    if options.recovers_full_text:
        await _recover_full_text(run)
    if options.defers_full_readings:
        _defer_full_readings(run, workers.processor)

    print(f"\n{len(run.entries)} entries to process")
    for e, _m, _p in run.entries + run.deferring:   # a fresh start, unless resumed
        run.attempts.setdefault(e.id, Attempt())
    # Cleaning and digesting the deferred posts takes seconds; it runs
    # alongside Phase 2 so they can be in the email with their bullets.
    preparing = asyncio.create_task(
        _prepare_deferred(run.deferring, run.attempts, workers.processor))
    await _narrate_entries(run, workers)
    _park_deferred(run, await preparing)

    _record_maths_skipped(run)
    _clean_up(run)
    episodes, rows, waiting = _publish_run(run)
    if options.pushes:
        await _push_outcome(run)
    _email_run(run, episodes, rows, waiting)
    print(f"\nPipeline complete.")


def _announce(options: RunOptions) -> None:
    """Start the log with what the run was asked to do."""
    if options.reprocess_entry:
        print(f"Reprocess requested for: {options.reprocess_entry}")
    if options.force_verbatim:
        if not options.reprocess_entry:
            print("Warning: FORCE_VERBATIM is set but no REPROCESS_ENTRY specified — flag will have no effect")
        else:
            print(f"Force verbatim enabled for: {options.reprocess_entry}")
    if options.inject_url:
        print(f"URL injection requested: {options.inject_url} (mode: {options.inject_mode})")


def _open_run(options: RunOptions, config_path: Path) -> Run:
    """Load the configuration and open the database."""
    print(f"Loading configuration from {config_path}")
    config = load_config(config_path)
    return Run(options=options, config=config, root=ROOT,
               monitor=FeedMonitor(ROOT / "data" / "posts.db"))


def _set_aside_reprocessed(run: Run) -> dict | None:
    """Delete the episode a reprocess names, by its id or its URL, so it is picked up again.

    Returns the row deleted, for _find_reprocessed to put back if the post
    cannot be found.
    """
    wanted = run.options.reprocess_entry
    row = run.monitor.get_entry(entry_id=wanted, link=wanted)
    if run.monitor.delete_entry(entry_id=wanted, link=wanted):
        print(f"  Deleted entry from database, will reprocess")
    else:
        print(f"  Entry not found in database (may be new)")
    return row


async def _inject(run: Run) -> None:
    """INJECT_URL: narrate one web page instead of the feeds.

    Re-injecting replaces the earlier episode. One stored from a feed has the
    feed's id and this URL as its link, so it is deleted by both.
    """
    url = run.options.inject_url
    print(f"\nInjecting URL (skipping RSS feeds)...")
    try:
        entry = await asyncio.to_thread(url_to_feed_entry, url)
    except ExtractionError as e:
        print(f"  Extraction failed: {e}")
        if run.options.pushes:
            await _send_ntfy(run.options.ntfy_topic, f"Failed to process: {url}\n{e}", "x")
        raise
    print(f"  Extracted: {entry.title} ({len(entry.content)} chars)")
    for row_id, title in run.monitor.delete_entry(entry_id=entry.id, link=url):
        print(f"  Deleted {row_id} ({title}) for re-injection")
    run.entries = [(entry, run.options.inject_mode, run.config.default_prompt)]


async def _fetch_new_entries(run: Run) -> list[tuple[FeedConfig, list[FeedEntry]]]:
    """Phase 1: every feed's new entries, fetched in parallel, in config order.

    A feed whose fetch raised returned nothing as surely as an empty feed,
    which the email lists, so it is listed too, with the error.
    """
    config = run.config
    print(f"\nPhase 1: Fetching {len(config.feeds)} feeds in parallel...")

    max_age = config.max_age_hours
    print(f"  Only entries published in the last {max_age:g}h are eligible"
          if max_age is not None else "  Age cutoff disabled — every unseen entry is eligible")

    for fc in config.feeds:
        print(f"  Fetching: {fc.name} ({fc.url})")
    fetched = []
    for fc, result in zip(config.feeds, await _fetch_feeds(config.feeds, run.monitor, max_age)):
        if isinstance(result, BaseException):
            print(f"  Warning: failed to fetch {fc.name}: {result!r}")
            run.dead_sources.append(f"{fc.name} ({type(result).__name__}: {result})")
            continue
        print(f"  {fc.name}: {len(result)} new entries")
        fetched.append((fc, result))
    return fetched


def _take_newest(run: Run, fetched: list[tuple[FeedConfig, list[FeedEntry]]]) -> None:
    """Narrate each feed's newest new entry, once however many feeds carry it.

    The others wait for a later run. `fetched` is in config order, where
    author feeds come before the aggregate ones, so a post two feeds carry
    keeps its author's attribution.
    """
    seen_ids: set[str] = set()
    seen_links: set[str] = set()
    for feed_config, entries in fetched:
        if not entries:
            continue
        entry = entries[-1]  # most recent only
        if len(entries) > 1:
            print(f"  {feed_config.name}: taking only the newest, {entry.title}; held back "
                  f"for a later run: " + "; ".join(e.title for e in entries[:-1]))
        if entry.id in seen_ids or (entry.link and entry.link in seen_links):
            print(f"  Skipping duplicate: {entry.title}")
            continue
        seen_ids.add(entry.id)
        if entry.link:
            seen_links.add(entry.link)
        mode = feed_config.mode
        if run.options.forces_verbatim(entry):
            print(f"    Overriding mode to verbatim (force_verbatim)")
            mode = "verbatim"
        run.add(entry, feed_config, mode)


async def _find_reprocessed(run: Run, replaced: dict | None) -> None:
    """Find the post a reprocess asked for, with the age cutoff off.

    The requested entry is usually older than the freshness window (that is
    why someone is asking for it again), so Phase 1 never sees it. Look for it
    once more and take only it; otherwise the window would turn a reprocess
    into a deletion. Not found, `replaced` (the episode _set_aside_reprocessed
    deleted) is put back.
    """
    wanted = run.options.reprocess_entry
    found = await _find_in_feeds(run.config, run.monitor, wanted)
    if isinstance(found, tuple):
        fc, e = found
        if not run.has(e.id):
            mode = "verbatim" if run.options.forces_verbatim(e) else fc.mode
            run.add(e, fc, mode)
            print(f"  Reprocessing: {e.title} ({fc.name}, mode {mode})")
        return
    missing = (f"a feed could not be read ({found}), so the post was not looked "
               f"for there" if isinstance(found, FetchFailed)
               else "not found in any feed")
    if replaced:
        run.monitor.restore_entry(replaced)
        print(f"  Requested entry {missing}; previous episode kept")
    else:
        print(f"  Requested entry {missing}")
    run.failures.append((wanted, f"{missing}; the existing episode was kept"))


async def _requeue_failures(run: Run) -> None:
    """Take back the entries that failed on an earlier run, to resume where they stopped.

    Their feed is fetched with the age cutoff off: a post that failed
    yesterday is outside the window by now, and that is exactly why it needs
    this path rather than Phase 1. Each gets MAX_ATTEMPTS mornings, then the
    email says so.
    """
    for row in run.monitor.pending_failures():
        if run.has(row["id"]):
            continue
        found = await _find_in_feeds(run.config, run.monitor, row["id"], row["link"],
                                     only_feed=row["feed_name"])
        if isinstance(found, FetchFailed):
            # Not knowing is not "gone": it stays queued for the next run.
            print(f"  Could not look for an earlier failure, keeping it queued: "
                  f"{row['title']} ({found})")
            continue
        if found is None:
            print(f"  Earlier failure is no longer in its feed, dropping: {row['title']}")
            run.monitor.clear_failure(row["id"])
            continue
        fc, e = found
        run.add(e, fc, fc.mode)
        attempt = run.attempts[e.id] = Attempt.from_row(row, number=row["attempts"] + 1)
        print(f"  Retrying from an earlier run: {e.title} "
              f"(attempt {attempt.number} of {run.monitor.MAX_ATTEMPTS}"
              + (", script kept — straight to narration)" if attempt.normalized_text
                 else ")"))


async def _add_briefing(run: Run) -> None:
    """Write today's news briefing, if configured, and narrate it first."""
    config = run.config
    if not (config.news_briefing and config.news_briefing.enabled):
        return
    recent_briefings = run.monitor.get_recent_briefings(5)
    aggregator = _make_aggregator(config, run.monitor, recent_briefings)
    # Idempotent per day: the briefing id is date-keyed, so once it is in
    # the database a second run today (a reprocess, a test run, the late
    # GitHub fire) must not pay for selection, fetches, writing and
    # checking again only to throw the result away.
    today_id = briefing_id(f"{datetime.now():%Y-%m-%d}")
    if run.monitor.is_processed(today_id):
        print(f"  {today_id} already exists; skipping briefing generation")
    else:
        run.briefing = await aggregator.generate_briefing()
        if run.briefing:
            run.entries.insert(0, (run.briefing, "verbatim", config.default_prompt))
    run.dead_sources += aggregator.dead_sources


async def _filter_maths(run: Run) -> None:
    """Set aside the posts built on real mathematics, to be linked rather than narrated."""
    if not (run.config.maths_filter.enabled and run.entries):
        return
    print(f"\nChecking {len(run.entries)} entries for maths density...")
    candidates = [
        (i, e) for i, (e, _m, _p) in enumerate(run.entries)
        if not is_briefing(e.id)
    ]
    verdicts = await asyncio.gather(
        *[asyncio.to_thread(assess, e.link, e.content,
                            run.config.maths_filter.threshold_per_1k)
          for _i, e in candidates],
        return_exceptions=True,
    )
    drop: set[int] = set()
    for (idx, entry), verdict in zip(candidates, verdicts):
        if isinstance(verdict, BaseException):
            # Keeping the post would score it on its RSS body, which has
            # its maths stripped. It fails, and the retry queue has it.
            _fail_before_narration(run, entry, "maths check", verdict)
            drop.add(idx)
            continue
        if verdict.is_heavy:
            print(f"  Too mathematical for audio ({verdict.score}/1k via "
                  f"{verdict.source}): {entry.title}")
            drop.add(idx)
            run.maths_skipped.append((entry, verdict))
    if drop:
        run.entries = [t for i, t in enumerate(run.entries) if i not in drop]


async def _recover_full_text(run: Run) -> None:
    """Swap each feed excerpt for the whole post, before anything reads it.

    Zvi's feed is a podcast feed whose body is a blurb plus a chapter list,
    three percent of the article, so the summariser would work from a table
    of contents. Runs after the maths filter so posts about to be dropped are
    not fetched twice.
    """
    enrichable = [e for e, _m, _p in run.entries if not is_briefing(e.id)]
    gains = await asyncio.gather(
        *[asyncio.to_thread(enrich_entry, e) for e in enrichable],
        return_exceptions=True,
    )
    unrecovered: set[str] = set()
    for entry, gain in zip(enrichable, gains):
        if isinstance(gain, BaseException):
            # The feed body may be an excerpt (Zvi's is three percent of
            # the post), so it is not narrated: the entry fails, and the
            # retry queue has it.
            _fail_before_narration(run, entry, "full text", gain)
            unrecovered.add(entry.id)
        elif gain.replaced:
            print(f"  Recovered full text: {entry.title} "
                  f"({gain.before:,} -> {gain.after:,} chars)")
        elif gain.is_failure:
            # LessWrong answered, and the post has no markdown (deleted, a
            # draft, or not a post): a permanent answer that a retry
            # cannot change, so the feed body is narrated. It may be an
            # excerpt, and silence is how a three-percent blurb ships as an
            # episode, so the email names it.
            note = (f"{entry.title}: LessWrong has no markdown for it, so it was "
                    f"narrated from the feed body ({gain.before:,} chars), which "
                    f"may be an excerpt")
            print(f"  WARNING: {note}")
            notices.add(note)
    run.entries = [t for t in run.entries if t[0].id not in unrecovered]


def _defer_full_readings(run: Run, processor: ContentProcessor) -> None:
    """Hold the posts read out in full back for the narration pass.

    The briefing and the summaries are narrated and published first; posts
    read out in full wait for the narration pass (FEEDCAST_PASS=narrate) and
    a second publish, so a long one cannot hold the rest back.
    """
    run.deferring = [t for t in run.entries if processor.reads_verbatim(t[0], t[1])]
    deferred_ids = {e.id for e, _m, _p in run.deferring}
    run.entries = [t for t in run.entries if t[0].id not in deferred_ids]
    if run.deferring:
        print("\nNarrating after the first publish: "
              + "; ".join(e.title for e, _m, _p in run.deferring))


async def _narrate_entries(run: Run, workers: Workers) -> None:
    """Phase 2 and 3: make this run's episodes in parallel, then record each outcome."""
    if not run.entries:
        print("No new entries to process.")
        return
    print(f"\nPhase 2: Processing {len(run.entries)} entries in parallel...")
    results = await _run_entries(run.entries, run.attempts, workers, run.audio_dir)

    print(f"\nPhase 3: Finalizing...")
    new_episodes = 0
    # gather() preserves input order, so zipping recovers which entry each
    # exception came from: the report needs to name what failed.
    for (submitted, _mode, _prompt), result in zip(run.entries, results):
        if isinstance(result, BaseException):
            _fail(run, submitted, run.attempts[submitted.id], result)
            continue
        _record_episode(run, *result)
        new_episodes += 1
    print(f"  {new_episodes} new episodes created")
    _report_unnormalized(workers.normalizer)


def _record_episode(run: Run, entry: FeedEntry, audio_path: Path) -> None:
    """Store a finished episode: its row, its writer's bundle, and the briefing's memory."""
    run.monitor.mark_processed(entry, audio_path.name, content=entry.content)
    run.monitor.clear_failure(entry.id)
    if entry.bundle:
        write_bundle(run.sources_dir, episode_id(entry.id), entry.bundle)
    run.new_ids.add(entry.id)
    # Store news briefing text for future dedup context
    if is_briefing(entry.id) and run.briefing:
        today = datetime.now().strftime("%Y-%m-%d")
        run.monitor.store_news_briefing(today, run.briefing.content)
        if run.briefing.markets:
            run.monitor.record_market_reports(run.briefing.markets["moves"])


def _park_deferred(run: Run, prepared: list) -> None:
    """Park the deferred posts for the narration pass, with what _prepare_deferred made.

    One that could not even be cleaned failed like any other entry and is
    queued the same way.
    """
    for (submitted, mode, _prompt), ready in zip(run.deferring, prepared):
        if isinstance(ready, BaseException):
            _fail(run, submitted, run.attempts[submitted.id], ready)
            continue
        run.monitor.defer_entry(submitted, mode, ready.processed_text,
                                ready.normalized_text, submitted.bullets)
        run.monitor.clear_failure(submitted.id)


def _record_maths_skipped(run: Run) -> None:
    """Record the maths-skipped posts with no audio file.

    This dedups them so they are not re-detected daily, and the feed
    generator already skips any entry without audio, so they never appear as
    a broken episode.
    """
    for entry, verdict in run.maths_skipped:
        run.monitor.mark_processed(
            entry, None, content=entry.content,
            maths={"score": verdict.score, "hits": verdict.hits,
                   "source": verdict.source})


def _clean_up(run: Run) -> None:
    """Forget old episodes with their files, old briefings and old failure records.

    Runs BEFORE the feed is generated, so the feed never references
    audio/transcripts that cleanup deletes in this same run (otherwise the
    deployed feed.xml advertises 404 enclosures).
    """
    config, monitor = run.config, run.monitor
    removed = monitor.cleanup_old_entries(days=config.retention_days, audio_dir=run.audio_dir,
                                          transcript_dir=_transcript_dir(run.output_dir),
                                          sources_dir=run.sources_dir)
    if removed:
        print(f"  Cleaned up {removed} old entries")
    removed_briefings = monitor.cleanup_old_briefings(days=7)
    if removed_briefings:
        print(f"  Cleaned up {removed_briefings} old news briefings")
    pruned = monitor.prune_failures(days=config.retention_days)
    if pruned:
        print(f"  Forgot {pruned} old failure records")


def _publish_run(run: Run) -> tuple[list[Episode], list[dict], list[dict]]:
    """Publish the site (_publish), and tell the workflow if the narration job has work."""
    print(f"\nGenerating podcast feed...")
    episodes, db_entries, waiting = _publish(run.monitor, run.feed_gen, run.audio_dir,
                                             run.output_dir)
    _gh_output(deferred=len(waiting))
    return episodes, db_entries, waiting


def _email_run(run: Run, episodes: list[Episode], db_entries: list[dict],
               waiting: list[dict]) -> None:
    """Email the run report, unless the run has nothing to tell.

    Off when FEEDCAST_EMAIL_TO is unset; a send that fails is recorded, and
    the workflow fails the run after publishing. FEEDCAST_EMAIL_ALWAYS sends
    it even on a run that produced nothing.
    """
    if not (run.new_ids or run.failures or run.maths_skipped or run.dead_sources
            or run.deferring or run.options.email_always):
        print("  Nothing new — email report skipped (set FEEDCAST_EMAIL_ALWAYS=true to send anyway)")
        return
    # Charts first: a chart that fails is a notice, and the report takes
    # the notices as they stand when it is built.
    briefing = run.briefing
    charts, images = (charts_for_report(briefing)
                      if briefing and briefing.id in run.new_ids else ([], {}))
    report = build_run_report(
        episodes, db_entries, run.new_ids, run.failures, run.config.podcast.base_url,
        run.maths_skipped, run.dead_sources, pending=waiting,
    )
    report.charts = charts
    _email(report, images=images)


async def _push_outcome(run: Run) -> None:
    """Push an injection's outcome to ntfy.sh: what was published, or why not.

    Before the email, so a push that fails is among the email's notices.
    """
    topic, url = run.options.ntfy_topic, run.options.inject_url
    made = [e for e, _m, _p in run.entries if e.id in run.new_ids]
    if made:
        await _send_ntfy(topic, f"New episode: {made[0].title}", "white_check_mark")
    else:
        await _send_ntfy(topic, f"Failed to process: {url}\n"
                         + "\n".join(why for _title, why in run.failures), "x")


def _fail(run: Run, entry: FeedEntry, attempt: Attempt, exc: BaseException) -> None:
    """Report an entry that failed this run, queued for the next if one can find it."""
    _report_entry_failure(entry, attempt, exc, run.monitor, run.failures,
                          queue=run.can_retry(entry))


def _fail_before_narration(run: Run, entry: FeedEntry, stage: str,
                           exc: BaseException) -> None:
    """Report an entry that failed at `stage`, before Phase 2 could start on it."""
    attempt = run.attempts.get(entry.id) or Attempt()
    attempt.stage = stage
    _fail(run, entry, attempt, exc)


async def _correct_publication_dates(entries: list[FeedEntry]) -> None:
    """Replace the feed's date with the real posting date, where they differ.

    LessWrong Curated dates an item by when it was curated. That stays the
    "is this new to us" date (`feed_date`), and LessWrong is asked when the
    post was actually written, so the email states a release date rather than
    a promotion date. Only LessWrong links can be resolved, and only a
    difference worth showing is applied (run_report.FEED_DATE_LAG): a silent
    no-op for every other feed.
    """
    for entry in entries:
        real = await posted_at(entry.link)
        if real is None or surfaced_date(entry.feed_date, real) is None:
            continue
        print(f"    {entry.title[:48]}: posted {real:%Y-%m-%d}, "
              f"in feed {entry.feed_date:%Y-%m-%d}")
        entry.published = real


def _make_aggregator(config: Config, monitor: FeedMonitor,
                     recent_briefings: list[dict]) -> NewsAggregator:
    """The briefing writer as configured, with the prediction-market scout if enabled."""
    nb, pm = config.news_briefing, config.prediction_markets
    scout = MarketScout(
        rules=MarketRules(move=pm.move, major_move=pm.major_move, max_moves=pm.max_moves),
        polymarket_tags=pm.polymarket_tags, kalshi_series=pm.kalshi_series,
        recently_reported=monitor.recent_market_reports(),
    ) if pm.enabled else None
    return NewsAggregator(
        sources=[s.model_dump() for s in nb.sources],
        prompt=nb.prompt,
        lookback_hours=nb.lookback_hours,
        recent_briefings=recent_briefings,
        full_text_stories=nb.full_text_stories,
        max_article_chars=nb.max_article_chars,
        author=config.podcast.author,
        verify=config.fidelity_check,
        markets=scout,
    )


async def _preview_briefing(monitor: FeedMonitor, config: Config) -> None:
    """PREVIEW_BRIEFING: write a fresh briefing and email it. Publishes nothing.

    The briefing is made once a day, so after the morning run there is no other
    way to see a change to it before tomorrow. This writes one from the news of
    the last day, prediction markets and fidelity check included, and emails
    it as the daily email would show it, charts and all. The workflow marks it
    a dev run, so it goes to FEEDCAST_EMAIL_TO only. Nothing is narrated, and
    nothing is written to the database, the feed or the site.
    """
    if not (config.news_briefing and config.news_briefing.enabled):
        print("Preview: the news briefing is disabled in config.yaml")
        return
    aggregator = _make_aggregator(config, monitor, monitor.get_recent_briefings(5))
    entry = await aggregator.generate_briefing()
    if not entry:
        print("Preview: no recent articles, no briefing")
        return
    entry.bullets = await safe_bullets(entry.content, is_briefing=True, label=entry.title,
                                       sources=entry.sources)
    # Charts first: a chart that fails is a notice, and the report takes
    # the notices as they stand when it is built.
    charts, images = charts_for_report(entry)
    _email(preview_report(entry, config.podcast.base_url, charts),
           subject_tag="[Preview]", images=images)


def _run_pass() -> str:
    """FEEDCAST_PASS: which half of a split run this process is.

    "first" fetches, writes and narrates everything except posts read out in
    full, publishes, and sends the email; "narrate" narrates those posts and
    publishes again. Unset (local runs, tests) does everything in one pass.
    Any other value is refused rather than read as one pass: a typo in the
    workflow would otherwise narrate every post in the first job.
    """
    value = os.environ.get("FEEDCAST_PASS", "").strip().lower()
    if not value:
        return "all"
    if value not in ("first", "narrate"):
        raise ValueError(f"FEEDCAST_PASS={value!r}: expected 'first' or 'narrate', "
                         f"or unset for one pass")
    return value


def _gh_output(**values) -> None:
    """Hand values to later workflow steps. A no-op outside GitHub Actions."""
    path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.writelines(f"{key}={value}\n" for key, value in values.items())


def _gh_warning(title: str, message: str) -> None:
    """Annotate the run's summary page with a warning. A no-op outside GitHub Actions."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning title={title}::{message}")


def _email(report: RunReport, **kwargs) -> None:
    """Send the report, and record a send that failed for the workflow.

    Most failures are only reported in this email, so one that does not go
    out must not leave the run green. The run still publishes: the workflow's
    last step reads `report_failed` and fails the job after the commit.
    """
    if send_report(report, **kwargs) is False:
        _gh_output(report_failed="true")


async def _narrate_deferred(monitor: FeedMonitor, config: Config, feed_gen: FeedGenerator,
                            audio_dir: Path, output_dir: Path) -> None:
    """FEEDCAST_PASS=narrate: narrate the posts the first pass deferred, publish again.

    The day's email has already gone out with these posts listed, so this pass
    mails only on failure, and only the operator. A post that fails stays
    parked with its script and is retried by the next run's narration pass,
    up to MAX_ATTEMPTS counted from the first try.
    """
    if not monitor.deferred_entries():
        print("Nothing waiting to be narrated.")
        return
    monitor.start_narration()
    failures: list[tuple[str, str]] = []
    todo: list[tuple[dict, FeedEntry]] = []
    for row in monitor.deferred_entries():
        entry = row["entry"]
        if row["attempts"] > monitor.MAX_ATTEMPTS:
            # Counted up front, so this is a post whose last pass was cut off.
            monitor.drop_deferred(entry.id)
            reason = row["last_error"] or "the run was cut off"
            why = f"narration: gave up after {monitor.MAX_ATTEMPTS} attempts ({reason})"
            print(f"  Giving up on {entry.title}: {why}")
            failures.append((entry.title, why))
            _gh_warning("Feedcast entry failed", f"{entry.title} — {why}")
            continue
        entry.bullets = row["bullets"]
        todo.append((row, entry))

    narrated = 0
    if todo:
        print(f"\nNarration pass: {len(todo)} "
              f"{'post' if len(todo) == 1 else 'posts'} read out in full")
        attempts = {entry.id: Attempt.from_row(row, number=row["attempts"])
                    for row, entry in todo}
        items = [(entry, row["mode"], config.default_prompt) for row, entry in todo]
        workers = Workers.from_config(config)
        results = await _run_entries(items, attempts, workers, audio_dir)
        for (entry, _mode, _prompt), result in zip(items, results):
            attempt = attempts[entry.id]
            if isinstance(result, BaseException):
                monitor.note_deferred_failure(
                    entry.id, f"{attempt.stage}: {type(result).__name__}: {result}",
                    attempt.normalized_text)
                if attempt.number >= monitor.MAX_ATTEMPTS:
                    monitor.drop_deferred(entry.id)
                _report_entry_failure(entry, attempt, result, monitor, failures,
                                      queue=False, note=_attempt_note(attempt.number))
                continue
            entry, audio_path = result
            monitor.mark_processed(entry, audio_path.name, content=entry.content)
            monitor.drop_deferred(entry.id)
            monitor.clear_failure(entry.id)
            narrated += 1
        print(f"  {narrated} narrated")
        _report_unnormalized(workers.normalizer)

    episodes, _rows, _waiting = _publish(monitor, feed_gen, audio_dir, output_dir)
    if failures:
        _email(failure_report(failures, config.podcast.base_url, len(episodes)),
               operator_only=True)


@dataclass
class FetchFailed:
    """_find_in_feeds could not read a feed it searched, so "not found" is not known."""

    feeds: list[str]   # "<feed>: <what went wrong>"

    def __str__(self) -> str:
        return "; ".join(self.feeds)


async def _find_in_feeds(
    config: Config, monitor: FeedMonitor, *keys: str, only_feed: str | None = None,
) -> tuple[FeedConfig, FeedEntry] | FetchFailed | None:
    """Find an entry by id or link across the feeds, with the age cutoff off.

    Shared by reprocessing and the failed-entry queue: both want a post the
    normal windowed fetch has already stopped seeing. None means every feed
    searched was read and none has the entry. FetchFailed means it was not
    found but a feed could not be read (its fetch raised, or it returned
    nothing), so it may be there: the queue keeps a failed entry rather than
    forgetting it for good, and a reprocess says why it found nothing.
    """
    feeds = [fc for fc in config.feeds if only_feed is None or fc.name == only_feed]
    feeds = feeds or config.feeds

    fetched = await _fetch_feeds(feeds, monitor, max_age_hours=None)
    unread: list[str] = []
    for fc, result in zip(feeds, fetched):
        if isinstance(result, BaseException):
            unread.append(f"{fc.name}: {type(result).__name__}: {result}")
            print(f"  Could not read {fc.name} to look for {keys[0]}: {unread[-1]}")
            continue
        for e in result:
            if e.id in keys or (e.link and e.link in keys):
                return (fc, e)
        if fc.name in monitor.dead_feeds:   # warn_if_dead has said so in the log
            unread.append(f"{fc.name}: returned no entries")
    return FetchFailed(unread) if unread else None


async def _fetch_feeds(feeds: list[FeedConfig], monitor: FeedMonitor,
                       max_age_hours: float | None) -> list[list[FeedEntry] | BaseException]:
    """Fetch the feeds in parallel: per feed, in order, its new entries or what its fetch raised.

    The exception is returned, not raised: one unreachable or slow feed must
    not abort the run, and feedparser raises (rather than setting bozo) on a
    socket timeout. `max_age_hours` is FeedMonitor.fetch_feed's window.
    """
    return await asyncio.gather(
        *[asyncio.to_thread(monitor.fetch_feed, fc.url, fc.name, fc.skip_patterns,
                            max_age_hours=max_age_hours) for fc in feeds],
        return_exceptions=True,
    )


def _transcript_dir(output_dir: Path) -> Path:
    """Where the briefings' transcripts are published, and deleted from by cleanup."""
    return output_dir / "transcripts"


def _publish(monitor: FeedMonitor, feed_gen: FeedGenerator, audio_dir: Path,
             output_dir: Path) -> tuple[list[Episode], list[dict], list[dict]]:
    """Write the site from the database, as both passes of a split run do.

    feed.xml, the index, a page per episode and per post still waiting to be
    narrated, and the briefings' transcripts. Returns the episodes, the
    processed_posts rows they were read from, and the waiting posts
    (FeedMonitor.deferred_entries()), for the email.
    """
    db_entries = monitor.get_processed_entries()
    episodes = feed_gen.load_episodes_from_db(db_entries, audio_dir)
    waiting = monitor.deferred_entries()
    feed_path = output_dir / "feed.xml"
    feed_gen.generate(episodes, feed_path)
    feed_gen.write_index(episodes, output_dir / "index.html")
    feed_gen.write_episode_pages(episodes, waiting, output_dir / "episodes")
    feed_gen.write_transcripts(episodes, db_entries, _transcript_dir(output_dir))
    print(f"  Generated feed with {len(episodes)} episodes: {feed_path}")
    return episodes, db_entries, waiting


def _report_entry_failure(
    entry: FeedEntry, attempt: Attempt, exc: BaseException,
    monitor: FeedMonitor, failures: list[tuple[str, str]], *, queue: bool,
    note: str = "",
) -> None:
    """Log a failed entry with its stage and traceback, queue it, tell the email.

    The stage and the traceback go in the log, and the stage and the attempt
    count in the email, so a bare exception such as `TypeError: 'NoneType'
    object is not subscriptable` can be placed.
    `note` carries the attempt count for a caller that keeps its own (the
    narration pass, whose posts wait in deferred_entries rather than here).
    """
    summary = f"{attempt.stage}: {type(exc).__name__}: {exc}"
    print(f"  Error processing {entry.title} at {summary}")
    print("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip())
    if queue:
        note = _attempt_note(monitor.record_failure(entry, summary, attempt.normalized_text))
    failures.append((entry.title, summary + note))
    # Surfaces on the run's summary page, so a green run that lost an
    # episode is not green at a glance.
    _gh_warning("Feedcast entry failed", f"{entry.title} — {summary}{note}")


def _attempt_note(n: int) -> str:
    """How the email and the log end the failure of attempt `n`: retried, or given up."""
    outcome = "will retry next run" if n < FeedMonitor.MAX_ATTEMPTS else "giving up"
    return f" — attempt {n} of {FeedMonitor.MAX_ATTEMPTS}, {outcome}"


def _report_unnormalized(normalizer: TextNormalizer) -> None:
    """Name each episode with passages narrated as written, in both passes.

    The log, the run's summary page and the email's notices each get a line:
    a passage every model refused is read with "45%" as "forty-five percent
    sign" at best, so someone should know which episode to listen to.
    """
    for title, chars in normalizer.unnormalized.items():
        msg = (f"{title}: {chars:,} chars narrated as written because every "
               f"normaliser model refused them")
        print(f"  WARNING: {msg}")
        notices.add(msg)
        _gh_warning("Feedcast normaliser", msg)


async def _send_ntfy(topic: str, message: str, tags: str) -> None:
    """Push an injection's outcome to ntfy.sh. A push that fails or is refused is a notice."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://ntfy.sh/{topic}",
                content=message,
                headers={"Title": "Feedcast", "Tags": tags},
            )
            response.raise_for_status()
        return
    except httpx.HTTPStatusError as e:
        # Only the status: the error's text holds the URL, and the URL the
        # topic, which is a secret and must not reach the email or the log.
        why = f"HTTPStatusError: HTTP {e.response.status_code}"
    except Exception as e:
        # A transport error's text can hold the URL too.
        why = f"{type(e).__name__}: {str(e).replace(topic, '<topic>')}"
    # A lost push does not fail the run. The push only repeats an outcome the
    # run has already reached (an episode made, or a failure the email or the
    # failed job reports), and failing over it would read as the episode
    # failing. It goes to the email's notices instead, so it is still seen.
    note = f"ntfy notification failed: {why}"
    print(f"  {note}")
    notices.add(note)


def main(config_path: Path | None = None) -> None:
    """Run the feedcast pipeline."""
    asyncio.run(async_main(config_path))


if __name__ == "__main__":
    main()
