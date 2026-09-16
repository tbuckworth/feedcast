"""Experimental: a full-detail bullet digest that restates the audio, not a précis of it.

`digest.py` condenses a spoken script to 3-6 bullets of at most 240 characters,
so the email is a summary of a summary. This variant asks the same writer model
to *restructure* the script instead: every claim, figure, name and caveat the
listener hears, in the order they hear it, as bullets a reader can scan. It is
still one model call, but the instruction is "keep everything", not "pick the
best five".

Only wired into `scripts/email_v2_test.py` for now. Nothing in the pipeline
imports this module.
"""

import re

from .digest import SOURCES_RULE, _clean, _split_source
from .llm import MODEL_WRITER, completion_text, get_client

MAX_DIGEST_CHARS = 120000
MAX_BULLETS = 40
MIN_BULLET_CHARS = 25
MAX_BULLET_CHARS = 700

PROMPT = """You are turning the script of a podcast episode into the bullet-point \
version of the same episode, for an email its listener reads instead of, or as \
well as, hearing it.

Cover everything the script says: every claim, figure, name, example, caveat and \
conclusion, in the order the script makes them. Do not condense, select or \
editorialise. Someone who reads the bullets should come away knowing everything \
someone who heard the audio knows. The only things to drop are spoken framing \
("Here is your briefing for...", "Let's begin", transitions) and repetition.

Rules:
- One bullet per distinct point, one or two sentences each. A typical episode \
needs 10 to 25 bullets; a short piece needs fewer. Never pad.
- Say what the piece actually claims, not that it discusses a topic.
- Where the script attributes a view to the author ("Zvi argues", "he worries"), \
keep the attribution.
- This is read, not spoken. Keep numerals, percent signs, currency and symbols, \
and convert anything spelled out for speech back into figures: "forty-five \
percent" becomes 45%, "two thousand twenty-six" becomes 2026, "thirteen billion \
dollars" becomes $13 billion, "five-point-zero-four percent" becomes 5.04%.
- No preamble, no closing line, no headings, no markdown, no bold.
- One bullet per line. Do not number them or prefix them with any character.
- If the text is a news briefing, keep the stories in the order given and start \
each story's FIRST bullet with a short topic label of two to five words and a \
colon, for example "AI safety talks: OpenAI, Anthropic and Google DeepMind..." \
Later bullets on the same story carry no label."""

_LABEL = re.compile(r"^([A-Z][^:.!?]{1,48}?):\s+(?=\S)")


def parse_bullets(raw: str, allowed_urls: set[str] | None = None,
                  is_briefing: bool = False) -> list:
    """Model reply -> bullets. Strings, or {"text", "url", "label"} dicts.

    Same furniture-stripping as `digest.parse_bullets`, with the caps raised:
    this digest is meant to be long. A briefing bullet that opens with a topic
    label keeps it in `label` so the email can set it in bold.
    """
    allowed = allowed_urls or set()
    out: list = []
    seen: set[str] = set()
    for line in (raw or "").splitlines():
        text = _clean(line)
        url = ""
        if allowed:
            text, url = _split_source(text, allowed)
        if text.endswith(":"):
            continue
        if len(text) < MIN_BULLET_CHARS or len(text) > MAX_BULLET_CHARS:
            continue
        if text in seen:
            continue
        seen.add(text)
        label = ""
        if is_briefing:
            m = _LABEL.match(text)
            if m and not any(ch.isdigit() for ch in m.group(1)):
                label, text = m.group(1), text[m.end():]
        if url or label:
            b = {"text": text}
            if url:
                b["url"] = url
            if label:
                b["label"] = label
            out.append(b)
        else:
            out.append(text)
    return out[:MAX_BULLETS]


def build_messages(text: str, is_briefing: bool = False,
                   sources: list[dict] | None = None) -> tuple[list[dict], set[str]]:
    """The exact request body, so a test harness can measure it."""
    system = PROMPT
    allowed = {s["url"] for s in (sources or []) if s.get("url")}
    if allowed:
        listing = "\n".join(
            f"- {s['title']} ({s.get('source', '')}) {s['url']}"
            for s in sources if s.get("url")
        )
        system += SOURCES_RULE.format(articles=listing)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": text[:MAX_DIGEST_CHARS]},
    ]
    return messages, allowed


async def to_bullets(text: str, is_briefing: bool = False, client=None,
                     sources: list[dict] | None = None,
                     model: str = MODEL_WRITER) -> list:
    if not text or not text.strip():
        return []
    client = client or get_client()
    messages, allowed = build_messages(text, is_briefing, sources)
    response = await client.chat.completions.create(
        model=model, max_tokens=6000, messages=messages,
    )
    return parse_bullets(completion_text(response, "full digest"), allowed, is_briefing)
