"""HTML run report emailed when the pipeline finishes.

Configured entirely through environment variables so the recipient address and
credentials live in GitHub secrets rather than in the repo. If the required
ones are absent the report is skipped with a log line — a missing mailbox must
never fail a pipeline run that otherwise succeeded.
"""

import os
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from html import escape

# Email clients are a hostile rendering target: no flexbox, no grid, no
# external stylesheets, and <style> blocks are stripped by several of them.
# Everything below is table layout with inline styles for that reason.
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
INK = "#1a1a1a"
MUTED = "#6b6b6b"
RULE = "#e3e3e3"
ACCENT = "#1f5f8b"
# A backup model wrote the script: noticeable on a second look, not an alarm.
BACKUP = "#9a5b00"

DEFAULT_PORT = 587

from .env import env_flag
from .llm import model_name
from .verify import fidelity_summary, material_flags


@dataclass
class ReportEpisode:
    """One episode to describe in the report."""

    title: str
    author: str
    feed_name: str
    link: str
    audio_url: str
    duration_seconds: int
    is_briefing: bool = False
    briefing_text: str = ""
    # Plain strings, or {"text", "url"} where the bullet names its source.
    bullets: list = field(default_factory=list)
    # When the source material was published — not when we narrated it. The
    # two diverge whenever a run is late or a post is picked up a day on.
    published: datetime | None = None
    # When the feed surfaced it, if that is materially later than publication:
    # a LessWrong curation can trail the post by weeks, and without this the
    # email looks like it dug up something from July for no reason.
    surfaced: datetime | None = None
    # Result of the second-model source check, when one ran.
    fidelity: dict | None = None
    # Read out in full and still being narrated when the email went out:
    # `audio_url` is then the episode's page, which plays it once it is ready.
    pending: bool = False
    # Which model wrote the script (llm.Completion.credit()); None when no
    # model did (verbatim posts) or the row predates the record.
    writer: dict | None = None


@dataclass
class ChartNote:
    """A prediction-market chart in the daily email, shown under its bullet."""

    cid: str            # Content-ID of the attached PNG
    title: str          # the market's question
    platform: str
    url: str
    caption: str        # "55% a week before the story, 3% now · $1.2M traded"
    anchor: str = ""    # bullet or sub-bullet URL to sit under; unplaced charts get their own section


@dataclass
class LinkedPost:
    """A post deliberately not narrated — too mathematical to follow by ear."""

    title: str
    author: str
    feed_name: str
    link: str
    maths_score: float = 0.0
    source: str = ""


@dataclass
class RunReport:
    """Everything the email needs about a single pipeline run."""

    episodes: list[ReportEpisode] = field(default_factory=list)
    recent: list[ReportEpisode] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    linked: list[LinkedPost] = field(default_factory=list)
    dead_sources: list[str] = field(default_factory=list)
    # Fallbacks and skips this run (notices.report(): "digest: served by ...
    # after ...", a busy TTS model, skipped prediction markets): worth a line,
    # because a backup that quietly serves for weeks is a primary that has
    # quietly died.
    notices: list[str] = field(default_factory=list)
    feed_url: str = ""
    site_url: str = ""
    total_in_feed: int = 0
    # The briefing's prediction-market charts (market_charts.charts_for_report).
    charts: list[ChartNote] = field(default_factory=list)


def format_duration(seconds: int) -> str:
    """Render a duration as '4 min 01 sec', or '' when unknown."""
    if not seconds:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} hr {minutes:02d} min"
    return f"{minutes} min {secs:02d} sec"


def format_published(when: datetime | None) -> str:
    """Render a source publication date, or '' when unknown."""
    return when.strftime("%d %b %Y") if when else ""


def bullet_parts(b) -> tuple[str, str]:
    """Normalise a stored bullet to (text, url). Old rows are bare strings."""
    if isinstance(b, dict):
        return str(b.get("text", "")), str(b.get("url", ""))
    return str(b), ""


def bullet_urls(b) -> list[str]:
    """Every link a top-level bullet carries: its own, then its sub-bullets'."""
    subs = (b.get("sub") or []) if isinstance(b, dict) else []
    return [u for u in [bullet_parts(b)[1], *(bullet_parts(sb)[1] for sb in subs)] if u]


def writer_line(writer: dict | None) -> tuple[str, bool]:
    """('Written by Claude Opus 5.5', False), or the backup that stood in, flagged.

    ('', False) when nothing is recorded, so old rows and verbatim posts
    simply have no line.
    """
    if not writer or not writer.get("model"):
        return "", False
    line = f"Written by {model_name(writer['model'])}"
    if not writer.get("backup"):
        return line, False
    primary = writer.get("primary")
    return line + (f" (backup: {model_name(primary)} was unavailable)" if primary
                   else " (backup model)"), True


def byline(author: str, feed_name: str) -> list[str]:
    """Who wrote it, then the feed, unless the feed is named after them.

    The per-author feeds are named after the author, so without this every one
    of those episodes reads "Scott Alexander / Scott Alexander".
    """
    return [b for b in (author, feed_name if feed_name != author else "") if b]


def _meta_bits(ep: "ReportEpisode") -> list[str]:
    """The line under an episode's title: byline, publication date, duration."""
    bits = byline(ep.author, ep.feed_name)
    # Before the duration: this answers "is this actually new?", which is the
    # first thing you want to know about an item in a daily email.
    bits.append(format_published(ep.published))
    if ep.surfaced:
        bits.append(f"in feed {format_published(ep.surfaced)}")
    bits.append("narrating now, in your feed shortly" if ep.pending
                else format_duration(ep.duration_seconds))
    return [b for b in bits if b]


def _btn(url: str, label: str) -> str:
    if not url:
        return ""
    return (
        f'<a href="{escape(url, quote=True)}" style="display:inline-block;'
        f"padding:7px 14px;margin:0 8px 0 0;background:{ACCENT};color:#ffffff;"
        f'text-decoration:none;border-radius:4px;font-size:13px;">{escape(label)}</a>'
    )


_STOP = {"that", "this", "with", "from", "have", "were", "been", "their", "which",
         "about", "into", "than", "then", "they", "them", "what", "when", "while",
         "would", "could", "should", "also", "more", "most", "over", "under"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 4 and w not in _STOP}


def _leaves(bullets: list):
    """Every bullet and sub-bullet, as (text, is_sub)."""
    for b in bullets:
        text, _ = bullet_parts(b)
        yield text, False
        if isinstance(b, dict):
            for sb in b.get("sub", []) or []:
                yield bullet_parts(sb)[0], True


def checker_notes(fid: dict | None) -> list[dict]:
    """The checker's complaints worth showing: what is still wrong after revision,
    or what was flagged when nothing was revised."""
    if not fid:
        return []
    if fid.get("status") == "revised":
        return list(fid.get("remaining") or [])
    if fid.get("status") == "flagged":
        return material_flags(fid.get("flags", []))
    return []


def checker_name(fid: dict | None) -> str:
    """The model that read an episode's script against its source, as people say it.

    'the checker' on rows from before the model was recorded (2026-10-30).
    """
    model = ((fid or {}).get("checker") or {}).get("model")
    return model_name(model) if model else "the checker"


def flag_marks(bullets: list, notes: list[dict]) -> dict[str, int]:
    """bullet text -> note number, for the bullet each complaint most resembles.

    The bullets are a rewrite of the script, not a quotation of it, so the
    match is by shared content words with the checker's `script_quote`. A
    weak match marks nothing rather than the wrong bullet.
    """
    marks: dict[str, int] = {}
    leaves = [t for t, _ in _leaves(bullets)]
    for i, note in enumerate(notes, 1):
        target = _words(note.get("script_quote", ""))
        if not target:
            continue
        best, best_score = "", 0.0
        for text in leaves:
            shared = len(target & _words(text))
            score = shared / len(target)
            if shared >= 3 and score > best_score:
                best, best_score = text, score
        if best and best_score >= 0.3 and best not in marks:
            marks[best] = i
    return marks


FLAG_BG = "#fff3c4"


def _bullet_html(b, marks: dict[str, int]) -> str:
    """One bullet, with a 'Source' link when it names the article it used.

    A bullet may carry `sub`, a list of detail bullets rendered as a nested
    list. A bullet that matches one of the checker's complaints is tinted and
    numbered to it.
    """
    text, url = bullet_parts(b)
    html = escape(text)
    if url:
        html += (f' <a href="{escape(url, quote=True)}" style="color:{ACCENT};'
                 f'text-decoration:none;white-space:nowrap;">Source&nbsp;&rarr;</a>')
    n = marks.get(text)
    if n:
        html = (f'<span style="background:{FLAG_BG};">{html}</span>'
                f'<sup style="color:#a33;font-size:10px;"> [{n}]</sup>')
    subs = b.get("sub") if isinstance(b, dict) else None
    if subs:
        items = "".join(
            f'<li style="margin:4px 0 0 0;font-size:13px;line-height:1.45;color:{INK};">'
            f"{_bullet_html(sb, marks)}</li>" for sb in subs)
        html += f'<ul style="margin:2px 0 6px 0;padding-left:18px;">{items}</ul>'
    return html


def _note_li(title: str, n: dict) -> str:
    """One of the checker's complaints, in the numbered list at the foot of the email."""
    return (f'<li style="margin:0 0 9px 0;">'
            f'<span style="color:{MUTED};">{escape(title)}</span> &middot; '
            f'<span style="color:#a33;">[{escape(str(n.get("severity", "")))}, '
            f'{escape(str(n.get("verdict", "")))}]</span> '
            f'{escape(str(n.get("explanation", "")))}<br>'
            f'<span style="color:{MUTED};">Script:</span> &ldquo;{escape(str(n.get("script_quote", "")))}&rdquo;<br>'
            f'<span style="color:{MUTED};">Source:</span> &ldquo;{escape(str(n.get("source_quote", "")))}&rdquo;</li>')


def number_notes(episodes: list) -> tuple[dict[int, dict[str, int]], list[tuple[str, dict]]]:
    """Number every checker complaint across the report, in episode order.

    Returns (marks per episode index, [(episode title, note), ...]) so the
    bullets can carry [n] markers that point at one list at the foot of the
    email rather than a box under each episode.
    """
    marks: dict[int, dict[str, int]] = {}
    ordered: list[tuple[str, dict]] = []
    for i, ep in enumerate(episodes):
        notes = checker_notes(ep.fidelity)
        if not notes:
            continue
        offset = len(ordered)
        local = flag_marks(ep.bullets, notes) if ep.bullets else {}
        marks[i] = {text: n + offset for text, n in local.items()}
        ordered += [(ep.title, n) for n in notes]
    return marks, ordered


def _chart_html(c: ChartNote) -> str:
    return (f'<div style="margin:6px 0 12px 0;padding:8px 10px;border:1px solid {RULE};'
            f'border-radius:4px;background:#fafafa;">'
            f'<div style="font-size:12px;color:{INK};margin-bottom:4px;">'
            f'<a href="{escape(c.url, quote=True)}" style="color:{ACCENT};text-decoration:none;">'
            f'{escape(c.platform)}: {escape(c.title)}</a></div>'
            f'<img src="cid:{escape(c.cid, quote=True)}" width="560" alt="{escape(c.title, quote=True)}"'
            f' style="display:block;max-width:100%;height:auto;">'
            f'<div style="font-size:11px;color:{MUTED};margin-top:3px;">{escape(c.caption)}</div></div>')


def _episode_html(ep: ReportEpisode, marks: dict[str, int],
                  charts: dict[str, list[ChartNote]] | None = None) -> str:
    title = escape(ep.title)
    title_html = (
        f'<a href="{escape(ep.link, quote=True)}" style="color:{INK};text-decoration:none;">{title}</a>'
        if ep.link else title
    )
    meta = " &middot; ".join(escape(bit) for bit in _meta_bits(ep))
    body = ""
    if ep.bullets:
        # A market chart sits under the first bullet, or the parent of the
        # first sub-bullet, that links its anchor.
        charts = dict(charts or {})
        items = "".join(
            f'<li style="margin:0 0 7px 0;font-size:14px;line-height:1.5;color:{INK};">'
            f"{_bullet_html(b, marks)}"
            + "".join(_chart_html(c) for u in bullet_urls(b) for c in charts.pop(u, []))
            + "</li>"
            for b in ep.bullets
        )
        # Outlook ignores list-style padding on <ul>, hence the margin as well.
        body = (f'<ul style="margin:12px 0 4px 0;padding-left:20px;'
                f'margin-left:0;">{items}</ul>')
    elif ep.is_briefing and ep.briefing_text:
        # The digest failed. The whole briefing is worse than bullets but far
        # better than an empty section where the day's news should be.
        paras = "".join(
            f'<p style="margin:0 0 11px 0;font-size:14px;line-height:1.55;color:{INK};">{escape(p.strip())}</p>'
            for p in ep.briefing_text.split("\n\n") if p.strip()
        )
        body = f'<div style="margin:12px 0 4px 0;">{paras}</div>'
    check = fidelity_summary(ep.fidelity)
    if check:
        # The complaints themselves are numbered at the foot of the email.
        body += (f'<div style="font-size:12px;color:{MUTED};margin-top:8px;">'
                 f'{escape(check)}</div>')
    written, backup = writer_line(ep.writer)
    if written:
        body += (f'<div style="font-size:11px;color:{BACKUP if backup else MUTED};'
                 f'margin-top:4px;">{escape(written)}</div>')

    return f"""
      <tr><td style="padding:18px 0;border-bottom:1px solid {RULE};">
        <div style="font-size:17px;font-weight:600;line-height:1.35;color:{INK};">{title_html}</div>
        <div style="font-size:12px;color:{MUTED};margin-top:5px;">{meta}</div>
        {body}
        <div style="margin-top:12px;">{_btn(ep.audio_url, "Listen (narrating)" if ep.pending else "Listen")}{_btn(ep.link, "Read source")}</div>
      </td></tr>"""


def _headline(n: int) -> str:
    """'No new episodes', '1 new episode', '3 new episodes'."""
    return f"{n} new episode{'s' if n != 1 else ''}" if n else "No new episodes"


# Under "Linked, not narrated", in both versions of the email.
LINKED_NOTE = ("These are built on real mathematics. Even a good spoken explanation is hard "
               "to follow without seeing the notation, so they are linked rather than read aloud.")


def _in_email_order(episodes: list) -> list:
    """Briefings first, then the rest, as both versions of the email list them.

    number_notes numbers the checker's complaints in this order, so the [n]
    on a bullet matches the list at the foot only if the episodes are shown
    in it too.
    """
    return [e for e in episodes if e.is_briefing] + [e for e in episodes if not e.is_briefing]


def _sections(report: RunReport, episodes: list, notes: list) -> list[tuple[str, str, list]]:
    """The email's sections in order, as (key, title, items), leaving out the empty ones.

    build_html and build_text both walk this, so the two versions say the same
    things in the same order; written out twice, they drift apart.
    """
    briefings = [e for e in episodes if e.is_briefing]
    others = [e for e in episodes if not e.is_briefing]
    # A chart sits under the briefing bullet that cites it; the rest get a section.
    cited = {u for e in briefings for b in e.bullets for u in bullet_urls(b)}
    sections = [
        ("briefing", "Daily news briefing", briefings),
        ("markets", "Prediction markets", [c for c in report.charts if c.anchor not in cited]),
        ("episodes", "New episode" if len(others) == 1 else "New episodes", others),
        ("failed", "Failed", report.failures),
        # Worth the space even though nothing broke visibly: a source that 404s
        # produces an empty feed, not an error, so the only symptom is a
        # briefing that quietly gets narrower.
        ("dead", "Sources that returned nothing", report.dead_sources),
        ("linked", "Linked, not narrated", report.linked),
        ("checked", "Checked against source", notes),
        ("notices", "Fallbacks and skips this run", report.notices),
        ("recent", "Also published this week", report.recent),
    ]
    return [section for section in sections if section[2]]


def _checked_intro(episodes: list) -> str:
    """The sentence above the checker's complaints, naming the model that made them."""
    names = list(dict.fromkeys(checker_name(e.fidelity) for e in episodes
                               if checker_notes(e.fidelity)))
    who = " and ".join(names)
    return (f"{who[:1].upper()}{who[1:]} read each script against its source; the writer "
            f"fixed what it could once. These are the complaints that remain. Numbers match "
            f"the marked bullets above.")


def build_html(report: RunReport, when: datetime) -> str:
    """Render the full HTML body."""
    episodes = _in_email_order(report.episodes)
    marks_by_idx, notes = number_notes(episodes)
    by_anchor: dict[str, list[ChartNote]] = {}
    for c in report.charts:
        by_anchor.setdefault(c.anchor, []).append(c)

    def section(label: str, rows: str) -> str:
        return (
            f'<tr><td style="padding:26px 0 2px 0;font-size:11px;font-weight:700;'
            f'letter-spacing:.09em;text-transform:uppercase;color:{MUTED};">{escape(label)}</td></tr>'
            + rows
        )

    def episode_rows(eps: list[ReportEpisode]) -> str:
        return "".join(_episode_html(e, marks_by_idx.get(episodes.index(e), {}),
                                     charts=by_anchor if e.is_briefing else None) for e in eps)

    def market_rows(charts: list[ChartNote]) -> str:
        return "".join(f'<tr><td style="padding:8px 0;">{_chart_html(c)}</td></tr>' for c in charts)

    def failed_rows(failures: list[tuple[str, str]]) -> str:
        return "".join(
            f'<tr><td style="padding:10px 0;border-bottom:1px solid {RULE};font-size:13px;color:{INK};">'
            f"<strong>{escape(t)}</strong><br>"
            f'<span style="color:#a33;font-size:12px;">{escape(err)}</span></td></tr>'
            for t, err in failures)

    def dead_rows(names: list[str]) -> str:
        return "".join(
            f'<tr><td style="padding:8px 0;border-bottom:1px solid {RULE};'
            f'font-size:13px;color:#a33;">{escape(name)}</td></tr>' for name in names)

    def linked_rows(posts: list[LinkedPost]) -> str:
        def row(post: LinkedPost) -> str:
            title = (f'<a href="{escape(post.link, quote=True)}" '
                     f'style="color:{INK};text-decoration:none;">{escape(post.title)}</a>'
                     if post.link else escape(post.title))
            # The separator stays outside escape(); escaping it yields "&amp;middot;",
            # which renders as literal text in the mail client.
            who = " &middot; ".join(escape(b) for b in byline(post.author, post.feed_name))
            # No score means the verdict predates it being recorded. Say
            # nothing rather than print a zero that reads as "no maths at all".
            score = (f' &middot; {post.maths_score:g} maths matches per 1000 words'
                     if post.maths_score > 0 else "")
            return (
                f'<tr><td style="padding:13px 0;border-bottom:1px solid {RULE};">'
                f'<div style="font-size:15px;font-weight:600;line-height:1.35;">{title}</div>'
                f'<div style="font-size:12px;color:{MUTED};margin-top:4px;">{who}'
                f'{score}</div>'
                f'<div style="margin-top:9px;">{_btn(post.link, "Read it")}</div>'
                "</td></tr>"
            )

        return "".join(row(p) for p in posts) + (
            f'<tr><td style="padding:2px 0 0 0;font-size:12px;color:{MUTED};'
            f'line-height:1.55;">{escape(LINKED_NOTE)}</td></tr>')

    def checked_rows(notes: list[tuple[str, dict]]) -> str:
        return (f'<tr><td style="padding:12px 0 0 0;font-size:12px;line-height:1.5;color:{INK};">'
                f'<div style="color:{MUTED};margin-bottom:8px;">{escape(_checked_intro(episodes))}</div>'
                f'<ol style="margin:0;padding-left:18px;">'
                f'{"".join(_note_li(title, n) for title, n in notes)}</ol></td></tr>')

    def notice_rows(notices: list[str]) -> str:
        return "".join(
            f'<tr><td style="padding:6px 0;border-bottom:1px solid {RULE};'
            f'font-size:12px;color:{MUTED};">{escape(n)}</td></tr>' for n in notices)

    def recent_rows(eps: list[ReportEpisode]) -> str:
        items = "".join(
            f'<li style="margin:0 0 6px 0;font-size:13px;line-height:1.45;">'
            + (f'<a href="{escape(e.link, quote=True)}" style="color:{ACCENT};text-decoration:none;">{escape(e.title)}</a>'
               if e.link else escape(e.title))
            + f'<span style="color:{MUTED};"> &middot; '
            + " &middot; ".join(escape(bit) for bit in
                                [*byline(e.author, e.feed_name), format_published(e.published)] if bit)
            + '</span></li>'
            for e in eps
        )
        return (f'<tr><td style="padding:14px 0;"><ul style="margin:0;padding-left:18px;'
                f'color:{INK};">{items}</ul></td></tr>')

    rows = {"briefing": episode_rows, "markets": market_rows, "episodes": episode_rows,
            "failed": failed_rows, "dead": dead_rows, "linked": linked_rows,
            "checked": checked_rows, "notices": notice_rows, "recent": recent_rows}
    parts = [section(title, rows[key](items))
             for key, title, items in _sections(report, episodes, notes)]

    headline = _headline(len(report.episodes))
    pending_note = (
        " Posts read out in full are narrated after this email: their Listen link"
        " opens a page that plays the episode once it is ready, usually within half"
        " an hour." if any(e.pending for e in report.episodes) else "")

    return f"""<div style="margin:0;padding:0;background:#f4f4f2;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f2;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:640px;background:#ffffff;border:1px solid {RULE};border-radius:6px;padding:28px 30px;font-family:{FONT};">
        <tr><td style="padding-bottom:6px;">
          <div style="font-size:21px;font-weight:700;color:{INK};">Feedcast</div>
          <div style="font-size:13px;color:{MUTED};margin-top:3px;">
            {escape(when.strftime('%A, %d %B %Y'))} &middot; {escape(headline)} &middot; {report.total_in_feed} in feed
          </div>
        </td></tr>
        {''.join(parts)}
        <tr><td style="padding-top:24px;font-size:12px;color:{MUTED};line-height:1.6;">
          {_btn(report.site_url, "Open site")}{_btn(report.feed_url, "RSS feed")}
          <div style="margin-top:14px;">
            Audio links go live once the GitHub Pages deploy finishes, a minute or two after this email.{escape(pending_note)}
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</div>"""


def _episode_text(ep: ReportEpisode, marks: dict[str, int]) -> list[str]:
    """One episode in the plain-text email."""
    lines = [f"* {ep.title}"]
    meta = " / ".join(_meta_bits(ep))
    if meta:
        lines.append(f"  {meta}")
    if ep.link:
        lines.append(f"  Source: {ep.link}")
    if ep.audio_url:
        lines.append(f"  Audio:  {ep.audio_url}"
                     + (" (still narrating; this page plays it once ready)" if ep.pending else ""))
    if ep.bullets:
        def line_for(b, indent: str) -> list[str]:
            t, u = bullet_parts(b)
            mark = f" [{marks[t]}]" if t in marks else ""
            out = [f"{indent}- {t}{mark}" + (f" ({u})" if u else "")]
            for sb in (b.get("sub", []) if isinstance(b, dict) else []):
                out += line_for(sb, indent + "    ")
            return out

        lines.append("")
        for b in ep.bullets:
            lines += line_for(b, "  ")
    elif ep.is_briefing and ep.briefing_text:
        lines += ["", *(f"  {p.strip()}" for p in ep.briefing_text.split("\n\n") if p.strip())]
    check = fidelity_summary(ep.fidelity)
    if check:
        lines.append(f"  ({check})")
    written = writer_line(ep.writer)[0]
    if written:
        lines.append(f"  ({written})")
    return lines


def build_text(report: RunReport, when: datetime) -> str:
    """Plain-text alternative for clients that refuse HTML."""
    episodes = _in_email_order(report.episodes)
    marks_by_idx, notes = number_notes(episodes)

    def episode_lines(eps: list[ReportEpisode]) -> list[str]:
        lines: list[str] = []
        for ep in eps:
            if lines:
                lines.append("")
            lines += _episode_text(ep, marks_by_idx.get(episodes.index(ep), {}))
        return lines

    def market_lines(charts: list[ChartNote]) -> list[str]:
        return [line for c in charts
                for line in (f"  - {c.platform}: {c.title}", f"    {c.url}", f"    {c.caption}")]

    def linked_lines(posts: list[LinkedPost]) -> list[str]:
        lines = []
        for p in posts:
            score = f" [{p.maths_score:g}/1k]" if p.maths_score > 0 else ""
            lines.append(f"  - {p.title} ({' / '.join(byline(p.author, p.feed_name))}){score}")
            if p.link:
                lines.append(f"    {p.link}")
        return lines + [f"  {LINKED_NOTE}"]

    def checked_lines(notes: list[tuple[str, dict]]) -> list[str]:
        lines = [f"  {_checked_intro(episodes)}"]
        for i, (title, n) in enumerate(notes, 1):
            lines.append(f"  [{i}] {title} — {n.get('severity')}, {n.get('verdict')}: {n.get('explanation')}")
            lines.append(f"      script: \"{n.get('script_quote')}\"")
            lines.append(f"      source: \"{n.get('source_quote')}\"")
        return lines

    def recent_lines(eps: list[ReportEpisode]) -> list[str]:
        return [f"  - {e.title} ({' / '.join(byline(e.author, e.feed_name))}"
                + (f", {format_published(e.published)}" if e.published else "") + ")"
                for e in eps]

    rows = {"briefing": episode_lines, "markets": market_lines, "episodes": episode_lines,
            "failed": lambda failures: [f"  - {t}: {err}" for t, err in failures],
            "dead": lambda names: [f"  - {n}" for n in names],
            "linked": linked_lines, "checked": checked_lines,
            "notices": lambda notices: [f"  - {n}" for n in notices],
            "recent": recent_lines}
    lines = [f"Feedcast — {when.strftime('%A, %d %B %Y')}",
             f"{_headline(len(report.episodes))}; {report.total_in_feed} in feed", ""]
    for key, title, items in _sections(report, episodes, notes):
        lines += [f"{title}:", *rows[key](items), ""]
    lines.append(report.feed_url)
    return "\n".join(lines)


def is_test_run() -> bool:
    """FEEDCAST_TEST_RUN: a dev run — publishes as normal, emails only the operator.

    The workflow sets this for every run someone asked for by hand (a
    reprocess, an injection, a resend, a force) unless they tick `notify_list`.
    On 2026-09-08 two debugging re-runs each emailed the whole BCC list, one of
    them announcing nothing but a failure.
    """
    return env_flag("FEEDCAST_TEST_RUN")


def _addresses(raw: str) -> list[str]:
    """Split a comma- or semicolon-separated address list, dropping blanks."""
    return [a.strip() for a in raw.replace(";", ",").split(",") if a.strip()]


@dataclass
class EmailSettings:
    """Who the report goes to and how it is sent, as the environment configures it."""

    to: list[str]
    bcc: list[str]
    sender: str
    user: str
    password: str
    host: str
    port: int
    test_run: bool

    @classmethod
    def from_env(cls) -> "EmailSettings | None":
        """The settings, or None when the email is off (FEEDCAST_EMAIL_TO unset).

        Raises ValueError, saying what is wrong, when the email is on but cannot
        be sent: SMTP_USER or the password missing (a missing or rotated CI
        secret is a failure, not a reason to stop reporting), or an SMTP_PORT
        that is not a number (a misconfiguration, not unset). An unset GitHub
        Actions `vars.X` interpolates to an empty string rather than being
        absent, so an empty host or port falls back as an unset one does.
        """
        to = _addresses(os.environ.get("FEEDCAST_EMAIL_TO", ""))
        if not to:
            return None
        user = os.environ.get("SMTP_USER", "").strip()
        password = (
            os.environ.get("SMTP_PASSWORD", "")
            or os.environ.get("GMAIL_APP_PASSWORD", "")
        ).strip()
        if not (user and password):
            raise ValueError("FEEDCAST_EMAIL_TO is set, but SMTP_USER or "
                             "GMAIL_APP_PASSWORD (alias SMTP_PASSWORD) is not")
        raw_port = os.environ.get("SMTP_PORT", "").strip()
        if raw_port and not raw_port.isdigit():
            raise ValueError(f"SMTP_PORT={raw_port!r} is not a number")
        return cls(
            to=to,
            bcc=_addresses(os.environ.get("FEEDCAST_EMAIL_BCC", "")),
            sender=os.environ.get("FEEDCAST_EMAIL_FROM", "").strip() or user,
            user=user,
            password=password,
            host=os.environ.get("SMTP_HOST", "").strip() or "smtp.gmail.com",
            port=int(raw_port) if raw_port else DEFAULT_PORT,
            test_run=is_test_run(),
        )


def compose_message(report: RunReport, when: datetime, settings: EmailSettings, *,
                    operator_only: bool = False, subject_tag: str = "",
                    images: dict[str, bytes] | None = None) -> EmailMessage:
    """The report as an email: plain text with an HTML alternative.

    A test run (FEEDCAST_TEST_RUN) is tagged [DEV] and, like an `operator_only`
    report, leaves out the BCC list. `subject_tag` prefixes the subject;
    `images` are inline PNGs (the market charts) keyed by the Content-ID the
    HTML cites.
    """
    n = len(report.episodes)
    subject = f"Feedcast — {when.strftime('%d %b')} — {n} new episode{'s' if n != 1 else ''}"
    if report.linked and not n:
        subject = (f"Feedcast — {when.strftime('%d %b')} — "
                   f"{len(report.linked)} linked, no audio")
    if report.failures and not n:
        subject = f"Feedcast — {when.strftime('%d %b')} — {len(report.failures)} failed"
    if subject_tag:
        subject = f"{subject_tag} {subject}"
    if settings.test_run:
        subject = f"[DEV] {subject}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.sender
    msg["To"] = ", ".join(settings.to)
    # send_message delivers to the Bcc addresses but strips the header from
    # the transmitted copy, so those recipients stay hidden from each other.
    if settings.bcc and not (settings.test_run or operator_only):
        msg["Bcc"] = ", ".join(settings.bcc)
    msg.set_content(build_text(report, when))
    msg.add_alternative(build_html(report, when), subtype="html")
    if images:
        html_part = msg.get_payload()[1]
        for cid, png in images.items():
            html_part.add_related(png, maintype="image", subtype="png", cid=f"<{cid}>")
    return msg


def _send(msg: EmailMessage, settings: EmailSettings) -> None:
    """Hand the message to the SMTP server, to the addresses its headers name."""
    # Port 465 is implicit TLS; 587 is STARTTLS. Gmail accepts both.
    if settings.port == 465:
        with smtplib.SMTP_SSL(settings.host, settings.port, timeout=60,
                              context=ssl.create_default_context()) as srv:
            srv.login(settings.user, settings.password)
            srv.send_message(msg)
    else:
        with smtplib.SMTP(settings.host, settings.port, timeout=60) as srv:
            srv.starttls(context=ssl.create_default_context())
            srv.login(settings.user, settings.password)
            srv.send_message(msg)


def send_report(report: RunReport, when: datetime | None = None,
                operator_only: bool = False, subject_tag: str = "",
                images: dict[str, bytes] | None = None) -> bool | None:
    """Email the run report.

    Returns True if sent, None if the email is off (FEEDCAST_EMAIL_TO unset),
    and False if it is on but was not sent, missing SMTP credentials included
    (EmailSettings.from_env). `operator_only` leaves out the BCC list, as a
    dev run does: the narration pass uses it to say a verbatim post failed
    after the day's email went out. `subject_tag` and `images` are as
    compose_message takes them.
    Never raises, because it runs before the run commits what it published;
    src.main records a False so the workflow fails the run afterwards.
    """
    try:
        settings = EmailSettings.from_env()
    except ValueError as e:
        print(f"  Email report failed: {e}")
        return False
    if settings is None:
        print("  Email report off (FEEDCAST_EMAIL_TO not set)")
        return None
    try:
        msg = compose_message(report, when or datetime.now(), settings,
                              operator_only=operator_only, subject_tag=subject_tag,
                              images=images)
        _send(msg, settings)
    except Exception as e:
        print(f"  Email report failed: {type(e).__name__}: {e}")
        return False
    # The Actions log is public: name only the To address (a secret, masked
    # there) and count the blind-copied readers.
    bcc = _addresses(msg["Bcc"] or "")
    bcc_note = f" and {len(bcc)} bcc" if bcc else ""
    print(f"  Email report sent to {', '.join(settings.to)}{bcc_note}")
    return True
