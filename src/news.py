"""Daily news briefing via RSS aggregation and LLM synthesis."""

import asyncio
from datetime import datetime, timedelta, timezone

import feedparser

from .extractor import extract_article
from .llm import complete, extract_json
from .markets import MarketContext, MarketScout
from .monitor import (FeedEntry, briefing_id, entry_body, entry_published, report_skipped,
                      warn_if_dead)
from .verify import Written, write_checked

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

# Headings of the writer's input. scripts/model_upgrade_test.py finds them in
# a saved writer bundle, so it reads them from here.
SELECTED_STORIES_HEADING = "## Selected stories (full text where available)"
OTHER_HEADLINES_HEADING = "## Other headlines (not selected; mention only if essential)"
ARTICLES_HEADING = "## Today's articles:"

SELECT_PROMPT = """You are choosing which stories a daily news briefing will cover, from a list of RSS headlines with short blurbs.

Pick the {n} most worth covering for a technically sophisticated audience, in priority order: AI safety and policy first, then AI capabilities, geopolitics, economics, markets. Prefer one strong item per story over several near-duplicates. Skip trivia, listicles and product fluff.

Return ONLY a JSON array of the chosen URLs, copied exactly from the list."""


def _selection(raw: str, by_url: dict[str, dict]) -> tuple[list[dict], str]:
    """The articles a story-selection reply chose, in its order, and what is wrong with it.

    The problem is "" for a usable reply: a JSON array naming at least one
    article from the list. Unknown and repeated URLs are dropped.
    """
    try:
        urls = extract_json(raw, list)
    except ValueError as e:
        return [], str(e)
    chosen, seen = [], set()
    for u in urls:
        if isinstance(u, str) and u in by_url and u not in seen:
            seen.add(u); chosen.append(by_url[u])
    return chosen, "" if chosen else "none of the URLs is in the list"


class NewsAggregator:
    """Aggregates news from multiple RSS sources and synthesizes a daily briefing."""

    def __init__(
        self,
        sources: list[dict],
        prompt: str,
        *,
        lookback_hours: int,
        full_text_stories: int,
        max_article_chars: int,
        author: str,
        verify: bool,
        recent_briefings: list[dict] | None = None,
        markets: MarketScout | None = None,
    ):
        self.sources = sources
        self.prompt = prompt
        self.lookback_hours = lookback_hours
        # Credited as the briefing's author: the podcast's own (config.yaml).
        self.author = author
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
            stale = undated = 0
            for entry in feed.entries:
                published = entry_published(entry)

                # Counted for report_skipped: a source that stops dating its
                # items would otherwise just look quiet.
                if published is None:
                    undated += 1
                    continue
                published = published.replace(tzinfo=timezone.utc)
                if published < cutoff:
                    stale += 1
                    continue

                articles.append({
                    "title": entry.get("title", "Untitled"),
                    "source": source["name"],
                    "category": source["category"],
                    "summary": entry_body(entry)[:500],
                    "published": published,
                    "url": entry.get("link", ""),
                })
            report_skipped(source["name"], self.lookback_hours, stale=stale, undated=undated,
                           already=0, skipped=0)
            return articles

        results = await asyncio.gather(
            *[fetch_one(s) for s in self.sources],
            return_exceptions=True,
        )

        all_articles = []
        for source, result in zip(self.sources, results):
            if isinstance(result, Exception):
                # feedparser raises on a socket timeout; the source returned
                # nothing as surely as an empty feed does, so the email lists it.
                print(f"  Warning: failed to fetch {source['name']}: {result!r}")
                self.dead_sources.append(f"{source['name']} ({type(result).__name__}: {result})")
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
        """Ask the writer which stories deserve full text. [] means: use blurbs only.

        A reply with no usable selection goes to the next writer, like an empty
        one; when none gives one, this raises and the briefing fails, to be
        retried, rather than being written from blurbs without a word.
        """
        n = self.full_text_stories
        if n <= 0 or not articles:
            return []
        if len(articles) <= n:
            return list(articles)
        by_url = {a["url"]: a for a in articles if a.get("url")}
        done = await complete(
            "writer", max_tokens=2000, client=self.client, label="story selection",
            check=lambda raw: _selection(raw, by_url)[1] or None,
            messages=[{"role": "system", "content": SELECT_PROMPT.format(n=n)},
                      {"role": "user", "content": self._format_articles_for_prompt(articles)}])
        return _selection(done.text, by_url)[0][:n]

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
            parts = [SELECTED_STORIES_HEADING, "",
                     self._format_articles_for_prompt(selected, markets)]
            if rest:
                parts += ["", OTHER_HEADLINES_HEADING, ""]
                parts += [f"- [{a['source']}] {a['title']}" + (f" {a['url']}" if a.get("url") else "")
                          for a in rest]
            text = "\n".join(parts)
        moves = markets.moves_section()
        return f"{text}\n\n{moves}" if moves else text

    async def synthesize_briefing(self, formatted_articles: str,
                                  extra_instructions: str = "") -> Written:
        """Write the briefing from formatted articles with the writer role, and check it.

        `extra_instructions` goes just before the articles, so a day without
        market data sends exactly the message it always did.
        """
        # The prompt tells the model to open with "[today's date]" and never
        # says what today is, so it inferred one from the articles and got it
        # wrong: the briefing filed on 2026-08-21 announced itself as
        # "August twenty-second". State the date.
        parts = [f"Today is {datetime.now().strftime('%A, %d %B %Y')}. "
                 f"Use this date when you open the briefing, not a date taken "
                 f"from any article.", ""]
        # Dedup context from recent briefings.
        if self.recent_briefings:
            parts.append(PREVIOUS_BRIEFINGS_HEADER)
            for briefing in self.recent_briefings:
                parts += [f"### {briefing['date']}", briefing["briefing_text"]]
            parts += ["---", ""]
        if extra_instructions:
            parts += [extra_instructions, ""]
        parts += [ARTICLES_HEADING, formatted_articles]

        return await write_checked(
            self.prompt, "\n".join(parts),
            title=f"Daily News Briefing - {datetime.now():%Y-%m-%d}",
            label="news briefing", check_label="news briefing", verify=self.verify,
            client=self.client)

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
        # The scout attaches odds to the stories the writer reads in full. With
        # full_text_stories at 0 the writer reads none in full, so the scout
        # gets no stories and only looks for unexplained moves.
        markets = (await self.markets.build(selected)
                   if self.markets else MarketContext())
        formatted = self._format_briefing_input(articles, selected, markets)
        print("  Synthesizing briefing via LLM...")
        briefing = await self.synthesize_briefing(formatted, markets.instructions())

        today = datetime.now().strftime("%Y-%m-%d")
        return FeedEntry(
            bundle=briefing.bundle,
            fidelity=briefing.fidelity,
            writer=briefing.writer,
            id=briefing_id(today),
            title=f"Daily News Briefing - {today}",
            link="",
            content=briefing.text,
            published=datetime.now(),
            author=self.author,
            feed_name="Daily News Briefing",
            authors=[self.author],
            # For the email's per-bullet links: only the stories the writer
            # was given in full. Passing every headline let the digest lift a
            # story the briefing never told (a SpaceX launch, 2026-09-16) and
            # cost ~4k tokens a call for the list alone.
            sources=[{"title": a["title"], "url": a["url"], "source": a["source"]}
                     for a in (selected or articles) if a.get("url")] + markets.sources(),
            markets=markets.to_dict() if markets else None,
        )
