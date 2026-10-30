"""Role routing: per-route parameter translation, fallback order, and the log."""

import asyncio
from types import SimpleNamespace

import anthropic
import pytest
import httpx
from openai import (APIConnectionError, APITimeoutError, BadRequestError, InternalServerError,
                    NotFoundError, PermissionDeniedError, RateLimitError, UnprocessableEntityError)

from src import llm, notices
from src.llm import ROLES, ROUTES, Target, complete
from tests.conftest import FakeApi, provider_error


MSGS = [{"role": "user", "content": "hi"}]


def test_primary_serves_and_nothing_is_logged(routes):
    routes["openai"] = FakeApi(["- bullets"])
    done = asyncio.run(complete("bullets", MSGS, max_tokens=50))
    assert done.text == "- bullets" and done.target == ROLES["bullets"][0]
    assert notices.report() == []


def test_openai_route_uses_its_own_parameter_names(routes):
    routes["openai"] = FakeApi(["ok"])
    asyncio.run(complete("bullets", MSGS, max_tokens=50, temperature=0))
    call = routes["openai"].calls[0]
    # GPT-5.x rejects max_tokens and any non-default temperature.
    assert call["max_completion_tokens"] == 50 and "max_tokens" not in call
    assert "temperature" not in call
    assert call["reasoning_effort"] == "low"           # the target's default: Sol's lowest


def test_openrouter_route_translates_reasoning_into_extra_body(routes):
    routes["openrouter"] = FakeApi(["ok", "ok"])
    asyncio.run(complete("checker", MSGS, max_tokens=50, temperature=0, reasoning={"budget": 4000}))
    asyncio.run(complete("checker", MSGS, max_tokens=50, reasoning={"off": True}))
    a, b = routes["openrouter"].calls
    assert a["max_tokens"] == 50 and a["temperature"] == 0
    assert a["extra_body"] == {"reasoning": {"max_tokens": 4000}}
    assert b["extra_body"] == {"reasoning": {"enabled": False}}


def test_anthropic_route_sends_no_temperature(routes):
    # Sonnet 5 400s on any temperature; the checker passes 0. With OpenRouter
    # down this sent every check to Gemini Flash (2026-09-22 to -27).
    routes["openrouter"] = FakeApi([_down("403")])
    routes["anthropic"] = FakeApi(["ok"])
    done = asyncio.run(complete("checker", MSGS, max_tokens=50, temperature=0))
    assert done.target.route == "anthropic"
    assert "temperature" not in routes["anthropic"].calls[0]


def test_failure_falls_through_to_the_next_target_and_is_logged(routes):
    routes["openai"] = FakeApi([_down("openai down")])
    routes["openrouter"] = FakeApi(["from openrouter"])
    done = asyncio.run(complete("bullets", MSGS, max_tokens=50, label="digest"))
    assert done.text == "from openrouter"
    assert done.target == Target("openrouter", "openai/gpt-6.1-sol", {"effort": "low"},
                                 min_effort="low")
    assert len(notices.report()) == 1
    assert "digest: served by openai/gpt-6.1-sol via openrouter" in notices.report()[0]
    assert "InternalServerError: openai down" in notices.report()[0]


def test_empty_reply_counts_as_a_failure(routes):
    routes["openai"] = FakeApi(["<empty>"])
    routes["openrouter"] = FakeApi(["real text"])
    done = asyncio.run(complete("bullets", MSGS, max_tokens=50))
    assert done.text == "real text" and len(notices.report()) == 1


def test_routes_without_a_key_are_skipped_and_the_skip_is_logged(routes):
    # Only OpenRouter is keyed: the Anthropic backup is skipped, not tried,
    # and the note says so alongside the primary's failure.
    routes["openrouter"] = FakeApi([_down("primary down"), "sibling model"])
    done = asyncio.run(complete("writer", MSGS, max_tokens=50))
    assert done.text == "sibling model"
    assert done.target.model == "openai/gpt-6.1-sol"
    assert [c["model"] for c in routes["openrouter"].calls] == [
        "anthropic/claude-opus-5.5", "openai/gpt-6.1-sol"]
    assert "ANTHROPIC_API_KEY not set" in notices.report()[0]


def test_a_missing_primary_key_is_reported_not_swallowed(routes):
    # OPENAI_API_KEY absent in CI: Sol via OpenRouter serves (at 3x the
    # price), and the email must say so every run until the key is added.
    routes["openrouter"] = FakeApi(["from openrouter"])
    done = asyncio.run(complete("bullets", MSGS, max_tokens=50, label="digest"))
    assert done.target.route == "openrouter"
    assert notices.report() == [
        "digest: served by openai/gpt-6.1-sol via openrouter after "
        "gpt-6.1-sol via openai: skipped, OPENAI_API_KEY not set"]


def test_every_target_failing_raises_the_last_error(routes):
    routes["openai"] = FakeApi([_down("a")])
    routes["openrouter"] = FakeApi([_down("b")])
    routes["anthropic"] = FakeApi([_down("c")])
    with pytest.raises(InternalServerError, match="c"):
        asyncio.run(complete("bullets", MSGS, max_tokens=50))


def test_no_keys_at_all_is_a_clear_error(routes):
    with pytest.raises(RuntimeError, match="no route"):
        asyncio.run(complete("writer", MSGS, max_tokens=50))


def test_a_pinned_client_gets_the_primary_model_and_no_fallback(routes):
    pinned = FakeApi([RuntimeError("pinned client failed")])
    routes["openrouter"] = FakeApi(["would have served"])
    with pytest.raises(RuntimeError, match="pinned"):
        asyncio.run(complete("writer", MSGS, max_tokens=50, client=pinned))
    assert pinned.calls[0]["model"] == llm.pinned_target("writer").model
    assert routes["openrouter"].calls == []


def test_every_role_target_names_a_known_route():
    for role, targets in ROLES.items():
        for t in targets:
            assert t.route in ROUTES, (role, t)


def test_empty_reply_can_be_told_not_to_fall_back(routes):
    routes["anthropic"] = FakeApi(["<empty>"])
    with pytest.raises(llm.EmptyCompletion):
        asyncio.run(complete("checker", MSGS, max_tokens=50, fallback_on_empty=False))
    assert notices.report() == [] and len(routes["anthropic"].calls) == 1


def test_a_pinned_client_gets_the_openrouter_spelling_of_the_model(routes):
    # A pinned client is OpenRouter's; the bullets role's primary is the
    # OpenAI-direct spelling, which OpenRouter does not know.
    pinned = FakeApi(["ok"])
    asyncio.run(complete("bullets", MSGS, max_tokens=50, client=pinned))
    call = pinned.calls[0]
    assert call["model"] == "openai/gpt-6.1-sol" and call["max_tokens"] == 50
    assert call["extra_body"] == {"reasoning": {"effort": "low"}}


def test_a_switch_before_a_non_fallback_empty_reply_is_still_logged(routes):
    # Primary down, backup empty, fallback_on_empty off: the caller retries,
    # but the primary's failure must not vanish from the report.
    routes["openai"] = FakeApi([_down("openai down")])
    routes["openrouter"] = FakeApi(["<empty>"])
    with pytest.raises(llm.EmptyCompletion):
        asyncio.run(complete("bullets", MSGS, max_tokens=50, label="digest", fallback_on_empty=False))
    assert len(notices.report()) == 1
    assert "openai down" in notices.report()[0] and "(empty)" in notices.report()[0]


def test_a_provider_failure_falls_back_even_when_empty_replies_are_held(routes):
    # choices=None is OpenRouter saying the provider failed: that is the route
    # being down, not a budget spent, so the hold does not apply.
    routes["openrouter"] = FakeApi(["<no-choices>", "sibling answered"])
    done = asyncio.run(complete("checker", MSGS, max_tokens=50, fallback_on_empty=False))
    assert done.text == "sibling answered"
    assert len(notices.report()) == 1 and "NoChoices" in notices.report()[0]


def _down(message):
    """A provider outage: what the SDK raises for a 500."""
    return provider_error(InternalServerError, 500, message)


@pytest.mark.parametrize("direct_openai", [True, False])
def test_writer_recovers_when_claude_is_blocked_and_anthropic_has_no_credit(routes, direct_openai):
    """Both daily runs on 2026-09-19 exhausted the all-Claude fallback chain."""
    denied = provider_error(PermissionDeniedError, 403, "Provider Terms Of Service")
    no_credit = provider_error(BadRequestError, 400, "Your credit balance is too low")
    routes["openrouter"] = FakeApi([denied, '["https://example.com/story"]'])
    routes["anthropic"] = FakeApi([no_credit, no_credit])
    if direct_openai:
        routes["openai"] = FakeApi(['["https://example.com/story"]'])

    done = asyncio.run(complete("writer", MSGS, max_tokens=2000, label="story selection"))

    assert done.text == '["https://example.com/story"]'
    assert done.target.route == ("openai" if direct_openai else "openrouter")
    assert done.target.model.endswith("gpt-6.1-sol")
    # The dead account is the headline; the switch that served follows it.
    head, served = notices.report()
    assert head.startswith("anthropic account unavailable for the rest of the run")
    assert "PermissionDeniedError" in served and "credit balance" in served
    # Out of credit is the whole account: Opus 4.6 on it is not even tried.
    assert len(routes["anthropic"].calls) == 1
    call = routes[done.target.route].calls[-1]
    # Sol cannot switch reasoning off, so it writes at low, like Opus.
    if direct_openai:
        assert call["max_completion_tokens"] == 2000
        assert call["reasoning_effort"] == "low"
    else:
        assert call["max_tokens"] == 2000
        assert call["extra_body"] == {"reasoning": {"effort": "low"}}


def test_checker_recovers_on_a_different_model_family_from_the_backup_writer(routes):
    denied = provider_error(PermissionDeniedError, 403, "Provider Terms Of Service")
    no_credit = provider_error(BadRequestError, 400, "Your credit balance is too low")
    routes["openrouter"] = FakeApi([denied, denied, '{"claims_total": 1, "flags": []}'])
    routes["anthropic"] = FakeApi([no_credit])

    done = asyncio.run(complete("checker", MSGS, max_tokens=16000, temperature=0,
                               reasoning={"budget": 4000}, fallback_on_empty=False))

    assert done.target == Target("openrouter", "google/gemini-3-flash-preview")
    assert routes["openrouter"].calls[-1]["extra_body"] == {"reasoning": {"max_tokens": 4000}}
    assert "served by google/gemini-3-flash-preview" in notices.report()[1]


def test_writer_raises_when_the_non_claude_backups_also_fail(routes):
    routes["openrouter"] = FakeApi([_down("Claude blocked"), _down("GPT unavailable")])
    routes["anthropic"] = FakeApi([_down("Opus overloaded"), _down("Opus overloaded")])
    routes["openai"] = FakeApi([_down("OpenAI unavailable")])
    with pytest.raises(InternalServerError, match="GPT unavailable"):
        asyncio.run(complete("writer", MSGS, max_tokens=2000))


def test_anthropic_effort_goes_to_the_native_api(routes):
    # The compat endpoint ignores reasoning_effort, so an effort-carrying
    # anthropic call goes native (the fixture's fake records `effort`).
    routes["openrouter"] = FakeApi([_down("403")])
    routes["anthropic"] = FakeApi(["native"])
    done = asyncio.run(complete("writer", [{"role": "system", "content": "s"}] + MSGS, max_tokens=50))
    assert done.text == "native" and done.target.model == "claude-opus-5-5"
    call = routes["anthropic"].calls[0]
    assert call["effort"] == "low" and "temperature" not in call and "reasoning_effort" not in call


def test_anthropic_without_effort_stays_on_the_compat_endpoint(routes):
    routes["openrouter"] = FakeApi([_down("403")])
    routes["anthropic"] = FakeApi(["compat"])
    done = asyncio.run(complete("checker", MSGS, max_tokens=50, reasoning={"budget": 4000}))
    assert done.text == "compat" and len(routes["anthropic"].calls) == 1


def test_claude_roles_try_anthropic_direct_first(routes):
    # OpenRouter has refused Claude since 2026-09-22; with Anthropic first a
    # healthy run logs no fallback at all.
    routes["anthropic"] = FakeApi(["script", "checked"])
    asyncio.run(complete("writer", MSGS, max_tokens=50))
    asyncio.run(complete("checker", MSGS, max_tokens=50))
    assert [c["model"] for c in routes["anthropic"].calls] == ["claude-opus-5-5", "claude-sonnet-5-5"]
    assert notices.report() == []


# --- what is the provider's failure, and what is our own bug --------------------

def test_a_bug_in_our_own_code_raises_instead_of_reading_as_an_outage(routes):
    # A TypeError in the native adapter, say: every target would hit it, and
    # the email would blame each provider in turn.
    routes["anthropic"] = FakeApi([TypeError("create() got an unexpected keyword argument")])
    routes["openrouter"] = FakeApi(["would have served"])
    with pytest.raises(TypeError, match="unexpected keyword"):
        asyncio.run(complete("writer", MSGS, max_tokens=50))
    assert routes["openrouter"].calls == [] and notices.report() == []


def test_a_request_the_provider_rejects_as_malformed_raises(routes):
    # Sonnet 5 400s on any temperature. Falling through on it sent every
    # check to Gemini Flash from 2026-09-22 to -27, reported as a fallback.
    bad = provider_error(BadRequestError, 400, "`temperature` is deprecated for this model")
    routes["anthropic"] = FakeApi([bad])
    routes["openrouter"] = FakeApi(["would have served"])
    with pytest.raises(BadRequestError, match="temperature"):
        asyncio.run(complete("checker", MSGS, max_tokens=50))
    assert routes["openrouter"].calls == [] and llm.dead_routes == {}


def test_a_switch_before_a_malformed_request_still_reaches_the_report(routes):
    routes["anthropic"] = FakeApi([provider_error(InternalServerError, 500, "overloaded")])
    routes["openrouter"] = FakeApi([provider_error(UnprocessableEntityError, 422,
                                                    "max_tokens: must be at most 64000")])
    with pytest.raises(UnprocessableEntityError):
        asyncio.run(complete("checker", MSGS, max_tokens=50, label="checker"))
    (note,) = notices.report()
    assert "checker: reached anthropic/claude-sonnet-5.5 via openrouter (rejected)" in note
    assert "overloaded" in note


_REQUEST = httpx.Request("POST", "https://example.com")


@pytest.mark.parametrize("error", [
    provider_error(InternalServerError, 500, "upstream error"),
    provider_error(RateLimitError, 429, "Rate limit exceeded, retry in 2s"),
    # OpenRouter refusing Claude only: a model-level refusal, not our request.
    provider_error(PermissionDeniedError, 403, "violation of provider Terms Of Service"),
    provider_error(NotFoundError, 404, "No endpoints found for anthropic/claude-sonnet-5.5"),
    # The two 400s that are the provider's: the account, and the content.
    provider_error(BadRequestError, 400, "Your credit balance is too low"),
    provider_error(BadRequestError, 400, "Invalid prompt: your prompt was flagged as "
                                          "potentially violating our usage policy"),
    APIConnectionError(request=_REQUEST),
    APITimeoutError(request=_REQUEST),
    anthropic.APIConnectionError(request=_REQUEST),
    httpx.ConnectError("connection refused"),
], ids=lambda e: type(e).__name__)
def test_provider_and_transport_failures_fall_through(routes, error):
    routes["anthropic"] = FakeApi([error])
    routes["openrouter"] = FakeApi(["served"])
    done = asyncio.run(complete("checker", MSGS, max_tokens=50))
    assert done.text == "served" and done.target.route == "openrouter"


@pytest.mark.parametrize("error, ours", [
    (provider_error(BadRequestError, 400, "`temperature` is deprecated for this model"), True),
    (provider_error(BadRequestError, 400, "reasoning_effort: Supported values are: 'low', "
                                           "'medium', 'high', and 'xhigh'"), True),
    (provider_error(UnprocessableEntityError, 422, "max_tokens: must be at most 64000"), True),
    (provider_error(BadRequestError, 400, "Your credit balance is too low"), False),
    (provider_error(BadRequestError, 400, "Invalid prompt: flagged as potentially violating "
                                           "our usage policy"), False),
    (provider_error(PermissionDeniedError, 403, "violation of provider Terms Of Service"), False),
    (provider_error(InternalServerError, 500, "Bad request upstream"), False),
    (APIConnectionError(request=_REQUEST), False),
])
def test_rejected_request_is_our_malformed_request_only(error, ours):
    assert llm.rejected_request(error) is ours


@pytest.mark.parametrize("reply, kind, value", [
    ('{"a": 1}', dict, {"a": 1}),
    ('```json\n{"a": [1, 2]}\n```', dict, {"a": [1, 2]}),
    ('Here it is: {"a": {"b": 2}} and that is all.', dict, {"a": {"b": 2}}),
    ('```json\n["x", "y"]\n```', list, ["x", "y"]),
    ('Chosen: ["x"]. Done.', list, ["x"]),
])
def test_extract_json_reads_the_value_out_of_fences_and_prose(reply, kind, value):
    assert llm.extract_json(reply, kind) == value


@pytest.mark.parametrize("reply, kind, error", [
    ("No JSON here.", dict, r"^no JSON object in the reply$"),
    (None, list, r"^no JSON array in the reply$"),
    ('{"a": 1,}', dict, r"^the object is not valid JSON \(Expecting property name"),
    ('["x",]', list, r"^the array is not valid JSON \(Expecting value"),
    # An array is not an object, and an object is not an array.
    ('["x"]', dict, r"^no JSON object in the reply$"),
    ('{"a": 1}', list, r"^no JSON array in the reply$"),
])
def test_extract_json_raises_saying_why_there_is_none(reply, kind, error):
    with pytest.raises(ValueError, match=error):
        llm.extract_json(reply, kind)


class _WebSearch:
    """Anthropic's Messages API with server-side web search, a paid API: each call
    records its request and answers with the next (stop_reason, content blocks)."""

    def __init__(self, *turns):
        self.turns, self.requests = list(turns), []
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        stop_reason, content = self.turns.pop(0)
        return SimpleNamespace(stop_reason=stop_reason, content=content)


def _block(kind, text=""):
    return SimpleNamespace(type=kind, text=text)


def test_web_search_resumes_a_paused_turn_with_the_checkers_anthropic_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    # The model follows the checker role, so an upgrade there reaches the search.
    monkeypatch.setitem(ROLES, "checker", (Target("openrouter", "anthropic/claude-x"),
                                           Target("anthropic", "claude-sonnet-9")))
    paused = [_block("server_tool_use"), _block("text", "Searching")]
    api = _WebSearch(("pause_turn", paused),
                     ("end_turn", [_block("web_search_tool_result"), _block("text", '{"found": '),
                                   _block("text", "false}")]))
    monkeypatch.setattr(llm, "native_anthropic", lambda: api)

    reply = asyncio.run(llm.complete_with_web_search("Why did it move?", max_tokens=2000))

    assert reply == '{"found": false}'
    first, second = api.requests
    assert first["model"] == second["model"] == "claude-sonnet-9"
    assert first["tools"] == [llm.WEB_SEARCH_TOOL] and first["max_tokens"] == 2000
    assert first["messages"] == [{"role": "user", "content": "Why did it move?"}]
    assert second["messages"] == [{"role": "user", "content": "Why did it move?"},
                                  {"role": "assistant", "content": paused}]


def test_web_search_stops_resuming_after_three_requests(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    api = _WebSearch(*[("pause_turn", [_block("text", f"part {i}")]) for i in range(4)])
    monkeypatch.setattr(llm, "native_anthropic", lambda: api)
    assert asyncio.run(llm.complete_with_web_search("q", max_tokens=10)) == "part 2"
    assert len(api.requests) == 3


def test_web_search_without_an_anthropic_key_raises_before_any_request(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    api = _WebSearch()
    monkeypatch.setattr(llm, "native_anthropic", lambda: api)
    with pytest.raises(RuntimeError, match="^ANTHROPIC_API_KEY not set$"):
        asyncio.run(llm.complete_with_web_search("q", max_tokens=10))
    assert api.requests == []
