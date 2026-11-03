"""Whether two posts are one text published twice, from their HTML, with no model calls.

A post reposted elsewhere, such as Scott Alexander's crossposts from Astral
Codex Ten to LessWrong, comes with a new guid, a new link and sometimes a new
title, so only its text shows that it was narrated already. Two posts count as
one when most of each is in the other, so neither a reply that quotes a post
at length nor a short post quoted whole inside a long one counts.
"""

import re

from .html_text import clean_html

# Measured on 3 Nov 2026 over 12-word runs: four of Scott Alexander's
# LessWrong crossposts share 98 to 100% with the ACX original; Zvi's reply to
# "Against SURA", which quotes it, shares 2%; and no two of the 42 posts then
# stored share more than 2.1%.
RUN_WORDS = 12
SAME_TEXT_SHARE = 0.5


def word_runs(html: str) -> frozenset[int]:
    """Hashes of every run of RUN_WORDS consecutive words, ignoring markup, case and punctuation.

    The hashes are only comparable within one process (Python salts str hashes).
    """
    text = clean_html(html).lower().replace("’", "'").replace("‘", "'")
    words = re.findall(r"[a-z0-9']+", text)
    return frozenset(hash(" ".join(words[i:i + RUN_WORDS]))
                     for i in range(len(words) - RUN_WORDS + 1))


def same_text(a: frozenset[int], b: frozenset[int]) -> bool:
    """Whether most of each text is in the other. A text with no runs matches nothing."""
    if not a or not b:
        return False
    return len(a & b) / max(len(a), len(b)) >= SAME_TEXT_SHARE
