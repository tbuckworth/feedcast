"""Small price charts of prediction markets, for the trial email.

PNG, because Gmail renders neither SVG nor scripts. One line, the market's
probability over the last 30 days, with a dashed line where the story broke.
"""

import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # no display on a CI runner
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

LINE = "#1f5f8b"
MARK = "#b5532c"
MUTED = "#6b6b6b"


def render_chart(history: list[tuple[datetime, float]], story_time: datetime | None = None,
                 width_px: int = 560, height_px: int = 190) -> bytes | None:
    """One market's odds as a PNG, or None when there is too little history to draw."""
    if len(history) < 2:
        return None
    times = [t for t, _ in history]
    probs = [p * 100 for _, p in history]
    dpi = 100
    fig, ax = plt.subplots(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    try:
        ax.plot(times, probs, color=LINE, linewidth=1.6)
        ax.fill_between(times, probs, color=LINE, alpha=0.08)
        if story_time and times[0] <= story_time <= times[-1]:
            ax.axvline(story_time, color=MARK, linestyle="--", linewidth=1)
            ax.annotate("story", (story_time, 100), xytext=(3, -10), textcoords="offset points",
                        color=MARK, fontsize=8)
        ax.annotate(f"{probs[-1]:.0f}%", (times[-1], probs[-1]), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=9, color=LINE,
                    fontweight="bold")
        ax.set_ylim(0, 100)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_yticklabels(["0", "25", "50", "75", "100%"], fontsize=8, color=MUTED)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
        ax.tick_params(axis="x", labelsize=8, colors=MUTED)
        ax.grid(axis="y", color="#e3e3e3", linewidth=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#cccccc")
        fig.tight_layout(pad=0.4)
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)
