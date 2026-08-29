"""Bullet-point digests of each episode, for the email rather than the ear.

The report tells you an episode exists; it does not tell you whether you want
to hear it. A few concrete bullets do, and they are the only part of the
pipeline written to be *read*, which inverts most of the rules elsewhere:
keep the digits, keep the percent signs, keep the symbols. The TTS normaliser
turns "45%" into "forty-five percent" because that is what a voice needs. An
email that says "forty-five percent" just looks broken.

Input is the spoken script before normalisation, for the same reason.

One call per episode rather than folding this into the summariser's prompt.
The summariser only runs for summarize-mode posts, and across a fortnight of
real runs 60% of the daily text was verbatim episodes that never make a
content call at all — precisely the ones the email had nothing to say about.
One mechanism covers everything.
"""

import re

from .llm import get_client, MODEL_WRITER

# ~30k tokens. Nothing observed comes close (the largest episode in a fortnight
# was 70k chars), but an unbounded prompt on an unattended daily job is a
# standing invitation to a surprise bill.
MAX_DIGEST_CHARS = 120000

MAX_BULLETS = 6
# Every bullet in the real runs landed between 150 and 250 characters. The
# floor is here to drop headings and stray labels, not to shorten anything.
MIN_BULLET_CHARS = 25
MAX_BULLET_CHARS = 240

PROMPT = """You are writing the bullet-point digest of a podcast episode for an \
email that its listener reads over breakfast, to decide what is worth their time.

Write {n} bullets, each one sentence, each carrying a specific claim, number, \
name or finding from the text. Order them by importance.

Rules:
- Say what the piece actually claims, not that it discusses a topic. "Anthropic's \
revenue growth slowed ahead of its IPO" — not "the author covers Anthropic's IPO".
- This is read, not spoken. Keep numerals, percent signs, currency and symbols as \
they are, and convert anything already spelled out for speech back into figures: \
"forty-five percent" becomes 45%, "two-thousand twenty-six" becomes 2026, \
"thirteen billion dollars" becomes $13 billion.
- No preamble, no closing line, no headings, no markdown, no bold.
- One bullet per line. Do not number them or prefix them with any character.
- If the text is a news briefing, give one bullet per story it covers."""

# Appended when the caller knows which articles the text was synthesised from.
# The briefing is written from many sources, so "read the source" is ambiguous
# per bullet unless the model says which one it used.
SOURCES_RULE = """

The text was synthesised from the articles below. End every bullet with the URL \
of the single article it draws on, in the form:

  The bullet sentence. || https://example.com/article

Use a URL from this list verbatim, never one you remember or invent. If a \
bullet draws on no single article, end it with `|| none`.

Articles:
{articles}"""


def _clean(line: str) -> str:
    """Strip whatever bullet furniture the model reached for anyway."""
    line = re.sub(r"^\s*(?:[-*•–—]|\d+[.)])\s*", "", line).strip()
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)          # stray bold
    return line.strip()


def _split_source(text: str, allowed: set[str]) -> tuple[str, str]:
    """Peel a trailing `|| url` off a bullet, keeping only a URL we supplied.

    A model that invents a plausible-looking link is worse than one that gives
    none: the reader clicks it and lands nowhere. Anything not in `allowed` is
    dropped and the bullet stands on its own.
    """
    if "||" not in text:
        return text.strip(), ""
    body, _, tail = text.rpartition("||")
    url = tail.strip().strip("<>").rstrip(".,)")
    return body.strip(), url if url in allowed else ""


def parse_bullets(raw: str, allowed_urls: set[str] | None = None) -> list:
    """Turn a model response into clean bullets, dropping anything odd.

    Returns plain strings, or {"text", "url"} dicts where a bullet named one
    of `allowed_urls` as its source.
    """
    allowed = allowed_urls or set()
    out: list = []
    seen: set[str] = set()
    for line in (raw or "").splitlines():
        text = _clean(line)
        url = ""
        if allowed:
            text, url = _split_source(text, allowed)
        # A trailing colon means a preamble or a heading ("Here are the
        # bullets:", "Key points:"), never a claim. Length alone does not catch
        # those — the preamble is longer than some genuine bullets.
        if text.endswith(":"):
            continue
        if len(text) < MIN_BULLET_CHARS or len(text) > MAX_BULLET_CHARS:
            continue
        if text not in seen:
            seen.add(text)
            out.append({"text": text, "url": url} if url else text)
    return out[:MAX_BULLETS]


async def to_bullets(text: str, is_briefing: bool = False, client=None,
                     sources: list[dict] | None = None) -> list:
    """Digest one episode's script into bullets, each optionally linked."""
    if not text or not text.strip():
        return []
    client = client or get_client()
    n = "4 to 6" if is_briefing else "3 to 5"
    system = PROMPT.format(n=n)
    allowed = {s["url"] for s in (sources or []) if s.get("url")}
    if allowed:
        listing = "\n".join(
            f"- {s['title']} ({s.get('source', '')}) {s['url']}"
            for s in sources if s.get("url")
        )
        system += SOURCES_RULE.format(articles=listing)
    response = await client.chat.completions.create(
        model=MODEL_WRITER,
        max_tokens=1600 if allowed else 1200,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": text[:MAX_DIGEST_CHARS]},
        ],
    )
    return parse_bullets(response.choices[0].message.content, allowed)


async def safe_bullets(text: str, is_briefing: bool = False, client=None,
                       label: str = "", sources: list[dict] | None = None) -> list:
    """to_bullets with the failure swallowed and logged.

    A digest is a nicety on top of an episode that already exists. It must
    never be the reason a run fails or a finished MP3 is thrown away.
    """
    try:
        return await to_bullets(text, is_briefing, client, sources)
    except Exception as exc:
        print(f"    Digest failed for {label or 'episode'}: {exc!r}")
        return []
