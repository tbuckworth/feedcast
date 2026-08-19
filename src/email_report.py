"""HTML run report emailed when the pipeline finishes.

Configured entirely through environment variables so the recipient address and
credentials live in GitHub secrets rather than in the repo. If the required
ones are absent the report is skipped with a log line — a missing mailbox must
never fail a pipeline run that otherwise succeeded.
"""

import os
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

DEFAULT_PORT = 587


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


@dataclass
class RunReport:
    """Everything the email needs about a single pipeline run."""

    episodes: list[ReportEpisode] = field(default_factory=list)
    recent: list[ReportEpisode] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    feed_url: str = ""
    site_url: str = ""
    total_in_feed: int = 0


def format_duration(seconds: int) -> str:
    """Render a duration as '4 min 01 sec', or '' when unknown."""
    if not seconds:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} hr {minutes:02d} min"
    return f"{minutes} min {secs:02d} sec"


def _meta_bits(ep: "ReportEpisode") -> list[str]:
    """Author / feed / duration, minus the duplicate when they are the same.

    The per-author feeds are named after the author, so without this every one
    of those episodes reads "Scott Alexander / Scott Alexander".
    """
    bits = [ep.author]
    if ep.feed_name and ep.feed_name != ep.author:
        bits.append(ep.feed_name)
    bits.append(format_duration(ep.duration_seconds))
    return [b for b in bits if b]


def _btn(url: str, label: str) -> str:
    if not url:
        return ""
    return (
        f'<a href="{escape(url, quote=True)}" style="display:inline-block;'
        f"padding:7px 14px;margin:0 8px 0 0;background:{ACCENT};color:#ffffff;"
        f'text-decoration:none;border-radius:4px;font-size:13px;">{escape(label)}</a>'
    )


def _episode_html(ep: ReportEpisode) -> str:
    title = escape(ep.title)
    title_html = (
        f'<a href="{escape(ep.link, quote=True)}" style="color:{INK};text-decoration:none;">{title}</a>'
        if ep.link else title
    )
    meta = " &middot; ".join(escape(bit) for bit in _meta_bits(ep))
    body = ""
    if ep.is_briefing and ep.briefing_text:
        paras = "".join(
            f'<p style="margin:0 0 11px 0;font-size:14px;line-height:1.55;color:{INK};">{escape(p.strip())}</p>'
            for p in ep.briefing_text.split("\n\n") if p.strip()
        )
        body = f'<div style="margin:12px 0 4px 0;">{paras}</div>'

    return f"""
      <tr><td style="padding:18px 0;border-bottom:1px solid {RULE};">
        <div style="font-size:17px;font-weight:600;line-height:1.35;color:{INK};">{title_html}</div>
        <div style="font-size:12px;color:{MUTED};margin-top:5px;">{meta}</div>
        {body}
        <div style="margin-top:12px;">{_btn(ep.audio_url, "Listen")}{_btn(ep.link, "Read source")}</div>
      </td></tr>"""


def build_html(report: RunReport, when: datetime) -> str:
    """Render the full HTML body."""
    briefings = [e for e in report.episodes if e.is_briefing]
    others = [e for e in report.episodes if not e.is_briefing]
    n = len(report.episodes)

    def section(label: str, rows: str) -> str:
        if not rows:
            return ""
        return (
            f'<tr><td style="padding:26px 0 2px 0;font-size:11px;font-weight:700;'
            f'letter-spacing:.09em;text-transform:uppercase;color:{MUTED};">{escape(label)}</td></tr>'
            + rows
        )

    parts = [section("Daily news briefing", "".join(_episode_html(e) for e in briefings))]
    parts.append(section(
        "New episodes" if len(others) != 1 else "New episode",
        "".join(_episode_html(e) for e in others),
    ))

    if report.failures:
        rows = "".join(
            f'<tr><td style="padding:10px 0;border-bottom:1px solid {RULE};font-size:13px;color:{INK};">'
            f"<strong>{escape(t)}</strong><br>"
            f'<span style="color:#a33;font-size:12px;">{escape(err)}</span></td></tr>'
            for t, err in report.failures
        )
        parts.append(section("Failed", rows))

    if report.recent:
        items = "".join(
            f'<li style="margin:0 0 6px 0;font-size:13px;line-height:1.45;">'
            + (f'<a href="{escape(e.link, quote=True)}" style="color:{ACCENT};text-decoration:none;">{escape(e.title)}</a>'
               if e.link else escape(e.title))
            + f'<span style="color:{MUTED};"> &middot; {escape(e.author or e.feed_name)}</span></li>'
            for e in report.recent
        )
        parts.append(section(
            "Also published this week",
            f'<tr><td style="padding:14px 0;"><ul style="margin:0;padding-left:18px;color:{INK};">{items}</ul></td></tr>',
        ))

    headline = f"{n} new episode{'s' if n != 1 else ''}"
    if not n:
        headline = "No new episodes"

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
            Audio links go live once the GitHub Pages deploy finishes, a minute or two after this email.
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</div>"""


def build_text(report: RunReport, when: datetime) -> str:
    """Plain-text alternative for clients that refuse HTML."""
    lines = [f"Feedcast — {when.strftime('%A, %d %B %Y')}",
             f"{len(report.episodes)} new episode(s); {report.total_in_feed} in feed", ""]
    for ep in report.episodes:
        lines.append(f"* {ep.title}")
        meta = " / ".join(_meta_bits(ep))
        if meta:
            lines.append(f"  {meta}")
        if ep.link:
            lines.append(f"  Source: {ep.link}")
        if ep.audio_url:
            lines.append(f"  Audio:  {ep.audio_url}")
        if ep.is_briefing and ep.briefing_text:
            lines += ["", *(f"  {p.strip()}" for p in ep.briefing_text.split("\n\n") if p.strip())]
        lines.append("")
    if report.failures:
        lines.append("Failed:")
        lines += [f"  - {t}: {err}" for t, err in report.failures] + [""]
    if report.recent:
        lines.append("Also published this week:")
        lines += [f"  - {e.title} ({e.author or e.feed_name})" for e in report.recent] + [""]
    lines.append(report.feed_url)
    return "\n".join(lines)


def send_report(report: RunReport, when: datetime | None = None) -> bool:
    """Email the run report. Returns True if sent, False if skipped or failed.

    Never raises: a broken mailbox must not fail an otherwise-good run.
    """
    when = when or datetime.now()
    to_addr = os.environ.get("FEEDCAST_EMAIL_TO", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = (
        os.environ.get("SMTP_PASSWORD", "")
        or os.environ.get("GMAIL_APP_PASSWORD", "")
    ).strip()

    if not (to_addr and user and password):
        print("  Email report skipped (FEEDCAST_EMAIL_TO / SMTP_USER / SMTP_PASSWORD not set)")
        return False

    # An unset GitHub Actions `vars.X` interpolates to an empty string rather
    # than being absent, so fall back on emptiness, not just on the key missing.
    host = os.environ.get("SMTP_HOST", "").strip() or "smtp.gmail.com"
    raw_port = os.environ.get("SMTP_PORT", "").strip()
    try:
        port = int(raw_port) if raw_port else DEFAULT_PORT
    except ValueError:
        print(f"  Email report: SMTP_PORT={raw_port!r} is not a number, using {DEFAULT_PORT}")
        port = DEFAULT_PORT

    try:
        from_addr = os.environ.get("FEEDCAST_EMAIL_FROM", "").strip() or user

        n = len(report.episodes)
        subject = f"Feedcast — {when.strftime('%d %b')} — {n} new episode{'s' if n != 1 else ''}"
        if report.failures and not n:
            subject = f"Feedcast — {when.strftime('%d %b')} — {len(report.failures)} failed"

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.set_content(build_text(report, when))
        msg.add_alternative(build_html(report, when), subtype="html")

        # Port 465 is implicit TLS; 587 is STARTTLS. Gmail accepts both.
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=60,
                                  context=ssl.create_default_context()) as srv:
                srv.login(user, password)
                srv.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=60) as srv:
                srv.starttls(context=ssl.create_default_context())
                srv.login(user, password)
                srv.send_message(msg)
        print(f"  Email report sent to {to_addr}")
        return True
    except Exception as e:
        print(f"  Email report failed: {type(e).__name__}: {e}")
        return False
