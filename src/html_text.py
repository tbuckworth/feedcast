"""Plain text from HTML, with no model calls: stripping tags, and small tables as prose."""

import re

from bs4 import BeautifulSoup, Tag

# Substack's calls to action, which every Substack post carries: the
# "Subscribe now" and "Share" buttons, a button's caption ("Share this
# Transformer article with a friend or colleague") and the subscribe box.
SUBSTACK_WIDGETS = ".button-wrapper, .captioned-button-wrap, .subscription-widget-wrap-editor"

# The elements drop_blocks matches against a pattern.
_BLOCKS = ["p", "h1", "h2", "h3", "h4", "h5", "h6"]


def clean_html(html_content: str) -> str:
    """Extract clean text from HTML content, without Substack's buttons and subscribe box."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()
    for element in soup.select(SUBSTACK_WIDGETS):
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


def drop_blocks(html_content: str, patterns: list[str]) -> tuple[str, int]:
    """`html_content` without the paragraphs and headings whose whole text matches a pattern.

    A block's text is matched with its whitespace collapsed to single spaces,
    and the match ignores case. Returns the HTML and the number of blocks dropped.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    dropped = 0
    for block in soup.find_all(_BLOCKS):
        text = " ".join(block.get_text(" ").split())
        if any(re.fullmatch(p, text, re.IGNORECASE) for p in patterns):
            block.decompose()
            dropped += 1
    return str(soup), dropped


def small_table_to_prose(table: Tag) -> str:
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
