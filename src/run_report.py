"""The run's email report, assembled from what the run did and the rows it stored.

email_report.py renders and sends a RunReport; this builds one. The daily
report comes from the processed_posts rows the feed was published from
(build_run_report), so the email says what the listener gets; the preview and
the narration pass's failure email from what those runs made.
"""

from datetime import datetime, timedelta

from . import notices
from .email_report import ChartNote, LinkedPost, ReportEpisode, RunReport
from .feed import Episode, audio_url, episode_page_url, feed_url
from .mathiness import MathsVerdict
from .monitor import FeedEntry, is_briefing, stored_author, stored_json

# How far a post's feed date must be from its posting date before the email
# gives both: an hour's lag between posting and curation is noise.
FEED_DATE_LAG = timedelta(days=1)


def surfaced_date(feed_date: datetime | None, published: datetime | None) -> datetime | None:
    """When the feed surfaced a post, if that is not when it was written.

    None without a feed date, or with one within FEED_DATE_LAG of `published`.
    """
    if feed_date is None:
        return None
    if published and abs(feed_date - published) < FEED_DATE_LAG:
        return None
    return feed_date


def stored_feed_date(row: dict) -> datetime | None:
    """The feed date a row stores; None for rows from before the column.

    The pipeline writes a full date or nothing, so anything else is a corrupt
    row and raises.
    """
    raw = (row.get("feed_date") or "").strip()
    if not raw:
        return None
    return datetime.fromisoformat(raw)


def json_dict(row: dict, column: str) -> dict | None:
    """A JSON object stored in `column`; None when the row has none. Corrupt JSON raises."""
    return stored_json(row, column, dict)


def bullets_of(row: dict) -> list:
    """Read a stored digest. Rows written before the column existed have ''.

    Bullets are strings, or {"text", "url"} once they cite a source; rows
    written before that keep the old shape and render without a link.
    Corrupt JSON raises, naming the row.
    """
    parsed = stored_json(row, "bullets", list) or []
    return [b for b in parsed
            if isinstance(b, str) or (isinstance(b, dict) and b.get("text"))]


def stored_verdict(row: dict) -> MathsVerdict:
    """The maths verdict recorded when the post was linked.

    Rows written before the column existed have nothing stored. Those report a
    zero score, which the email renders as "linked, not narrated" with no
    number rather than an invented figure.
    Corrupt JSON raises, naming the row (monitor.stored_json).
    """
    data = stored_json(row, "maths", dict)
    if data is None:
        return MathsVerdict(is_heavy=True, score=0.0, hits=0, source="unrecorded")
    return MathsVerdict(is_heavy=True, score=float(data.get("score") or 0.0),
                        hits=int(data.get("hits") or 0),
                        source=str(data.get("source") or "unrecorded"))


def build_run_report(
    episodes: list[Episode], db_entries: list[dict], new_entry_ids: set[str],
    failures: list[tuple[str, str]], base_url: str,
    maths_skipped: list[tuple[FeedEntry, MathsVerdict]] | None = None,
    dead_sources: list[str] | None = None,
    pending: list[dict] | None = None,
) -> RunReport:
    """Assemble the emailed report from this run's episodes and the feed.

    `pending` is FeedMonitor.deferred_entries(): posts read out in full that
    the narration pass has yet to publish. They are listed with their bullets
    and a link to the episode's page, which plays the audio once it exists.
    """
    db_by_id = {d["id"]: d for d in db_entries}
    cutoff = datetime.now() - timedelta(days=7)

    def to_report(ep: Episode) -> ReportEpisode:
        row = db_by_id[ep.id]     # the episodes were read from these rows
        briefing = is_briefing(ep.id)
        return ReportEpisode(
            title=ep.title,
            author="" if briefing else stored_author(row),
            feed_name=row["feed_name"],
            link=ep.link or "",
            audio_url=audio_url(base_url, ep.audio_file),
            duration_seconds=ep.duration_seconds,
            is_briefing=briefing,
            briefing_text=(row.get("content") or "") if briefing else "",
            bullets=bullets_of(row),
            published=ep.published,
            surfaced=surfaced_date(stored_feed_date(row), ep.published),
            fidelity=json_dict(row, "fidelity"),
            writer=json_dict(row, "writer"),
        )

    def waiting(row: dict) -> ReportEpisode:
        e: FeedEntry = row["entry"]
        return ReportEpisode(
            title=e.title, author=e.author or e.feed_name, feed_name=e.feed_name,
            link=e.link or "", audio_url=episode_page_url(base_url, e.id),
            duration_seconds=0, bullets=row.get("bullets") or [], published=e.published,
            surfaced=surfaced_date(e.feed_date, e.published), pending=True,
        )

    ordered = sorted(episodes, key=lambda e: e.published, reverse=True)
    pending_rows = sorted(pending or [], key=lambda r: r["entry"].published, reverse=True)
    return RunReport(
        episodes=[to_report(e) for e in ordered if e.id in new_entry_ids]
                 + [waiting(r) for r in pending_rows],
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
        dead_sources=sorted(set(dead_sources or [])),
        notices=notices.report(),
        feed_url=feed_url(base_url),
        site_url=base_url,
        total_in_feed=len(episodes),
    )


def preview_report(entry: FeedEntry, base_url: str, charts: list[ChartNote]) -> RunReport:
    """PREVIEW_BRIEFING's email: a briefing nobody has published, with its charts.

    The digest as the daily email shows it, then the whole script, which is
    where the market lines actually are.
    """
    def item(**kw) -> ReportEpisode:
        return ReportEpisode(author="", feed_name=entry.feed_name, link="", audio_url="",
                             duration_seconds=0, is_briefing=True, published=entry.published,
                             **kw)

    return RunReport(
        episodes=[item(title=f"Preview: {entry.title}", bullets=entry.bullets,
                       fidelity=entry.fidelity, writer=entry.writer),
                  item(title="Full script", briefing_text=entry.content)],
        notices=notices.report(), feed_url=feed_url(base_url), site_url=base_url,
        charts=charts,
    )


def failure_report(failures: list[tuple[str, str]], base_url: str,
                   total_in_feed: int) -> RunReport:
    """A report of what failed and nothing else, with the feed's size.

    The narration pass sends one: the day's email has already listed its posts.
    """
    return RunReport(
        failures=failures, notices=notices.report(),
        feed_url=feed_url(base_url), site_url=base_url,
        total_in_feed=total_in_feed)
