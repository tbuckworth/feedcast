"""Content processing with Claude API for summarization."""

import os
import re
from typing import Optional

from anthropic import Anthropic
from bs4 import BeautifulSoup

from .monitor import FeedEntry

AUTO_VERBATIM_LIMIT = 24000  # ~25 min of audio at ~0.063 sec/char


class ContentProcessor:
    """Processes feed content - either summarizing with Claude or cleaning for verbatim."""

    def __init__(self, default_prompt: str):
        self.client = Anthropic()
        self.default_prompt = default_prompt

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

    def summarize(
        self, entry: FeedEntry, prompt: Optional[str] = None
    ) -> str:
        """Summarize content using Claude API."""
        clean_content = self.clean_html(entry.content)

        if not clean_content:
            return f"No content available for: {entry.title}"

        system_prompt = prompt or self.default_prompt

        # Build the message with context
        user_message = f"""Title: {entry.title}
Author: {entry.author}
Published: {entry.published.strftime("%Y-%m-%d")}

Content:
{clean_content}"""

        # Truncate if too long (Claude can handle ~100k tokens, but we'll be conservative)
        max_chars = 100000
        if len(user_message) > max_chars:
            user_message = user_message[:max_chars] + "\n\n[Content truncated due to length]"

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        return response.content[0].text

    def process_verbatim(self, entry: FeedEntry) -> str:
        """Process content for verbatim reading - clean and format for TTS."""
        clean_content = self.clean_html(entry.content)

        # Add intro
        intro = f"{entry.title}. By {entry.author}. Published {entry.published.strftime('%B %d, %Y')}."

        return f"{intro}\n\n{clean_content}"

    def process(
        self, entry: FeedEntry, mode: str, prompt: Optional[str] = None
    ) -> str:
        """Process a feed entry based on mode (summarize or verbatim)."""
        if mode == "summarize":
            summary = self.summarize(entry, prompt)
            # Add intro for context
            intro = f"Summary of {entry.title} by {entry.author}."
            return f"{intro}\n\n{summary}"
        elif mode == "verbatim":
            return self.process_verbatim(entry)
        elif mode == "auto":
            clean_text = self.clean_html(entry.content)
            if len(clean_text) <= AUTO_VERBATIM_LIMIT:
                print(f"    Auto mode: {len(clean_text)} chars ≤ {AUTO_VERBATIM_LIMIT} → verbatim")
                return self.process_verbatim(entry)
            else:
                print(f"    Auto mode: {len(clean_text)} chars > {AUTO_VERBATIM_LIMIT} → summarize")
                summary = self.summarize(entry, prompt)
                intro = f"Summary of {entry.title} by {entry.author}."
                return f"{intro}\n\n{summary}"
        else:
            raise ValueError(f"Unknown processing mode: {mode}")
