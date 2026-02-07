"""TTS text normalization using Claude Haiku."""

from anthropic import AsyncAnthropic

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
    """Normalizes text for TTS using Claude Haiku."""

    def __init__(self):
        self.client = AsyncAnthropic()

    async def normalize_for_tts(self, text: str) -> str:
        """Normalize text for TTS: convert numbers, dates, symbols to spoken form."""
        if not text.strip():
            return text

        # For long texts, split into paragraph batches to stay within token limits
        if len(text) > 20000:
            return await self._normalize_in_batches(text)

        return await self._normalize_chunk(text)

    async def _normalize_chunk(self, text: str) -> str:
        """Normalize a single chunk of text."""
        response = await self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            system=NORMALIZE_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        return response.content[0].text

    async def _normalize_in_batches(self, text: str) -> str:
        """Split long text into paragraph batches and normalize each."""
        paragraphs = text.split("\n\n")
        batches: list[list[str]] = []
        current_batch: list[str] = []
        current_len = 0

        for para in paragraphs:
            if current_len + len(para) > 18000 and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_len = 0
            current_batch.append(para)
            current_len += len(para)

        if current_batch:
            batches.append(current_batch)

        normalized_parts = []
        for batch in batches:
            batch_text = "\n\n".join(batch)
            normalized = await self._normalize_chunk(batch_text)
            normalized_parts.append(normalized)

        return "\n\n".join(normalized_parts)
