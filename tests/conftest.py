"""Shared test setup: a fresh run's state, and fakes for the paid and networked
services the real classes call: the LLM routes, DeepInfra's voice upload and
TTS, and the SMTP server."""

import io
import shutil
import wave
from types import SimpleNamespace

import httpx
import pytest

from src import audio, llm, notices
from src.audio import AudioGenerator
from src.config import load_config

# The real AudioGenerator joins its chunks with ffmpeg.
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


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
    fixed voice id instead.
    """
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test-key")
    monkeypatch.setattr(audio, "upload_voice_to_deepinfra", lambda voice_path, api_key: "voice-1")
    return lambda: AudioGenerator(voice_sample=load_config().tts.voice_path)


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
