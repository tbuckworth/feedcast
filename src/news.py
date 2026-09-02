"""Daily news briefing via RSS aggregation and LLM synthesis."""

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone

import feedparser

from .bundle import writer_bundle
from .extractor import extract_article
from .llm import get_client, MODEL_STRONG
from .monitor import FeedEntry, warn_if_dead
from .verify import fidelity_markdown, verify_script

SELECT_PROMPT = """You are choosing which stories a daily news briefing will cover, from a list of RSS headlines with short blurbs.

Pick the {n} most worth covering for a technically sophisticated audience, in priority order: AI safety and policy first, then AI capabilities, geopolitics, economics, markets. Prefer one strong item per story over several near-duplicates. Skip trivia, listicles and product fluff.

Return ONLY a JSON array of the chosen URLs, copied exactly from the list."""


class NewsAggregator:
    """Aggregates news from multiple RSS sources and synthesizes a daily briefing."""

    def __init__(
        self,
        sources: list[dict],
        prompt: str,
        lookback_hours: int = 48,
        recent_briefings: list[dict] | None = None,
        full_text_stories: int = 12,
        max_article_chars: int = 6000,
        verify: bool = True,
    ):
        self.sources = sources
        self.prompt = prompt
        self.lookback_hours = lookback_hours
        self.last_bundle: str | None = None
        self.last_fidelity: dict | None = None
        # Two calls, not one. The writer used to see only each item's RSS
        # blurb (a title and up to 500 characters the publisher wrote), so
        # everything beyond that in the briefing came from the model's memory.
        # Now it first picks the stories worth covering from the blurbs, then
        # writes from those articles' full text. Roughly three times the
        # tokens of the old single call; a tenth of fetching everything.
        self.full_text_stories = full_text_stories
        self.max_article_chars = max_article_chars
        self.verify = verify
        self.recent_briefings = recent_briefings or []
        self.client = get_client()
        # Sources that returned nothing this run. A dead feed reads as a slow
        # news day, so the briefing silently narrows without anyone noticing.
        self.dead_sources: list[str] = []

    async def fetch_all_sources(self) -> list[dict]:
        """Fetch all RSS sources in parallel, filtering to recent articles."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)

        async def fetch_one(source: dict) -> list[dict]:
            feed = await asyncio.to_thread(feedparser.parse, source["url"])
            if warn_if_dead(feed, source["name"], source["url"]):
                if source["name"] not in self.dead_sources:
                    self.dead_sources.append(source["name"])
                return []
            articles = []
            for entry in feed.entries:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                if published is None or published < cutoff:
                    continue

                summary = ""
                if hasattr(entry, "summary"):
                    summary = entry.summary
                elif hasattr(entry, "description"):
                    summary = entry.description

                articles.append({
                    "title": entry.get("title", "Untitled"),
                    "source": source["name"],
                    "category": source["category"],
                    "summary": summary[:500],
                    "published": published,
                    "url": entry.get("link", ""),
                })
            return articles

        results = await asyncio.gather(
            *[fetch_one(s) for s in self.sources],
            return_exceptions=True,
        )

        all_articles = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"  Warning: failed to fetch {self.sources[i]['name']}: {result}")
                continue
            all_articles.extend(result)

        return all_articles

    def _format_articles_for_prompt(self, articles: list[dict]) -> str:
        """Group articles by category and format as structured text."""
        by_category: dict[str, list[dict]] = {}
        for article in articles:
            by_category.setdefault(article["category"], []).append(article)

        sections = []
        for category, items in sorted(by_category.items()):
            section_lines = [f"## {category.upper().replace('_', ' ')}"]
            for item in items:
                # The URL rides along so the digest can attribute each bullet
                # back to the article it came from.
                url = f"\n  URL: {item['url']}" if item.get("url") else ""
                body = item.get("text") or item["summary"]
                section_lines.append(
                    f"- [{item['source']}] {item['title']}{url}\n  {body}"
                )
            sections.append("\n".join(section_lines))

        return "\n\n".join(sections)

    async def select_stories(self, articles: list[dict]) -> list[dict]:
        """Ask the writer which stories deserve full text. [] means: use blurbs only."""
        n = self.full_text_stories
        if n <= 0 or not articles:
            return []
        if len(articles) <= n:
            return list(articles)
        by_url = {a["url"]: a for a in articles if a.get("url")}
        response = await self.client.chat.completions.create(
            model=MODEL_STRONG, max_tokens=2000,
            messages=[{"role": "system", "content": SELECT_PROMPT.format(n=n)},
                      {"role": "user", "content": self._format_articles_for_prompt(articles)}])
        raw = response.choices[0].message.content or ""
        m = re.search(r"\[.*\]", raw, re.S)
        try:
            urls = json.loads(m.group(0)) if m else []
        except ValueError:
            urls = []
        chosen, seen = [], set()
        for u in urls:
            if isinstance(u, str) and u in by_url and u not in seen:
                seen.add(u); chosen.append(by_url[u])
        return chosen[:n]

    async def fetch_full_text(self, articles: list[dict]) -> int:
        """Fill in article["text"] from the page. Keeps the blurb where fetching fails."""
        sem = asyncio.Semaphore(5)

        async def one(a: dict) -> bool:
            if not a.get("url"):
                return False
            async with sem:
                try:
                    got = await asyncio.wait_for(asyncio.to_thread(extract_article, a["url"]), 45)
                except Exception as e:  # noqa: BLE001 — a paywall is not a failed run
                    print(f"    full text unavailable ({a['source']}): {type(e).__name__}")
                    return False
            a["text"] = got["text"][: self.max_article_chars]
            return True

        results = await asyncio.gather(*[one(a) for a in articles])
        return sum(results)

    def _format_briefing_input(self, articles: list[dict], selected: list[dict]) -> str:
        """What the writer sees: chosen stories in full, everything else as headlines."""
        if not selected:
            return self._format_articles_for_prompt(articles)
        chosen = {id(a) for a in selected}
        rest = [a for a in articles if id(a) not in chosen]
        parts = ["## Selected stories (full text where available)", "",
                 self._format_articles_for_prompt(selected)]
        if rest:
            parts += ["", "## Other headlines (not selected; mention only if essential)", ""]
            parts += [f"- [{a['source']}] {a['title']}" + (f" {a['url']}" if a.get("url") else "")
                      for a in rest]
        return "\n".join(parts)

    async def synthesize_briefing(self, formatted_articles: str) -> str:
        """Synthesize the briefing from formatted articles via MODEL_STRONG."""
        # Build user message with dedup context from recent briefings
        user_message_parts = []
        if self.recent_briefings:
            user_message_parts.append(
                "## Previous briefings (do NOT repeat stories unless there is genuinely new information):"
            )
            for briefing in self.recent_briefings:
                user_message_parts.append(f"### {briefing['date']}")
                user_message_parts.append(briefing["briefing_text"])
            user_message_parts.append("---")
            user_message_parts.append("")

        # The prompt tells the model to open with "[today's date]" and never
        # says what today is, so it inferred one from the articles and got it
        # wrong: the briefing filed on 2026-08-21 announced itself as
        # "August twenty-second". State the date.
        user_message_parts.insert(
            0, f"Today is {datetime.now().strftime('%A, %d %B %Y')}. "
               f"Use this date when you open the briefing, not a date taken "
               f"from any article.")
        user_message_parts.insert(1, "")
        user_message_parts.append("## Today's articles:")
        user_message_parts.append(formatted_articles)
        user_message = "\n".join(user_message_parts)

        response = await self.client.chat.completions.create(
            model=MODEL_STRONG,
            max_tokens=16000,
            messages=[
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": user_message},
            ],
        )
        briefing = response.choices[0].message.content
        draft, fidelity = briefing, None
        if self.verify:
            briefing, fidelity = await verify_script(
                briefing, user_message, writer_system_prompt=self.prompt,
                label="news briefing", client=self.client)
            self.last_fidelity = fidelity.to_dict()
        self.last_bundle = writer_bundle(
            title=f"Daily News Briefing - {datetime.now():%Y-%m-%d}",
            model=MODEL_STRONG, system_prompt=self.prompt,
            user_message=user_message, response=briefing,
            notes=fidelity_markdown(fidelity, draft if fidelity and fidelity.revised else None))
        return briefing

    async def generate_briefing(self) -> FeedEntry | None:
        """Orchestrate fetch → format → synthesize, return a FeedEntry or None."""
        print("  Fetching news sources...")
        articles = await self.fetch_all_sources()

        if not articles:
            print("  No recent articles found for news briefing")
            return None

        print(f"  Found {len(articles)} recent articles across {len(self.sources)} sources")

        selected = await self.select_stories(articles)
        if selected:
            got = await self.fetch_full_text(selected)
            print(f"  Selected {len(selected)} stories; full text for {got}")
        formatted = self._format_briefing_input(articles, selected)
        print("  Synthesizing briefing via LLM...")
        briefing_text = await self.synthesize_briefing(formatted)
        bundle = self.last_bundle

        today = datetime.now().strftime("%Y-%m-%d")
        return FeedEntry(
            bundle=bundle,
            fidelity=self.last_fidelity,
            id=f"news-briefing-{today}",
            title=f"Daily News Briefing - {today}",
            link="",
            content=briefing_text,
            published=datetime.now(),
            author="Feedcast Bot",
            feed_name="Daily News Briefing",
            authors=["Feedcast Bot"],
            sources=[{"title": a["title"], "url": a["url"], "source": a["source"]}
                     for a in articles if a.get("url")],
        )
