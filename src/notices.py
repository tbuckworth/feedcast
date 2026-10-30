"""What this run fell back on or skipped, for the email's "Fallbacks and skips this run".

Any module that switches to a backup or leaves something out records one line
here: llm.py its model and account switches, audio.py a busy TTS model,
markets.py a skipped market scan and failed market calls and cause lookups,
market_charts.py charts left out, lesswrong.py a failed date lookup, digest.py
a failed digest, main.py an episode with passages narrated un-normalised. A backup that quietly
serves for weeks is a primary that has quietly died, so each one is worth a line.

One process is one run (each CI pass is a process of its own), so the log
lives at module level; `reset()` starts a new one, as tests do before each test.
"""

from collections import Counter

_headlines: list[str] = []
_notes: list[str] = []


def add(note: str, *, headline: bool = False) -> None:
    """Record one notice. A headline sums up others (a whole account gone) and leads the list."""
    (_headlines if headline else _notes).append(note)


def report() -> list[str]:
    """The run's notices for the email: headlines first, then the rest in order, repeats collapsed.

    One dead account touches every call on it, so without collapsing, a long
    post's normalisation alone would print a dozen identical lines.
    """
    counts = Counter(_notes)
    return list(dict.fromkeys(_headlines)) + [
        note if counts[note] == 1 else f"{note} ({counts[note]} calls)"
        for note in dict.fromkeys(_notes)]


def reset() -> None:
    """Forget every notice: a new run starts here."""
    _headlines.clear()
    _notes.clear()
