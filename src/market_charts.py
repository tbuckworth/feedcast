"""Small price charts of prediction markets, and which ones the daily email gets.

PNG, because Gmail renders neither SVG nor scripts. The main panel is the
market's whole life (capped at a year by the fetch), so a long-running question
shows months of context and a short-dated one its short life. When that life
goes back more than ZOOM_MIN_HISTORY_DAYS, a second panel zooms in on the last
seven days, where the intraday move that shows how surprising the news was
would otherwise be a few pixels at the end of a months-long line. A younger
market gets the one panel: its last week is already wide enough to read.
"""

import io
from datetime import datetime, timedelta

import matplotlib

matplotlib.use("Agg")  # no display on a CI runner
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from . import notices  # noqa: E402
# The email's palette: the charts appear only in it.
from .email_report import ACCENT, MUTED, RULE, ChartNote, bullet_urls  # noqa: E402
from .monitor import FeedEntry  # noqa: E402

MARK = "#b5532c"
ZOOM_DAYS = 7
# The 7-day zoom only for a market whose history goes back more than this
# (three months). Younger ones get the one panel.
ZOOM_MIN_HISTORY_DAYS = 90


def history_days(history: list[tuple[datetime, float]]) -> float:
    """How far back `history` goes from its latest point, in days."""
    if len(history) < 2:
        return 0.0
    times = [t for t, _ in history]
    return (max(times) - min(times)).total_seconds() / 86400


def wants_zoom(history: list[tuple[datetime, float]]) -> bool:
    """True when the market's history goes back more than ZOOM_MIN_HISTORY_DAYS."""
    return history_days(history) > ZOOM_MIN_HISTORY_DAYS


def zoom_window(history: list[tuple[datetime, float]], end: datetime) -> list:
    """The last ZOOM_DAYS of `history` up to `end`."""
    start = end - timedelta(days=ZOOM_DAYS)
    return [(t, p) for t, p in history if t >= start]


def _style(ax, probs: list[float], full_range: bool, span_days: float) -> None:
    if full_range:
        ax.set_ylim(0, 100)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_yticklabels(["0", "25", "50", "75", "100%"], fontsize=8, color=MUTED)
    else:
        # Magnify, but never so far that a two-point wobble looks dramatic.
        lo, hi = min(probs), max(probs)
        mid, half = (lo + hi) / 2, max((hi - lo) / 2 + 3, 6)
        ax.set_ylim(max(0, mid - half), min(100, mid + half))
        ax.yaxis.set_major_formatter(lambda v, _pos: f"{v:.0f}%")
        ax.tick_params(axis="y", labelsize=8, colors=MUTED)
    locator = mdates.AutoDateLocator(minticks=3, maxticks=5)
    ax.xaxis.set_major_locator(locator)
    if span_days < 60:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))   # "05 Oct", never a bare "05"
    else:
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, show_offset=False))
    ax.tick_params(axis="x", labelsize=8, colors=MUTED)
    ax.grid(axis="y", color=RULE, linewidth=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#cccccc")


def _plot(ax, history, story_time, label_end: bool) -> None:
    times = [t for t, _ in history]
    probs = [p * 100 for _, p in history]
    ax.plot(times, probs, color=ACCENT, linewidth=1.5)
    ax.fill_between(times, probs, ax.get_ylim()[0] if ax.get_ylim()[0] > 0 else 0,
                    color=ACCENT, alpha=0.08)
    # A story from this morning can postdate the last trade: still mark it.
    if story_time and times[0] <= story_time <= times[-1] + timedelta(days=2):
        ax.axvline(story_time, color=MARK, linestyle="--", linewidth=1)
        ax.annotate("story", (story_time, 1), xycoords=("data", "axes fraction"),
                    xytext=(3, -10), textcoords="offset points", color=MARK, fontsize=8)
    if label_end:
        ax.annotate(f"{probs[-1]:.0f}%", (times[-1], probs[-1]), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=9, color=ACCENT,
                    fontweight="bold")


def render_chart(history: list[tuple[datetime, float]], story_time: datetime | None = None,
                 zoom: list[tuple[datetime, float]] | None = None,
                 width_px: int = 560) -> bytes | None:
    """One market's odds as a PNG, or None when there is too little history to draw.

    `zoom`, when given (at least two points), adds a "last 7 days" panel.
    """
    history = sorted(history)
    if len(history) < 2:
        return None
    zoom = sorted(zoom) if zoom and len(zoom) >= 2 else None
    dpi = 100
    height_px = 300 if zoom else 190
    if zoom:
        fig, (ax, az) = plt.subplots(2, 1, figsize=(width_px / dpi, height_px / dpi), dpi=dpi,
                                     gridspec_kw={"height_ratios": [3, 2], "hspace": 0.55})
    else:
        fig, ax = plt.subplots(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
        az = None
    try:
        _style(ax, [p * 100 for _, p in history], full_range=True,
               span_days=history_days(history))
        _plot(ax, history, story_time, label_end=True)
        if az is not None:
            _style(az, [p * 100 for _, p in zoom], full_range=False,
                   span_days=history_days(zoom))
            _plot(az, zoom, story_time, label_end=False)
            az.set_title(f"Last {ZOOM_DAYS} days", fontsize=8, color=MUTED, loc="left", pad=3)
        fig.subplots_adjust(left=0.08, right=0.93, top=0.95, bottom=0.12 if zoom else 0.14)
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)


def charts_for_report(briefing: FeedEntry) -> tuple[list[ChartNote], dict[str, bytes]]:
    """Price charts for the daily email: the notes, and the PNGs by Content-ID.

    A chart is drawn for each unexplained move and for each story market the
    digest cites, and sits under the bullet that links it. Every chart shows
    the market's whole life; one whose history goes back more than three
    months also gets a 7-day zoom (wants_zoom). Nothing on days the
    briefing used no market. Never raises: a missing chart must not cost the
    day's email. A failure is printed and added to the run's notices.
    """
    charts: list[ChartNote] = []
    images: dict[str, bytes] = {}
    try:
        data = briefing.markets
        if not data:
            return [], {}
        cited = {u for b in briefing.bullets for u in bullet_urls(b)}
        drawn: set[str] = set()

        def points(m: dict, key: str) -> list:
            return [(datetime.fromisoformat(when), p) for when, p in m.get(key) or []]

        def add(m: dict, anchor: str, story_time: datetime | None, caption: str) -> None:
            if m["key"] in drawn:   # one market linked to two stories
                return
            drawn.add(m["key"])
            # The whole life for context, with the hourly last 30 days spliced
            # onto the end for detail.
            recent, life = points(m, "history"), points(m, "long_history")
            line = [pt for pt in life if not recent or pt[0] < recent[0][0]] + recent
            # Past three months the last week is a sliver at the end of the
            # line, so it gets a panel of its own.
            zoom = zoom_window(line, line[-1][0]) if wants_zoom(line) else []
            png = render_chart(line, story_time, zoom)
            panels = ("not drawn, too little history" if not png else
                      f"whole life plus a {ZOOM_DAYS}-day zoom" if len(zoom) >= 2 else
                      "whole life only")
            print(f"    chart: {m['title'][:70]}: {history_days(line):.0f} days of history, {panels}")
            if png:
                cid = f"market-{len(images)}@feedcast"
                images[cid] = png
                charts.append(ChartNote(cid=cid, title=m["title"], platform=m["platform"],
                                        url=m["url"], caption=caption, anchor=anchor))

        for m in data.get("moves") or []:
            add(m, m["url"] if m["url"] in cited else "", None,
                f"{m['prob_24h']:.0%} to {m['prob']:.0%} in the last 24 hours · {m['traded']}")
        for story_url, markets in (data.get("stories") or {}).items():
            raw_time = (data.get("story_times") or {}).get(story_url)
            story_time = datetime.fromisoformat(raw_time) if raw_time else None
            for m in markets:
                # Only markets the digest cites, which it does when the script
                # quotes them. "The platform is named somewhere and the story
                # has a bullet" charted, on 14 Oct, a Gemini benchmark market
                # the script never mentioned under the Gemini bullet, and
                # skipped the Houthi market it did quote: that one was linked
                # only from a sub-bullet.
                if m["url"] not in cited:
                    continue
                add(m, m["url"], story_time,
                    f"Now {m['prob']:.0%} · {m['traded']} · dashed line: the story")
    except Exception as e:  # noqa: BLE001 — the email goes out without charts
        note = f"prediction-market charts left out of this email: {type(e).__name__}: {e}"
        print(f"  {note}")
        notices.add(note)
        return [], {}
    return charts, images
