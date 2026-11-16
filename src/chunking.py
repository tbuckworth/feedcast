"""Cutting text into pieces no longer than a limit, at the most natural break that fits,
and into its sentences.

The pieces are used where a request takes bounded text: TTS chunks
(audio.MAX_CHUNK_CHARS) and normaliser batches (normalizer.MAX_BATCH_CHARS).
The sentences are used where one must stand alone: the sentence of a prediction
market's rules that says how it resolves (markets.rule_sentence).
"""

import re

# Where a piece may be cut. Looser than SENTENCE_END on purpose: a piece only
# has to end somewhere a voice or a model can pause, which the full stop of
# "e.g." or "U.S." is, and every place it may not cut makes a long sentence
# harder to fit in the limit.
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
CLAUSE_BREAK = re.compile(r"(?<=,)\s+")

# Where one sentence ends and the next begins: closing punctuation, any closing
# quote or bracket, a space, then a capital, a digit or an opening quote.
SENTENCE_END = re.compile(r"""(?<=[.!?])["'”’)\]]*\s+(?=["'“‘(\[]?[A-Z0-9])""")
# A full stop that ends an abbreviation or an initial, not a sentence.
_ABBREVIATION = re.compile(
    r"(?:\b(?:e\.g|i\.e|vs|etc|Inc|Mr|Dr|[ap]\.m|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\."
    r"|(?:[A-Z]\.){2,}|(?:^|\s)[A-Z]\.)$")


def sentences(text: str) -> list[str]:
    """`text` as its sentences, in order, each with its spaces collapsed.

    A line break always ends a sentence. A full stop after an abbreviation
    ("e.g.", "11:59 p.m.", "Dec."), in an initialism ("U.S.") or after an
    initial ("Donald J. Trump") does not, so a sentence that really ends on
    one of these runs on into the next.
    """
    out = []
    for line in text.splitlines():
        line = " ".join(line.split())
        start = 0
        for m in SENTENCE_END.finditer(line):
            if not _ABBREVIATION.search(line[start:m.start()]):
                out.append(line[start:m.end()].strip())
                start = m.end()
        out.append(line[start:])
    return [s for s in out if s]


def pack(pieces: list[str], limit: int, sep: str) -> list[list[str]]:
    """Group consecutive `pieces` greedily, so each group joined by `sep` fits in `limit`.

    A piece longer than `limit` is cut every `limit` characters, each cut a
    group of its own, so no group is over the limit.
    """
    groups: list[list[str]] = []
    current: list[str] = []
    size = 0
    for piece in pieces:
        if len(piece) > limit:
            if current:
                groups.append(current)
            groups += [[piece[i:i + limit]] for i in range(0, len(piece), limit)]
            current, size = [], 0
        elif current and size + len(sep) + len(piece) <= limit:
            current.append(piece)
            size += len(sep) + len(piece)
        else:
            if current:
                groups.append(current)
            current, size = [piece], len(piece)
    if current:
        groups.append(current)
    return groups


def split_sentences(text: str, limit: int, *, at_commas: bool = False) -> list[str]:
    """`text` in pieces of at most `limit` characters, broken at sentence ends.

    A sentence longer than `limit` starts a new piece; with `at_commas` it is
    broken at its commas, and the sentences after it pack on from its last
    clause. Pieces are stripped, and empty ones dropped.
    """
    runs: list[list[str]] = [[]]
    for sentence in SENTENCE_BREAK.split(text):
        if len(sentence) > limit:
            runs.append(CLAUSE_BREAK.split(sentence) if at_commas else [sentence])
        else:
            runs[-1].append(sentence)
    pieces = (" ".join(group).strip() for run in runs for group in pack(run, limit, " "))
    return [p for p in pieces if p]
