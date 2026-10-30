"""Shared test setup: a fresh run's state, fakes for the paid and networked
services the real classes call (the LLM routes, Anthropic's Messages API for
the web search, DeepInfra's voice upload and TTS, and the SMTP server), a real
MP3, and a scratch repository to run the whole pipeline on (the `pipeline`
fixture)."""

import asyncio
import io
import shutil
import subprocess
import wave
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import feedparser
import httpx
import pytest
import yaml

import src.main as main
from src import audio, lesswrong, llm, notices
from src.audio import AudioGenerator
from src.config import CONFIG_PATH, load_config
from src.monitor import FeedMonitor

# The real AudioGenerator joins its chunks with ffmpeg.
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@lru_cache(maxsize=1)
def silent_mp3() -> bytes:
    """Two seconds of silence as a real MP3, made with the ffmpeg the pipeline needs.

    For tests that write an episode's MP3 themselves rather than narrate it
    (narration goes through the real AudioGenerator and `tts`): the feed reads
    each episode's duration with ffprobe, which fails on a fake.
    """
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "2",
         "-c:a", "libmp3lame", "-q:a", "9", "-f", "mp3", "pipe:1"],
        capture_output=True, check=True).stdout


@pytest.fixture(autouse=True)
def _fresh_run(monkeypatch):
    """Each test starts as a new run: every account usable, no notices yet.

    `llm.dead_routes` remembers, for the rest of a run, an account that is out
    of credit, and `notices` every fallback and skip; across tests either would
    leak one test's run into the next.
    """
    monkeypatch.setattr(llm, "dead_routes", {})
    notices.reset()


class FakeApi:
    """One route's client: replies in order, records calls. An Exception reply raises;
    a (text, finish_reason) pair sets the finish reason, which is otherwise "stop"."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw):
        self.calls.append(kw)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if reply == "<no-choices>":
            return SimpleNamespace(choices=None, error={"code": 502})
        reply, finish = reply if isinstance(reply, tuple) else (reply, "stop")
        content = None if reply == "<empty>" else reply
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)],
            usage=SimpleNamespace(completion_tokens=3))

    def asked(self) -> list[str]:
        """The text each recorded request asked the model to work on: its last message."""
        return [call["messages"][-1]["content"] for call in self.calls]


# Anthropic's native Messages API, a paid network API, is the boundary
# `llm.native_anthropic()` returns; the web search (`llm.complete_with_web_search`,
# which markets.find_cause calls) runs on it. Tests patch `llm.native_anthropic`
# to return a FakeMessagesApi.
class FakeMessagesApi:
    """Anthropic's Messages API: each call records its request and answers with
    the next turn. A turn is a (stop_reason, content blocks) pair, such as a
    paused search; a str, a finished reply with that one text block; or an
    Exception, which the call raises."""

    def __init__(self, *turns):
        self.turns, self.requests = list(turns), []
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        stop_reason, content = ("end_turn", [block("text", turn)]) if isinstance(turn, str) else turn
        return SimpleNamespace(stop_reason=stop_reason, content=content)


def block(kind: str, text: str = ""):
    """One content block of a Messages API reply: "text", "server_tool_use"..."""
    return SimpleNamespace(type=kind, text=text)


@pytest.fixture
def routes(monkeypatch):
    """Fake clients per route name; a route missing from the dict has no key."""
    fakes: dict[str, FakeApi] = {}
    monkeypatch.setattr(llm, "client_for", lambda route: fakes.get(route.name))

    # Effort-carrying anthropic calls take the native API; the fake anthropic
    # route answers those too, recording the effort it was sent.
    async def native(model, messages, max_tokens, effort):
        return await fakes["anthropic"]._create(model=model, messages=messages,
                                                max_tokens=max_tokens, effort=effort)
    monkeypatch.setattr(llm, "_anthropic_native", native)
    return fakes


def provider_error(error_class, status: int, message: str):
    """What an SDK raises for a provider's HTTP error: `error_class` is the
    openai or anthropic exception for `status` (InternalServerError for 500...)."""
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.com"))
    return error_class(message, response=response, body={"error": {"message": message}})


def silent_wav(seconds: float = 0.1) -> bytes:
    """A short silent WAV, the shape of what DeepInfra's TTS returns for a chunk."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b"\0\0" * int(24000 * seconds))
    return buf.getvalue()


@pytest.fixture
def narrator(monkeypatch):
    """Builds the real AudioGenerator with the configured voice sample.

    Its constructor uploads the sample to DeepInfra, a paid network call, so
    the upload (which also waits for the voice to replicate) answers with a
    fixed voice id instead. The fixture sets DEEPINFRA_API_KEY and replaces the
    upload for the whole test, so every AudioGenerator the test builds works,
    including one the code under test builds itself (main's narration pass);
    such tests request the fixture without calling it.
    """
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test-key")
    monkeypatch.setattr(audio, "upload_voice_to_deepinfra", lambda voice_path, api_key: "voice-1")
    return lambda: AudioGenerator(voice_sample=load_config().tts.voice_path)


def rfc822(when: datetime) -> str:
    return when.strftime("%a, %d %b %Y %H:%M:%S GMT")


def feed_xml(*items: tuple[str, datetime | None]) -> str:
    """A minimal RSS document; a None date means the item publishes no date."""
    entries = []
    for title, when in items:
        date = f"<pubDate>{rfc822(when)}</pubDate>" if when else ""
        entries.append(
            f"<item><title>{title}</title>"
            f"<link>https://example.com/{title.replace(' ', '-')}</link>"
            f"<guid>https://example.com/{title.replace(' ', '-')}</guid>"
            f"<description>Body of {title}</description>{date}</item>"
        )
    return ("<?xml version='1.0'?><rss version='2.0'><channel>"
            "<title>Test feed</title>" + "".join(entries) + "</channel></rss>")


class FakeTts:
    """DeepInfra's TTS inference, a paid network API: a silent WAV per request.

    Records the text of each request. A request whose text contains any of
    `fail_on` drops its connection, as DeepInfra's did on 2026-09-08.
    """

    def __init__(self):
        self.texts: list[str] = []
        self.fail_on: set[str] = set()

    async def __call__(self, text, voice_id, api_key, http_client, *, model,
                       save_debug_wav=None, tag=""):
        self.texts.append(text)
        if any(f in text for f in self.fail_on):
            raise httpx.ReadError("connection dropped")
        return silent_wav()


@pytest.fixture
def tts(monkeypatch):
    """The FakeTts that the real AudioGenerator's TTS requests go to."""
    fake = FakeTts()
    monkeypatch.setattr(audio, "generate_with_deepinfra_async", fake)
    return fake


@pytest.fixture
def smtp(monkeypatch):
    """The messages the real send_report hands to the mail server.

    The server is a network service, so a recorder stands in for smtplib.SMTP.
    The environment names a recipient, a BCC list and a login, as CI's do.
    """
    sent = []

    class Server:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self, **kw): pass
        def login(self, *a): pass
        def send_message(self, msg): sent.append(msg)

    monkeypatch.setattr("smtplib.SMTP", Server)
    for key, value in {"FEEDCAST_EMAIL_TO": "operator@example.com",
                       "FEEDCAST_EMAIL_BCC": "list@example.com",
                       "SMTP_USER": "bot@example.com", "SMTP_PASSWORD": "pw"}.items():
        monkeypatch.setenv(key, value)
    for key in ("FEEDCAST_TEST_RUN", "SMTP_PORT"):
        monkeypatch.delenv(key, raising=False)
    return sent


# --- The whole pipeline on a scratch repository ---------------------------------
#
# async_main end to end: the real config.yaml with local feed files, a real
# database, and the real cleaning, normaliser, digest, narrator, retry queue,
# feed generation and email. Stood in for, at the edges only: DeepInfra's voice
# upload and TTS (`narrator`, `tts`), the LLM accounts (`routes`), every other
# HTTP request (`Pipeline.answer`), the article download for an injected URL,
# and the mail server (`smtp`): paid APIs, the network and SMTP.

BROKEN = "https://feeds.example/broken.xml"
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


def item(title: str, link: str, hours_ago: float = 1.0) -> str:
    when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return (f"<item><title>{title}</title><link>{link}</link><guid>{link}</guid>"
            f"<description>&lt;p&gt;{title}: land value taxes work, and here is why.&lt;/p&gt;"
            f"</description><pubDate>{when:%a, %d %b %Y %H:%M:%S} GMT</pubDate></item>")


class Pipeline:
    """One scratch repository: its feeds, its database, and what each run emailed."""

    def __init__(self, root: Path, monkeypatch, sent: list):
        self.root, self.mp, self.sent = root, monkeypatch, sent
        self.feeds: list[dict] = []
        self.briefing_sources: list[dict] = []
        self.maths = True
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

    def run(self, **env) -> str | None:
        """Run the pipeline once; the plain text of the email it sent, or None."""
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
        before = len(self.sent)
        asyncio.run(main.async_main(config))
        if len(self.sent) == before:
            return None
        (msg,) = self.sent[before:]
        return msg.get_body(("plain",)).get_content()

    def ntfy(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == "ntfy.sh"]


@pytest.fixture
def pipeline(tmp_path, monkeypatch, routes, narrator, tts, smtp):
    # `narrator` is not called: it sets the key and fake upload for main's own AudioGenerator.
    monkeypatch.setattr(main, "ROOT", tmp_path)
    for var in ("REPROCESS_ENTRY", "FORCE_VERBATIM", "INJECT_URL", "INJECT_MODE", "NTFY_TOPIC",
                "FEEDCAST_PASS", "RESEND_REPORT", "PREVIEW_BRIEFING", "FEEDCAST_EMAIL_ALWAYS",
                "GITHUB_OUTPUT", "GITHUB_ACTIONS"):
        monkeypatch.delenv(var, raising=False)
    routes["openrouter"] = Model(lambda m: m[-1]["content"])     # the normaliser repeats it
    routes["openai"] = Model(lambda m: "- Land value taxes work.")  # the digest
    p = Pipeline(tmp_path, monkeypatch, smtp)

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
