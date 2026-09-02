"""Keep exactly what the writer model was shown and what it wrote, per episode.

Nothing else in the pipeline preserves this. The database keeps a post's
source text, and transcripts keep the briefing as spoken, but the prompt the
writer actually saw — for a briefing, the article blurbs; for a summary, the
cleaned post — and its unnormalised reply were gone the moment the run ended.
Auditing a summary against its source then meant rebuilding the source from
live feeds and Wayback snapshots, which on 2026-09-02 recovered 16 of a day's
articles and made a faithful briefing look fabricated.

One Markdown file per episode under data/sources/, named by episode id like
the audio, written when the episode is marked processed and deleted by the
same 30-day cleanup. Plain text, tens of kilobytes a day.
"""

from pathlib import Path


def writer_bundle(*, title: str, model: str, system_prompt: str,
                  user_message: str, response: str, notes: str = "") -> str:
    """Render one writer exchange as Markdown, plus any check notes."""
    tail = ["## Fidelity check", "", notes.rstrip(), ""] if notes.strip() else []
    return "\n".join([
        f"# {title}", "",
        f"Writer: {model}", "",
        "## System prompt", "", system_prompt.rstrip(), "",
        "## What the writer was given", "", user_message.rstrip(), "",
        "## What the writer wrote", "", response.rstrip(), "",
        *tail,
    ])


def write_bundle(sources_dir: Path, episode_id: str, text: str) -> Path:
    sources_dir.mkdir(parents=True, exist_ok=True)
    path = sources_dir / f"{episode_id}.md"
    path.write_text(text, encoding="utf-8")
    return path
