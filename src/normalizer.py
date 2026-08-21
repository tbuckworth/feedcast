"""TTS text normalization using LLM."""

import re

from .llm import get_client, MODEL_NORMALIZER

# One request's worth of input. Normalisation EXPANDS text — "1,234" becomes
# nine words — so the output ceiling has to clear this comfortably.
MAX_BATCH_CHARS = 18000

# Measured on a real 17,458-char batch: Gemini 3 Flash returned 3,698 output
# tokens, so this is ~2x headroom. It is a ceiling, not a spend. Raise it if
# MAX_BATCH_CHARS or MODEL_NORMALIZER changes — a thinking model bills its
# reasoning against this too, and gemini-3.7-flash needed 8,547 for the same
# input, which truncates at 8,000.
MAX_OUTPUT_TOKENS = 12000


class NormalizationTruncated(RuntimeError):
    """The model hit its output ceiling, so the tail of the text is missing."""

NORMALIZE_PROMPT = """\
You are a text normalizer preparing written text for text-to-speech (TTS) synthesis.

Convert the text so it reads naturally when spoken aloud. Apply these rules:

1. Numbers to words: "1,234" → "one thousand two hundred thirty-four", "42" → "forty-two"
2. Dates to spoken form: "2026-02-07" → "February seventh, twenty twenty-six", "02/07/2026" → "February seventh, twenty twenty-six"
3. Percentages: "45%" → "forty-five percent"
4. Currency: "$1.5M" → "one point five million dollars", "$42" → "forty-two dollars"
5. Fractions: "1/3" → "one third", "3/4" → "three quarters"
6. Abbreviations: "e.g." → "for example", "i.e." → "that is", "etc." → "etcetera", "vs." → "versus", "approx." → "approximately"
7. URLs: Remove or describe briefly (e.g., "link to example dot com")
8. Special characters: "&" → "and", "%" → "percent", "+" → "plus", "=" → "equals"
9. Remove markdown formatting artifacts (**, ##, -, etc.) while preserving the text
10. Ordinals: "1st" → "first", "2nd" → "second", "23rd" → "twenty-third"

IMPORTANT: Preserve ALL other text exactly as-is. Do not summarize, rephrase, or remove any content. Only transform the specific patterns listed above. Output ONLY the normalized text with no preamble."""


class TextNormalizer:
    """Normalizes text for TTS using MODEL_NORMALIZER via OpenRouter."""

    def __init__(self):
        self.client = get_client()

    async def normalize_for_tts(self, text: str) -> str:
        """Normalize text for TTS: convert numbers, dates, symbols to spoken form."""
        if not text.strip():
            return text

        # For long texts, split into paragraph batches to stay within token limits
        if len(text) > MAX_BATCH_CHARS:
            return await self._normalize_in_batches(text)

        return await self._normalize_chunk(text)

    async def _normalize_chunk(self, text: str) -> str:
        """Normalize a single chunk of text."""
        response = await self.client.chat.completions.create(
            model=MODEL_NORMALIZER,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": NORMALIZE_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        choice = response.choices[0]

        # A truncated completion is indistinguishable from a complete one in the
        # returned text: the episode simply ends mid-article and the MP3 stops.
        # Fail loudly instead — the run reports the entry and the rest continue.
        if choice.finish_reason == "length":
            raise NormalizationTruncated(
                f"{MODEL_NORMALIZER} hit its {MAX_OUTPUT_TOKENS}-token output "
                f"ceiling on a {len(text)}-char chunk; text would be silently "
                f"cut short"
            )
        return choice.message.content

    @staticmethod
    def _split_oversized(paragraph: str) -> list[str]:
        """Break a paragraph that is itself larger than a batch, at sentences.

        Batching alone cannot bound this: appending an over-long paragraph to an
        empty batch flushes the *previous* batch, never the paragraph, so a
        single huge one would be sent whole.
        """
        if len(paragraph) <= MAX_BATCH_CHARS:
            return [paragraph]
        pieces, current = [], ""
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            if current and len(current) + len(sentence) + 1 > MAX_BATCH_CHARS:
                pieces.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            pieces.append(current)
        # A single sentence longer than the cap still has to be cut somewhere.
        out = []
        for piece in pieces:
            while len(piece) > MAX_BATCH_CHARS:
                out.append(piece[:MAX_BATCH_CHARS])
                piece = piece[MAX_BATCH_CHARS:]
            if piece:
                out.append(piece)
        return out

    async def _normalize_in_batches(self, text: str) -> str:
        """Split long text into paragraph batches and normalize each."""
        paragraphs = [
            piece
            for para in text.split("\n\n")
            for piece in self._split_oversized(para)
        ]
        batches: list[list[str]] = []
        current_batch: list[str] = []
        current_len = 0

        for para in paragraphs:
            # Count the "\n\n" the join will add, or a post made of many short
            # list items overshoots the cap by two characters per paragraph —
            # enough to blow past it entirely and defeat the bound.
            extra = len(para) + (2 if current_batch else 0)
            if current_batch and current_len + extra > MAX_BATCH_CHARS:
                batches.append(current_batch)
                current_batch = []
                current_len = 0
                extra = len(para)
            current_batch.append(para)
            current_len += extra

        if current_batch:
            batches.append(current_batch)

        normalized_parts = []
        for batch in batches:
            batch_text = "\n\n".join(batch)
            normalized = await self._normalize_chunk(batch_text)
            normalized_parts.append(normalized)

        return "\n\n".join(normalized_parts)
