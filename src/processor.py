"""Content processing with LLM API for summarization."""

from typing import Optional

from bs4 import BeautifulSoup

from .bundle import writer_bundle
from .html_text import clean_html, small_table_to_prose
from .verify import fidelity_markdown, verify_script
from .llm import complete
from .monitor import FeedEntry


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

    def __init__(self, default_prompt: str, *, verify: bool, auto_verbatim_limit: int):
        # None routes each call through llm.complete() with fallbacks; tests
        # pin a fake client here instead.
        self.client = None
        self.default_prompt = default_prompt
        # Check summaries against their source with a second model and fix
        # them once (src/verify.py). Off in tests and when config says so.
        self.verify = verify
        # Auto mode reads a post out in full up to this many characters.
        self.auto_verbatim_limit = auto_verbatim_limit

    def reads_verbatim(self, entry: FeedEntry, mode: str) -> bool:
        """Whether `process` will read this entry out in full rather than summarise it.

        Decides which publish an episode goes out in: everything a writer
        produced (summaries, the briefing) first, full readings after.
        """
        return self._reads_verbatim(entry, mode)[0]

    def _reads_verbatim(self, entry: FeedEntry, mode: str) -> tuple[bool, int]:
        """reads_verbatim, with the cleaned length auto mode measured (0 in other modes).

        The one place the rule lives: `process` resolves auto mode with it too,
        so the publish an episode goes out in always matches how it is read.
        """
        chars = len(clean_html(entry.content)) if mode == "auto" else 0
        if entry.id.startswith("news-briefing-"):
            return False, chars
        if mode == "auto":
            return chars <= self.auto_verbatim_limit, chars
        return mode == "verbatim", chars

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
                prose = small_table_to_prose(table)
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

    async def clean_text(self, entry: FeedEntry) -> str:
        """The post as plain text, its tables turned to prose. Raises on an empty post.

        A table of more than three data rows is turned to prose by the writer
        model (process_tables), so this can make a model call.

        Narrating nothing would publish an episode that is only its intro and
        outro, so an empty post fails like any other entry: the run reports
        it, and a feed entry is queued for a retry.
        """
        text = clean_html(await self.process_tables(entry.content))
        if not text.strip():
            raise ValueError(f"no content to narrate in {entry.title!r}: "
                             f"the post is empty once cleaned")
        return text

    async def summarize(
        self, entry: FeedEntry, prompt: Optional[str] = None
    ) -> str:
        """Summarize content with the writer role."""
        clean_content = await self.clean_text(entry)

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
        entry.writer = done.credit()
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
        clean_content = await self.clean_text(entry)

        # Add intro
        intro = (f"{spoken_title(entry.title, entry.author)}. By {entry.author}. "
                 f"Published {entry.published.strftime('%B %d, %Y')}.")

        return f"{intro}\n\n{clean_content}"

    async def process(self, entry: FeedEntry, mode: str, prompt: Optional[str] = None) -> str:
        """Process a feed entry based on mode (summarize or verbatim).

        Args:
            entry: The feed entry to process
            mode: Processing mode - "summarize", "verbatim", or "auto"
            prompt: Optional custom prompt for summarization
        """
        is_news_briefing = entry.id.startswith("news-briefing-")
        if mode == "auto":
            verbatim, chars = self._reads_verbatim(entry, mode)
            mode = "verbatim" if verbatim else "summarize"
            sign = "≤" if chars <= self.auto_verbatim_limit else ">"
            print(f"    Auto mode: {chars} chars {sign} {self.auto_verbatim_limit} → {mode}")

        if is_news_briefing and mode == "verbatim":
            # News briefings: the synthesis already opens with the date, skip redundant intro
            text = await self.clean_text(entry)
        elif mode == "summarize":
            summary = await self.summarize(entry, prompt)
            # Add intro for context
            intro = f"Summary of {spoken_title(entry.title, entry.author)} by {entry.author}."
            text = f"{intro}\n\n{summary}"
        elif mode == "verbatim":
            text = await self.process_verbatim(entry)
        else:
            raise ValueError(f"Unknown processing mode: {mode}")

        # Append end announcement
        if is_news_briefing:
            text = f"{text}\n\nEnd of daily news briefing."
        else:
            text = f"{text}\n\nEnd of {spoken_title(entry.title, entry.author)}."
        return text
