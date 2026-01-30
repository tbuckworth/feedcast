"""Daily news briefing via RSS aggregation and Claude synthesis."""

import asyncio
from datetime import datetime, timedelta, timezone

import feedparser
from anthropic import AsyncAnthropic

from .monitor import FeedEntry


class NewsAggregator:
    """Aggregates news from multiple RSS sources and synthesizes a daily briefing."""

    def __init__(
        self,
        sources: list[dict],
        prompt: str,
        lookback_hours: int = 48,
    ):
        self.sources = sources
        self.prompt = prompt
        self.lookback_hours = lookback_hours
        self.client = AsyncAnthropic()

    async def fetch_all_sources(self) -> list[dict]:
        """Fetch all RSS sources in parallel, filtering to recent articles."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)

        async def fetch_one(source: dict) -> list[dict]:
            feed = await asyncio.to_thread(feedparser.parse, source["url"])
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
                section_lines.append(
                    f"- [{item['source']}] {item['title']}\n  {item['summary']}"
                )
            sections.append("\n".join(section_lines))

        return "\n\n".join(sections)

    async def synthesize_briefing(self, formatted_articles: str) -> str:
        """Call Claude to synthesize the briefing from formatted articles."""
        response = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=self.prompt,
            messages=[{"role": "user", "content": formatted_articles}],
        )
        return response.content[0].text

    async def generate_briefing(self) -> FeedEntry | None:
        """Orchestrate fetch → format → synthesize, return a FeedEntry or None."""
        print("  Fetching news sources...")
        articles = await self.fetch_all_sources()

        if not articles:
            print("  No recent articles found for news briefing")
            return None

        print(f"  Found {len(articles)} recent articles across {len(self.sources)} sources")

        formatted = self._format_articles_for_prompt(articles)
        print("  Synthesizing briefing via Claude...")
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
        )
