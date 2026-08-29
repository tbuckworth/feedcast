"""Daily news briefing via RSS aggregation and LLM synthesis."""

import asyncio
from datetime import datetime, timedelta, timezone

import feedparser

from .llm import get_client, MODEL_STRONG
from .monitor import FeedEntry, warn_if_dead


class NewsAggregator:
    """Aggregates news from multiple RSS sources and synthesizes a daily briefing."""

    def __init__(
        self,
        sources: list[dict],
        prompt: str,
        lookback_hours: int = 48,
        recent_briefings: list[dict] | None = None,
    ):
        self.sources = sources
        self.prompt = prompt
        self.lookback_hours = lookback_hours
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
                section_lines.append(
                    f"- [{item['source']}] {item['title']}{url}\n  {item['summary']}"
                )
            sections.append("\n".join(section_lines))

        return "\n\n".join(sections)

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
        return response.choices[0].message.content

    async def generate_briefing(self) -> FeedEntry | None:
        """Orchestrate fetch → format → synthesize, return a FeedEntry or None."""
        print("  Fetching news sources...")
        articles = await self.fetch_all_sources()

        if not articles:
            print("  No recent articles found for news briefing")
            return None

        print(f"  Found {len(articles)} recent articles across {len(self.sources)} sources")

        formatted = self._format_articles_for_prompt(articles)
        print("  Synthesizing briefing via LLM...")
        briefing_text = await self.synthesize_briefing(formatted)

        today = datetime.now().strftime("%Y-%m-%d")
        return FeedEntry(
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
