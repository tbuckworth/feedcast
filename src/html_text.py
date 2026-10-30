"""Plain text from HTML, with no model calls: stripping tags, and small tables as prose."""

import re

from bs4 import BeautifulSoup, Tag


def clean_html(html_content: str) -> str:
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
