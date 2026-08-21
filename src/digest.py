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
they are.
- No preamble, no closing line, no headings, no markdown, no bold.
- One bullet per line. Do not number them or prefix them with any character.
- If the text is a news briefing, give one bullet per story it covers."""


def _clean(line: str) -> str:
    """Strip whatever bullet furniture the model reached for anyway."""
    line = re.sub(r"^\s*(?:[-*•–—]|\d+[.)])\s*", "", line).strip()
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)          # stray bold
    return line.strip()


def parse_bullets(raw: str) -> list[str]:
    """Turn a model response into clean bullets, dropping anything odd."""
    out: list[str] = []
    for line in (raw or "").splitlines():
        text = _clean(line)
        # A trailing colon means a preamble or a heading ("Here are the
        # bullets:", "Key points:"), never a claim. Length alone does not catch
        # those — the preamble is longer than some genuine bullets.
        if text.endswith(":"):
            continue
        if len(text) < MIN_BULLET_CHARS or len(text) > MAX_BULLET_CHARS:
            continue
        if text not in out:
            out.append(text)
    return out[:MAX_BULLETS]


async def to_bullets(text: str, is_briefing: bool = False, client=None) -> list[str]:
    """Digest one episode's script into bullets."""
    if not text or not text.strip():
        return []
    client = client or get_client()
    n = "4 to 6" if is_briefing else "3 to 5"
    response = await client.chat.completions.create(
        model=MODEL_WRITER,
        max_tokens=1200,
        messages=[
            {"role": "system", "content": PROMPT.format(n=n)},
            {"role": "user", "content": text[:MAX_DIGEST_CHARS]},
        ],
    )
    return parse_bullets(response.choices[0].message.content)


async def safe_bullets(text: str, is_briefing: bool = False, client=None,
                       label: str = "") -> list[str]:
    """to_bullets with the failure swallowed and logged.

    A digest is a nicety on top of an episode that already exists. It must
    never be the reason a run fails or a finished MP3 is thrown away.
    """
    try:
        return await to_bullets(text, is_briefing, client)
    except Exception as exc:
        print(f"    Digest failed for {label or 'episode'}: {exc!r}")
        return []
