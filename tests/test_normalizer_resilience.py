"""One paragraph the model will not normalise must not cost the episode.

On 2026-09-06 and again on 2026-09-08 a 58k-char ACX review failed in the
normaliser with `'NoneType' object is not subscriptable`: OpenRouter returned a
200 with no choices for one batch. The batch is now halved until the paragraph
is isolated, and that paragraph is narrated as written.
"""

import asyncio
from types import SimpleNamespace as NS

import pytest

from src.normalizer import (
    MAX_BATCH_CHARS, MIN_FALLBACK_CHARS, NormalizationTruncated, TextNormalizer,
)


def _normalizer(poison: str, finish="stop"):
    """A normaliser whose model returns no choices for any batch containing `poison`."""
    n = TextNormalizer.__new__(TextNormalizer)
    n.unnormalized_chars = 0
    calls: list[str] = []

    async def create(**kw):
        text = kw["messages"][1]["content"]
        calls.append(text)
        if poison in text:
            return NS(choices=None, model_extra={"error": {"message": "filtered"}})
        return NS(choices=[NS(message=NS(content=text.upper(), refusal=None),
                              finish_reason=finish)])

    n.client = NS(chat=NS(completions=NS(create=create)))
    return n, calls


def test_clean_text_is_normalised_in_one_call():
    n, calls = _normalizer(poison="NEVER")
    assert asyncio.run(n.normalize_for_tts("one.\n\ntwo.")) == "ONE.\n\nTWO."
    assert len(calls) == 1 and n.unnormalized_chars == 0


def test_offending_paragraph_is_isolated_and_kept_as_written():
    paras = ["alpha one.", "beta two.", "gamma POISON three.", "delta four."]
    n, calls = _normalizer(poison="POISON")
    out = asyncio.run(n.normalize_for_tts("\n\n".join(paras)))
    assert out.split("\n\n") == ["ALPHA ONE.", "BETA TWO.", "gamma POISON three.", "DELTA FOUR."]
    assert n.unnormalized_chars == len("gamma POISON three.")
    # whole -> two halves -> the bad half split again: the good half of each
    # split succeeds in one call, so five calls, not one per paragraph.
    assert len(calls) == 5


def test_long_text_loses_nothing_around_a_bad_batch():
    good = ["Sentence number %d is fine." % i for i in range(1, 2001)]
    good.insert(1000, "This one has POISON in it.")
    text = "\n\n".join(good)
    assert len(text) > MAX_BATCH_CHARS  # exercises the batching path
    n, _ = _normalizer(poison="POISON")
    out = asyncio.run(n.normalize_for_tts(text)).split("\n\n")
    assert len(out) == len(good)
    assert out[1000] == "This one has POISON in it."
    assert all(p == g.upper() for p, g in zip(out, good) if "POISON" not in g)


def test_single_long_paragraph_is_narrowed_to_the_offending_sentences():
    # Single-newline prose (ACX) reaches the normaliser as one paragraph; the
    # 2026-09-08 fallback then passed 17,909 chars through as written.
    sentences = [f"Sentence number {i} says something ordinary and fine." for i in range(120)]
    sentences[60] = "This sentence carries the POISON the filter objects to."
    text = " ".join(sentences)
    assert len(text) > MIN_FALLBACK_CHARS
    n, _ = _normalizer(poison="POISON")
    out = asyncio.run(n.normalize_for_tts(text))
    assert "POISON" in out and "SENTENCE NUMBER 0" in out and "SENTENCE NUMBER 119" in out
    # The raw remainder is a handful of sentences, not the paragraph.
    assert n.unnormalized_chars <= MIN_FALLBACK_CHARS
    assert n.unnormalized_chars < len(text) / 4
    assert len(out.split()) == len(text.split())          # nothing dropped or duplicated


def test_short_passage_falls_back_whole_rather_than_splitting_forever():
    n, calls = _normalizer(poison="POISON")
    text = "Short one. Has POISON here. Done."
    assert asyncio.run(n.normalize_for_tts(text)) == text
    assert len(calls) == 1 and n.unnormalized_chars == len(text)


def test_truncation_still_fails_loudly():
    n, _ = _normalizer(poison="NEVER", finish="length")
    with pytest.raises(NormalizationTruncated):
        asyncio.run(n.normalize_for_tts("some text."))
