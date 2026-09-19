"""Live, bounded LLM smoke check. No feeds, database, TTS, mail, or publishing.

Run with `bwsrun uv run python -m scripts.check_llm`, or dispatch update-feed.yml
with llm_smoke_test=true to check the actual GitHub Actions secrets.
"""

import asyncio

from src.digest import safe_bullets
from src.llm import fallback_log
from src.news import NewsAggregator
from src.normalizer import TextNormalizer
from src.verify import check


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
    print("PASS: briefing and fidelity check")

    # Availability alone is not enough: the backup must parse and catch an
    # obvious factual error using the real checker's prompt and token settings.
    _, flags = await check("The lab evaluated 999 systems.", "The lab evaluated 100 systems.")
    if not any(f["severity"] in ("medium", "high") for f in flags):
        raise RuntimeError("Checker missed the deliberate numeric contradiction")
    print("PASS: checker catches a deliberate contradiction")

    normalized = await TextNormalizer().normalize_for_tts("The lab reported that 45% passed.")
    if not normalized.strip() or "%" in normalized or "45" in normalized:
        raise RuntimeError("Normalizer did not convert the percentage")
    print("PASS: TTS normalization (text only)")

    bullets = await safe_bullets(briefing, is_briefing=True, label="Fictional smoke test")
    if not bullets:
        raise RuntimeError("Bullet digest returned no bullets")
    print("PASS: bullet digest")
    print(f"All live LLM checks passed; {len(fallback_log)} fallback notices.")


if __name__ == "__main__":
    asyncio.run(main())
