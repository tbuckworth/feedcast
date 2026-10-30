"""scripts/model_upgrade_test.py: its setups, its arguments, its meter and run.json.

The API clients are the network boundary and are faked: `llm.client_for`
returns a chat-completions client per route and `llm.native_anthropic` a
Messages client, each answering in its SDK's own response types. Nothing is
sent anywhere.
"""

import asyncio
import importlib
import json
import sys
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from anthropic.types import Message
from openai import InternalServerError
from openai.types.chat import ChatCompletion

from src import bundle, digest, llm, verify
from src.llm import Target
from tests.conftest import provider_error

SCRIPT = "scripts.model_upgrade_test"

SYSTEM = "Summarise the post for audio."
USER = "Title: A lab ships a model\n\nContent:\nThe model writes its own tests."
DRAFT = "A lab shipped a model this week that writes its own tests."
CLEAN_CHECK = '{"claims_total": 2, "flags": []}'
BULLETS = "- A lab shipped a model that writes its own unit tests"


def load_script(monkeypatch):
    """A fresh import of the script. The import points verify's and digest's
    `complete` at the meter, and run() updates llm.ROLES in place; monkeypatch
    puts all three back after the test."""
    monkeypatch.setattr(llm, "ROLES", dict(llm.ROLES))
    monkeypatch.setattr(verify, "complete", verify.complete)
    monkeypatch.setattr(digest, "complete", digest.complete)
    monkeypatch.delitem(sys.modules, SCRIPT, raising=False)
    return importlib.import_module(SCRIPT)


@pytest.fixture
def upgrade(monkeypatch):
    return load_script(monkeypatch)


class FakeChat:
    """One route's chat-completions client: answers (text, usage) in turn; an
    Exception raises. Records every request."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw):
        self.requests.append(kw)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        text, usage = reply
        return ChatCompletion.model_validate({
            "id": "c", "object": "chat.completion", "created": 0, "model": kw["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
            "usage": usage})


class FakeMessages:
    """Anthropic's Messages API: answers (text, input_tokens, output_tokens) in turn."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kw):
        self.requests.append(kw)
        text, tokens_in, tokens_out = self.replies.pop(0)
        return Message.model_validate({
            "id": "m", "type": "message", "role": "assistant", "model": kw["model"],
            "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out}})


def usage(prompt, completion, **extra):
    return {"prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": prompt + completion, **extra}


@pytest.fixture
def api(monkeypatch):
    """The fake accounts. `current` sends the writer natively (effort low), the
    checker to Anthropic's chat endpoint and the digest to OpenAI."""
    fakes = {"anthropic": FakeChat((CLEAN_CHECK, usage(2000, 100))),
             "openai": FakeChat((BULLETS, usage(300, 200))),
             "openrouter": FakeChat(),
             "native": FakeMessages((DRAFT, 1000, 500))}
    monkeypatch.setattr(llm, "client_for", lambda route: fakes.get(route.name))
    monkeypatch.setattr(llm, "native_anthropic", lambda: fakes["native"])
    return fakes


def test_current_setup_runs_write_check_and_digest(upgrade, api):
    # Until e5ed9bf the script patched llm internals whose signatures had
    # moved on, and every call off the native path raised TypeError.
    result = asyncio.run(upgrade.run("current", SYSTEM, USER, False, []))

    assert result["draft"] == result["script"] == DRAFT
    assert result["fidelity"]["status"] == "clean"
    assert result["bullets"] == ["A lab shipped a model that writes its own unit tests"]
    assert [(c["call"], c["model"]) for c in result["calls"]] == [
        ("write", "claude-opus-5-5 via anthropic"),
        ("checker", "claude-sonnet-5-5 via anthropic"),
        ("digest (current)", "gpt-6.1-sol via openai")]
    assert api["native"].requests[0]["output_config"] == {"effort": "low"}


def test_meter_reads_the_tokens_and_list_price_of_each_reply(upgrade, api):
    calls = asyncio.run(upgrade.run("current", SYSTEM, USER, False, []))["calls"]

    assert [(c["prompt_tokens"], c["completion_tokens"], c["billed_usd"], c["list_usd"])
            for c in calls] == [(1000, 500, None, 0.014),     # Opus 5.5 at $4 / $20
                                (2000, 100, None, 0.005),     # Sonnet 5.5 at $2 / $10
                                (300, 200, None, 0.0026)]     # Sol at $2 / $10


def test_meter_counts_the_reply_that_served_the_call(upgrade, api):
    api["anthropic"].replies = [provider_error(InternalServerError, 529, "overloaded")]
    api["openrouter"].replies = [(CLEAN_CHECK, usage(2100, 90, cost=0.0042))]

    asyncio.run(upgrade.metered("checker", [{"role": "user", "content": "x"}], max_tokens=100))

    assert upgrade.calls[-1] == {
        "call": "checker", "model": "anthropic/claude-sonnet-5.5 via openrouter",
        "prompt_tokens": 2100, "completion_tokens": 90, "reasoning_tokens": None,
        "billed_usd": 0.0042, "list_usd": 0.0051, "chars_out": len(CLEAN_CHECK)}


def test_meter_refuses_a_reply_it_cannot_cost(upgrade, api, monkeypatch):
    monkeypatch.setitem(llm.ROLES, "checker", (Target("anthropic", "claude-unpriced"),))

    with pytest.raises(KeyError, match="claude-unpriced has no list price"):
        asyncio.run(upgrade.metered("checker", [{"role": "user", "content": "x"}],
                                    max_tokens=100))


def test_current_is_each_roles_primary_in_llm_roles(monkeypatch):
    monkeypatch.setitem(llm.ROLES, "writer", (Target("openai", "gpt-next"), *llm.ROLES["writer"]))
    script = load_script(monkeypatch)

    assert script.SETUPS["current"] == {role: targets[:1] for role, targets in llm.ROLES.items()}
    assert script.SETUPS["current"]["writer"] == (Target("openai", "gpt-next"),)
    proposed = script.SETUPS["proposed"]
    assert {r for r in proposed if proposed[r] != script.SETUPS["current"][r]} == {"writer", "bullets"}


def test_parse_args_refuses_an_unknown_setup_before_any_call(upgrade, capsys):
    assert upgrade.parse_args(["b.md", "--out", "o", "--setups", "current,proposed"]).setups == [
        "current", "proposed"]
    with pytest.raises(SystemExit):
        upgrade.parse_args(["b.md", "--out", "o", "--setups", "current,nope"])
    assert "unknown setup(s) nope" in capsys.readouterr().err


def test_main_records_its_inputs_in_run_json(upgrade, api, tmp_path, monkeypatch):
    saved = tmp_path / "ep.md"
    saved.write_text(bundle.writer_bundle(title="A lab ships a model", model="claude-opus-5-5",
                                          system_prompt=SYSTEM, user_message=USER,
                                          response="Production's script."), encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["model_upgrade_test", str(saved), "--out", str(out),
                                      "--setups", "current"])

    asyncio.run(upgrade.main())

    run = json.loads((out / "run.json").read_text())
    assert run["args"] == {"bundle": str(saved), "out": str(out), "setups": ["current"],
                           "system_file": None, "current_prompts": False}
    assert (run["system"], run["user"]) == (SYSTEM, USER)
    assert run["setups"] == {"current": {role: [asdict(targets[0])]
                                         for role, targets in llm.ROLES.items()}}
    result = json.loads((out / "current.json").read_text())
    assert result["production"] == "Production's script."
    assert len(result["calls"]) == 3
    assert result["cost_usd"] == 0.0216
