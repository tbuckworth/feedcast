"""Keep exactly what the writer model was shown and what it wrote, per episode.

Nothing else in the pipeline keeps this. The database keeps a post's source
text, and transcripts keep the briefing as spoken, but neither keeps the
prompt the writer saw (for a briefing, the selected articles and the other
headlines; for a summary, the cleaned post) or its unnormalised reply.
Without them, auditing a summary against its source means rebuilding the
source from live feeds and archived snapshots, which recovers only part of a
day's articles and can make a faithful briefing look fabricated.

One Markdown file per episode under data/sources/, named by episode id like
the audio, written when the episode is marked processed and deleted with the
episode after `retention_days`. Plain text, tens of kilobytes a day.
"""

import re
from pathlib import Path

# The bundle's own section headings, in the order it writes them. The writer's
# input has ## headings of its own (a briefing's categories and "Selected
# stories"), so `read_bundle` splits on these names and no others.
SYSTEM_PROMPT = "System prompt"
WRITER_INPUT = "What the writer was given"
WRITER_OUTPUT = "What the writer wrote"
FIDELITY_CHECK = "Fidelity check"
SECTIONS = (SYSTEM_PROMPT, WRITER_INPUT, WRITER_OUTPUT, FIDELITY_CHECK)


def writer_bundle(*, title: str, model: str, system_prompt: str,
                  user_message: str, response: str, notes: str = "") -> str:
    """Render one writer exchange as Markdown, plus any check notes."""
    tail = [f"## {FIDELITY_CHECK}", "", notes.rstrip(), ""] if notes.strip() else []
    return "\n".join([
        f"# {title}", "",
        f"Writer: {model}", "",
        f"## {SYSTEM_PROMPT}", "", system_prompt.rstrip(), "",
        f"## {WRITER_INPUT}", "", user_message.rstrip(), "",
        f"## {WRITER_OUTPUT}", "", response.rstrip(), "",
        *tail,
    ])


def read_bundle(text: str) -> dict[str, str]:
    """The sections of a bundle `writer_bundle` rendered, by heading name.

    A section the bundle lacks (no fidelity notes) is absent from the result.
    """
    marks = [m for m in re.finditer(r"^## (.+)$", text, re.M) if m.group(1) in SECTIONS]
    ends = [m.start() for m in marks[1:]] + [len(text)]
    return {m.group(1): text[m.end():end].removeprefix("\n\n").rstrip()
            for m, end in zip(marks, ends)}


def bundle_path(sources_dir: Path, episode_id: str) -> Path:
    """Where an episode's bundle is kept: written with the episode, deleted by cleanup."""
    return sources_dir / f"{episode_id}.md"


def write_bundle(sources_dir: Path, episode_id: str, text: str) -> Path:
    sources_dir.mkdir(parents=True, exist_ok=True)
    path = bundle_path(sources_dir, episode_id)
    path.write_text(text, encoding="utf-8")
    return path
