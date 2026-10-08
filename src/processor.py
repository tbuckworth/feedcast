"""Content processing with LLM API for summarization."""

import os
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from .bundle import writer_bundle
from .verify import fidelity_markdown, verify_script
from .llm import complete
from .monitor import FeedEntry

AUTO_VERBATIM_LIMIT = 24000  # ~25 min of audio at ~0.063 sec/char


def spoken_title(title: str, author: str) -> str:
    """The title as the intro and outro say it, without a "by <author>" tail.

    Zvi's feed titles every post '“The Curve Bends You” by Zvi', so episodes
    opened "Summary of ... by Zvi by Zvi Mowshowitz" and closed "End of ... by
    Zvi": his name three times, in two forms, by a voice that already says it
    a different way each time. The tail is dropped only when the name after
    the last " by " is the author (whole, or their first or last name), so a
    title like "Stand by Me" is left alone.
    """
    head, sep, tail = title.rpartition(" by ")
    if not sep or not head.strip():
        return title
    names = {author.strip().lower()} | {n.lower() for n in author.split()} if author else set()
    return head.rstrip(" ,:-—") if tail.strip().strip(".").lower() in names else title
MAX_PROMPT_CHARS = 400000    # ~100k tokens; a cost ceiling, not a context limit


class ContentProcessor:
    """Processes feed content - either summarizing via the LLM or cleaning for verbatim."""

    def __init__(self, default_prompt: str, verify: bool = True):
        # None routes each call through llm.complete() with fallbacks; tests
        # pin a fake client here instead.
        self.client = None
        self.default_prompt = default_prompt
        # Check summaries against their source with a second model and fix
        # them once (src/verify.py). Off in tests and when config says so.
        self.verify = verify

    def reads_verbatim(self, entry: FeedEntry, mode: str) -> bool:
        """Whether `process` will read this entry out in full rather than summarise it.

        Decides which publish an episode goes out in: everything a writer
        produced (summaries, the briefing) first, full readings after.
        """
        if entry.id.startswith("news-briefing-"):
            return False
        if mode == "auto":
            return len(self.clean_html(entry.content)) <= AUTO_VERBATIM_LIMIT
        return mode == "verbatim"

    def clean_html(self, html_content: str) -> str:
        """Extract clean text from HTML content."""
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Get text
        text = soup.get_text(separator="\n")

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        # Remove excessive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _table_to_prose_simple(self, table: Tag) -> str:
        """Convert a small HTML table to inline prose (Header: value pairs)."""
        rows = table.find_all("tr")
        if not rows:
            return ""

        # Extract headers from first row
        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

        prose_parts = []
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            pairs = []
            for i, cell in enumerate(cells):
                if i < len(headers) and headers[i]:
                    pairs.append(f"{headers[i]}: {cell}")
                else:
                    pairs.append(cell)
            prose_parts.append(", ".join(pairs))

        return ". ".join(prose_parts) + "."

    async def process_tables(self, html_content: str) -> str:
        """Convert HTML tables to prose before clean_html strips them."""
        soup = BeautifulSoup(html_content, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return html_content

        for table in tables:
            # Count data rows (excluding header row)
            rows = table.find_all("tr")
            data_rows = max(0, len(rows) - 1)

            if data_rows <= 3:
                prose = self._table_to_prose_simple(table)
            else:
                # Larger tables: summarize with the cheap model
                table_html = str(table)
                done = await complete(
                    "writer", max_tokens=4000, client=self.client, label="table-to-prose",
                    messages=[
                        {"role": "system", "content": "Convert this HTML table into natural spoken prose. Be concise but preserve all key data points. Do not use bullet points or formatting."},
                        {"role": "user", "content": table_html},
                    ],
                )
                prose = done.text

            replacement = f"Here is a summary of the following table. {prose} Now continuing with the article."
            table.replace_with(BeautifulSoup(f"<p>{replacement}</p>", "html.parser"))

        return str(soup)

    async def summarize(
        self, entry: FeedEntry, prompt: Optional[str] = None
    ) -> str:
        """Summarize content with the writer role."""
        content_with_tables = await self.process_tables(entry.content)
        clean_content = self.clean_html(content_with_tables)

        if not clean_content:
            return f"No content available for: {entry.title}"

        system_prompt = prompt or self.default_prompt

        # Build the message with context
        user_message = f"""Title: {entry.title}
Author: {entry.author}
Published: {entry.published.strftime("%Y-%m-%d")}

Content:
{clean_content}"""

        # A ceiling, not a working limit. The writer model holds a million tokens
        # and the longest post we see is a Zvi weekly at ~100,000 characters
        # (~25,000 tokens), so this should never bind — but an unbounded prompt
        # is an unbounded bill. Say so when it does bind: a truncated summary is
        # exactly the failure this module was just fixed for, and it must not be
        # able to happen again in silence.
        if len(user_message) > MAX_PROMPT_CHARS:
            print(f"    WARNING: content truncated for the summariser "
                  f"({len(user_message):,} > {MAX_PROMPT_CHARS:,} chars) — "
                  f"the summary will not cover the whole post")
            user_message = user_message[:MAX_PROMPT_CHARS] + "\n\n[Content truncated due to length]"

        done = await complete(
            "writer", max_tokens=16000, client=self.client,
            label=f"summariser ({entry.title})",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )

        summary = done.text
        draft, fidelity = summary, None
        if self.verify:
            summary, fidelity = await verify_script(
                summary, user_message, writer_system_prompt=system_prompt,
                label=entry.title, client=self.client)
            entry.fidelity = fidelity.to_dict()
        entry.bundle = writer_bundle(
            title=entry.title, model=done.target.label, system_prompt=system_prompt,
            user_message=user_message, response=summary,
            notes=fidelity_markdown(fidelity, draft if fidelity and fidelity.revised else None))
        return summary

    async def process_verbatim(self, entry: FeedEntry) -> str:
        """Process content for verbatim reading - clean and format for TTS."""
        content_with_tables = await self.process_tables(entry.content)
        clean_content = self.clean_html(content_with_tables)

        # Add intro
        intro = (f"{spoken_title(entry.title, entry.author)}. By {entry.author}. "
                 f"Published {entry.published.strftime('%B %d, %Y')}.")

        return f"{intro}\n\n{clean_content}"

    async def process(
        self, entry: FeedEntry, mode: str, prompt: Optional[str] = None, title: Optional[str] = None
    ) -> str:
        """Process a feed entry based on mode (summarize or verbatim).

        Args:
            entry: The feed entry to process
            mode: Processing mode - "summarize", "verbatim", or "auto"
            prompt: Optional custom prompt for summarization
            title: Title for the end announcement (defaults to entry.title)
        """
        # Use provided title or fall back to entry title
        episode_title = spoken_title(title or entry.title, entry.author)
        is_news_briefing = entry.id.startswith("news-briefing-")

        if is_news_briefing and mode == "verbatim":
            # News briefings: the synthesis already opens with the date, skip redundant intro
            content_with_tables = await self.process_tables(entry.content)
            text = self.clean_html(content_with_tables)
        elif mode == "summarize":
            summary = await self.summarize(entry, prompt)
            # Add intro for context
            intro = f"Summary of {spoken_title(entry.title, entry.author)} by {entry.author}."
            text = f"{intro}\n\n{summary}"
        elif mode == "verbatim":
            text = await self.process_verbatim(entry)
        elif mode == "auto":
            clean_text = self.clean_html(entry.content)
            if self.reads_verbatim(entry, mode):
                print(f"    Auto mode: {len(clean_text)} chars ≤ {AUTO_VERBATIM_LIMIT} → verbatim")
                text = await self.process_verbatim(entry)
            else:
                print(f"    Auto mode: {len(clean_text)} chars > {AUTO_VERBATIM_LIMIT} → summarize")
                summary = await self.summarize(entry, prompt)
                intro = f"Summary of {spoken_title(entry.title, entry.author)} by {entry.author}."
                text = f"{intro}\n\n{summary}"
        else:
            raise ValueError(f"Unknown processing mode: {mode}")

        # Append end announcement
        if is_news_briefing:
            text = f"{text}\n\nEnd of daily news briefing."
        else:
            text = f"{text}\n\nEnd of {episode_title}."
        return text
