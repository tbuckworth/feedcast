"""Decide whether a post is too maths-heavy to be worth hearing.

Some LessWrong and Alignment Forum posts are built on real mathematics. Even a
good spoken explanation of them is hard to follow without seeing the notation,
so those posts are better linked than narrated: no audio is generated, and the
email lists them with a link to the original.

Detection has to happen on the MARKDOWN, not the RSS content. LessWrong's feed
strips MathJax entirely, and so does the rendered page — MathJax v3 puts glyphs
in CSS pseudo-elements, so BeautifulSoup's get_text() returns nothing for them.
Formulas therefore arrive as holes ("a function f is anytime computable if ___
where ___ is finitely computable"), and scoring that text finds no maths at all.
The GraphQL `contents{markdown}` field preserves the LaTeX.
"""

import re
from dataclasses import dataclass
from typing import Optional

import httpx

# Per 1000 words, re-measured after the inline-LaTeX pattern was tightened to
# exclude currency (which lowered every score). Across 20 recent LessWrong and
# Alignment Forum posts the mathematical ones now score 99.0, 23.1 and 9.8, and
# every prose post scores 6.6 or below. 8 sits in that gap.
#
# Recalibrate this whenever _PATTERNS changes — the two numbers are coupled, and
# a pattern change silently moves every score.
DEFAULT_THRESHOLD = 8.0

# A density alone is not enough. On a short post two matches can clear 10/1000
# words, and being wrong here is expensive and silent: the post gets no audio
# and is marked processed, so it never comes back. Require real volume too.
MIN_HITS = 8

_LW_HOSTS = ("lesswrong.com", "alignmentforum.org")
_POST_ID = re.compile(r"/posts/([A-Za-z0-9]{17})")
_UA = {"User-Agent": "Mozilla/5.0 (feedcast)"}

_PATTERNS = [
    # Inline LaTeX. The lookahead demands a genuinely mathematical character
    # inside the delimiters, so prose about money — "raised $10M at a $1B
    # valuation" — is not read as an equation. Costs us bare "$D$"-style
    # single letters, which is the right trade: a false negative merely
    # narrates a post, a false positive deletes it.
    r"\$(?=[^$\n]*[\\=^_{}])[^$\n]{1,120}\$",
    r"\\\(", r"\\\[",                           # alternative delimiters
    r"\\begin\{(align|equation|cases|matrix)",  # display environments
    r"\\frac", r"\\sum", r"\\prod", r"\\int", r"\\lim",
    r"\\mathbb", r"\\mathcal", r"\\infty",
    r"\\leq", r"\\geq", r"\\in\b", r"\\forall", r"\\exists",
]


@dataclass
class MathsVerdict:
    """Why a post was or was not judged too mathematical for audio."""

    is_heavy: bool
    score: float          # matches per 1000 words
    hits: int
    source: str           # "markdown" (authoritative) or "rss" (maths may be stripped)


def maths_score(text: str) -> tuple[int, float]:
    """Return (raw hits, hits per 1000 words)."""
    if not text:
        return 0, 0.0
    hits = sum(len(re.findall(p, text)) for p in _PATTERNS)
    words = max(1, len(text.split()))
    return hits, hits / words * 1000


def lesswrong_post_id(link: str) -> Optional[str]:
    """Extract the 17-character post id from a LessWrong/Alignment Forum URL."""
    if not link or not any(h in link for h in _LW_HOSTS):
        return None
    m = _POST_ID.search(link)
    return m.group(1) if m else None


def fetch_lesswrong_markdown(link: str, timeout: float = 30.0) -> Optional[str]:
    """Fetch a post's markdown source, where the LaTeX survives.

    Returns None on any failure — a maths check is never worth failing a run
    over, and the caller falls back to scoring whatever text it already had.
    """
    post_id = lesswrong_post_id(link)
    if not post_id:
        return None
    host = "alignmentforum.org" if "alignmentforum" in link else "lesswrong.com"
    query = ('{post(input:{selector:{_id:"%s"}}){result{contents{markdown}}}}'
             % post_id)
    try:
        r = httpx.post(f"https://www.{host}/graphql", json={"query": query},
                       timeout=timeout, headers=_UA)
        r.raise_for_status()
        data = r.json()
        return (((data.get("data") or {}).get("post") or {})
                .get("result", {}).get("contents", {}).get("markdown"))
    except Exception:
        return None


def assess(link: str, fallback_text: str,
           threshold: float = DEFAULT_THRESHOLD) -> MathsVerdict:
    """Judge a post, preferring the markdown source when one is reachable."""
    md = fetch_lesswrong_markdown(link)
    text, source = (md, "markdown") if md else (fallback_text, "rss")
    hits, score = maths_score(text)
    return MathsVerdict(is_heavy=score >= threshold and hits >= MIN_HITS,
                        score=round(score, 1), hits=hits, source=source)
