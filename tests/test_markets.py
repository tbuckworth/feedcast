"""Prediction markets in the briefing: parsing, the move rules, the writer's input,
and the daily email's charts. No network: every API reply here is a fixture."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

import src.main as main
import src.markets as markets
from src import notices
from src.config import load_config
from src.email_report import (ChartNote, ReportEpisode, RunReport, build_html, send_report)
from src.market_charts import charts_for_report
from src.markets import (Market, MarketContext, MarketRules, MarketScout, is_move,
                         kalshi_markets, pick_moves, polymarket_markets)
from src.monitor import FeedEntry, FeedMonitor
from src.news import NewsAggregator
from tests.conftest import FakeApi

NOW = datetime(2026, 9, 19, 4, 0, tzinfo=timezone.utc)
# The backtest's move sizes, which config.yaml `prediction_markets` sets.
RULES = MarketRules(move=0.15, major_move=0.20, max_moves=3)


def _m(title="Will Congress pass an AI safety bill in 2026?", platform="Polymarket", prob=0.30,
       before=0.55, volume=500_000.0, volume_30d=100_000.0, volume_24h=40_000.0,
       closes=NOW + timedelta(days=90), event=None, key=None, traders=None):
    key = key or f"{platform.lower()}:{title}"
    return Market(platform=platform, key=key, title=title, url=f"https://pm/{abs(hash(title))}",
                  prob=prob, prob_24h=before, volume=volume, volume_30d=volume_30d,
                  volume_24h=volume_24h, closes=closes, event=event or key, traders=traders)


class TestParsing:

    def test_polymarket_reads_yes_price_and_derives_yesterday(self):
        event = {"id": 7, "slug": "anthropic-ipo-by", "title": "Anthropic IPO by ___?", "markets": [
            {"id": "1", "question": "Anthropic IPO by October 31, 2026?", "outcomes": '["Yes", "No"]',
             "outcomePrices": '["0.03", "0.97"]', "oneDayPriceChange": -0.52, "volumeNum": 1160616,
             "volume1mo": 432462, "volume24hr": 50000, "endDate": "2026-10-31T12:00:00Z",
             "clobTokenIds": '["tok1", "tok2"]'},
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

    def test_kalshi_titles_carry_the_outcome_and_skip_untraded_markets(self):
        event = {"event_ticker": "KXIPOANTHROPIC-DATE", "series_ticker": "KXIPOANTHROPIC",
                 "title": "When will Anthropic officially announce an IPO?", "markets": [
                     {"ticker": "A", "yes_sub_title": "Before Nov 1, 2026", "last_price_dollars": "0.06",
                      "previous_price_dollars": "0.53", "volume_fp": "478276", "volume_24h_fp": "40565",
                      "close_time": "2026-11-01T03:59:00Z"},
                     {"ticker": "B", "yes_sub_title": "Before Dec 1", "last_price_dollars": "0.5",
                      "previous_price_dollars": "0.5", "volume_fp": "0"}]}
        (m,) = kalshi_markets(event)
        assert m.title == "When will Anthropic officially announce an IPO? Before Nov 1, 2026"
        assert m.move == pytest.approx(-0.47) and m.history_ref == "KXIPOANTHROPIC|A"
        assert m.url == "https://kalshi.com/markets/kxipoanthropic"


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


def _ctx_with_story_and_move(cause):
    story = _m("Will Democrats win the Ohio Senate race in 2026?", prob=0.62, before=None)
    story.history = [(NOW - timedelta(days=8), 0.58), (NOW - timedelta(days=2), 0.60),
                     (NOW - timedelta(hours=1), 0.62)]
    move = _m("Anthropic IPO by October 31, 2026?", prob=0.03, before=0.55, key="pm:ipo")
    return MarketContext(stories={"https://news/ohio": [story]},
                         story_times={"https://news/ohio": NOW}, moves=[move],
                         causes={"pm:ipo": cause})


class TestWriterInput:

    def test_story_block_gives_odds_before_the_story_and_now(self):
        block = _ctx_with_story_and_move(None).story_block("https://news/ohio")
        assert "58% a week before this story, 60% the day before it, 62% now" in block
        assert "$500k traded" in block and _ctx_with_story_and_move(None).story_block("x") == ""

    def test_moves_section_says_what_the_search_found_or_did_not(self):
        found = {"found": True, "summary": "The Journal reported a November target.",
                 "source": "WSJ", "url": "https://wsj/x"}
        assert "Cause found by a news search: The Journal reported" in \
               _ctx_with_story_and_move(found).moves_section()
        assert "no clear cause" in _ctx_with_story_and_move({"found": False}).moves_section()
        assert "55% to 3%" in _ctx_with_story_and_move({"found": False}).moves_section()

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


class _Anthropic:
    """Anthropic's Messages API with web search, for find_cause: a paid API, so
    each call returns the next of `replies` (a text block's text) or raises it."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kw):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=reply)])


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
    "clobTokenIds": '["tok1", "tok2"]'}]}
BILL = "Will Congress pass an AI safety bill in 2026?"


class TestFailuresReachTheEmail:
    """A market call that fails, or a model reply that cannot be read, costs the
    briefing a market, some odds or a chart. Each used to cost it in silence."""

    def test_a_failed_cause_lookup_drops_the_move_instead_of_reading_as_no_cause(
            self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.setattr(markets, "native_anthropic",
                            lambda: _Anthropic("I looked, but here is prose, not JSON."))
        assert asyncio.run(markets.find_cause(_m(), NOW)) is None
        (note,) = notices.report()
        assert note.startswith(f"market cause lookup for {BILL!r} failed (the reply was not JSON")
        assert note.endswith("left out of the briefing")

    def test_no_anthropic_key_is_a_failed_lookup_too(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert asyncio.run(markets.find_cause(_m(), NOW)) is None
        assert "(ANTHROPIC_API_KEY not set)" in notices.report()[0]

    def test_a_search_that_finds_nothing_is_a_finding(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.setattr(markets, "native_anthropic",
                            lambda: _Anthropic('{"found": false, "summary": ""}'))
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
        monkeypatch.setattr(markets, "native_anthropic", lambda: _Anthropic(RuntimeError("down")))
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


class TestReportedMoves:

    def test_recorded_moves_are_remembered_for_a_week(self, tmp_path):
        m = FeedMonitor(tmp_path / "posts.db")
        m.record_market_reports([{"key": "pm:ipo", "prob": 0.03}])
        assert m.recent_market_reports() == {"pm:ipo": 0.03}
        assert m.recent_market_reports(days=0) == {}


class TestChartsInTheEmail:

    def _report(self):
        briefing = ReportEpisode(title="Daily News Briefing - 2026-09-19", author="", feed_name="",
                                 link="", audio_url="a.mp3", duration_seconds=300, is_briefing=True,
                                 bullets=[{"text": "Ohio race", "url": "https://news/ohio"},
                                          {"text": "No link"}])
        return RunReport(episodes=[briefing])

    def test_charts_sit_under_their_bullet_and_the_rest_get_a_section(self):
        report = self._report()
        report.charts = [
            ChartNote(cid="c0@f", title="Democrats win Ohio?", platform="Polymarket",
                      url="https://pm/ohio", caption="Now 62%", anchor="https://news/ohio"),
            ChartNote(cid="c1@f", title="Anthropic IPO by Oct 31?", platform="Polymarket",
                      url="https://pm/ipo", caption="55% to 3%", anchor=""),
        ]
        html = build_html(report, datetime(2026, 9, 19))
        assert html.index("Ohio race") < html.index("cid:c0@f") < html.index("No link")
        assert html.count("cid:c0@f") == 1
        assert html.index("Prediction markets") < html.index("cid:c1@f")
        assert "cid:" not in build_html(self._report(), datetime(2026, 9, 19))

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
        report.charts = [ChartNote(cid="c0@f", title="t", platform="Polymarket", url="u",
                                   caption="c", anchor="https://news/ohio")]
        assert send_report(report, images={"c0@f": b"\x89PNG"})
        (msg,) = sent
        # The one daily email: the operator plus the list.
        assert msg["To"] == "titus@x" and msg["Bcc"] == "list@x"
        assert msg["Subject"].startswith("Feedcast")
        raw = msg.as_string()
        assert "Content-ID: <c0@f>" in raw and "multipart/related" in raw

    def test_only_markets_the_digest_cites_are_charted(self):
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
        charts, images = charts_for_report(briefing)
        assert [c.title for c in charts] == [
            "Anthropic IPO by October 31, 2026?", "Will Democrats win the Ohio Senate race in 2026?",
            "Houthi military action against Saudi Arabia on October 15?"]
        assert [c.anchor for c in charts] == ["", ohio.url, yemen.url]
        assert set(images) == {c.cid for c in charts}
        assert all(png.startswith(b"\x89PNG") for png in images.values())

    def test_a_chart_cited_from_a_sub_bullet_sits_under_its_parent(self):
        report = self._report()
        report.episodes[0].bullets = [
            {"text": "Houthi escalation", "sub": [{"text": "Odds 65%", "url": "https://pm/houthi"}]},
            {"text": "Ohio race", "url": "https://news/ohio"}]
        report.charts = [ChartNote(cid="c0@f", title="Houthi action Oct 15?", platform="Polymarket",
                                   url="https://pm/houthi", caption="Now 65%",
                                   anchor="https://pm/houthi")]
        html = build_html(report, datetime(2026, 9, 19))
        assert html.index("Odds 65%") < html.index("cid:c0@f") < html.index("Ohio race")
        assert html.count("cid:c0@f") == 1 and "Prediction markets" not in html

    def test_no_market_data_no_charts(self):
        briefing = FeedEntry(id="b", title="b", link="", published=NOW, author="", feed_name="",
                             content="Polymarket")
        assert charts_for_report(briefing) == ([], {})

    def test_a_chart_that_fails_costs_the_charts_not_the_email(self, monkeypatch):
        import src.market_charts as market_charts

        def broken(*a, **kw):
            raise ValueError("bad history")
        monkeypatch.setattr(market_charts, "render_chart", broken)
        briefing = FeedEntry(id="b", title="b", link="", published=NOW, author="", feed_name="",
                             content="Polymarket", markets=_ctx_with_story_and_move(None).to_dict())
        assert charts_for_report(briefing) == ([], {})
        assert notices.report() == [
            "prediction-market charts left out of this email: ValueError: bad history"]


def test_market_record_round_trips_through_json():
    ctx = _ctx_with_story_and_move({"found": False})
    data = json.loads(json.dumps(ctx.to_dict()))
    assert data["moves"][0]["prob_24h"] == pytest.approx(0.55)
    assert data["stories"]["https://news/ohio"][0]["history"][0][1] == 0.58
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
    text = msg.get_body(("plain",)).get_content()
    assert "Democratic odds in Ohio rose to 62% on Polymarket." in text   # the digest
    assert "On Polymarket, odds rose." in text                            # the full script
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
        charts, images = charts_for_report(briefing)
        return {c.title.split("(")[1].rstrip(")?"): _png_height(images[c.cid]) for c in charts}

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
        _, images = charts_for_report(briefing)
        (png,) = images.values()
        assert _png_height(png) == 190
