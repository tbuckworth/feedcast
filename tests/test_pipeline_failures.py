"""Failures in the pipeline's own steps: in the log, in the email, and in the retry queue.

These run async_main end to end on a scratch repository: the real config.yaml
with local feed files, a real database, and the real cleaning, normaliser,
digest, retry queue and feed generation. Stood in for, at the edges only:
DeepInfra's TTS (`Narrator`, a paid API), the LLM accounts (the `routes`
fixture), every HTTP request (`Pipeline.answer`), the article download for an
injected URL, and SMTP (the report is captured where main hands it over).
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx
import pytest
import yaml

import src.main as main
from src import lesswrong, market_charts, notices
from src.config import CONFIG_PATH
from src.markets import Market, MarketContext, MarketScout
from src.monitor import FeedEntry, FeedMonitor
from tests.conftest import FakeApi, silent_mp3

LW = "https://www.lesswrong.com/posts/AAAAAAAAAAAAAAAAA/on-land"
BROKEN = "https://feeds.example/broken.xml"
INJECTED = "https://blog.example/land"
ARTICLE = ("<html><head><title>Land</title></head><body><article><p>"
           + "Land value taxes work, and here is why. " * 20 + "</p></article></body></html>")


class Model(FakeApi):
    """An LLM account, a paid API, answering every call with `answer(messages)`."""

    def __init__(self, answer):
        super().__init__([])
        self.answer = answer

    async def _create(self, **kw):
        self.replies = [self.answer(kw["messages"])]
        return await super()._create(**kw)


class Narrator:
    """DeepInfra's TTS, a paid API: writes a real, silent MP3, or raises `fail`."""

    fail: Exception | None = None

    def __init__(self, *a, **kw):
        pass

    async def generate_episode(self, text, audio_dir, ep_id, title, http_client):
        if Narrator.fail:
            raise Narrator.fail
        path = Path(audio_dir) / f"{ep_id}.mp3"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(silent_mp3())
        return path


def item(title: str, link: str, hours_ago: float = 1.0) -> str:
    when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return (f"<item><title>{title}</title><link>{link}</link><guid>{link}</guid>"
            f"<description>&lt;p&gt;{title}: land value taxes work, and here is why.&lt;/p&gt;"
            f"</description><pubDate>{when:%a, %d %b %Y %H:%M:%S} GMT</pubDate></item>")


def lesswrong_down(request: httpx.Request) -> httpx.Response:
    """LessWrong's GraphQL dates posts but fails every markdown fetch."""
    if "postedAt" in json.loads(request.content)["query"]:
        return httpx.Response(200, json={"data": {"post": {"result": {
            "postedAt": datetime.now(timezone.utc).isoformat()}}}})
    return httpx.Response(502)


def _entry(entry_id: str, title: str, feed_name: str, link: str = "") -> FeedEntry:
    return FeedEntry(id=entry_id, title=title, link=link or entry_id, content="<p>Land.</p>",
                     published=datetime.now() - timedelta(days=3), author="Scott Alexander",
                     feed_name=feed_name)


class Pipeline:
    """One scratch repository: its feeds, its database, and what each run emailed."""

    def __init__(self, root: Path, monkeypatch):
        self.root, self.mp = root, monkeypatch
        self.feeds: list[dict] = []
        self.briefing_sources: list[dict] = []
        self.maths = True
        self.reports = []
        self.requests: list[httpx.Request] = []
        self.answer = lambda request: httpx.Response(404)
        self.monitor = FeedMonitor(root / "data" / "posts.db")

    def feed(self, name: str, *items: str) -> None:
        path = self.root / "feeds" / f"{name}.xml"
        path.parent.mkdir(exist_ok=True)
        path.write_text("<?xml version='1.0'?><rss version='2.0'><channel>"
                        f"<title>{name}</title>{''.join(items)}</channel></rss>")
        self.feeds.append({"name": name, "url": str(path), "mode": "verbatim"})

    def broken_feed(self, name: str) -> None:
        """A feed whose fetch raises, as feedparser does on a socket timeout."""
        self.feeds.append({"name": name, "url": BROKEN, "mode": "verbatim"})

    def run(self, **env):
        """Run the pipeline once; the report it emailed, or None."""
        data = yaml.safe_load(CONFIG_PATH.read_text())
        data["feeds"] = self.feeds
        data["fidelity_check"] = False
        data["maths_filter"]["enabled"] = self.maths
        data["news_briefing"].update(enabled=bool(self.briefing_sources),
                                     sources=self.briefing_sources, full_text_stories=0)
        data["prediction_markets"]["enabled"] = bool(self.briefing_sources)
        config = self.root / "config.yaml"
        config.write_text(yaml.safe_dump(data))
        for key, value in env.items():
            self.mp.setenv(key, value)
        before = len(self.reports)
        asyncio.run(main.async_main(config))
        return self.reports[-1] if len(self.reports) > before else None

    def ntfy(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == "ntfy.sh"]


@pytest.fixture
def pipeline(tmp_path, monkeypatch, routes):
    monkeypatch.setattr(main, "ROOT", tmp_path)
    monkeypatch.setattr(main, "AudioGenerator", Narrator)
    Narrator.fail = None
    for var in ("REPROCESS_ENTRY", "FORCE_VERBATIM", "INJECT_URL", "INJECT_MODE", "NTFY_TOPIC",
                "FEEDCAST_PASS", "RESEND_REPORT", "PREVIEW_BRIEFING", "FEEDCAST_EMAIL_ALWAYS",
                "GITHUB_OUTPUT", "GITHUB_ACTIONS"):
        monkeypatch.delenv(var, raising=False)
    routes["openrouter"] = Model(lambda m: m[-1]["content"])     # the normaliser repeats it
    routes["openai"] = Model(lambda m: "- Land value taxes work.")  # the digest
    p = Pipeline(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "send_report", lambda report, **kw: p.reports.append(report))

    # Every HTTP request goes to the test: LessWrong's GraphQL and ntfy.
    lesswrong._graphql_markdown.cache_clear()
    real_client = httpx.AsyncClient

    def handle(request):
        p.requests.append(request)
        return p.answer(request)

    def post(url, **kw):
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            return client.post(url, **kw)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real_client(
        *a, transport=httpx.MockTransport(handle), **kw))
    monkeypatch.setattr(httpx, "post", post)
    real_parse = feedparser.parse

    def parse(url, *a, **kw):
        if url == BROKEN:
            raise TimeoutError("timed out")
        return real_parse(url, *a, **kw)
    monkeypatch.setattr(feedparser, "parse", parse)
    monkeypatch.setattr("src.extractor.trafilatura.fetch_url", lambda url: ARTICLE)
    yield p
    lesswrong._graphql_markdown.cache_clear()


class TestFindingAnEntryAgain:
    """_find_in_feeds: an errored or empty feed is not a feed without the post."""

    @pytest.mark.parametrize("dead", ["broken", "empty"])
    def test_a_queued_failure_whose_feed_cannot_be_read_stays_queued(self, pipeline, dead):
        pipeline.monitor.record_failure(_entry("https://acx/1", "Does Georgism Work?", "Scott"),
                                        "tts: ReadError")
        pipeline.broken_feed("Scott") if dead == "broken" else pipeline.feed("Scott")
        pipeline.run()
        (row,) = pipeline.monitor.pending_failures()
        assert row["id"] == "https://acx/1" and row["attempts"] == 1

    def test_a_queued_failure_gone_from_a_working_feed_is_still_dropped(self, pipeline):
        pipeline.monitor.record_failure(_entry("https://acx/1", "Does Georgism Work?", "Scott"),
                                        "tts: ReadError")
        pipeline.feed("Scott", item("Another Post", "https://acx/2"))
        pipeline.run()
        assert pipeline.monitor.pending_failures() == []

    def test_a_reprocess_whose_feed_cannot_be_read_says_so(self, pipeline, capsys):
        pipeline.monitor.mark_processed(_entry("https://acx/1", "Does Georgism Work?", "Scott"),
                                        "old.mp3")
        pipeline.broken_feed("Scott")
        report = pipeline.run(REPROCESS_ENTRY="https://acx/1")
        assert report.failures == [(
            "https://acx/1",
            "a feed could not be read (Scott: TimeoutError: timed out), so the post was not "
            "looked for there; the existing episode was kept")]
        assert pipeline.monitor.is_processed("https://acx/1")
        assert "Scott: TimeoutError: timed out" in capsys.readouterr().out


def test_a_feed_whose_fetch_raises_is_listed_with_the_dead_sources(pipeline):
    pipeline.feed("Scott", item("Does Georgism Work?", "https://acx/1"))
    pipeline.broken_feed("Zvi")
    report = pipeline.run()
    assert report.dead_sources == ["Zvi (TimeoutError: timed out)"]
    assert [e.title for e in report.episodes] == ["Does Georgism Work?"]


def test_the_posts_held_back_for_a_later_run_are_named(pipeline, capsys):
    pipeline.feed("Scott", item("Older Post", "https://acx/1", hours_ago=5),
                  item("Newest Post", "https://acx/2"))
    pipeline.run()
    assert "Scott: taking only the newest, Newest Post; held back for a later run: Older Post" \
        in capsys.readouterr().out


class TestLessWrongUnreachable:
    """Titus's call (T4): fail the entry and retry it, rather than narrate degraded text."""

    def test_a_maths_check_that_cannot_reach_lesswrong_fails_the_entry(self, pipeline):
        pipeline.feed("Zvi", item("On Land", LW))
        pipeline.answer = lesswrong_down
        report = pipeline.run()
        ((title, why),) = report.failures
        assert title == "On Land" and why.startswith("maths check: HTTPStatusError")
        assert why.endswith("attempt 1 of 3, will retry next run")
        assert report.episodes == [] and not pipeline.monitor.is_processed(LW)
        (row,) = pipeline.monitor.pending_failures()
        assert row["id"] == LW

    def test_a_full_text_fetch_that_fails_fails_the_entry(self, pipeline):
        """Zvi's feed body is a 3% blurb: narrating it was the silent outcome."""
        pipeline.maths = False
        pipeline.feed("Zvi", item("On Land", LW))
        pipeline.answer = lesswrong_down
        report = pipeline.run()
        ((title, why),) = report.failures
        assert title == "On Land" and why.startswith("full text: HTTPStatusError")
        assert report.episodes == [] and pipeline.monitor.pending_failures()[0]["id"] == LW

    def test_a_failed_digest_backfill_is_in_the_resent_email(self, pipeline):
        pipeline.monitor.mark_processed(_entry(LW, "On Land", "Zvi"), "a.mp3")
        (pipeline.root / "data" / "audio").mkdir(parents=True)
        (pipeline.root / "data" / "audio" / "a.mp3").write_bytes(silent_mp3())
        pipeline.answer = lesswrong_down
        report = pipeline.run(RESEND_REPORT="true")
        ((title, why),) = report.failures
        assert title == "On Land" and why.startswith("digest backfill: HTTPStatusError")


class TestInjection:

    def test_a_failed_injection_pushes_a_failure_not_a_new_episode(self, pipeline):
        Narrator.fail = RuntimeError("3 of 10 TTS chunks failed")
        pipeline.answer = lambda request: httpx.Response(200)
        pipeline.run(INJECT_URL=INJECTED, NTFY_TOPIC="feedcast-test")
        (push,) = pipeline.ntfy()
        assert push.headers["Tags"] == "x"
        assert push.content.decode() == (f"Failed to process: {INJECTED}\n"
                                         f"tts: RuntimeError: 3 of 10 TTS chunks failed")

    def test_an_injection_that_worked_pushes_its_title(self, pipeline):
        pipeline.answer = lambda request: httpx.Response(200)
        pipeline.run(INJECT_URL=INJECTED, NTFY_TOPIC="feedcast-test")
        (push,) = pipeline.ntfy()
        assert push.headers["Tags"] == "white_check_mark"
        assert push.content.decode() == "New episode: Land"

    def test_a_push_ntfy_refuses_is_logged(self, pipeline, capsys):
        pipeline.answer = lambda request: httpx.Response(403)
        pipeline.run(INJECT_URL=INJECTED, NTFY_TOPIC="feedcast-test")
        assert "ntfy notification failed: HTTPStatusError" in capsys.readouterr().out

    def test_reinjecting_deletes_the_earlier_episode_however_it_was_stored(self, pipeline,
                                                                            capsys):
        """An earlier copy matched by link, under a feed's guid, used to survive."""
        pipeline.monitor.mark_processed(_entry("lw-guid-1", "Land", "Scott", link=INJECTED),
                                        "old.mp3")
        pipeline.run(INJECT_URL=INJECTED)
        assert not pipeline.monitor.is_processed("lw-guid-1")
        assert "Deleted lw-guid-1 (Land) for re-injection" in capsys.readouterr().out


def test_a_chart_failure_reaches_the_email_it_was_left_out_of(pipeline, monkeypatch, routes):
    """The charts are drawn for the email, so their notice must be in it."""
    news = pipeline.root / "news.xml"
    news.write_text("<?xml version='1.0'?><rss version='2.0'><channel><title>BBC</title>"
                    + item("Land tax passes", "https://bbc.example/land") + "</channel></rss>")
    pipeline.briefing_sources = [{"name": "BBC", "url": str(news), "category": "politics"}]
    routes["anthropic"] = Model(lambda m: "Friday's briefing. Parliament passed a land tax.")
    now = datetime.now(timezone.utc)
    move = Market(platform="Polymarket", key="pm:1", title="Land tax by 2027?",
                  url="https://pm/land", prob=0.8, prob_24h=0.5,
                  history=[(now - timedelta(days=1), 0.5), (now, 0.8)])

    async def scan(self, selected):   # Polymarket, Kalshi and the checker, over the network
        return MarketContext(moves=[move], causes={"pm:1": {"found": False}})
    monkeypatch.setattr(MarketScout, "_build", scan)

    def broken(*a, **kw):
        raise ValueError("bad history")
    monkeypatch.setattr(market_charts, "render_chart", broken)
    report = pipeline.run()
    assert "prediction-market charts left out of this email: ValueError: bad history" \
        in report.notices
    assert notices.report() == report.notices
