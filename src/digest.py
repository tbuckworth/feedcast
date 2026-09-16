"""Two-level bullet digests of each episode, for the email rather than the ear.

The email is meant to say what the audio says, so a reader can skip the
episode and lose nothing but the voice. A few headline bullets do not do that:
the previous digest asked for 3-6 one-sentence bullets and then dropped any
over 240 characters, and on 2026-09-16 that left the Zvi episode with two
bullets out of five written. The reader's own words for it were "a summary of
the summary".

So each episode gets 4-6 headline bullets, each with 1-4 indented sub-bullets
carrying the figures, names, examples and caveats the script gives for that
point. The headline is what a reader in a hurry reads; the sub-bullets are
what the audio adds. Chosen over an uncapped flat list and a full restatement
after all three were sent side by side.

Input is the spoken script *after* the fidelity check and revision, and never
the source: the bullets are not checked themselves, and the source is exactly
where a bullet the audio never said would come from. The one thing taken from
the source side is the briefing's list of selected articles, so bullets can
carry links. This is the only part of the pipeline written to be *read*, which
inverts most of the rules elsewhere: keep the digits, keep the percent signs.

Written by the "bullets" role (GPT-5.6 Sol, reasoning off). One call per
episode, whatever mode the episode was processed in.
"""

import re

from .llm import complete

# ~30k tokens. Nothing observed comes close (the largest episode in a fortnight
# was 70k chars), but an unbounded prompt on an unattended daily job is a
# standing invitation to a surprise bill.
MAX_DIGEST_CHARS = 120000

MAX_BULLETS = 8            # headlines; the prompt asks for 4-6
# The floor drops headings and stray labels, not content. The ceiling drops a
# paragraph the model returned as one line, rather than render a wall.
MIN_BULLET_CHARS = 25
MAX_BULLET_CHARS = 700

PROMPT = """You are writing the bullet-point digest of a podcast episode for an \
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

# Appended when the caller knows which articles the text was synthesised from.
# The briefing is written from many sources, so "read the source" is ambiguous
# per bullet unless the model says which one it used.
SOURCES_RULE = """

The text was synthesised from the articles below. End each top-level bullet, and \
each sub-bullet that draws on a single article, with the URL of that article, in \
the form:

  - The bullet sentence. || https://example.com/article

Use a URL from this list verbatim, never one you remember or invent. If a bullet \
draws on no single article, give it no URL.

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


def _one(line: str, allowed: set[str]):
    """One line -> a bullet (str, or {"text", "url"}), or None if it is not one."""
    text = _clean(line)
    url = ""
    if allowed:
        text, url = _split_source(text, allowed)
    # A trailing colon means a preamble or a heading ("Here are the bullets:",
    # "Key points:"), never a claim. Length alone does not catch those — the
    # preamble is longer than some genuine bullets.
    if text.endswith(":") or not (MIN_BULLET_CHARS <= len(text) <= MAX_BULLET_CHARS):
        return None
    return {"text": text, "url": url} if url else text


_MARKER = re.compile(r"^(\s*)(?:[-*•–—]|\d+[.)])\s+")


def _indent_of(line: str) -> int:
    """Leading whitespace before the bullet marker; -1 for a line without one."""
    m = _MARKER.match(line)
    return len(m.group(1).expandtabs(4)) if m else -1


def parse_bullets(raw: str, allowed_urls: set[str] | None = None) -> list:
    """Turn a model response into clean bullets, dropping anything odd.

    Returns plain strings, or {"text", "url"?, "sub"?} dicts where a bullet
    names one of `allowed_urls` as its source or has sub-bullets beneath it.

    Level is relative, not absolute: the shallowest marker indent in the reply
    is the top level and anything deeper is a sub-bullet, so a model that
    indents its whole answer still yields headlines. Sub-bullets of a headline
    the parser rejected go with it rather than attaching to the previous one.
    """
    allowed = allowed_urls or set()
    lines = [l for l in (raw or "").splitlines() if l.strip()]
    indents = [_indent_of(l) for l in lines]
    tops = [i for i in indents if i >= 0]
    base = min(tops) if tops else 0
    out: list = []
    seen: set[str] = set()
    open_parent = False   # the last top-level line was kept
    for line, indent in zip(lines, indents):
        b = _one(line, allowed)
        if indent > base:
            if b is not None and open_parent:
                parent = out[-1]
                if not isinstance(parent, dict):
                    parent = out[-1] = {"text": parent}
                parent.setdefault("sub", []).append(b)
            continue
        if b is None:
            open_parent = False
            continue
        key = b["text"] if isinstance(b, dict) else b
        if key in seen:
            open_parent = False
            continue
        seen.add(key)
        out.append(b)
        open_parent = True
    return out[:MAX_BULLETS]


def build_messages(text: str, is_briefing: bool = False,
                   sources: list[dict] | None = None) -> tuple[list[dict], set[str]]:
    """The exact request, so a test harness can measure it."""
    system = PROMPT.format(n="4 to 6" if is_briefing else "3 to 5")
    allowed = {s["url"] for s in (sources or []) if s.get("url")}
    if allowed:
        listing = "\n".join(
            f"- {s['title']} ({s.get('source', '')}) {s['url']}"
            for s in sources if s.get("url")
        )
        system += SOURCES_RULE.format(articles=listing)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": text[:MAX_DIGEST_CHARS]},
    ], allowed


async def to_bullets(text: str, is_briefing: bool = False, client=None,
                     sources: list[dict] | None = None, label: str = "") -> list:
    """Digest one episode's script into two-level bullets, linked where possible."""
    if not text or not text.strip():
        return []
    messages, allowed = build_messages(text, is_briefing, sources)
    done = await complete("bullets", messages, max_tokens=6000, client=client,
                          label=f"digest ({label})" if label else "digest")
    return parse_bullets(done.text, allowed)


async def safe_bullets(text: str, is_briefing: bool = False, client=None,
                       label: str = "", sources: list[dict] | None = None) -> list:
    """to_bullets with the failure swallowed and logged.

    A digest is a nicety on top of an episode that already exists. It must
    never be the reason a run fails or a finished MP3 is thrown away.
    """
    try:
        return await to_bullets(text, is_briefing, client, sources, label)
    except Exception as exc:
        print(f"    Digest failed for {label or 'episode'}: {exc!r}")
        return []
