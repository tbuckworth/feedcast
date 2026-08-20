"""Tests for TTS normalization batching and truncation handling."""

import asyncio

import pytest

from src.normalizer import (
    MAX_BATCH_CHARS, MAX_OUTPUT_TOKENS, NormalizationTruncated, TextNormalizer,
)


class TestSplitOversized:
    def test_short_paragraph_untouched(self):
        assert TextNormalizer._split_oversized("hello there") == ["hello there"]

    def test_exactly_at_cap_untouched(self):
        para = "x" * MAX_BATCH_CHARS
        assert TextNormalizer._split_oversized(para) == [para]

    def test_oversized_paragraph_is_split(self):
        pieces = TextNormalizer._split_oversized("word " * 8000)
        assert len(pieces) > 1
        assert all(len(p) <= MAX_BATCH_CHARS for p in pieces)

    def test_prefers_sentence_boundaries(self):
        para = ("This is a sentence. " * 2000)
        pieces = TextNormalizer._split_oversized(para)
        assert all(len(p) <= MAX_BATCH_CHARS for p in pieces)
        # Nothing should be cut mid-word when sentences are available
        assert all(p.strip().endswith(".") for p in pieces)

    def test_single_sentence_longer_than_cap_still_bounded(self):
        """No sentence boundary to use — must still be cut, not sent whole."""
        pieces = TextNormalizer._split_oversized("x" * 40000)
        assert all(len(p) <= MAX_BATCH_CHARS for p in pieces)
        assert sum(len(p) for p in pieces) == 40000

    def test_nothing_is_lost(self):
        para = "Alpha beta gamma. " * 3000
        assert "".join(TextNormalizer._split_oversized(para)).replace(" ", "") \
            == para.replace(" ", "")


class TestTruncationIsLoud:
    """asyncio.run rather than pytest-asyncio, so the suite needs no extra dep."""

    @staticmethod
    def _stub(finish_reason: str, text: str = "normalised text"):
        n = TextNormalizer()
        seen = {}

        class Msg:
            content = text

        class Choice:
            pass

        Choice.finish_reason = finish_reason
        Choice.message = Msg()

        class Resp:
            choices = [Choice()]

        async def fake(**kw):
            seen.update(kw)
            return Resp()

        n.client.chat.completions.create = fake
        return n, seen

    def test_length_finish_reason_raises(self):
        """A truncated completion looks identical to a complete one in the text,
        so it must raise rather than silently ship half an episode."""
        n, seen = self._stub("length", "partial text")
        with pytest.raises(NormalizationTruncated):
            asyncio.run(n._normalize_chunk("some text"))
        assert seen["max_tokens"] == MAX_OUTPUT_TOKENS

    def test_normal_finish_returns_text(self):
        n, _ = self._stub("stop")
        assert asyncio.run(n._normalize_chunk("some text")) == "normalised text"

    def test_batching_splits_an_oversized_paragraph(self):
        """End to end: one huge paragraph must arrive as several bounded calls."""
        n, _ = self._stub("stop")
        calls = []

        async def fake_chunk(text):
            calls.append(len(text))
            return text

        n._normalize_chunk = fake_chunk
        asyncio.run(n.normalize_for_tts("word " * 12000))
        assert len(calls) > 1
        assert all(c <= MAX_BATCH_CHARS for c in calls)
