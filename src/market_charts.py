"""Small price charts of prediction markets, for the trial email.

PNG, because Gmail renders neither SVG nor scripts. The main panel is the
market's whole life (capped at a year by the fetch), so a long-running question
shows months of context and a short-dated one its short life. When the market
moved around the story, a second panel zooms in on the last seven days, where
the intraday move that shows how surprising the news was would otherwise be a
few pixels at the end of a year-long line.
"""

import io
from datetime import datetime, timedelta

import matplotlib

matplotlib.use("Agg")  # no display on a CI runner
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

LINE = "#1f5f8b"
MARK = "#b5532c"
MUTED = "#6b6b6b"
ZOOM_DAYS = 7


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
    ax.grid(axis="y", color="#e3e3e3", linewidth=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#cccccc")


def _plot(ax, history, story_time, label_end: bool) -> None:
    times = [t for t, _ in history]
    probs = [p * 100 for _, p in history]
    ax.plot(times, probs, color=LINE, linewidth=1.5)
    ax.fill_between(times, probs, ax.get_ylim()[0] if ax.get_ylim()[0] > 0 else 0,
                    color=LINE, alpha=0.08)
    # A story from this morning can postdate the last trade: still mark it.
    if story_time and times[0] <= story_time <= times[-1] + timedelta(days=2):
        ax.axvline(story_time, color=MARK, linestyle="--", linewidth=1)
        ax.annotate("story", (story_time, 1), xycoords=("data", "axes fraction"),
                    xytext=(3, -10), textcoords="offset points", color=MARK, fontsize=8)
    if label_end:
        ax.annotate(f"{probs[-1]:.0f}%", (times[-1], probs[-1]), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=9, color=LINE,
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
        span = lambda pts: (pts[-1][0] - pts[0][0]).total_seconds() / 86400  # noqa: E731
        _style(ax, [p * 100 for _, p in history], full_range=True, span_days=span(history))
        _plot(ax, history, story_time, label_end=True)
        if az is not None:
            _style(az, [p * 100 for _, p in zoom], full_range=False, span_days=span(zoom))
            _plot(az, zoom, story_time, label_end=False)
            az.set_title(f"Last {ZOOM_DAYS} days", fontsize=8, color=MUTED, loc="left", pad=3)
        fig.subplots_adjust(left=0.08, right=0.93, top=0.95, bottom=0.12 if zoom else 0.14)
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)
