"""Prediction markets in the daily briefing.

Two things, both optional and both silent when they find nothing:

1. Story context. For each story the briefing writer is given in full, find
   the prediction markets that are about it and give the writer the odds a
   week before the story, the day before it, and now. "Polymarket had this at
   twenty percent a week ago; it is eighty-five now" says how surprising the
   news was in a way the article cannot.
2. Moves. Scan the AI markets for big 24-hour moves that none of today's
   stories explains, look up the cause with a web search, and hand them to
   the writer for a short closing segment. The Anthropic IPO odds fell from
   fifty-five to three percent on 19 Sep 2026 on a report none of the
   briefing's sources carried until the 24th.

The thresholds come from a 30-day backtest (8 Sep to 8 Oct 2026, 768 AI
markets): a 15-point move, a volume floor, no markets about to close, no
leaderboards, and a topic whitelist fired about three days a week in a busy
month and about once a week without its one big story. Without the volume
floor some market moved 15 points every single day.

Public read APIs only, no keys: Polymarket (Gamma + CLOB), Kalshi (trade API
v2) and Manifold (play money, so context only, never a "move"). Every network
call is bounded and every failure degrades to "no market data", never to a
failed briefing.
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from .llm import ROUTES, complete, fallback_log, native_anthropic

POLYMARKET = "https://gamma-api.polymarket.com"
POLY_CLOB = "https://clob.polymarket.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
MANIFOLD = "https://api.manifold.markets/v0"
HEADERS = {"User-Agent": "feedcast (https://github.com/tbuckworth/feedcast)"}

# The model that looks up why a market moved. Server-side web search runs on
# Anthropic's API only, and Sonnet is plenty for "find the news story".
CAUSE_MODEL = "claude-sonnet-5"
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _float(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _when(raw) -> datetime | None:
    """Parse an ISO string or a millisecond timestamp to an aware UTC datetime."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class Market:
    """One yes/no question on one platform, with its odds now and a day ago."""

    platform: str                 # "Polymarket" | "Kalshi" | "Manifold"
    key: str                      # unique across platforms
    title: str
    url: str
    prob: float                   # 0..1, now
    prob_24h: float | None = None
    volume: float = 0.0           # lifetime, in the platform's own unit
    volume_30d: float | None = None
    volume_24h: float | None = None
    traders: int | None = None
    closes: datetime | None = None
    event: str = ""               # groups the outcomes of one question
    history_ref: str = ""         # what the history endpoint wants
    history: list = field(default_factory=list)   # [(datetime, prob)], hourly, last 30 days
    # The market's whole life (capped at a year), coarser, for the charts: a
    # long-running question needs months of context to show how surprising a
    # move was, and a short-dated one simply has a short line.
    long_history: list = field(default_factory=list)

    @property
    def move(self) -> float | None:
        return None if self.prob_24h is None else self.prob - self.prob_24h

    def traded(self) -> str:
        """How much backs the price, in words a listener can weigh."""
        if self.platform == "Polymarket":
            v = self.volume
            amount = f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:.0f}k"
            return f"{amount} traded"
        if self.platform == "Kalshi":
            return f"{self.volume:,.0f} contracts traded"
        return f"{self.traders or 0} traders, play money"

    def prob_at(self, when: datetime) -> float | None:
        """The last price at or before `when`, from the fetched history."""
        before = [p for t, p in self.history if t <= when]
        return before[-1] if before else None

    def to_dict(self) -> dict:
        """Plain JSON for the episode record and the trial email."""
        return {
            "platform": self.platform, "key": self.key, "title": self.title, "url": self.url,
            "prob": self.prob, "prob_24h": self.prob_24h, "traded": self.traded(),
            "history": [[t.isoformat(), p] for t, p in self.history],
            "long_history": [[t.isoformat(), p] for t, p in self.long_history],
        }


# --- Fetching -------------------------------------------------------------


def polymarket_markets(event: dict) -> list[Market]:
    """The open yes/no markets of one Polymarket event."""
    out = []
    for m in event.get("markets") or []:
        if m.get("closed") or not m.get("active", True):
            continue
        try:
            outcomes = json.loads(m.get("outcomes") or "[]")
            prices = json.loads(m.get("outcomePrices") or "[]")
            token = json.loads(m.get("clobTokenIds") or "[]")[0]
        except (ValueError, IndexError, TypeError):
            continue
        prob = _float(prices[0]) if prices else None
        if outcomes != ["Yes", "No"] or prob is None:
            continue
        change = _float(m.get("oneDayPriceChange"))
        out.append(Market(
            platform="Polymarket", key=f"polymarket:{m.get('id')}",
            title=m.get("question") or event.get("title", ""),
            url=f"https://polymarket.com/event/{event.get('slug', '')}",
            prob=prob, prob_24h=None if change is None else prob - change,
            volume=_float(m.get("volumeNum")) or 0.0, volume_30d=_float(m.get("volume1mo")),
            volume_24h=_float(m.get("volume24hr")),
            closes=_when(m.get("endDate") or event.get("endDate")),
            event=f"polymarket:{event.get('id')}", history_ref=str(token),
        ))
    return out


def kalshi_markets(event: dict) -> list[Market]:
    """The traded markets of one Kalshi event."""
    out = []
    series = event.get("series_ticker", "")
    for m in event.get("markets") or []:
        prob, prev = _float(m.get("last_price_dollars")), _float(m.get("previous_price_dollars"))
        volume = _float(m.get("volume_fp")) or 0.0
        if prob is None or not volume:
            continue
        sub = (m.get("yes_sub_title") or "").strip()
        title = event.get("title", "")
        out.append(Market(
            platform="Kalshi", key=f"kalshi:{m.get('ticker')}",
            title=f"{title} {sub}".strip() if sub and sub.lower() not in title.lower() else title,
            url=f"https://kalshi.com/markets/{series.lower()}",
            prob=prob, prob_24h=prev, volume=volume, volume_24h=_float(m.get("volume_24h_fp")),
            closes=_when(m.get("close_time")), event=f"kalshi:{event.get('event_ticker')}",
            history_ref=f"{series}|{m.get('ticker')}",
        ))
    return out


def manifold_market(m: dict) -> Market | None:
    prob = _float(m.get("probability"))
    if prob is None:
        return None
    return Market(
        platform="Manifold", key=f"manifold:{m.get('id')}", title=m.get("question", ""),
        url=m.get("url", ""), prob=prob, volume=_float(m.get("volume")) or 0.0,
        volume_24h=_float(m.get("volume24Hours")), traders=m.get("uniqueBettorCount"),
        closes=_when(m.get("closeTime")), event=f"manifold:{m.get('id')}",
        history_ref=str(m.get("id")),
    )


async def _get(client: httpx.AsyncClient, url: str, **params):
    r = await client.get(url, params=params)
    r.raise_for_status()
    return r.json()


async def polymarket_search(client: httpx.AsyncClient, query: str) -> list[Market]:
    data = await _get(client, f"{POLYMARKET}/public-search", q=query, limit_per_type=6)
    return [m for e in data.get("events") or [] if not e.get("closed")
            for m in polymarket_markets(e)]


async def polymarket_scan(client: httpx.AsyncClient, tags: list[str]) -> list[Market]:
    """The 100 busiest open events under each tag; quieter ones cannot pass the floor."""
    out: dict[str, Market] = {}
    for tag in tags:
        events = await _get(client, f"{POLYMARKET}/events", tag_slug=tag, active="true",
                            closed="false", limit=100, order="volume24hr", ascending="false")
        for e in events:
            for m in polymarket_markets(e):
                out[m.key] = m
    return list(out.values())


async def kalshi_scan(client: httpx.AsyncClient, series: list[str]) -> list[Market]:
    sem = asyncio.Semaphore(5)

    async def one(s: str) -> list[Market]:
        async with sem:
            data = await _get(client, f"{KALSHI}/events", series_ticker=s, status="open",
                              with_nested_markets="true", limit=200)
        return [m for e in data.get("events") or [] for m in kalshi_markets(e)]

    found = await asyncio.gather(*[one(s) for s in series], return_exceptions=True)
    return [m for r in found if not isinstance(r, BaseException) for m in r]


async def manifold_search(client: httpx.AsyncClient, term: str) -> list[Market]:
    data = await _get(client, f"{MANIFOLD}/search-markets", term=term, filter="open",
                      contractType="BINARY", limit=6)
    return [m for m in (manifold_market(x) for x in data or []) if m]


async def fetch_history(client: httpx.AsyncClient, market: Market, since: datetime) -> None:
    """Fill market.history from `since` to now. Leaves it empty on any failure."""
    try:
        if market.platform == "Polymarket":
            data = await _get(client, f"{POLY_CLOB}/prices-history", market=market.history_ref,
                              startTs=int(since.timestamp()), fidelity=60)
            points = [(datetime.fromtimestamp(h["t"], tz=timezone.utc), float(h["p"]))
                      for h in data.get("history") or []]
        elif market.platform == "Kalshi":
            series, ticker = market.history_ref.split("|", 1)
            data = await _get(client, f"{KALSHI}/series/{series}/markets/{ticker}/candlesticks",
                              start_ts=int(since.timestamp()),
                              end_ts=int(_utcnow().timestamp()), period_interval=60)
            points = []
            for c in data.get("candlesticks") or []:
                price = c.get("price") or {}
                p = _float(price.get("close_dollars")) or _float(price.get("previous_dollars"))
                if p is not None:
                    points.append((datetime.fromtimestamp(c["end_period_ts"], tz=timezone.utc), p))
        else:
            bets = await _get(client, f"{MANIFOLD}/bets", contractId=market.history_ref, limit=1000)
            points = sorted((_when(b["createdTime"]), float(b["probAfter"]))
                            for b in bets or [] if b.get("probAfter") is not None)
            # Keep the last bet before the window as its starting price.
            early = [pt for pt in points if pt[0] < since]
            points = early[-1:] + [pt for pt in points if pt[0] >= since]
        market.history = sorted(points)
    except Exception as e:  # noqa: BLE001 — a missing chart is not a failed run
        print(f"    market history unavailable ({market.key}): {type(e).__name__}")
        market.history = []


async def fetch_long_history(client: httpx.AsyncClient, market: Market,
                             max_days: int = 365) -> None:
    """Fill market.long_history: about two points a day since the market opened,
    at most `max_days` back. Leaves it empty on any failure."""
    since = _utcnow() - timedelta(days=max_days)
    try:
        if market.platform == "Polymarket":
            data = await _get(client, f"{POLY_CLOB}/prices-history", market=market.history_ref,
                              interval="max", fidelity=720)
            points = [(datetime.fromtimestamp(h["t"], tz=timezone.utc), float(h["p"]))
                      for h in data.get("history") or []]
        elif market.platform == "Kalshi":
            series, ticker = market.history_ref.split("|", 1)
            data = await _get(client, f"{KALSHI}/series/{series}/markets/{ticker}/candlesticks",
                              start_ts=int(since.timestamp()),
                              end_ts=int(_utcnow().timestamp()), period_interval=1440)
            points = []
            for c in data.get("candlesticks") or []:
                price = c.get("price") or {}
                p = _float(price.get("close_dollars")) or _float(price.get("previous_dollars"))
                if p is not None:
                    points.append((datetime.fromtimestamp(c["end_period_ts"], tz=timezone.utc), p))
        else:
            # Newest first, 1,000 a page; three pages reach back far enough
            # for all but the busiest markets.
            bets, before = [], None
            for _ in range(3):
                page = await _get(client, f"{MANIFOLD}/bets", contractId=market.history_ref,
                                  limit=1000, **({"before": before} if before else {}))
                bets += page or []
                if len(page or []) < 1000:
                    break
                before = page[-1]["id"]
            points = sorted((_when(b["createdTime"]), float(b["probAfter"]))
                            for b in bets if b.get("probAfter") is not None)
        market.long_history = _thin([pt for pt in sorted(points) if pt[0] >= since], 800)
    except Exception as e:  # noqa: BLE001 — the chart falls back to the 30-day history
        print(f"    long market history unavailable ({market.key}): {type(e).__name__}")
        market.long_history = []


def _thin(points: list, limit: int) -> list:
    """At most `limit` points, evenly spaced through the list, keeping the last."""
    if len(points) <= limit:
        return points
    step = len(points) / limit
    return [points[int(i * step)] for i in range(limit - 1)] + [points[-1]]


# --- Rules ------------------------------------------------------------------


@dataclass
class MarketRules:
    """What counts as a move worth a closing line. Defaults from the backtest."""

    move: float = 0.15
    major_move: float = 0.20
    polymarket_volume_30d: float = 50_000
    polymarket_volume: float = 200_000
    kalshi_volume: float = 20_000
    kalshi_volume_24h: float = 1_000
    context_polymarket_volume: float = 20_000
    context_kalshi_volume: float = 5_000
    context_manifold_traders: int = 50
    min_days_to_close: float = 7
    # A move that ends at the very edge is usually a question being settled
    # early. The backtest used 3%; 2% keeps the Anthropic IPO fall to 3%
    # (19 Sep), which was news, not a settlement.
    edge: float = 0.02
    max_moves: int = 3
    # Leaderboards, benchmark debuts, market share, token prices: they move
    # every time one benchmark updates and say nothing about the world.
    exclude: str = (
        r"best (ai|llm)|best .*model|top[- ](ranked|ai|model|coding|chinese|math|llm)|"
        r"#\s?\d|ranked|arena|market share|token usage|openrouter|share of|"
        r"debut|second-best|third-best|runner.up|gpu rental|hourly price|ddr5|token price|"
        r"output token|input token|app downloads|app store|\bcompany [a-z]\b|"
        r"released on|release date|which company has")
    # Timelines and capabilities; policy and safety.
    topics: str = (
        r"\bAGI\b|general AI|superintelligen|millennium|frontiermath|human.level|"
        r"self.improv|singularity|AI winter|capabilit|"
        r"\bbill\b|\blaw\b|moratorium|regulat|kill.?switch|pause|\bban\b|safety|pentagon|"
        r"executive order|sandbox|vetting|training|federal|congress|preempt|export|treaty")
    # Allowed, but only at major_move: corporate stories.
    major_only: str = r"\bIPO\b|valuation|market cap|\bCEO\b|acquire|bankrupt|lawsuit|board"


def is_liquid(m: Market, rules: MarketRules, *, context: bool = False) -> bool:
    """Enough money behind the price to take it seriously."""
    if m.platform == "Polymarket":
        if context:
            return m.volume >= rules.context_polymarket_volume
        return ((m.volume_30d or 0) >= rules.polymarket_volume_30d
                or m.volume >= rules.polymarket_volume)
    if m.platform == "Kalshi":
        if context:
            return m.volume >= rules.context_kalshi_volume
        return m.volume >= rules.kalshi_volume and (m.volume_24h or 0) >= rules.kalshi_volume_24h
    # Play money: context only, never a move.
    return context and (m.traders or 0) >= rules.context_manifold_traders


def is_move(m: Market, rules: MarketRules, now: datetime) -> bool:
    """A big, liquid, on-topic 24-hour move that is not just a market expiring."""
    if m.move is None or abs(m.move) < rules.move - 1e-9 or not is_liquid(m, rules):
        return False
    if m.closes and (m.closes - now).total_seconds() < rules.min_days_to_close * 86400:
        return False
    if m.prob <= rules.edge or m.prob >= 1 - rules.edge:
        return False
    if re.search(rules.exclude, m.title, re.I):
        return False
    if re.search(rules.topics, m.title, re.I):
        return True
    return bool(re.search(rules.major_only, m.title, re.I)) and abs(m.move) >= rules.major_move - 1e-9


_STOP = {"will", "the", "and", "for", "are", "was", "has", "its", "new", "now", "not", "but",
         "who", "how", "why", "per", "via", "any", "before", "after", "with", "from", "this",
         "that", "what", "when", "which", "than", "more", "less", "end", "2026", "2027", "2028",
         # Generic to every product-launch market; matching on them pairs a
         # GPT story with a Claude release market.
         "release", "released", "releases", "launch", "launches", "model", "models",
         "announce", "announced", "officially", "company", "next"}


def _words(text: str) -> set[str]:
    """Content words, short acronyms included: "IPO" and "AGI" carry the meaning."""
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in _STOP}


def pick_moves(markets: list[Market], rules: MarketRules, now: datetime,
               skip_events: set[str] | None = None,
               recently_reported: dict[str, float] | None = None) -> list[Market]:
    """The moves for the closing segment: one per story, the most liquid first.

    `skip_events`: events already attached to one of today's stories, whose
    move the story itself explains. `recently_reported`: market key -> the
    price at which it was last reported; a market is reported again only once
    it has moved another threshold's worth since.
    """
    skip_events = skip_events or set()
    recently_reported = recently_reported or {}
    best: dict[str, Market] = {}
    for m in markets:
        if not is_move(m, rules, now) or m.event in skip_events:
            continue
        last = recently_reported.get(m.key)
        if last is not None and abs(m.prob - last) < rules.move - 1e-9:
            continue
        cur = best.get(m.event)
        if cur is None or abs(m.move) > abs(cur.move):
            best[m.event] = m
    # The same story on two platforms ("Anthropic IPO" on Polymarket and
    # Kalshi) is one line: keep the one with more money behind it.
    chosen: list[Market] = []
    for m in sorted(best.values(), key=lambda m: m.volume_24h or 0, reverse=True):
        if any(len(_words(m.title) & _words(c.title)) >= 2 for c in chosen):
            continue
        chosen.append(m)
    return chosen[: rules.max_moves]


# --- Story context ----------------------------------------------------------


QUERY_PROMPT = """For each news story below, give one or two short search queries (two to four words each) that would find prediction markets about the story's subject or its direct consequences, on sites like Polymarket. Skip stories no market is likely to cover (an op-ed, a product review, a feature).

Return ONLY JSON: {"<story number>": ["query", ...], ...}"""

MATCH_PROMPT = """Below are news stories, each followed by candidate prediction markets found by keyword search. For each story, pick the markets (at most two) whose question is directly about the story's subject or its immediate consequence, so that the odds would tell a listener how expected the news was or how it changed expectations. Reject anything only loosely related, and reject a market when the story gives no reason to care about it. Never pick two markets that ask the same question on different platforms: keep the one with real money behind it (Polymarket or Kalshi over Manifold).

Return ONLY JSON: {"<story number>": ["<market key>", ...], ...} listing only stories with a match."""


def _json_object(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


async def link_stories(client: httpx.AsyncClient, stories: list[dict], rules: MarketRules,
                       kalshi_pool: list[Market]) -> dict[int, list[Market]]:
    """story index -> the markets about it. Two small checker-model calls."""
    if not stories:
        return {}
    now = _utcnow()
    listing = "\n".join(f"{i}. {s['title']} — {(s.get('summary') or '')[:300]}"
                        for i, s in enumerate(stories))
    done = await complete("checker", max_tokens=2000, label="market queries", messages=[
        {"role": "system", "content": QUERY_PROMPT}, {"role": "user", "content": listing}])
    queries = {int(k): [q for q in v if isinstance(q, str)][:2]
               for k, v in _json_object(done.text).items()
               if str(k).isdigit() and int(k) < len(stories) and isinstance(v, list)}

    sem = asyncio.Semaphore(6)

    async def search(q: str) -> list[Market]:
        async with sem:
            found = await asyncio.gather(polymarket_search(client, q), manifold_search(client, q),
                                         return_exceptions=True)
        return [m for r in found if not isinstance(r, BaseException) for m in r]

    candidates: dict[int, dict[str, Market]] = {}
    for i, qs in queries.items():
        results = await asyncio.gather(*[search(q) for q in qs])
        pool = {m.key: m for r in results for m in r}
        # Kalshi has no search; match its AI markets by shared words instead.
        for m in kalshi_pool:
            if any(len(_words(q) & _words(m.title)) >= max(1, len(_words(q)) - 1) for q in qs):
                pool[m.key] = m
        # Open, liquid, undecided, and one outcome per question: "Democrats
        # win Ohio" and "Republicans win Ohio" are the same number twice.
        per_event: dict[str, Market] = {}
        for m in pool.values():
            if (is_liquid(m, rules, context=True) and 0.01 < m.prob < 0.99
                    and (m.closes is None or m.closes > now)):
                cur = per_event.get(m.event)
                if cur is None or m.volume > cur.volume:
                    per_event[m.event] = m
        if per_event:
            candidates[i] = {m.key: m for m in
                             sorted(per_event.values(), key=lambda m: m.volume, reverse=True)[:8]}
    if not candidates:
        return {}

    blocks = []
    for i, pool in candidates.items():
        lines = [f"{i}. {stories[i]['title']} — {(stories[i].get('summary') or '')[:300]}"]
        lines += [f"   [{m.key}] {m.platform}: {m.title} (now {m.prob:.0%}, {m.traded()})"
                  for m in pool.values()]
        blocks.append("\n".join(lines))
    done = await complete("checker", max_tokens=2000, label="market matching", messages=[
        {"role": "system", "content": MATCH_PROMPT},
        {"role": "user", "content": "\n\n".join(blocks)}])
    linked: dict[int, list[Market]] = {}
    for k, keys in _json_object(done.text).items():
        if not str(k).isdigit() or int(k) not in candidates or not isinstance(keys, list):
            continue
        pool = candidates[int(k)]
        picked = [pool[key] for key in keys if isinstance(key, str) and key in pool][:2]
        if picked:
            linked[int(k)] = picked
    return linked


# --- Causes -------------------------------------------------------------------


CAUSE_PROMPT = """A prediction market moved sharply in the last day. Search recent news for what moved it.

Market ({platform}): {title}
Moved from {before:.0%} to {after:.0%} between {start} and {end} (UTC).

Reply with ONLY JSON, no other text:
{{"found": true or false, "summary": "one or two sentences: what happened, according to whom, and when", "source": "publication name", "url": "link to the report"}}
Set found to false if nothing you find clearly explains the move. Do not guess."""


async def find_cause(m: Market, now: datetime) -> dict | None:
    """Ask a web-searching model why `m` moved. None when the lookup itself fails."""
    if not os.environ.get(ROUTES["anthropic"].key_env):
        return None
    prompt = CAUSE_PROMPT.format(platform=m.platform, title=m.title, before=m.prob_24h,
                                 after=m.prob, start=f"{now - timedelta(days=1):%d %b %H:%M}",
                                 end=f"{now:%d %b %H:%M}")
    messages = [{"role": "user", "content": prompt}]
    try:
        for _ in range(3):   # pause_turn: a long search turn is resumed, not restarted
            msg = await native_anthropic().messages.create(
                model=CAUSE_MODEL, max_tokens=2000, messages=messages, tools=[WEB_SEARCH_TOOL])
            if msg.stop_reason != "pause_turn":
                break
            messages = [*messages, {"role": "assistant", "content": msg.content}]
        text = "".join(b.text for b in msg.content if b.type == "text")
    except Exception as e:  # noqa: BLE001 — no cause is a sentence, not a failure
        note = f"market cause lookup: {type(e).__name__}: {str(e)[:160]}"
        print(f"    {note}")
        fallback_log.append(note)
        return None
    found = _json_object(text)
    if not found.get("found") or not found.get("summary"):
        return {"found": False}
    return {"found": True, "summary": str(found["summary"])[:500],
            "source": str(found.get("source") or "")[:80], "url": str(found.get("url") or "")}


# --- Putting it together ------------------------------------------------------


@dataclass
class MarketContext:
    """What the briefing writer is given, and what the email draws."""

    stories: dict[str, list[Market]] = field(default_factory=dict)   # article url -> markets
    story_times: dict[str, datetime] = field(default_factory=dict)  # article url -> published
    moves: list[Market] = field(default_factory=list)
    causes: dict[str, dict | None] = field(default_factory=dict)     # market key -> cause

    def __bool__(self) -> bool:
        return bool(self.stories or self.moves)

    def story_block(self, url: str) -> str:
        """The lines appended to one story in the writer's input."""
        markets = self.stories.get(url) or []
        when = self.story_times.get(url)
        if not markets or when is None:
            return ""
        lines = ["  Prediction markets on this story:"]
        for m in markets:
            week, day = m.prob_at(when - timedelta(days=7)), m.prob_at(when - timedelta(days=1))
            then = []
            if week is not None:
                then.append(f"{week:.0%} a week before this story")
            if day is not None:
                then.append(f"{day:.0%} the day before it")
            then.append(f"{m.prob:.0%} now")
            lines.append(f'  - {m.platform}, "{m.title}": {", ".join(then)} ({m.traded()}). {m.url}')
        return "\n".join(lines)

    def moves_section(self) -> str:
        if not self.moves:
            return ""
        lines = ["## Prediction-market moves in the last 24 hours that today's stories do not explain", ""]
        for m in self.moves:
            line = (f'- {m.platform}, "{m.title}": {m.prob_24h:.0%} to {m.prob:.0%} in the last '
                    f"24 hours ({m.traded()}). {m.url}")
            cause = self.causes.get(m.key)
            if cause and cause.get("found"):
                line += (f"\n  Cause found by a news search: {cause['summary']}"
                         f" Source: {cause.get('source') or 'unnamed'} {cause.get('url') or ''}".rstrip())
            elif cause is not None:
                line += "\n  A news search found no clear cause."
            else:
                line += "\n  The cause was not looked up."
            lines.append(line)
        return "\n".join(lines)

    def instructions(self) -> str:
        """Added to the writer's input only on days with market data."""
        parts = []
        if self.stories:
            parts.append(
                "Some stories carry prediction-market odds. Where they add something, such as how "
                "expected the news was or how the odds moved after it, work them into that story in "
                "one short clause and name the platform. Leave them out when they add nothing. Use "
                "only the numbers given.")
        if self.moves:
            parts.append(
                "After your closing forward look, end with a short segment that begins "
                "\"On the prediction markets,\" and covers each move in the section below in one or "
                "two sentences: the question, where the odds went, and the cause the section gives, "
                "attributed to its source. If it gives none, say no clear cause was found. At most "
                "eighty words, and not counted in your word limit.")
        return "\n\n".join(parts)

    def sources(self) -> list[dict]:
        """Market links for the email digest, alongside the articles."""
        seen, out = set(), []
        for m in [*self.moves, *(m for ms in self.stories.values() for m in ms)]:
            if m.url and m.url not in seen:
                seen.add(m.url)
                out.append({"title": m.title, "url": m.url, "source": m.platform})
        return out

    def to_dict(self) -> dict:
        return {
            "stories": {u: [m.to_dict() for m in ms] for u, ms in self.stories.items()},
            "story_times": {u: t.isoformat() for u, t in self.story_times.items()},
            "moves": [m.to_dict() for m in self.moves],
            "causes": self.causes,
        }


@dataclass
class MarketScout:
    """Builds a MarketContext for one briefing. Never raises."""

    rules: MarketRules = field(default_factory=MarketRules)
    polymarket_tags: list[str] = field(default_factory=lambda: ["ai", "openai", "anthropic"])
    kalshi_series: list[str] = field(default_factory=list)
    recently_reported: dict[str, float] = field(default_factory=dict)
    timeout_seconds: float = 240

    async def build(self, selected: list[dict]) -> MarketContext:
        try:
            return await asyncio.wait_for(self._build(selected), self.timeout_seconds)
        except Exception as e:  # noqa: BLE001 — the briefing goes ahead without markets
            note = f"prediction markets skipped: {type(e).__name__}: {str(e)[:160]}"
            print(f"  {note}")
            fallback_log.append(note)
            return MarketContext()

    async def _build(self, selected: list[dict]) -> MarketContext:
        now = _utcnow()
        ctx = MarketContext()
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), headers=HEADERS) as client:
            scans = await asyncio.gather(polymarket_scan(client, self.polymarket_tags),
                                         kalshi_scan(client, self.kalshi_series),
                                         return_exceptions=True)
            poly_pool, kalshi_pool = [r if isinstance(r, list) else [] for r in scans]
            for r in scans:
                if isinstance(r, BaseException):
                    print(f"    market scan failed: {type(r).__name__}: {r}")
            print(f"  Prediction markets: {len(poly_pool)} Polymarket and "
                  f"{len(kalshi_pool)} Kalshi AI markets")

            stories = [a for a in selected if a.get("url")]
            linked = await link_stories(client, stories, self.rules, kalshi_pool)
            for i, markets in linked.items():
                url = stories[i]["url"]
                ctx.stories[url] = markets
                published = stories[i].get("published")
                if isinstance(published, datetime):
                    ctx.story_times[url] = (published if published.tzinfo
                                            else published.replace(tzinfo=timezone.utc))
            linked_events = {m.event for ms in ctx.stories.values() for m in ms}
            ctx.moves = pick_moves(poly_pool + kalshi_pool, self.rules, now,
                                   skip_events=linked_events,
                                   recently_reported=self.recently_reported)

            since = now - timedelta(days=30)
            everything = [*ctx.moves, *(m for ms in ctx.stories.values() for m in ms)]
            await asyncio.gather(*[fetch_history(client, m, since) for m in everything],
                                 *[fetch_long_history(client, m) for m in everything])
        causes = await asyncio.gather(*[find_cause(m, now) for m in ctx.moves])
        ctx.causes = {m.key: c for m, c in zip(ctx.moves, causes)}
        print(f"  Prediction markets: {sum(len(v) for v in ctx.stories.values())} linked to "
              f"{len(ctx.stories)} stories, {len(ctx.moves)} unexplained moves")
        return ctx
