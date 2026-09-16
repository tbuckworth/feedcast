"""Role routing: per-route parameter translation, fallback order, and the log."""

import asyncio
from types import SimpleNamespace

import pytest

from src import llm
from src.llm import ROLES, ROUTES, Target, complete


class FakeApi:
    """One route's client: replies in order, records calls. An Exception reply raises."""

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
        content = None if reply == "<empty>" else reply
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
            usage=SimpleNamespace(completion_tokens=3))


@pytest.fixture
def routes(monkeypatch):
    """Fake clients per route name; a route missing from the dict has no key."""
    fakes: dict[str, FakeApi] = {}
    monkeypatch.setattr(llm, "client_for", lambda route: fakes.get(route.name))
    monkeypatch.setattr(llm, "fallback_log", [])
    return fakes


MSGS = [{"role": "user", "content": "hi"}]


def test_primary_serves_and_nothing_is_logged(routes):
    routes["openai"] = FakeApi(["- bullets"])
    done = asyncio.run(complete("bullets", MSGS, max_tokens=50))
    assert done.text == "- bullets" and done.target == ROLES["bullets"][0]
    assert llm.fallback_log == []


def test_openai_route_uses_its_own_parameter_names(routes):
    routes["openai"] = FakeApi(["ok"])
    asyncio.run(complete("bullets", MSGS, max_tokens=50, temperature=0))
    call = routes["openai"].calls[0]
    # GPT-5.x rejects max_tokens and any non-default temperature.
    assert call["max_completion_tokens"] == 50 and "max_tokens" not in call
    assert "temperature" not in call
    assert call["reasoning_effort"] == "none"          # the target's default: reasoning off


def test_openrouter_route_translates_reasoning_into_extra_body(routes):
    routes["openrouter"] = FakeApi(["ok", "ok"])
    asyncio.run(complete("checker", MSGS, max_tokens=50, temperature=0, reasoning={"budget": 4000}))
    asyncio.run(complete("checker", MSGS, max_tokens=50, reasoning={"off": True}))
    a, b = routes["openrouter"].calls
    assert a["max_tokens"] == 50 and a["temperature"] == 0
    assert a["extra_body"] == {"reasoning": {"max_tokens": 4000}}
    assert b["extra_body"] == {"reasoning": {"enabled": False}}


def test_failure_falls_through_to_the_next_target_and_is_logged(routes):
    routes["openai"] = FakeApi([RuntimeError("openai down")])
    routes["openrouter"] = FakeApi(["from openrouter"])
    done = asyncio.run(complete("bullets", MSGS, max_tokens=50, label="digest"))
    assert done.text == "from openrouter"
    assert done.target == Target("openrouter", "openai/gpt-5.6-sol", {"off": True})
    assert len(llm.fallback_log) == 1
    assert "digest: served by openai/gpt-5.6-sol via openrouter" in llm.fallback_log[0]
    assert "RuntimeError: openai down" in llm.fallback_log[0]


def test_empty_reply_counts_as_a_failure(routes):
    routes["openai"] = FakeApi(["<empty>"])
    routes["openrouter"] = FakeApi(["real text"])
    done = asyncio.run(complete("bullets", MSGS, max_tokens=50))
    assert done.text == "real text" and len(llm.fallback_log) == 1


def test_routes_without_a_key_are_skipped_and_the_skip_is_logged(routes):
    # Only OpenRouter is keyed: the Anthropic backup is skipped, not tried,
    # and the note says so alongside the primary's failure.
    routes["openrouter"] = FakeApi([RuntimeError("primary down"), "sibling model"])
    done = asyncio.run(complete("writer", MSGS, max_tokens=50))
    assert done.text == "sibling model"
    assert done.target.model == "anthropic/claude-opus-5"
    assert [c["model"] for c in routes["openrouter"].calls] == [
        "anthropic/claude-opus-4.6", "anthropic/claude-opus-5"]
    assert "ANTHROPIC_API_KEY not set" in llm.fallback_log[0]


def test_a_missing_primary_key_is_reported_not_swallowed(routes):
    # OPENAI_API_KEY absent in CI: Sol via OpenRouter serves (at 3x the
    # price), and the email must say so every run until the key is added.
    routes["openrouter"] = FakeApi(["from openrouter"])
    done = asyncio.run(complete("bullets", MSGS, max_tokens=50, label="digest"))
    assert done.target.route == "openrouter"
    assert llm.fallback_log == [
        "digest: served by openai/gpt-5.6-sol via openrouter after "
        "gpt-5.6-sol via openai: skipped, OPENAI_API_KEY not set"]


def test_every_target_failing_raises_the_last_error(routes):
    routes["openai"] = FakeApi([RuntimeError("a")])
    routes["openrouter"] = FakeApi([RuntimeError("b"), RuntimeError("c")])
    with pytest.raises(RuntimeError, match="c"):
        asyncio.run(complete("bullets", MSGS, max_tokens=50))


def test_no_keys_at_all_is_a_clear_error(routes):
    with pytest.raises(RuntimeError, match="no route"):
        asyncio.run(complete("writer", MSGS, max_tokens=50))


def test_a_pinned_client_gets_the_primary_model_and_no_fallback(routes):
    pinned = FakeApi([RuntimeError("pinned client failed")])
    routes["openrouter"] = FakeApi(["would have served"])
    with pytest.raises(RuntimeError, match="pinned"):
        asyncio.run(complete("writer", MSGS, max_tokens=50, client=pinned))
    assert pinned.calls[0]["model"] == llm.MODEL_WRITER
    assert routes["openrouter"].calls == []


def test_every_role_target_names_a_known_route():
    for role, targets in ROLES.items():
        for t in targets:
            assert t.route in ROUTES, (role, t)


def test_empty_reply_can_be_told_not_to_fall_back(routes):
    routes["openrouter"] = FakeApi(["<empty>"])
    with pytest.raises(llm.EmptyCompletion):
        asyncio.run(complete("checker", MSGS, max_tokens=50, fallback_on_empty=False))
    assert llm.fallback_log == [] and len(routes["openrouter"].calls) == 1


def test_a_pinned_client_gets_the_openrouter_spelling_of_the_model(routes):
    # get_client() is OpenRouter's client; the bullets role's primary is the
    # OpenAI-direct spelling, which OpenRouter does not know.
    pinned = FakeApi(["ok"])
    asyncio.run(complete("bullets", MSGS, max_tokens=50, client=pinned))
    call = pinned.calls[0]
    assert call["model"] == "openai/gpt-5.6-sol" and call["max_tokens"] == 50
    assert call["extra_body"] == {"reasoning": {"enabled": False}}


def test_a_switch_before_a_non_fallback_empty_reply_is_still_logged(routes):
    # Primary down, backup empty, fallback_on_empty off: the caller retries,
    # but the primary's failure must not vanish from the report.
    routes["openai"] = FakeApi([RuntimeError("openai down")])
    routes["openrouter"] = FakeApi(["<empty>"])
    with pytest.raises(llm.EmptyCompletion):
        asyncio.run(complete("bullets", MSGS, max_tokens=50, label="digest", fallback_on_empty=False))
    assert len(llm.fallback_log) == 1
    assert "openai down" in llm.fallback_log[0] and "(empty)" in llm.fallback_log[0]


def test_a_provider_failure_falls_back_even_when_empty_replies_are_held(routes):
    # choices=None is OpenRouter saying the provider failed: that is the route
    # being down, not a budget spent, so the hold does not apply.
    routes["openrouter"] = FakeApi(["<no-choices>", "sibling answered"])
    done = asyncio.run(complete("checker", MSGS, max_tokens=50, fallback_on_empty=False))
    assert done.text == "sibling answered"
    assert len(llm.fallback_log) == 1 and "NoChoices" in llm.fallback_log[0]
