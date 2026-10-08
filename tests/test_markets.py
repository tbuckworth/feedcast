"""Prediction markets in the briefing: parsing, the move rules, the writer's input,
and the trial email's charts. No network: every API reply here is a fixture."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from email import message_from_string
from types import SimpleNamespace

import pytest

import src.main as main
import src.markets as markets
from src.email_report import (ChartNote, ReportEpisode, RunReport, build_html, send_report)
from src.markets import (Market, MarketContext, MarketRules, MarketScout, is_move,
                         kalshi_markets, pick_moves, polymarket_markets)
from src.monitor import FeedEntry, FeedMonitor
from src.news import NewsAggregator

NOW = datetime(2026, 9, 19, 4, 0, tzinfo=timezone.utc)


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
        assert is_move(_m(), MarketRules(), NOW)

    @pytest.mark.parametrize("change", [
        dict(before=0.40),                               # 10 points: too small
        dict(volume=10_000, volume_30d=5_000),           # thin
        dict(closes=NOW + timedelta(days=3)),            # expiring
        dict(prob=0.01, before=0.40),                    # resolving
        dict(title="Best AI model end of October: Google"),   # leaderboard
        dict(title="Will SpaceXAI rename itself by October 31?"),  # off topic
    ])
    def test_what_does_not_count(self, change):
        assert not is_move(_m(**change), MarketRules(), NOW)

    def test_corporate_markets_need_the_major_threshold(self):
        ipo = dict(title="Anthropic IPO by October 31, 2026?")
        assert not is_move(_m(prob=0.40, before=0.57, **ipo), MarketRules(), NOW)   # 17 points
        assert is_move(_m(prob=0.03, before=0.55, **ipo), MarketRules(), NOW)

    def test_manifold_is_context_never_a_move(self):
        assert not is_move(_m(platform="Manifold", traders=900), MarketRules(), NOW)

    def test_one_line_per_story_most_liquid_first_and_no_repeats(self):
        a = _m("Anthropic IPO by October 31, 2026?", prob=0.03, before=0.55, event="pm:ipo",
               key="pm:1", volume_24h=50_000)
        a2 = _m("Anthropic IPO by November 15, 2026?", prob=0.51, before=0.71, event="pm:ipo",
                key="pm:2", volume_24h=60_000)
        k = _m("When will Anthropic officially announce an IPO? Before Nov 1, 2026",
               platform="Kalshi", prob=0.06, before=0.53, volume=478_276, volume_24h=40_565,
               key="ks:1", event="ks:ipo")
        bill = _m(key="pm:bill", event="pm:bill", volume_24h=10_000)
        moves = pick_moves([a, a2, k, bill], MarketRules(), NOW)
        assert [m.key for m in moves] == ["pm:1", "pm:bill"]   # biggest move per event; Kalshi dupe dropped
        assert pick_moves([a, bill], MarketRules(), NOW, skip_events={"pm:ipo"}) == [bill]
        # Reported yesterday at 3%: not again until it moves another 15 points.
        assert pick_moves([a], MarketRules(), NOW, recently_reported={"pm:1": 0.04}) == []
        assert pick_moves([a], MarketRules(), NOW, recently_reported={"pm:1": 0.30}) == [a]


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
        assert "not looked up" in _ctx_with_story_and_move(None).moves_section()
        assert "55% to 3%" in _ctx_with_story_and_move(None).moves_section()

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

        agg = NewsAggregator(sources=[], prompt="Write.", verify=False)
        agg.client = Client()
        asyncio.run(agg.synthesize_briefing("ARTICLES"))
        asyncio.run(agg.synthesize_briefing("ARTICLES", MarketContext().instructions()))
        assert sent[0] == sent[1]
        asyncio.run(agg.synthesize_briefing("ARTICLES", _ctx_with_story_and_move(None).instructions()))
        assert '"On the prediction markets,"' in sent[2] and "Leave them out" in sent[2]
        assert sent[2].index("prediction markets") < sent[2].index("## Today's articles:")

    def test_briefing_input_carries_the_odds_and_the_moves(self):
        agg = NewsAggregator(sources=[], prompt="Write.", verify=False)
        story = {"title": "Brown runs on datacenters", "source": "Guardian", "category": "politics",
                 "summary": "b", "url": "https://news/ohio", "published": NOW}
        text = agg._format_briefing_input([story], [story], _ctx_with_story_and_move(None))
        assert "Prediction markets on this story" in text and text.rstrip().endswith("not looked up.")
        assert agg._format_briefing_input([story], [story]) == \
               agg._format_briefing_input([story], [story], MarketContext())

    def test_a_failing_scout_leaves_the_briefing_without_markets(self, monkeypatch):
        async def boom(self, selected):
            raise RuntimeError("Polymarket is down")
        monkeypatch.setattr(MarketScout, "_build", boom)
        log = []
        monkeypatch.setattr(markets, "fallback_log", log)
        ctx = asyncio.run(MarketScout().build([]))
        assert not ctx and "prediction markets skipped" in log[0]


class TestReportedMoves:

    def test_recorded_moves_are_remembered_for_a_week(self, tmp_path):
        m = FeedMonitor(tmp_path / "posts.db")
        m.record_market_reports([{"key": "pm:ipo", "prob": 0.03}])
        assert m.recent_market_reports() == {"pm:ipo": 0.03}
        assert m.recent_market_reports(days=0) == {}


class TestTrialEmail:

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

    def test_trial_goes_to_its_own_list_with_inline_images(self, monkeypatch):
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
        assert send_report(report, recipients=["titus@x", "jason@x"],
                           subject_tag="[DEV - Prediction Markets]", images={"c0@f": b"\x89PNG"})
        (msg,) = sent
        assert msg["To"] == "titus@x, jason@x" and msg["Bcc"] is None
        assert msg["Subject"].startswith("[DEV - Prediction Markets] Feedcast")
        raw = msg.as_string()
        assert "Content-ID: <c0@f>" in raw and "multipart/related" in raw

    def test_only_markets_the_script_used_are_charted(self, monkeypatch):
        calls = []
        monkeypatch.setattr(main, "send_report", lambda report, **kw: calls.append((report, kw)))
        monkeypatch.setenv("FEEDCAST_MARKETS_TRIAL_TO", "titus@x,jason@x")
        monkeypatch.delenv("FEEDCAST_TEST_RUN", raising=False)
        ctx = _ctx_with_story_and_move({"found": False})
        for m in ctx.moves:
            m.history = [(NOW - timedelta(days=2), 0.55), (NOW, 0.03)]
        unused = _m("Will Republicans win the Ohio Senate race in 2026?", prob=0.38, before=None)
        unused.history = [(NOW - timedelta(days=2), 0.40), (NOW, 0.38)]
        ctx.stories["https://news/other"] = [unused]
        briefing = FeedEntry(id="news-briefing-2026-09-19", title="b", link="", published=NOW,
                             author="", feed_name="", content="On Polymarket, Democratic odds rose.",
                             bullets=[{"text": "Ohio", "url": "https://news/ohio"}],
                             markets=ctx.to_dict())
        main._send_markets_trial(self._report(), briefing)
        ((report, kw),) = calls
        assert kw["recipients"] == ["titus@x", "jason@x"]
        assert [c.title for c in report.charts] == [
            "Anthropic IPO by October 31, 2026?", "Will Democrats win the Ohio Senate race in 2026?"]
        assert report.charts[1].anchor == "https://news/ohio"
        assert set(kw["images"]) == {c.cid for c in report.charts}
        assert all(png.startswith(b"\x89PNG") for png in kw["images"].values())

    def test_no_trial_list_no_trial_email(self, monkeypatch):
        calls = []
        monkeypatch.setattr(main, "send_report", lambda report, **kw: calls.append(kw))
        monkeypatch.delenv("FEEDCAST_MARKETS_TRIAL_TO", raising=False)
        briefing = FeedEntry(id="b", title="b", link="", published=NOW, author="", feed_name="",
                             content="Polymarket", markets=_ctx_with_story_and_move(None).to_dict())
        main._send_markets_trial(self._report(), briefing)
        assert calls == []


def test_market_record_round_trips_through_json():
    ctx = _ctx_with_story_and_move({"found": False})
    data = json.loads(json.dumps(ctx.to_dict()))
    assert data["moves"][0]["prob_24h"] == pytest.approx(0.55)
    assert data["stories"]["https://news/ohio"][0]["history"][0][1] == 0.58
    assert [s["url"] for s in ctx.sources()] == [ctx.moves[0].url, ctx.stories["https://news/ohio"][0].url]


def test_preview_writes_a_briefing_and_emails_it_without_publishing(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_report", lambda report, **kw: sent.append((report, kw)))
    monkeypatch.setattr(main, "_send_markets_trial",
                        lambda report, entry: sent.append(("trial", entry.markets)))

    async def fake_bullets(text, **kw):
        return [{"text": "Ohio odds rose", "url": "https://news/ohio"}]
    monkeypatch.setattr(main, "safe_bullets", fake_bullets)

    class Aggregator:
        async def generate_briefing(self):
            return FeedEntry(id="news-briefing-2026-10-08", title="Daily News Briefing - 2026-10-08",
                             link="", published=NOW, author="Feedcast Bot",
                             feed_name="Daily News Briefing", content="On Polymarket, odds rose.",
                             markets={"moves": [], "stories": {}})
    monkeypatch.setattr(main, "_make_aggregator", lambda *a: Aggregator())
    config = main.load_config(main.Path(__file__).resolve().parent.parent / "config.yaml")
    monitor = FeedMonitor(tmp_path / "posts.db")
    asyncio.run(main._preview_briefing(monitor, config))
    (report, kw), trial = sent
    assert kw == {"subject_tag": "[Preview]"} and trial[0] == "trial"
    digest, script = report.episodes
    assert digest.bullets and script.briefing_text == "On Polymarket, odds rose."
    assert monitor.get_processed_entries() == [] and monitor.get_recent_briefings() == []
