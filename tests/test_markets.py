"""Prediction markets in the briefing: parsing, the move rules, the sentence on how
each market resolves, the writer's input, and the daily email's market notes. No
network: every API reply here is a fixture."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

import src.main as main
import src.markets as markets
from src import llm, notices
from src.chunking import sentences
from src.config import load_config
from src.email_report import (MarketNote, ReportEpisode, RunReport, build_html, build_text,
                              send_report)
from src.market_charts import market_notes_for_report
from src.markets import (MAX_RESOLVES_WORDS, NO_RULES, Market, MarketContext, MarketRules,
                         MarketScout, is_move, kalshi_markets, pick_moves, polymarket_markets,
                         resolution, rule_sentence)
from src.monitor import FeedEntry, FeedMonitor
from src.news import NewsAggregator
from tests.conftest import FakeApi, FakeMessagesApi

NOW = datetime(2026, 9, 19, 4, 0, tzinfo=timezone.utc)
# The backtest's move sizes, which config.yaml `prediction_markets` sets.
RULES = MarketRules(move=0.15, major_move=0.20, max_moves=3)

# Rules as each platform's API returned them on 16 Nov 2026 (the Polymarket and
# Manifold ones shortened after their second paragraph), and the sentence of
# each that says how the market resolves.
POLYMARKET_RULES = (
    'This market will resolve to "Yes" if Anthropic shares are listed on a public securities '
    'exchange and open for trading by 11:59 PM ET on the listed date. Otherwise, this market '
    'will resolve to "No."\n\nIf Anthropic is acquired by another company that is already '
    'public, this market will immediately resolve to "No."')
POLYMARKET_RESOLVES = (
    'This market will resolve to "Yes" if Anthropic shares are listed on a public securities '
    "exchange and open for trading by 11:59 PM ET on the listed date.")
KALSHI_PRIMARY = "If Anthropic confirms an IPO before Dec 1, 2026, then the market resolves to Yes."
KALSHI_SECONDARY = (
    "An IPO is confirmed if 1) the SEC declares the company's Form S-1 effective OR 2) the IPO "
    "is priced OR 3) a securities exchange has assigned a ticker to it.")
MANIFOLD_RULES = (
    "Artificial General Intelligence (AGI) refers to a type of artificial intelligence that has "
    "the ability to understand, learn, and apply its intelligence to a wide variety of "
    "problems, much like a human being. It involves the capability to reason, plan, solve "
    "problems, think abstractly, comprehend complex ideas, learn quickly, and learn from "
    "experience.\n\nResolves as YES if such a system is created and publicly announced before "
    "January 1st 2029\n\nMOD EDIT (Nov 2, 2025 - @Stralor)\n\nIf that resolves NO for this "
    "market's year (and every year earlier), this also resolves NO.")
MANIFOLD_RESOLVES = ("Resolves as YES if such a system is created and publicly announced before "
                     "January 1st 2029.")
BILL_RESOLVES = ('This market will resolve to "Yes" if a federal AI safety bill is signed into '
                 "law by December 31, 2026, 11:59 PM ET.")


def _m(title="Will Congress pass an AI safety bill in 2026?", platform="Polymarket", prob=0.30,
       before=0.55, volume=500_000.0, volume_30d=100_000.0, volume_24h=40_000.0,
       closes=NOW + timedelta(days=90), event=None, key=None, traders=None,
       resolves=BILL_RESOLVES):
    key = key or f"{platform.lower()}:{title}"
    return Market(platform=platform, key=key, title=title, url=f"https://pm/{abs(hash(title))}",
                  prob=prob, prob_24h=before, volume=volume, volume_30d=volume_30d,
                  volume_24h=volume_24h, closes=closes, event=event or key, traders=traders,
                  resolves=resolves)


class TestParsing:

    def test_polymarket_reads_yes_price_and_derives_yesterday(self):
        event = {"id": 7, "slug": "anthropic-ipo-by", "title": "Anthropic IPO by ___?", "markets": [
            {"id": "1", "question": "Anthropic IPO by October 31, 2026?", "outcomes": '["Yes", "No"]',
             "outcomePrices": '["0.03", "0.97"]', "oneDayPriceChange": -0.52, "volumeNum": 1160616,
             "volume1mo": 432462, "volume24hr": 50000, "endDate": "2026-10-31T12:00:00Z",
             "clobTokenIds": '["tok1", "tok2"]', "description": POLYMARKET_RULES},
            {"id": "2", "question": "closed one", "closed": True, "outcomes": '["Yes", "No"]',
             "outcomePrices": '["1", "0"]', "clobTokenIds": '["t"]'},
            {"id": "3", "question": "three-way", "outcomes": '["A", "B", "C"]',
             "outcomePrices": '["0.2", "0.3", "0.5"]', "clobTokenIds": '["t"]'},
        ]}
        (m,) = polymarket_markets(event)
        assert m.prob == pytest.approx(0.03) and m.prob_24h == pytest.approx(0.55)
        assert m.url == "https://polymarket.com/event/anthropic-ipo-by"
        assert m.event == "polymarket:7" and m.history_ref == "tok1"
        assert m.traded() == "$1.2M traded"
        assert m.rules == POLYMARKET_RULES and resolution(m) == POLYMARKET_RESOLVES

    def test_kalshi_titles_carry_the_outcome_and_skip_untraded_markets(self):
        event = {"event_ticker": "KXIPOANTHROPIC-DATE", "series_ticker": "KXIPOANTHROPIC",
                 "title": "When will Anthropic officially announce an IPO?", "markets": [
                     {"ticker": "A", "yes_sub_title": "Before Nov 1, 2026", "last_price_dollars": "0.06",
                      "previous_price_dollars": "0.53", "volume_fp": "478276", "volume_24h_fp": "40565",
                      "close_time": "2026-11-01T03:59:00Z", "rules_primary": KALSHI_PRIMARY,
                      "rules_secondary": KALSHI_SECONDARY},
                     {"ticker": "B", "yes_sub_title": "Before Dec 1", "last_price_dollars": "0.5",
                      "previous_price_dollars": "0.5", "volume_fp": "0"}]}
        (m,) = kalshi_markets(event)
        assert m.title == "When will Anthropic officially announce an IPO? Before Nov 1, 2026"
        assert m.move == pytest.approx(-0.47) and m.history_ref == "KXIPOANTHROPIC|A"
        assert m.url == "https://kalshi.com/markets/kxipoanthropic"
        assert m.rules == f"{KALSHI_PRIMARY}\n{KALSHI_SECONDARY}" and resolution(m) == KALSHI_PRIMARY


class TestMoveRules:

    def test_a_big_liquid_on_topic_move_counts(self):
        assert is_move(_m(), RULES, NOW)

    @pytest.mark.parametrize("change", [
        dict(before=0.40),                               # 10 points: too small
        dict(volume=10_000, volume_30d=5_000),           # thin
        dict(closes=NOW + timedelta(days=3)),            # expiring
        dict(prob=0.01, before=0.40),                    # resolving
        dict(title="Best AI model end of October: Google"),   # leaderboard
        dict(title="Will SpaceXAI rename itself by October 31?"),  # off topic
    ])
    def test_what_does_not_count(self, change):
        assert not is_move(_m(**change), RULES, NOW)

    def test_corporate_markets_need_the_major_threshold(self):
        ipo = dict(title="Anthropic IPO by October 31, 2026?")
        assert not is_move(_m(prob=0.40, before=0.57, **ipo), RULES, NOW)   # 17 points
        assert is_move(_m(prob=0.03, before=0.55, **ipo), RULES, NOW)

    def test_manifold_is_context_never_a_move(self):
        assert not is_move(_m(platform="Manifold", traders=900), RULES, NOW)

    def test_one_line_per_story_most_liquid_first_and_no_repeats(self):
        a = _m("Anthropic IPO by October 31, 2026?", prob=0.03, before=0.55, event="pm:ipo",
               key="pm:1", volume_24h=50_000)
        a2 = _m("Anthropic IPO by November 15, 2026?", prob=0.51, before=0.71, event="pm:ipo",
                key="pm:2", volume_24h=60_000)
        k = _m("When will Anthropic officially announce an IPO? Before Nov 1, 2026",
               platform="Kalshi", prob=0.06, before=0.53, volume=478_276, volume_24h=40_565,
               key="ks:1", event="ks:ipo")
        bill = _m(key="pm:bill", event="pm:bill", volume_24h=10_000)
        moves = pick_moves([a, a2, k, bill], RULES, NOW)
        assert [m.key for m in moves] == ["pm:1", "pm:bill"]   # biggest move per event; Kalshi dupe dropped
        assert pick_moves([a, bill], RULES, NOW, skip_events={"pm:ipo"}) == [bill]
        # Reported yesterday at 3%: not again until it moves another 15 points.
        assert pick_moves([a], RULES, NOW, recently_reported={"pm:1": 0.04}) == []
        assert pick_moves([a], RULES, NOW, recently_reported={"pm:1": 0.30}) == [a]


class TestResolutionSentence:
    """The one sentence on how a market resolves is lifted from its rules, never written."""

    @pytest.mark.parametrize("rules, sentence", [
        (POLYMARKET_RULES, POLYMARKET_RESOLVES),
        (f"{KALSHI_PRIMARY}\n{KALSHI_SECONDARY}", KALSHI_PRIMARY),
        # Background first, and the rule on a line with no full stop: one is added.
        (MANIFOLD_RULES, MANIFOLD_RESOLVES),
        # A link and an image, as Manifold's plain text leaves them.
        ("(https://www.metaculus.com/questions/embed/41141)Resolves according to Metaculus "
         "resolution.\n\n[image]More below.", "Resolves according to Metaculus resolution."),
        ("I'll resolve this entirely subjectively.", "I'll resolve this entirely subjectively."),
    ])
    def test_it_is_the_first_sentence_of_the_rules_that_says_how(self, rules, sentence):
        found = rule_sentence(rules)
        assert found == sentence
        # Word for word from the rules, but for the full stop a bare line gets.
        assert found.rstrip(".") in rules

    @pytest.mark.parametrize("rules", [POLYMARKET_RULES, f"{KALSHI_PRIMARY}\n{KALSHI_SECONDARY}",
                                       MANIFOLD_RULES])
    def test_it_is_exactly_one_sentence(self, rules):
        found = rule_sentence(rules)
        assert found.endswith(".") and len(found.split()) <= MAX_RESOLVES_WORDS
        assert sentences(found) == [found]   # no second sentence

    @pytest.mark.parametrize("sentence", [
        'This market will resolve to "Yes" if the U.S. federal government or OpenAI publicly '
        "alleges that he acted on behalf of the listed entity by December 31, 2026, 11:59 PM ET.",
        "This market will resolve according to the number of qualifying resets announced between "
        "12:00 a.m. ET on November 16, 2026, and 11:59 p.m. ET on November 22, 2026.",
        "This market will resolve to the company with the highest market capitalization in U.S. "
        "dollars, e.g. Anthropic, on its first trading day before Dec. 31, 2026.",
        "This market resolves YES if Donald J. Trump signs the bill before 2027.",
    ])
    def test_an_abbreviation_does_not_end_the_sentence(self, sentence):
        assert rule_sentence(f"{sentence} Otherwise, this market will resolve to \"No.\" "
                             "More rules follow.") == sentence

    def test_a_closing_quote_after_the_full_stop_ends_the_sentence(self):
        assert sentences('It will resolve to "No." If acquired, it resolves "No". Then more.') == [
            'It will resolve to "No."', 'If acquired, it resolves "No".', "Then more."]

    @pytest.mark.parametrize("rules", [
        # "Resolve" the noun, not the verb.
        "China might seize an island to test American and Taiwanese resolve, as a bargaining chip.",
        # The rule introduces a list the sentence does not carry; the side
        # condition after it is not passed off as the rule.
        "Resolves YES if OpenAI offers compute through ANY of the following:\n"
        "Public cloud service\nResolves NO if he dies in custody.",
        # Too long to read out.
        "This market will resolve to \"Yes\" if " + "the agency confirms it " * 20 + "by June.",
        "Background only, with no rule in it.",
    ])
    def test_rules_with_no_usable_sentence_give_none(self, rules):
        assert rule_sentence(rules) is None

    def test_only_a_manifold_market_may_state_no_rules(self):
        assert resolution(_m(platform="Manifold")) is None         # rules not read yet
        blank = _m(platform="Manifold")
        blank.rules = "  \n"
        assert resolution(blank) == NO_RULES
        assert NO_RULES == "This market states no resolution rules beyond its title."
        # Polymarket and Kalshi always publish rules: none means the reply changed
        # shape, and the market is dropped rather than said to have no rules.
        for platform in ("Polymarket", "Kalshi"):
            empty = _m(platform=platform)
            empty.rules = ""
            assert resolution(empty) is None


IPO = "Anthropic IPO by October 31, 2026?"
OHIO_RESOLVES = ("This market will resolve according to the party of the candidate who wins the "
                 "2026 Ohio Senate election.")


def _ctx_with_story_and_move(cause):
    story = _m("Will Democrats win the Ohio Senate race in 2026?", prob=0.62, before=None,
               resolves=OHIO_RESOLVES)
    story.history = [(NOW - timedelta(days=8), 0.58), (NOW - timedelta(days=2), 0.60),
                     (NOW - timedelta(hours=1), 0.62)]
    move = _m(IPO, prob=0.03, before=0.55, key="pm:ipo", resolves=POLYMARKET_RESOLVES)
    return MarketContext(stories={"https://news/ohio": [story]},
                         story_times={"https://news/ohio": NOW}, moves=[move],
                         causes={"pm:ipo": cause})


class TestWriterInput:

    def test_story_block_gives_odds_before_the_story_and_now(self):
        block = _ctx_with_story_and_move(None).story_block("https://news/ohio")
        assert "58% a week before this story, 60% the day before it, 62% now" in block
        assert "$500k traded" in block and _ctx_with_story_and_move(None).story_block("x") == ""
        assert block.endswith(f"\n    Resolves: {OHIO_RESOLVES}")

    def test_moves_section_says_what_the_search_found_or_did_not(self):
        found = {"found": True, "summary": "The Journal reported a November target.",
                 "source": "WSJ", "url": "https://wsj/x"}
        assert "Cause found by a news search: The Journal reported" in \
               _ctx_with_story_and_move(found).moves_section()
        assert "no clear cause" in _ctx_with_story_and_move({"found": False}).moves_section()
        assert "55% to 3%" in _ctx_with_story_and_move({"found": False}).moves_section()
        # The move's own sentence, between its odds and its cause.
        assert (f"https://pm/{abs(hash(IPO))}\n  Resolves: {POLYMARKET_RESOLVES}\n  Cause found"
                in _ctx_with_story_and_move(found).moves_section())

    def test_no_market_data_means_no_instructions_and_an_unchanged_message(self):
        assert MarketContext().instructions() == "" and not MarketContext()
        sent = []

        class Client:
            def __init__(self):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
            async def create(self, **kw):
                sent.append(kw["messages"][-1]["content"])
                return SimpleNamespace(choices=[SimpleNamespace(
                    message=SimpleNamespace(content="Briefing."), finish_reason="stop")])

        agg = NewsAggregator(sources=[], prompt="Write.", lookback_hours=24,
                             full_text_stories=12, max_article_chars=6000,
                             author="Feedcast Bot", verify=False)
        agg.client = Client()
        asyncio.run(agg.synthesize_briefing("ARTICLES"))
        asyncio.run(agg.synthesize_briefing("ARTICLES", MarketContext().instructions()))
        assert sent[0] == sent[1]
        asyncio.run(agg.synthesize_briefing("ARTICLES", _ctx_with_story_and_move(None).instructions()))
        assert '"On the prediction markets,"' in sent[2] and "Leave them out" in sent[2]
        assert ('Every market below has a "Resolves:" line' in sent[2]
                and "never describe from memory how a market resolves" in sent[2])
        assert sent[2].index("prediction markets") < sent[2].index("## Today's articles:")

    def test_briefing_input_carries_the_odds_and_the_moves(self):
        agg = NewsAggregator(sources=[], prompt="Write.", lookback_hours=24,
                             full_text_stories=12, max_article_chars=6000,
                             author="Feedcast Bot", verify=False)
        story = {"title": "Brown runs on datacenters", "source": "Guardian", "category": "politics",
                 "summary": "b", "url": "https://news/ohio", "published": NOW}
        text = agg._format_briefing_input([story], [story],
                                          _ctx_with_story_and_move({"found": False}))
        assert "Prediction markets on this story" in text and text.rstrip().endswith("no clear cause.")
        assert agg._format_briefing_input([story], [story]) == \
               agg._format_briefing_input([story], [story], MarketContext())

    def test_a_failing_scout_leaves_the_briefing_without_markets(self, monkeypatch):
        async def boom(self, selected):
            raise RuntimeError("Polymarket is down")
        monkeypatch.setattr(MarketScout, "_build", boom)
        ctx = asyncio.run(MarketScout(rules=RULES, polymarket_tags=["ai"]).build([]))
        assert not ctx and "prediction markets skipped" in notices.report()[0]


def _market_api(monkeypatch, handler) -> None:
    """Send every market request to `handler` instead of the network."""
    real = httpx.AsyncClient
    monkeypatch.setattr(markets.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


BILL_EVENT = {"id": 7, "slug": "ai-bill", "title": "AI bill", "markets": [{
    "id": "1", "question": "Will Congress pass an AI safety bill in 2026?",
    "outcomes": '["Yes", "No"]', "outcomePrices": '["0.30", "0.70"]',
    "oneDayPriceChange": -0.25, "volumeNum": 500000, "volume1mo": 100000, "volume24hr": 40000,
    "endDate": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
    "clobTokenIds": '["tok1", "tok2"]',
    "description": f'{BILL_RESOLVES} Otherwise, this market will resolve to "No".'}]}
BILL = "Will Congress pass an AI safety bill in 2026?"


class TestFailuresReachTheEmail:
    """A market call that fails, or a model reply that cannot be read, costs the
    briefing a market, some odds or a chart. Each used to cost it in silence."""

    def test_a_failed_cause_lookup_drops_the_move_instead_of_reading_as_no_cause(
            self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.setattr(llm, "native_anthropic",
                            lambda: FakeMessagesApi("I looked, but here is prose, not JSON."))
        assert asyncio.run(markets.find_cause(_m(), NOW)) is None
        (note,) = notices.report()
        assert note.startswith(f"market cause lookup for {BILL!r} failed (the reply was not JSON")
        assert note.endswith("left out of the briefing")

    def test_no_anthropic_key_is_a_failed_lookup_too(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert asyncio.run(markets.find_cause(_m(), NOW)) is None
        assert "(RuntimeError: ANTHROPIC_API_KEY not set)" in notices.report()[0]

    def test_a_search_that_finds_nothing_is_a_finding(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.setattr(llm, "native_anthropic",
                            lambda: FakeMessagesApi('{"found": false, "summary": ""}'))
        assert asyncio.run(markets.find_cause(_m(), NOW)) == {"found": False}
        assert notices.report() == []

    def test_scan_history_and_cause_failures_are_counted_and_the_move_left_out(
            self, monkeypatch, routes):
        def handler(request):
            if request.url.host == "gamma-api.polymarket.com":
                return httpx.Response(200, json=[BILL_EVENT])
            if request.url.host == "api.elections.kalshi.com":
                if request.url.params["series_ticker"] == "KXBAD":
                    return httpx.Response(503)
                return httpx.Response(200, json={"events": []})
            return httpx.Response(502)          # the CLOB's price history
        _market_api(monkeypatch, handler)
        routes["anthropic"] = FakeApi(["Sorry, I can only answer in prose."])   # the checker
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.setattr(llm, "native_anthropic", lambda: FakeMessagesApi(RuntimeError("down")))
        scout = MarketScout(rules=RULES, polymarket_tags=["ai"], kalshi_series=["KXBAD", "KXOK"])
        story = {"title": "Senate debates an AI bill", "url": "https://news/bill",
                 "summary": "The bill would require safety tests.", "published": NOW}

        ctx = asyncio.run(scout._build([story]))

        assert ctx.moves == [] and ctx.causes == {} and ctx.stories == {}
        kalshi, queries, history, long_history, cause = notices.report()
        assert kalshi.startswith("prediction markets: 1 of 2 Kalshi series scans failed "
                                 "(first: KXBAD: HTTPStatusError")
        assert queries.startswith("prediction markets: the market queries reply was not JSON")
        assert history.startswith("prediction markets: 1 of 1 30-day price histories failed")
        assert long_history.startswith("prediction markets: 1 of 1 long price histories failed")
        assert cause.startswith(f"market cause lookup for {BILL!r} failed (RuntimeError: down)")

    def test_every_market_handed_on_has_its_sentence_and_the_rest_are_left_out(
            self, monkeypatch, routes):
        close = int((datetime.now(timezone.utc) + timedelta(days=60)).timestamp() * 1000)
        descriptions = {"agi": MANIFOLD_RULES, "blank": "", "vague": "Background, and no rule."}
        asked_for = []

        def manifold(mid: str) -> dict:
            return {"id": mid, "question": f"Will the Senate pass an AI bill ({mid})?",
                    "probability": 0.4, "volume": 1000, "uniqueBettorCount": 120,
                    "closeTime": close, "url": f"https://manifold.markets/{mid}"}

        def handler(request):
            host, path = request.url.host, request.url.path
            if host == "gamma-api.polymarket.com":
                return httpx.Response(200, json=[BILL_EVENT] if path == "/events"
                                      else {"events": []})
            if host == "api.elections.kalshi.com":
                return httpx.Response(200, json={"events": []})
            if path == "/v0/search-markets":   # the listing: no description in it
                return httpx.Response(200, json=[manifold(m) for m in
                                                 ("agi", "blank", "vague", "down")])
            if path.startswith("/v0/market/"):
                mid = path.rsplit("/", 1)[1]
                asked_for.append(mid)
                if mid == "down":
                    return httpx.Response(503)
                return httpx.Response(200, json={**manifold(mid),
                                                 "textDescription": descriptions[mid]})
            return httpx.Response(200, json=[] if host == "api.manifold.markets"
                                  else {"history": []})
        _market_api(monkeypatch, handler)
        # The checker: one story's queries, then two markets for each story.
        routes["anthropic"] = FakeApi([
            '{"0": ["AI bill"], "1": ["AI bill"]}',
            '{"0": ["manifold:agi", "manifold:blank"], "1": ["manifold:vague", "manifold:down"]}'])
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        search = FakeMessagesApi('{"found": false}')
        monkeypatch.setattr(llm, "native_anthropic", lambda: search)
        stories = [{"title": f"Senate debates an AI bill, day {i}", "url": f"https://news/{i}",
                    "summary": "s", "published": NOW} for i in (1, 2)]

        ctx = asyncio.run(MarketScout(rules=RULES, polymarket_tags=["ai"])._build(stories))

        # Polymarket's rules came with the listing; Manifold's were read one by
        # one, for the four linked markets only.
        assert sorted(asked_for) == ["agi", "blank", "down", "vague"]
        assert [(m.key, m.resolves) for m in ctx.moves] == [("polymarket:1", BILL_RESOLVES)]
        # The second story's markets had no rules to give, so it carries none.
        assert {url: [(m.key, m.resolves) for m in ms] for url, ms in ctx.stories.items()} == {
            "https://news/1": [("manifold:agi", MANIFOLD_RESOLVES), ("manifold:blank", NO_RULES)]}
        assert list(ctx.story_times) == ["https://news/1"]
        lookups, left_out = notices.report()
        assert lookups.startswith("prediction markets: 1 of 4 market rules lookups failed "
                                  "(first: manifold:down: HTTPStatusError")
        assert left_out == (
            "prediction markets: 1 left out because their rules have no sentence of at most 60 "
            "words saying how they resolve (first: manifold:vague, "
            "'Will the Senate pass an AI bill (vague)?')")
        # The writer is given each sentence, and so is the search for a move's cause.
        assert f"Resolves: {MANIFOLD_RESOLVES}" in ctx.story_block("https://news/1")
        assert f"Resolves: {NO_RULES}" in ctx.story_block("https://news/1")
        assert f"Resolves: {BILL_RESOLVES}" in ctx.moves_section()
        (request,) = search.requests
        assert (f"How it resolves, from its rules: {BILL_RESOLVES}"
                in request["messages"][0]["content"])

    def test_failed_searches_and_an_unreadable_match_are_reported(self, routes):
        close = int((datetime.now(timezone.utc) + timedelta(days=60)).timestamp() * 1000)

        def handler(request):
            if request.url.host == "gamma-api.polymarket.com":
                return httpx.Response(500)
            return httpx.Response(200, json=[{
                "id": "m1", "question": "Will the Senate pass an AI bill in 2026?",
                "probability": 0.4, "volume": 1000, "uniqueBettorCount": 120,
                "closeTime": close, "url": "https://manifold.markets/m1"}])
        routes["anthropic"] = FakeApi(['{"0": ["AI bill"]}', "No good match, sorry."])

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await markets.link_stories(
                    client, [{"title": "Senate debates an AI bill", "summary": "s"}], RULES, [])

        assert asyncio.run(run()) == {}
        searched, matched = notices.report()
        assert searched.startswith("prediction markets: 1 of 2 market searches failed "
                                   "(first: Polymarket 'AI bill': HTTPStatusError")
        assert matched.startswith("prediction markets: the market matching reply was not JSON")


def _secs(when: datetime) -> int:
    return int(when.timestamp())


class TestPriceHistories:
    """Each platform's price history, as read from its own API's reply."""

    @pytest.fixture
    def api(self, monkeypatch):
        """Every history request answered from fixtures, and the requests made.

        The clock is fixed at NOW so the requests' time windows can be pinned.
        """
        monkeypatch.setattr(markets, "_utcnow", lambda: NOW)
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path.endswith("/prices-history"):
                return httpx.Response(200, json={"history": [
                    {"t": _secs(NOW - timedelta(days=400)), "p": 0.2},
                    {"t": _secs(NOW - timedelta(days=2)), "p": 0.4},
                    {"t": _secs(NOW - timedelta(hours=1)), "p": 0.45}]})
            if request.url.path.endswith("/candlesticks"):
                return httpx.Response(200, json={"candlesticks": [
                    {"end_period_ts": _secs(NOW - timedelta(days=2)),
                     "price": {"close_dollars": "0.30"}},
                    # No trade in the period: the previous price stands.
                    {"end_period_ts": _secs(NOW - timedelta(days=1)),
                     "price": {"close_dollars": None, "previous_dollars": "0.31"}},
                    {"end_period_ts": _secs(NOW - timedelta(hours=2)), "price": {}}]})
            # Manifold's bets, newest first; one without a price after it.
            return httpx.Response(200, json=[
                {"id": f"b{i}", "createdTime": _secs(NOW - back) * 1000, "probAfter": p}
                for i, (back, p) in enumerate([(timedelta(hours=1), 0.5),
                                               (timedelta(days=40), 0.35),
                                               (timedelta(days=50), 0.3),
                                               (timedelta(days=400), 0.1)])]
                + [{"id": "bx", "createdTime": _secs(NOW - timedelta(days=3)) * 1000}])

        async def fetch(fetcher, market_list, *args):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                for m in market_list:
                    await fetcher(client, m, *args)
        return SimpleNamespace(fetch=fetch, requests=requests)

    @staticmethod
    def _markets():
        pm, ks, mf = _m(), _m(platform="Kalshi"), _m(platform="Manifold")
        pm.history_ref, ks.history_ref, mf.history_ref = "tok", "KXAI|KXAI-1", "abc"
        return pm, ks, mf

    def test_thirty_day_history_hourly_from_each_platform(self, api):
        since = NOW - timedelta(days=30)
        pm, ks, mf = self._markets()
        asyncio.run(api.fetch(markets.fetch_history, [pm, ks, mf], since))

        assert pm.history == [(NOW - timedelta(days=400), 0.2), (NOW - timedelta(days=2), 0.4),
                              (NOW - timedelta(hours=1), 0.45)]
        assert ks.history == [(NOW - timedelta(days=2), 0.30), (NOW - timedelta(days=1), 0.31)]
        # Manifold keeps the last bet before the window as its starting price.
        assert mf.history == [(NOW - timedelta(days=40), 0.35), (NOW - timedelta(hours=1), 0.5)]
        assert [(r.url.path, dict(r.url.params)) for r in api.requests] == [
            ("/prices-history", {"market": "tok", "startTs": str(_secs(since)), "fidelity": "60"}),
            ("/trade-api/v2/series/KXAI/markets/KXAI-1/candlesticks",
             {"start_ts": str(_secs(since)), "end_ts": str(_secs(NOW)), "period_interval": "60"}),
            ("/v0/bets", {"contractId": "abc", "limit": "1000"})]

    def test_long_history_from_each_platform_reaches_back_a_year(self, api):
        pm, ks, mf = self._markets()
        asyncio.run(api.fetch(markets.fetch_long_history, [pm, ks, mf]))

        assert pm.long_history == [(NOW - timedelta(days=2), 0.4), (NOW - timedelta(hours=1), 0.45)]
        assert ks.long_history == [(NOW - timedelta(days=2), 0.30), (NOW - timedelta(days=1), 0.31)]
        assert mf.long_history == [(NOW - timedelta(days=50), 0.3), (NOW - timedelta(days=40), 0.35),
                                   (NOW - timedelta(hours=1), 0.5)]
        year_ago = NOW - timedelta(days=365)
        assert [(r.url.path, dict(r.url.params)) for r in api.requests] == [
            ("/prices-history", {"market": "tok", "interval": "max", "fidelity": "720"}),
            ("/trade-api/v2/series/KXAI/markets/KXAI-1/candlesticks",
             {"start_ts": str(_secs(year_ago)), "end_ts": str(_secs(NOW)),
              "period_interval": "1440"}),
            ("/v0/bets", {"contractId": "abc", "limit": "1000"})]

    def test_an_unknown_platform_raises_instead_of_passing_for_manifold(self, api):
        """Every platform branch used to end in an `else` that read any other
        platform as Manifold: play money, never liquid, priced from its bets."""
        odd = _m(platform="Metaculus")
        unknown = "unknown market platform 'Metaculus'"
        with pytest.raises(ValueError, match=unknown):
            odd.traded()
        with pytest.raises(ValueError, match=unknown):
            markets.is_liquid(odd, RULES, context=True)
        with pytest.raises(ValueError, match=unknown):
            asyncio.run(api.fetch(markets.fetch_history, [odd], NOW - timedelta(days=30)))
        with pytest.raises(ValueError, match=unknown):
            asyncio.run(api.fetch(markets.fetch_long_history, [odd]))
        assert api.requests == []


class TestModelRepliesAreRead:
    """The checker's and the web search's replies carry their JSON in a code
    fence, between sentences, or not at all."""

    @pytest.mark.parametrize("reply, found", [
        ('```json\n{"found": true, "summary": "The Journal reported a delay.", "source": "WSJ",'
         ' "url": "https://wsj/x"}\n```',
         {"found": True, "summary": "The Journal reported a delay.", "source": "WSJ",
          "url": "https://wsj/x"}),
        ('I searched. {"found": false, "summary": ""} Nothing explains it.', {"found": False}),
    ])
    def test_a_cause_is_read_from_a_fenced_or_wrapped_reply(self, monkeypatch, reply, found):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.setattr(llm, "native_anthropic", lambda: FakeMessagesApi(reply))
        assert asyncio.run(markets.find_cause(_m(), NOW)) == found
        assert notices.report() == []

    @pytest.mark.parametrize("reply", ["No JSON at all.", '{"found": true, "summary": "x",}'])
    def test_a_cause_reply_without_valid_json_is_a_failed_lookup(self, monkeypatch, reply):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.setattr(llm, "native_anthropic", lambda: FakeMessagesApi(reply))
        assert asyncio.run(markets.find_cause(_m(), NOW)) is None
        (note,) = notices.report()
        assert f"failed (the reply was not JSON: {reply!r})" in note

    def test_story_links_are_read_from_fenced_and_wrapped_replies(self, routes):
        close = int((datetime.now(timezone.utc) + timedelta(days=60)).timestamp() * 1000)

        def handler(request):
            if request.url.host == "gamma-api.polymarket.com":
                return httpx.Response(200, json={"events": []})
            return httpx.Response(200, json=[{
                "id": "m1", "question": "Will the Senate pass an AI bill in 2026?",
                "probability": 0.4, "volume": 1000, "uniqueBettorCount": 120,
                "closeTime": close, "url": "https://manifold.markets/m1"}])
        routes["anthropic"] = FakeApi(['```json\n{"0": ["AI bill"]}\n```',
                                       'My pick: {"0": ["manifold:m1"]} and no other.'])

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await markets.link_stories(
                    client, [{"title": "Senate debates an AI bill", "summary": "s"}], RULES, [])

        linked = asyncio.run(run())
        assert {i: [m.key for m in ms] for i, ms in linked.items()} == {0: ["manifold:m1"]}
        assert notices.report() == []


class TestReportedMoves:

    def test_recorded_moves_are_remembered_for_a_week(self, tmp_path):
        m = FeedMonitor(tmp_path / "posts.db")
        m.record_market_reports([{"key": "pm:ipo", "prob": 0.03}])
        assert m.recent_market_reports() == {"pm:ipo": 0.03}
        assert m.recent_market_reports(days=0) == {}


class TestMarketNotesInTheEmail:

    def _report(self):
        briefing = ReportEpisode(title="Daily News Briefing - 2026-09-19", author="", feed_name="",
                                 link="", audio_url="a.mp3", duration_seconds=300, is_briefing=True,
                                 bullets=[{"text": "Ohio race", "url": "https://news/ohio"},
                                          {"text": "No link"}])
        return RunReport(episodes=[briefing])

    def test_notes_sit_under_their_bullet_and_the_rest_get_a_section(self):
        report = self._report()
        report.market_notes = [
            MarketNote(cid="c0@f", title="Democrats win Ohio?", platform="Polymarket",
                       url="https://pm/ohio", caption="Now 62%", resolves=OHIO_RESOLVES,
                       anchor="https://news/ohio"),
            MarketNote(cid="c1@f", title="Anthropic IPO by Oct 31?", platform="Polymarket",
                       url="https://pm/ipo", caption="55% to 3%", resolves=POLYMARKET_RESOLVES,
                       anchor=""),
        ]
        html = build_html(report, datetime(2026, 9, 19))
        assert html.index("Ohio race") < html.index("cid:c0@f") < html.index("No link")
        assert html.count("cid:c0@f") == 1
        assert html.index("Prediction markets") < html.index("cid:c1@f")
        assert "cid:" not in build_html(self._report(), datetime(2026, 9, 19))

    def test_every_note_says_how_its_market_resolves_in_both_versions(self):
        report = self._report()
        report.market_notes = [
            MarketNote(cid="c0@f", title="Democrats win Ohio?", platform="Polymarket",
                       url="https://pm/ohio", caption="Now 62%", resolves=OHIO_RESOLVES,
                       anchor="https://news/ohio"),
            MarketNote(cid="c1@f", title="Anthropic IPO by Oct 31?", platform="Polymarket",
                       url="https://pm/ipo", caption="55% to 3%", resolves=POLYMARKET_RESOLVES,
                       anchor=""),
        ]
        html = build_html(report, datetime(2026, 9, 19))
        # Under its chart, escaped: the rules quote "Yes".
        assert html.index("cid:c0@f") < html.index(f"How it resolves: {OHIO_RESOLVES}")
        assert ("How it resolves: This market will resolve to &quot;Yes&quot; if Anthropic shares"
                in html)
        text = build_text(report, datetime(2026, 9, 19)).splitlines()
        # The plain-text email has no charts, and places the notes as the HTML does.
        ohio = text.index("      - Polymarket: Democrats win Ohio?")
        assert text.index("  - Ohio race (https://news/ohio)") < ohio < text.index("  - No link")
        assert text[ohio + 3] == f"        How it resolves: {OHIO_RESOLVES}"
        ipo = text.index("  - Polymarket: Anthropic IPO by Oct 31?")
        assert text.index("Prediction markets:") < ipo
        assert text[ipo + 3] == f"    How it resolves: {POLYMARKET_RESOLVES}"

    def test_a_market_with_no_chart_keeps_its_note(self):
        report = self._report()
        report.market_notes = [MarketNote(
            cid="", title="Democrats win Ohio?", platform="Polymarket", url="https://pm/ohio",
            caption="Now 62%", resolves=OHIO_RESOLVES, anchor="https://news/ohio")]
        html = build_html(report, datetime(2026, 9, 19))
        assert "<img" not in html and "cid:" not in html
        assert (html.index("Ohio race") < html.index("Polymarket: Democrats win Ohio?")
                < html.index(f"How it resolves: {OHIO_RESOLVES}") < html.index("No link"))

    def test_charts_go_in_the_daily_email_to_the_whole_list(self, monkeypatch):
        sent = []

        class SMTP:
            def __init__(self, *a, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def starttls(self, **kw): pass
            def login(self, *a): pass
            def send_message(self, msg): sent.append(msg)
        monkeypatch.setattr("smtplib.SMTP", SMTP)
        for k, v in {"FEEDCAST_EMAIL_TO": "titus@x", "FEEDCAST_EMAIL_BCC": "list@x",
                     "SMTP_USER": "bot@x", "SMTP_PASSWORD": "pw"}.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("FEEDCAST_TEST_RUN", raising=False)
        report = self._report()
        report.market_notes = [MarketNote(cid="c0@f", title="t", platform="Polymarket", url="u",
                                          caption="c", resolves=OHIO_RESOLVES,
                                          anchor="https://news/ohio")]
        assert send_report(report, images={"c0@f": b"\x89PNG"})
        (msg,) = sent
        # The one daily email: the operator plus the list.
        assert msg["To"] == "titus@x" and msg["Bcc"] == "list@x"
        assert msg["Subject"].startswith("Feedcast")
        raw = msg.as_string()
        assert "Content-ID: <c0@f>" in raw and "multipart/related" in raw

    def test_only_markets_the_digest_cites_are_noted(self):
        ctx = _ctx_with_story_and_move({"found": False})
        for m in ctx.moves:
            m.history = [(NOW - timedelta(days=2), 0.55), (NOW, 0.03)]
        (ohio,) = ctx.stories["https://news/ohio"]
        # The 14 Oct case: a second market on a story that has a bullet, in a
        # script that names Polymarket, but which the script never quoted.
        unused = _m("Will Republicans win the Ohio Senate race in 2026?", prob=0.38, before=None)
        unused.history = [(NOW - timedelta(days=2), 0.40), (NOW, 0.38)]
        ctx.stories["https://news/ohio"].append(unused)
        # And a market on a story with no bullet of its own, quoted in a
        # sub-bullet under a bullet that has no link: still charted.
        yemen = _m("Houthi military action against Saudi Arabia on October 15?", prob=0.65,
                   before=None)
        yemen.history = [(NOW - timedelta(days=2), 0.48), (NOW, 0.65)]
        ctx.stories["https://news/yemen-background"] = [yemen]
        ctx.stories["https://news/ohio-again"] = [ohio]   # linked twice, drawn once
        briefing = FeedEntry(id="news-briefing-2026-09-19", title="b", link="", published=NOW,
                             author="", feed_name="", content="On Polymarket, Democratic odds rose.",
                             bullets=[{"text": "Ohio", "url": "https://news/ohio", "sub": [
                                          {"text": "Polymarket odds rose", "url": ohio.url}]},
                                      {"text": "Saudi Arabia and the Houthis", "sub": [
                                          {"text": "Strikes", "url": "https://news/yemen"},
                                          {"text": "Polymarket: 65%", "url": yemen.url}]}],
                             markets=ctx.to_dict())
        found, images = market_notes_for_report(briefing)
        assert [n.title for n in found] == [
            "Anthropic IPO by October 31, 2026?", "Will Democrats win the Ohio Senate race in 2026?",
            "Houthi military action against Saudi Arabia on October 15?"]
        assert [n.anchor for n in found] == ["", ohio.url, yemen.url]
        assert [n.resolves for n in found] == [POLYMARKET_RESOLVES, OHIO_RESOLVES, BILL_RESOLVES]
        assert set(images) == {n.cid for n in found}
        assert all(png.startswith(b"\x89PNG") for png in images.values())
        # Only a chart with a story on it explains its dashed line.
        assert [n.caption for n in found] == [
            "55% to 3% in the last 24 hours · $500k traded",
            "Now 62% · $500k traded · dashed line: the story",
            "Now 65% · $500k traded"]

    def test_a_market_with_too_little_history_to_draw_is_noted_without_a_chart(self):
        ctx = _ctx_with_story_and_move({"found": False})   # the move has no price history
        briefing = FeedEntry(id="b", title="b", link="", published=NOW, author="", feed_name="",
                             content="On Polymarket, the IPO odds fell.", markets=ctx.to_dict())
        (note,), images = market_notes_for_report(briefing)
        assert (note.cid, images) == ("", {})
        assert note.title == IPO and note.resolves == POLYMARKET_RESOLVES
        assert note.caption == "55% to 3% in the last 24 hours · $500k traded"

    def test_a_chart_cited_from_a_sub_bullet_sits_under_its_parent(self):
        report = self._report()
        report.episodes[0].bullets = [
            {"text": "Houthi escalation", "sub": [{"text": "Odds 65%", "url": "https://pm/houthi"}]},
            {"text": "Ohio race", "url": "https://news/ohio"}]
        report.market_notes = [MarketNote(
            cid="c0@f", title="Houthi action Oct 15?", platform="Polymarket",
            url="https://pm/houthi", caption="Now 65%", resolves=BILL_RESOLVES,
            anchor="https://pm/houthi")]
        html = build_html(report, datetime(2026, 9, 19))
        assert html.index("Odds 65%") < html.index("cid:c0@f") < html.index("Ohio race")
        assert html.count("cid:c0@f") == 1 and "Prediction markets" not in html

    def test_no_market_data_no_notes(self):
        briefing = FeedEntry(id="b", title="b", link="", published=NOW, author="", feed_name="",
                             content="Polymarket")
        assert market_notes_for_report(briefing) == ([], {})

    def test_a_chart_that_fails_costs_the_market_notes_not_the_email(self, monkeypatch):
        import src.market_charts as market_charts

        def broken(*a, **kw):
            raise ValueError("bad history")
        monkeypatch.setattr(market_charts, "render_chart", broken)
        briefing = FeedEntry(id="b", title="b", link="", published=NOW, author="", feed_name="",
                             content="Polymarket", markets=_ctx_with_story_and_move(None).to_dict())
        assert market_notes_for_report(briefing) == ([], {})
        assert notices.report() == [
            "prediction-market notes left out of this email: ValueError: bad history"]


def test_market_record_round_trips_through_json():
    ctx = _ctx_with_story_and_move({"found": False})
    data = json.loads(json.dumps(ctx.to_dict()))
    assert data["moves"][0]["prob_24h"] == pytest.approx(0.55)
    assert data["stories"]["https://news/ohio"][0]["history"][0][1] == 0.58
    assert data["moves"][0]["resolves"] == POLYMARKET_RESOLVES
    assert data["stories"]["https://news/ohio"][0]["resolves"] == OHIO_RESOLVES
    assert [s["url"] for s in ctx.sources()] == [ctx.moves[0].url, ctx.stories["https://news/ohio"][0].url]


def test_preview_writes_a_briefing_and_emails_it_without_publishing(tmp_path, monkeypatch,
                                                                   routes, smtp):
    ctx = _ctx_with_story_and_move({"found": False})
    (ohio,) = ctx.stories["https://news/ohio"]
    # The digest's model (a paid API) cites the Ohio market, so its chart is drawn.
    routes["openai"] = FakeApi([f"- Democratic odds in Ohio rose to 62% on Polymarket. || {ohio.url}"])

    class Aggregator:
        """Stands in for NewsAggregator, whose briefing takes live RSS fetches and the
        paid writer model. Its briefing carries a real markets record."""
        async def generate_briefing(self):
            return FeedEntry(id="news-briefing-2026-10-08", title="Daily News Briefing - 2026-10-08",
                             link="", published=NOW, author="Feedcast Bot",
                             feed_name="Daily News Briefing", content="On Polymarket, odds rose.",
                             sources=ctx.sources(), markets=ctx.to_dict())
    monkeypatch.setattr(main, "_make_aggregator", lambda *a: Aggregator())
    config = load_config()
    monitor = FeedMonitor(tmp_path / "posts.db")
    asyncio.run(main._preview_briefing(monitor, config))
    (msg,) = smtp   # one email, charts in it
    assert msg["Subject"].startswith("[Preview] Feedcast")
    # The cited market's chart, inline; the uncited move has no history to draw.
    (png,) = [part for part in msg.walk() if part.get_content_type() == "image/png"]
    assert png["Content-ID"] == "<market-0@feedcast>"
    assert png.get_payload(decode=True).startswith(b"\x89PNG")
    html = msg.get_body(("html",)).get_content()
    assert html.index("Democratic odds in Ohio rose") < html.index("cid:market-0@feedcast")
    assert html.index("cid:market-0@feedcast") < html.index(f"How it resolves: {OHIO_RESOLVES}")
    text = msg.get_body(("plain",)).get_content()
    assert "Democratic odds in Ohio rose to 62% on Polymarket." in text   # the digest
    assert "On Polymarket, odds rose." in text                            # the full script
    # Both markets say how they resolve, the uncited move in a section of its own.
    assert f"How it resolves: {OHIO_RESOLVES}" in text
    assert f"How it resolves: {POLYMARKET_RESOLVES}" in text
    assert monitor.get_processed_entries() == [] and monitor.get_recent_briefings() == []


def _png_height(png: bytes) -> int:
    return int.from_bytes(png[20:24], "big")   # IHDR height


class TestLongHistoryCharts:

    def test_zoom_panel_only_when_asked_and_short_history_draws_nothing(self):
        from src.market_charts import render_chart
        line = [(NOW - timedelta(days=d), 0.4) for d in range(90, -1, -1)]
        assert _png_height(render_chart(line, NOW)) == 190
        assert _png_height(render_chart(line, NOW, zoom=line[-8:])) == 300
        assert render_chart(line[:1]) is None

    def test_thin_keeps_the_latest_point(self):
        pts = list(range(1000))
        thin = markets._thin(pts, 100)
        assert len(thin) == 100 and thin[-1] == 999 and thin[0] == 0

    def test_long_history_reads_a_markets_whole_life_and_pages_manifold(self):
        import httpx
        seen = []

        def handler(request):
            seen.append(request.url)
            if "prices-history" in str(request.url):
                start = int((NOW - timedelta(days=200)).timestamp())
                return httpx.Response(200, json={"history": [
                    {"t": start + i * 43200, "p": 0.5} for i in range(400)]})
            # Manifold: a full page, then a short one.
            page = 1000 if "before" not in str(request.url) else 3
            return httpx.Response(200, json=[
                {"id": f"b{i}", "createdTime": int((NOW - timedelta(hours=i)).timestamp() * 1000),
                 "probAfter": 0.3} for i in range(page)])

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                pm, mf = _m(), _m(platform="Manifold")
                pm.history_ref, mf.history_ref = "tok", "abc"
                await markets.fetch_long_history(client, pm)
                await markets.fetch_long_history(client, mf)
                return pm, mf

        pm, mf = asyncio.run(run())
        assert "interval=max" in str(seen[0]) and len(pm.long_history) == 400
        assert len(mf.long_history) == 800 and any("before=b999" in str(u) for u in seen)

    # Exactly three months is not more than three months: one panel.
    @pytest.mark.parametrize("back, zoomed", [
        (timedelta(days=90) - timedelta(hours=1), False),
        (timedelta(days=90), False),
        (timedelta(days=90) + timedelta(hours=1), True),
    ])
    def test_zoom_only_past_three_months_of_history(self, back, zoomed):
        from src.market_charts import ZOOM_MIN_HISTORY_DAYS, wants_zoom
        assert ZOOM_MIN_HISTORY_DAYS == 90
        line = [(NOW - back, 0.5), (NOW - timedelta(days=3), 0.5), (NOW, 0.6)]
        assert wants_zoom(line) is zoomed
        assert wants_zoom(list(reversed(line))) is zoomed   # order does not matter
        assert not wants_zoom(line[:1]) and not wants_zoom([])

    def _chart_heights(self, story_days_back: dict, move_days_back: dict | None = None,
                       jump: float = 0.10) -> dict[str, int]:
        """Each market's chart height in the email: 300 with the zoom, 190 without."""

        def market(name: str, back: timedelta) -> Market:
            m = _m(f"Will Democrats win the Ohio Senate race ({name})?", prob=0.6 + jump, before=0.6,
                   key=f"pm:{name}")
            # The market moves in the last ten hours, so the old rule (zoom on a
            # move around the story) would have zoomed on every one of these.
            hourly = min(back, timedelta(days=30))
            m.history = [(NOW - timedelta(hours=h), 0.6 + (jump if h < 10 else 0))
                         for h in range(int(hourly.total_seconds() // 3600), -1, -1)]
            m.long_history = [(NOW - back + timedelta(hours=12 * i), 0.5)
                              for i in range(int(back.total_seconds() // 43200))]
            return m

        ctx = MarketContext()
        ctx.stories["https://news/ohio"] = [market(n, b) for n, b in story_days_back.items()]
        ctx.story_times["https://news/ohio"] = NOW - timedelta(hours=12)
        ctx.moves = [market(n, b) for n, b in (move_days_back or {}).items()]
        cites = [{"text": m.title, "url": m.url}
                 for m in [*ctx.stories["https://news/ohio"], *ctx.moves]]
        briefing = FeedEntry(id="b", title="b", link="", published=NOW, author="", feed_name="",
                             content="Polymarket",
                             bullets=[{"text": "Ohio", "url": "https://news/ohio", "sub": cites}],
                             markets=ctx.to_dict())
        found, images = market_notes_for_report(briefing)
        return {c.title.split("(")[1].rstrip(")?"): _png_height(images[c.cid]) for c in found}

    def test_zoom_only_on_markets_older_than_three_months(self, capsys):
        heights = self._chart_heights({
            "twelve days": timedelta(days=12),
            "just under": timedelta(days=90) - timedelta(hours=1),
            "just over": timedelta(days=90) + timedelta(hours=1),
            "a year": timedelta(days=365),
        })
        assert heights == {"twelve days": 190, "just under": 190, "just over": 300, "a year": 300}
        log = capsys.readouterr().out
        assert "(twelve days)?: 12 days of history, whole life only" in log
        assert "(a year)?: 365 days of history, whole life plus a 7-day zoom" in log

    def test_an_unexplained_move_follows_the_same_rule(self):
        # Moves used to zoom always; now only an old market's does.
        heights = self._chart_heights({}, {"young move": timedelta(days=20),
                                                        "old move": timedelta(days=200)},
                                      jump=-0.30)
        assert heights == {"young move": 190, "old move": 300}

    def test_a_flat_old_market_still_gets_the_zoom(self):
        heights = self._chart_heights({"flat": timedelta(days=150)}, jump=0.0)
        assert heights == {"flat": 300}

    def test_no_long_history_falls_back_to_thirty_days_and_one_panel(self):
        m = _m("Will Democrats win the Ohio Senate race?", prob=0.6, before=None)
        m.history = [(NOW - timedelta(hours=h), 0.6) for h in range(720, -1, -1)]
        ctx = MarketContext(stories={"https://news/ohio": [m]})
        briefing = FeedEntry(id="b", title="b", link="", published=NOW, author="", feed_name="",
                             content="Polymarket", bullets=[{"text": "Ohio", "url": m.url}],
                             markets=ctx.to_dict())
        _, images = market_notes_for_report(briefing)
        (png,) = images.values()
        assert _png_height(png) == 190
