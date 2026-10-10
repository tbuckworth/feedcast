"""Shared test setup: fresh account state, and fake LLM routes."""

from types import SimpleNamespace

import pytest

from src import llm


@pytest.fixture(autouse=True)
def _fresh_accounts(monkeypatch):
    """Each test starts with every account usable.

    `llm.dead_routes` remembers, for the rest of a run, an account that is out
    of credit; across tests that memory would leak one test's failure into the next.
    """
    monkeypatch.setattr(llm, "dead_routes", {})


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
    monkeypatch.setattr(llm, "fallback_log", [])
    return fakes
