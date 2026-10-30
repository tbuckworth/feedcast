"""Cutting text into pieces no longer than a limit, at the most natural break that fits.

Used where a request takes bounded text: TTS chunks (audio.MAX_CHUNK_CHARS)
and normaliser batches (normalizer.MAX_BATCH_CHARS).
"""

import re

SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
CLAUSE_BREAK = re.compile(r"(?<=,)\s+")


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
