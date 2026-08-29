"""When a LessWrong post was actually written, as opposed to curated.

The curated feed carries the curation date as its pubDate, and curation lags
publication by anything from hours to weeks (Big-World Intuitions: posted
2026-07-30, curated 2026-08-21). Both dates are wanted, for different jobs:
curation decides whether an item is new to us, publication is what the email
should call the release date.

Only the second needs asking LessWrong, and only for LessWrong links.
"""

import re
from datetime import datetime, timezone

import httpx

GRAPHQL_URL = "https://www.lesswrong.com/graphql"
POST_ID = re.compile(r"lesswrong\.com/posts/([A-Za-z0-9]+)")
TIMEOUT = 15.0


def post_id(link: str) -> str:
    """The post id embedded in a LessWrong URL, or '' for anything else."""
    match = POST_ID.search(link or "")
    return match.group(1) if match else ""


def _parse(stamp: str | None) -> datetime | None:
    """LessWrong returns UTC ISO-8601 with a Z; the pipeline works naive UTC."""
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


async def posted_at(link: str, client: httpx.AsyncClient | None = None) -> datetime | None:
    """When the post behind this link was published, or None if unknown.

    Never raises: a date that cannot be improved simply stays as the feed
    reported it. This runs on an unattended job with no one to see a stack
    trace, and a missing date is not worth losing an episode over.
    """
    pid = post_id(link)
    if not pid:
        return None
    query = ('{post(input:{selector:{_id:"%s"}}){result{postedAt}}}' % pid)
    try:
        owned = client is None
        client = client or httpx.AsyncClient(timeout=TIMEOUT)
        try:
            response = await client.post(
                GRAPHQL_URL, json={"query": query},
                headers={"user-agent": "feedcast/1.0"},
            )
            response.raise_for_status()
            data = response.json()
        finally:
            if owned:
                await client.aclose()
    except Exception as exc:
        print(f"    LessWrong date lookup failed for {pid}: {exc!r}")
        return None

    try:
        return _parse(data["data"]["post"]["result"]["postedAt"])
    except (KeyError, TypeError):
        return None
