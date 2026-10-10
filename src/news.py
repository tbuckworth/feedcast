"""Daily news briefing via RSS aggregation and LLM synthesis."""

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone

import feedparser

from .bundle import writer_bundle
from .extractor import extract_article
from .llm import complete
from .markets import MarketContext, MarketScout
from .monitor import FeedEntry, warn_if_dead
from .verify import fidelity_markdown, verify_script

# The previous briefings are there for dedup, but the writer also reads them
# as a style guide. Sol, a fallback writer on 19-21 Sep, closed three to five
# stories a day with "This matters because"; those briefings came back as
# context and Opus 4.6, which had used the phrase about once a week, then
# used it on nearly every story (5 of 5 on 24 Sep).
PREVIOUS_BRIEFINGS_HEADER = (
    "## Previous briefings (only so you know what was already covered: do NOT repeat "
    "stories unless there is genuinely new information, and do not copy their wording "
    "or sentence patterns):"
)

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
        markets: MarketScout | None = None,
    ):
        self.sources = sources
        self.prompt = prompt
        self.lookback_hours = lookback_hours
        self.last_bundle: str | None = None
        self.last_fidelity: dict | None = None
        self.last_writer: dict | None = None
        # Two calls, not one. The writer used to see only each item's RSS
        # blurb (a title and up to 500 characters the publisher wrote), so
        # everything beyond that in the briefing came from the model's memory.
        # Now it first picks the stories worth covering from the blurbs, then
        # writes from those articles' full text. Roughly three times the
        # tokens of the old single call; a tenth of fetching everything.
        self.full_text_stories = full_text_stories
        self.max_article_chars = max_article_chars
        self.verify = verify
        # Prediction-market odds for the chosen stories, and the day's big
        # unexplained moves (src/markets.py). None leaves the briefing as it was.
        self.markets = markets
        self.last_markets = MarketContext()
        self.recent_briefings = recent_briefings or []
        self.client = None   # None: llm.complete() routes with fallbacks; tests pin a fake
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

    def _format_articles_for_prompt(self, articles: list[dict],
                                    notes: MarketContext | None = None) -> str:
        """Group articles by category and format as structured text.

        `notes` appends each story's prediction-market odds, where it has any.
        """
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
                odds = notes.story_block(item.get("url", "")) if notes else ""
                section_lines.append(
                    f"- [{item['source']}] {item['title']}{url}\n  {body}"
                    + (f"\n{odds}" if odds else "")
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
        done = await complete(
            "writer", max_tokens=2000, client=self.client, label="story selection",
            messages=[{"role": "system", "content": SELECT_PROMPT.format(n=n)},
                      {"role": "user", "content": self._format_articles_for_prompt(articles)}])
        raw = done.text or ""
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

    def _format_briefing_input(self, articles: list[dict], selected: list[dict],
                               markets: MarketContext | None = None) -> str:
        """What the writer sees: chosen stories in full, everything else as headlines.

        With market data, the chosen stories carry their odds and a closing
        section lists the day's unexplained moves.
        """
        markets = markets or MarketContext()
        if not selected:
            text = self._format_articles_for_prompt(articles)
        else:
            chosen = {id(a) for a in selected}
            rest = [a for a in articles if id(a) not in chosen]
            parts = ["## Selected stories (full text where available)", "",
                     self._format_articles_for_prompt(selected, markets)]
            if rest:
                parts += ["", "## Other headlines (not selected; mention only if essential)", ""]
                parts += [f"- [{a['source']}] {a['title']}" + (f" {a['url']}" if a.get("url") else "")
                          for a in rest]
            text = "\n".join(parts)
        moves = markets.moves_section()
        return f"{text}\n\n{moves}" if moves else text

    async def synthesize_briefing(self, formatted_articles: str, extra_instructions: str = "") -> str:
        """Synthesize the briefing from formatted articles with the writer role.

        `extra_instructions` goes just before the articles, so a day without
        market data sends exactly the message it always did.
        """
        # Build user message with dedup context from recent briefings
        user_message_parts = []
        if self.recent_briefings:
            user_message_parts.append(PREVIOUS_BRIEFINGS_HEADER)
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
        if extra_instructions:
            user_message_parts += [extra_instructions, ""]
        user_message_parts.append("## Today's articles:")
        user_message_parts.append(formatted_articles)
        user_message = "\n".join(user_message_parts)

        done = await complete(
            "writer", max_tokens=16000, client=self.client, label="news briefing",
            messages=[
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": user_message},
            ],
        )
        briefing = done.text
        self.last_writer = done.credit()
        draft, fidelity = briefing, None
        if self.verify:
            briefing, fidelity = await verify_script(
                briefing, user_message, writer_system_prompt=self.prompt,
                label="news briefing", client=self.client)
            self.last_fidelity = fidelity.to_dict()
        self.last_bundle = writer_bundle(
            title=f"Daily News Briefing - {datetime.now():%Y-%m-%d}",
            model=done.target.label, system_prompt=self.prompt,
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
        markets = (await self.markets.build((selected or articles)[:self.full_text_stories or 12])
                   if self.markets else MarketContext())
        self.last_markets = markets
        formatted = self._format_briefing_input(articles, selected, markets)
        print("  Synthesizing briefing via LLM...")
        briefing_text = await self.synthesize_briefing(formatted, markets.instructions())
        bundle = self.last_bundle

        today = datetime.now().strftime("%Y-%m-%d")
        return FeedEntry(
            bundle=bundle,
            fidelity=self.last_fidelity,
            writer=self.last_writer,
            id=f"news-briefing-{today}",
            title=f"Daily News Briefing - {today}",
            link="",
            content=briefing_text,
            published=datetime.now(),
            author="Feedcast Bot",
            feed_name="Daily News Briefing",
            authors=["Feedcast Bot"],
            # For the email's per-bullet links: only the stories the writer
            # was given in full. Passing every headline let the digest lift a
            # story the briefing never told (a SpaceX launch, 2026-09-16) and
            # cost ~4k tokens a call for the list alone.
            sources=[{"title": a["title"], "url": a["url"], "source": a["source"]}
                     for a in (selected or articles) if a.get("url")] + markets.sources(),
            markets=markets.to_dict() if markets else None,
        )
