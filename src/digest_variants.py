"""Experimental email digests, second round (2026-09-16).

Two shapes Titus asked to see after the full restatement in `digest_full.py`
proved too verbose:

- `uncapped`: today's prompt, word for word, but the parser no longer drops
  bullets over 240 characters. On 2026-09-16 that cap threw away 3 of the 5
  bullets written for the Zvi episode.
- `tiered`: a handful of headline bullets, each with indented sub-bullets
  carrying the detail. The headline is what the current email gives; the
  sub-bullets are what the audio adds.

Bullets are plain strings or dicts: {"text", "url"?, "label"?, "sub"?: [...]}.
Nothing in the pipeline imports this module.
"""

import re

from .digest import PROMPT as CURRENT_PROMPT, SOURCES_RULE, _clean, _split_source
from .llm import MODEL_WRITER, completion_text, get_client

MAX_CHARS = 120000
MIN_BULLET_CHARS = 25
MAX_BULLET_CHARS = 700

TIERED_PROMPT = """You are writing the bullet-point digest of a podcast episode for an \
email that its listener reads over breakfast. The digest has two levels.

Top level: {n} bullets, one sentence each, each carrying the headline claim, \
number, name or finding of one part of the episode, ordered by importance. \
This is what a reader in a hurry reads.

Under each top-level bullet: 1 to 4 indented sub-bullets, one sentence each, \
with the supporting detail the script gives for that point — the figures, \
names, examples, caveats, who-said-what and the author's own judgement. \
Everything of substance in the script should land in some sub-bullet; do not \
repeat the headline sentence, and do not add anything the script does not say.

Rules:
- Say what the piece actually claims, not that it discusses a topic.
- Keep attributions ("Zvi argues", "the CBO found").
- This is read, not spoken. Keep numerals, percent signs, currency and symbols, \
and convert anything spelled out for speech back into figures: "forty-five \
percent" becomes 45%, "two thousand twenty-six" becomes 2026. Leave words \
inside a direct quotation exactly as spoken ("the two most successful").
- No preamble, no closing line, no headings, no markdown, no bold.
- Format: a top-level bullet is a line starting with "- ". A sub-bullet is a \
line starting with two spaces then "- ". Nothing else.
- If the text is a news briefing, make one top-level bullet per story, in the \
order the briefing gives them. Use the article list only to attach links, \
never as a source of stories: a story the script does not tell is not in the \
digest."""

TIERED_SOURCES_RULE = """

The text was synthesised from the articles below. End each top-level bullet, and \
each sub-bullet that draws on a single article, with the URL of that article, in \
the form:

  - The bullet sentence. || https://example.com/article

Use a URL from this list verbatim, never one you remember or invent. If a bullet \
draws on no single article, give it no URL.

Articles:
{articles}"""


def _listing(sources: list[dict]) -> str:
    return "\n".join(f"- {s['title']} ({s.get('source', '')}) {s['url']}"
                     for s in sources if s.get("url"))


def build_messages(variant: str, text: str, is_briefing: bool,
                   sources: list[dict] | None = None) -> tuple[list[dict], set[str]]:
    allowed = {s["url"] for s in (sources or []) if s.get("url")}
    if variant == "uncapped":
        system = CURRENT_PROMPT.format(n="4 to 6" if is_briefing else "3 to 5")
        if allowed:
            system += SOURCES_RULE.format(articles=_listing(sources))
    elif variant == "tiered":
        system = TIERED_PROMPT.format(n="4 to 6" if is_briefing else "3 to 5")
        if allowed:
            system += TIERED_SOURCES_RULE.format(articles=_listing(sources))
    else:
        raise ValueError(variant)
    return [{"role": "system", "content": system},
            {"role": "user", "content": text[:MAX_CHARS]}], allowed


def _one(line: str, allowed: set[str]):
    text = _clean(line)
    url = ""
    if allowed:
        text, url = _split_source(text, allowed)
    if text.endswith(":") or not (MIN_BULLET_CHARS <= len(text) <= MAX_BULLET_CHARS):
        return None
    return {"text": text, "url": url} if url else text


def parse_flat(raw: str, allowed: set[str] | None = None, max_bullets: int = 8) -> list:
    """The current parser minus the length cap."""
    out, seen = [], set()
    for line in (raw or "").splitlines():
        b = _one(line, allowed or set())
        if b is None:
            continue
        key = b["text"] if isinstance(b, dict) else b
        if key not in seen:
            seen.add(key)
            out.append(b)
    return out[:max_bullets]


_MARKER = re.compile(r"^(\s*)(?:[-*•–—]|\d+[.)])\s+")


def _indent_of(line: str) -> int:
    """Leading whitespace before the bullet marker; -1 for a line without one."""
    m = _MARKER.match(line)
    return len(m.group(1).expandtabs(4)) if m else -1


def parse_tiered(raw: str, allowed: set[str] | None = None, max_top: int = 8) -> list:
    """Two-level reply -> [{"text", "url"?, "sub": [...]}].

    Level is relative, not absolute: the shallowest marker indent seen in the
    reply is the top level, anything deeper is a sub-bullet. A model that
    indents its whole answer by two spaces therefore still yields headlines.
    Sub-bullets of a headline the parser rejected (a heading, an over-long
    line) are dropped with it rather than attached to the previous headline.
    """
    allowed = allowed or set()
    lines = [l for l in (raw or "").splitlines() if l.strip()]
    indents = [_indent_of(l) for l in lines]
    tops = [i for i in indents if i >= 0]
    base = min(tops) if tops else 0
    out: list[dict] = []
    open_parent = False   # the last top-level line was kept
    for line, indent in zip(lines, indents):
        b = _one(line, allowed)
        if indent > base:
            if b is not None and open_parent:
                out[-1].setdefault("sub", []).append(b if isinstance(b, dict) and b.get("url") else
                                                     (b["text"] if isinstance(b, dict) else b))
            continue
        if b is None:
            open_parent = False
            continue
        out.append(b if isinstance(b, dict) else {"text": b})
        open_parent = True
    for b in out:
        if not b.get("url"):
            b.pop("url", None)
    return out[:max_top]


async def to_bullets(variant: str, text: str, is_briefing: bool = False, client=None,
                     sources: list[dict] | None = None, model: str = MODEL_WRITER) -> list:
    if not text or not text.strip():
        return []
    client = client or get_client()
    messages, allowed = build_messages(variant, text, is_briefing, sources)
    response = await client.chat.completions.create(
        model=model, max_tokens=4000, messages=messages)
    raw = completion_text(response, f"{variant} digest")
    return parse_tiered(raw, allowed) if variant == "tiered" else parse_flat(raw, allowed)
