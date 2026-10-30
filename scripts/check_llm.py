"""Live, bounded LLM smoke check. No feeds, database, TTS, mail, or publishing.

Run with `bwsrun uv run python -m scripts.check_llm`, or dispatch update-feed.yml
with llm_smoke_test=true to check the actual GitHub Actions secrets.
"""

import asyncio

from src.digest import safe_bullets
from src.llm import fallback_notices, model_name
from src.news import NewsAggregator
from src.normalizer import TextNormalizer
from src.verify import check

# Text for the normaliser, and what must be gone once it is spoken. Every case
# has digits, so none may come back with any.
NORMALIZER_CASES = {
    "dates_iso": ("The paper was published on 2026-02-07 and revised on 2026-03-15.", []),
    "dates_us": ("The meeting is scheduled for 02/14/2026 and the deadline is 12/31/2026.", ["/"]),
    "dates_relative": ("On Jan 3rd, 2025, the 1st version was released. "
                       "The 23rd revision came on Nov 2nd.", []),
    "large_numbers": ("The model has 175,000,000,000 parameters and was trained on "
                      "1.4 trillion tokens over 34 days.", []),
    "decimals": ("The loss decreased from 3.14159 to 0.0042, a 99.87% improvement.", ["%"]),
    "currency": ("OpenAI raised $6.6B at a $157B valuation. The compute cost was $100M.", ["$"]),
    "percentages": ("The accuracy improved from 78.3% to 94.7%, while the false positive "
                    "rate dropped to 0.2%.", ["%"]),
    "abbreviations": ("The model (e.g. GPT-4) uses RLHF, i.e. reinforcement learning from "
                      "human feedback, etc.", ["e.g.", "i.e.", "etc."]),
    "mixed_content": (
        "On 2026-01-15, Anthropic released Claude 4.5 with 2x the context window. "
        "The benchmark scores improved by 23.4% vs. the previous version. "
        "Training cost approx. $50M over 90 days on 10,000 H100 GPUs. "
        "See https://anthropic.com/research for details.",
        ["%", "$", "vs.", "approx.", "https://"]),
    "date_pronunciation": (
        "The events of September 11th, 2001 changed the world. "
        "By 2024-06-15, 23 years had passed. "
        "The 1st amendment was ratified on 12/15/1791.", ["/"]),
}


async def main():
    articles = [
        {"title": "A fictional lab publishes an evaluation", "source": "Test News",
         "category": "ai_safety", "url": "https://example.com/evaluation",
         "summary": "In this fictional test, a lab evaluated 100 systems. "
                    "45 passed. It released its methods and results."},
        {"title": "A fictional council funds safety research", "source": "Test News",
         "category": "ai_safety", "url": "https://example.com/research",
         "summary": "In this fictional test, a council approved 3 research grants. "
                    "Each grant lasts 2 years. No amounts were announced."},
        {"title": "A fictional shop sells a new mug", "source": "Test News",
         "category": "business", "url": "https://example.com/mug",
         "summary": "A fictional shop introduced a blue mug."},
    ]
    aggregator = NewsAggregator(
        sources=[], full_text_stories=2,
        prompt="Write a short spoken briefing of at most 150 words from the supplied "
               "fictional test stories. Preserve the numbers; invent nothing.",
    )
    selected = await aggregator.select_stories(articles)
    if len(selected) != 2:
        raise RuntimeError("Story selection did not return two known URLs")
    print("PASS: story selection")

    briefing = await aggregator.synthesize_briefing(
        aggregator._format_briefing_input(articles, selected))
    if not briefing.strip() or aggregator.last_fidelity["status"] == "skipped":
        raise RuntimeError("Briefing generation or fidelity check failed")
    print(f"PASS: briefing and fidelity check (written by "
          f"{model_name(aggregator.last_writer['model'])}"
          f"{', a backup' if aggregator.last_writer['backup'] else ''})")

    # Availability alone is not enough: the backup must parse and catch an
    # obvious factual error using the real checker's prompt and token settings.
    _, flags = await check("The lab evaluated 999 systems.", "The lab evaluated 100 systems.")
    if not any(f["severity"] in ("medium", "high") for f in flags):
        raise RuntimeError("Checker missed the deliberate numeric contradiction")
    print("PASS: checker catches a deliberate contradiction")

    normalizer = TextNormalizer()
    spoken = await asyncio.gather(*(normalizer.normalize_for_tts(text)
                                    for text, _ in NORMALIZER_CASES.values()))
    for (name, (_, gone)), normalized in zip(NORMALIZER_CASES.items(), spoken):
        left = [s for s in gone if s in normalized]
        if not normalized.strip() or any(c.isdigit() for c in normalized) or left:
            raise RuntimeError(f"Normalizer left digits or {left} in {name}: {normalized!r}")
    print(f"PASS: TTS normalization, {len(NORMALIZER_CASES)} cases (text only)")

    bullets = await safe_bullets(briefing, is_briefing=True, label="Fictional smoke test")
    if not bullets:
        raise RuntimeError("Bullet digest returned no bullets")
    print("PASS: bullet digest")
    notices = fallback_notices()
    print(f"All live LLM checks passed; {len(notices)} fallback notices.")
    for note in notices:
        print(f"  - {note}")


if __name__ == "__main__":
    asyncio.run(main())
