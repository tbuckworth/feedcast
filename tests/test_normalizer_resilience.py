"""One paragraph the model will not normalise must not cost the episode.

On 2026-09-06 and again on 2026-09-08 a 58k-char ACX review failed in the
normaliser with `'NoneType' object is not subscriptable`: OpenRouter returned a
200 with no choices for one batch. The batch is now halved until the paragraph
is isolated, and that paragraph is narrated as written.
"""

import asyncio
from types import SimpleNamespace as NS

import pytest

from src.normalizer import MAX_BATCH_CHARS, NormalizationTruncated, TextNormalizer


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


def test_truncation_still_fails_loudly():
    n, _ = _normalizer(poison="NEVER", finish="length")
    with pytest.raises(NormalizationTruncated):
        asyncio.run(n.normalize_for_tts("some text."))
