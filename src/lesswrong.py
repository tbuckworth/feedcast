"""LessWrong and Alignment Forum over GraphQL: a post's markdown, and its date.

``fetch_lesswrong_markdown`` returns a post's markdown source, used by the
maths filter (mathiness.py) and full-text recovery (fulltext.py).

``posted_at`` says when a LessWrong post was actually written, as opposed to
curated. The curated feed carries the curation date as its pubDate, and
curation lags publication by anything from hours to weeks (Big-World
Intuitions: posted 2026-07-30, curated 2026-08-21). Both dates are wanted, for
different jobs: curation decides whether an item is new to us, publication is
what the email should call the release date.

Only the second needs asking the site, and only for LessWrong and Alignment
Forum links.
"""

import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

import httpx

TIMEOUT = 15.0

_LW_HOSTS = ("lesswrong.com", "alignmentforum.org")
_POST_ID = re.compile(r"/posts/([A-Za-z0-9]{17})")
_UA = {"User-Agent": "Mozilla/5.0 (feedcast)"}


def lesswrong_post_id(link: str) -> Optional[str]:
    """Extract the 17-character post id from a LessWrong/Alignment Forum URL."""
    if not link or not any(h in link for h in _LW_HOSTS):
        return None
    m = _POST_ID.search(link)
    return m.group(1) if m else None


def _graphql_url(link: str) -> str:
    """The GraphQL endpoint of the site the link points at; both serve the same API."""
    host = "alignmentforum.org" if "alignmentforum" in link else "lesswrong.com"
    return f"https://www.{host}/graphql"


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
    pid = lesswrong_post_id(link)
    if not pid:
        return None
    query = ('{post(input:{selector:{_id:"%s"}}){result{postedAt}}}' % pid)
    try:
        owned = client is None
        client = client or httpx.AsyncClient(timeout=TIMEOUT)
        try:
            response = await client.post(
                _graphql_url(link), json={"query": query}, headers=_UA,
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


@lru_cache(maxsize=128)
def _graphql_markdown(post_id: str, url: str, timeout: float) -> Optional[str]:
    """Fetch one post's markdown, raising on transport failure.

    Raising rather than returning None is what makes the cache safe. lru_cache
    stores return values and not exceptions, so a timeout or a 502 is retried
    by the next caller, while a real "this post has no markdown" answer is
    remembered. Caching the failure instead would be quietly destructive: the
    maths filter runs first, so one flaky GraphQL call would poison the entry
    for fulltext.py, the episode would be built from the 3% podcast blurb, and
    marking it processed means it never gets another chance.
    """
    query = ('{post(input:{selector:{_id:"%s"}}){result{contents{markdown}}}}'
             % post_id)
    r = httpx.post(url, json={"query": query}, timeout=timeout, headers=_UA)
    r.raise_for_status()
    data = r.json()
    # `or {}` at every level, not `.get(k, {})`. GraphQL answers a deleted,
    # draft or unknown post with an explicit null rather than a missing key, and
    # .get("result", {}) hands back that null. The AttributeError that follows
    # is swallowed as None by the caller, which inverts this function's whole
    # contract: a permanent "no markdown here" gets refetched every run and is
    # reported to the user as a transient failure.
    return ((((data.get("data") or {}).get("post") or {})
             .get("result") or {}).get("contents") or {}).get("markdown")


def fetch_lesswrong_markdown(link: str, timeout: float = 30.0) -> Optional[str]:
    """Fetch a post's markdown source, where the LaTeX survives.

    Returns None on any failure. The maths filter then scores, and full-text
    recovery then keeps, whatever text the feed already gave.
    Callers that need to tell "no markdown" from "fetch broke" should check
    lesswrong_post_id() first and treat a None on a real post id as a failure.
    """
    post_id = lesswrong_post_id(link)
    if not post_id:
        return None
    try:
        return _graphql_markdown(post_id, _graphql_url(link), timeout)
    except Exception:
        return None
