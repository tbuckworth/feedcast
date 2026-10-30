"""LLM roles, routes and fallbacks. Every model call in the pipeline goes through `complete()`.

Four roles, each an ordered list of (route, model) targets. A call tries the
first target; if the provider fails or the reply comes back empty it moves to
the next, logs the switch, and the run report says which one served. A request
the provider rejects as malformed, or an error in our own code, raises instead
(`rejected_request`): the next target would fail the same way. The routes are the
three API accounts the pipeline can bill: OpenRouter (the default for the
Anthropic models), OpenAI direct, and Anthropic direct. All three speak the
OpenAI chat-completions shape, so one SDK covers them; the per-route quirks
(parameter names, what "reasoning" is called) live in `Route`.

Roles, and why each model:

- writer (Claude Opus 5.5, effort low): prose a person listens to — summaries,
  the daily briefing, story selection, table descriptions, the one-shot
  revision after the fidelity check. Measured against Gemini 3 Flash on a real
  maths post, Flash emitted 14 raw LaTeX expressions into the spoken script;
  Opus emitted none. Compared with GPT-5.6 Sol on 2026-09-16, Opus wrote the
  more concrete, listenable script. Opus 5.5 replaced Opus 4.6 on 2026-09-27
  after a side-by-side (scripts/model_upgrade_test.py): more careful
  attribution, no longer, ~7% dearer a month because its tokenizer counts
  ~1.46x the tokens for the same text. Its thinking cannot be switched off,
  and low effort is plenty for writing.
- checker (Claude Sonnet 5.5): reads a finished script against its source and
  lists what is contradicted, distorted or unsupported (src/verify.py). A
  different model from the writer, so its blind spots are not the same ones.
  Replaced Sonnet 5 on 2026-10-30 at the same list price, after a side-by-side
  on six episodes; Sonnet 5 stays as a backup on the same account.
- bullets (GPT-6.1 Sol, OpenAI direct, effort low): turns the checked script
  into the email's bullets. Sol was chosen on 2026-09-16 after a side-by-side:
  its bullets were as faithful as Opus's at about three-quarters of the price,
  and the email is meant to restate the audio, so it works from the script and
  never the source. GPT-6.1 Sol replaced GPT-5.6 Sol on 2026-10-30 at half the
  price per token; it cannot switch reasoning off, so it runs at low. OpenRouter
  once billed Sol at ~3x its list price in testing, so direct is primary and
  OpenRouter the backup.
- normalizer (Gemini 3 Flash): only transforms, "45%" -> "forty-five percent".
  ~47% of all tokens; a stronger model is not better at "preserve everything
  else exactly", and Flash did it for 168 episodes without incident. Its
  backups are on the other two accounts (Haiku 5.5, then GPT-6.1 Sol): on
  2026-10-10 the OpenRouter account ran out of credit (402) and, with
  OpenRouter its only route, every episode failed at normalisation.

An account that refuses for a reason that lasts (out of credit, a bad key) is
skipped for the rest of the run, so each later call goes straight to a
working one instead of failing first (`account_failure`).
"""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace

import anthropic
import httpx
import openai
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from . import notices


@dataclass(frozen=True)
class Route:
    """One API account. `key_env` names the secret; unset means the route is skipped."""

    name: str
    key_env: str
    base_url: str | None
    # OpenAI's reasoning models take `max_completion_tokens`, reject
    # `max_tokens`, and reject any temperature but the default.
    max_tokens_param: str = "max_tokens"
    accepts_temperature: bool = True


ROUTES = {
    "openrouter": Route("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    "openai": Route("openai", "OPENAI_API_KEY", None, "max_completion_tokens", False),
    # Sonnet 5, Sonnet 5.5 and Opus 5.5 reject any sampling parameter ("`temperature` is
    # deprecated for this model"), so the checker's temperature=0 400'd here
    # and, with OpenRouter refusing Claude since 2026-09-22, every check fell
    # through to Gemini 3 Flash.
    "anthropic": Route("anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/",
                       accepts_temperature=False),
}


@dataclass(frozen=True)
class Target:
    """A model on a route, plus the default reasoning setting for it.

    `reasoning` is provider-neutral: {"off": True}, {"effort": "low"} or
    {"budget": 4000} (a thinking-token ceiling). Each route translates it.
    `min_effort` is for a model that cannot switch reasoning off: "off" is
    sent as that effort instead. GPT-6.1 Sol 400s on reasoning_effort "none"
    ("Supported values are: 'low', 'medium', 'high', and 'xhigh'", 2026-10-10).
    """

    route: str
    model: str
    reasoning: dict | None = None
    min_effort: str | None = None

    @property
    def label(self) -> str:
        return f"{self.model} via {self.route}"


# Claude goes to Anthropic direct first: since 2026-09-22 OpenRouter has
# refused every Claude request on the Arrow key (403 "violation of provider
# Terms Of Service"), so an OpenRouter primary put a fallback notice in every
# email. OpenRouter stays as the Claude backup.
#
# Prefer the same model on another account, then a sibling, but do not make
# every backup depend on the same provider. On 2026-09-19 OpenRouter rejected
# all Claude calls while Anthropic direct had no credit. GPT and Gemini still
# worked. The final writer/checker fallbacks use different model families so
# the fidelity check remains independent of the writer. Every role has a
# target on at least two of the three accounts.
#
# The writer's non-Claude backup is GPT-6.1 Sol (Titus's pick, 2026-10-10) at
# effort low, the same setting Opus writes at; Sol cannot switch reasoning off.
SOL_WRITER = dict(reasoning={"effort": "low"}, min_effort="low")
ROLES: dict[str, tuple[Target, ...]] = {
    "writer": (
        Target("anthropic", "claude-opus-5-5", {"effort": "low"}),
        Target("openrouter", "anthropic/claude-opus-5.5", {"effort": "low"}),
        Target("anthropic", "claude-opus-4-6"),
        Target("openai", "gpt-6.1-sol", **SOL_WRITER),
        Target("openrouter", "openai/gpt-6.1-sol", **SOL_WRITER),
    ),
    "checker": (
        Target("anthropic", "claude-sonnet-5-5"),
        Target("openrouter", "anthropic/claude-sonnet-5.5"),
        Target("anthropic", "claude-sonnet-5"),
        Target("openrouter", "anthropic/claude-sonnet-4.6"),
        Target("openrouter", "google/gemini-3-flash-preview"),
        # Last: the same family as the writer's backup, but a check by a
        # sibling beats no check when Anthropic and OpenRouter are both down.
        Target("openai", "gpt-6.1-sol", min_effort="low"),
    ),
    "bullets": (
        Target("openai", "gpt-6.1-sol", {"effort": "low"}, min_effort="low"),
        Target("openrouter", "openai/gpt-6.1-sol", {"effort": "low"}, min_effort="low"),
        Target("anthropic", "claude-opus-5-5", {"effort": "low"}),
    ),
    # Gemini stays first after a head-to-head with Haiku 5.5 (2026-10-10,
    # docs/normaliser-model-test-2026-10-10.md): on the same prompt two blind
    # judges preferred Gemini 8 to 4, mostly for converting more of what the
    # voice stumbles on, and it is ~1.5x faster. Haiku would save ~$0.30 a
    # month. Haiku is the backup because it took the Genji review passage
    # Gemini's filter blocks. It runs with its default adaptive thinking; at
    # effort low it refused an odd post in prose, which would have been read
    # out. Sol last: on a test passage it was slower than Haiku and left
    # "$1.5M/yr" and "~3x" as written.
    "normalizer": (
        Target("openrouter", "google/gemini-3-flash-preview"),
        Target("anthropic", "claude-haiku-5-5"),
        Target("openai", "gpt-6.1-sol", {"effort": "low"}, min_effort="low"),
    ),
}

# The checker role's primary model, for the email and tests.
MODEL_CHECKER = ROLES["checker"][0].model

# The SDK default is 600s x 2 retries, so one wedged request can stall a run
# for ~30 min. Flash calls finish in well under a minute; bound them.
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "180"))

# Routes whose account failed in a way that lasts the run (out of credit, bad
# key), with the error. Later calls skip every target on them. Each switch to a
# backup target goes to `notices`, and a dead account heads that list.
dead_routes: dict[str, Exception] = {}

# What an account-level refusal says, as opposed to a model-level one (OpenRouter's
# 403 "Terms Of Service" for Claude only ever applied to Claude) or a transient
# one (a 429 "rate limit exceeded" passes in seconds). Anthropic says "Your
# credit balance is too low" with a 400; OpenAI "exceeded your current quota"
# with a 429; OpenRouter 402 "Insufficient credits", or 403 "Key limit exceeded".
_ACCOUNT_WORDING = re.compile(
    r"credit|insufficient.?(funds|quota|balance)|quota|billing|key limit|payment", re.I)


def account_failure(e: BaseException) -> bool:
    """Whether `e` says the whole account is unusable, not just this model or moment."""
    status = getattr(e, "status_code", None)
    if status in (401, 402):
        return True
    return status in (400, 403, 429) and bool(_ACCOUNT_WORDING.search(str(e)))


# Failures that are the provider's, so worth trying on the next target. Both
# SDKs raise an APIError subclass for every HTTP status and for connection
# failures and timeouts; httpx's transport errors are what escapes when one
# slips past them. Anything else (a TypeError, a KeyError) is our own code.
PROVIDER_ERRORS = (openai.APIError, anthropic.APIError, httpx.TransportError)

# What a provider says when its content policy refuses the prompt, rather than
# its shape: OpenAI answers with a 400 "invalid_prompt ... flagged as potentially
# violating our usage policy". Another model may well take the passage.
_REFUSAL_WORDING = re.compile(
    r"invalid.?prompt|usage polic|content.?(polic|filter|management)", re.I)


def rejected_request(e: BaseException) -> bool:
    """Whether `e` is the provider rejecting the request we built: our bug, not their outage.

    A 400, 413 or 422 means the request itself is wrong: a parameter the model
    does not take, a value out of range, a prompt too long. The next target
    would get the same request, and falling through hides the bug behind a
    fallback notice: Sonnet 5's 400 on the checker's `temperature=0` sent every
    check to Gemini 3 Flash from 2026-09-22 to -27. Two kinds of 400 are the
    provider's after all, and still fall through: an account out of credit
    (`account_failure`; Anthropic says so with a 400) and a prompt the
    provider's content policy refuses. Every other status (401-404, 408, 429,
    5xx) is the provider's state, OpenRouter's Claude-only 403 included.
    """
    if getattr(e, "status_code", None) not in (400, 413, 422):
        return False
    return not (account_failure(e) or _REFUSAL_WORDING.search(str(e)))


def _mark_dead(route: Route, e: Exception) -> None:
    """Skip `route` for the rest of the run; the first call to find out heads the notices."""
    if route.name not in dead_routes:
        dead_routes[route.name] = e
        notices.add(f"{route.name} account unavailable for the rest of the run "
                    f"after: {type(e).__name__}: {str(e)[:200]}", headline=True)


def model_name(model: str) -> str:
    """A model id as people say it: 'claude-opus-5-5' and 'anthropic/claude-opus-5.5'
    are both 'Claude Opus 5.5'; 'gpt-6.1-sol' is 'GPT-6.1 Sol'."""
    m = model.split("/")[-1].removesuffix("-preview")
    if m.startswith("claude-"):
        family, *version = m.removeprefix("claude-").split("-")
        return f"Claude {family.title()} {'.'.join(version)}".rstrip()
    if m.startswith("gpt-"):
        _gpt, version, *rest = m.split("-") + [""]
        return " ".join([f"GPT-{version}", *(w.title() for w in rest if w)])
    if m.startswith("gemini-"):
        return "Gemini " + " ".join(w if w[:1].isdigit() else w.title()
                                    for w in m.split("-")[1:])
    return m


class EmptyCompletion(RuntimeError):
    """The model returned no text, though the HTTP call itself succeeded.

    Two kinds, told apart by `NoChoices`: a body with no choices at all is the
    provider failing (quota, upstream error, filter) and is treated like any
    other failure, i.e. the next target is tried; choices present but content
    None is the model returning nothing (typically a reasoning budget spent
    before any text), which a caller may prefer to retry differently.

    OpenRouter reports a provider-side failure (a filtered response, an upstream
    error, a quota) as a 200 whose body has `error` set and `choices` absent;
    the SDK parses that into a ChatCompletion with `choices=None`, and the SDK's
    own retries never fire because nothing failed at the transport layer.
    `response.choices[0]` on that object is the "'NoneType' object is not
    subscriptable" that took out an ACX book review twice (2026-09-06, -08),
    with nothing in the log to say which call or why.
    """


class NoChoices(EmptyCompletion):
    """Provider-side failure reported as a 200 with no choices."""


def completion_text(response, label: str = "") -> str:
    """The text of a chat completion, or EmptyCompletion saying why there is none.

    Every call site that reads `response.choices[0].message.content` should go
    through here, so an empty reply names the call and carries the provider's
    reason instead of surfacing as a type error three frames away.
    """
    where = f"{label}: " if label else ""
    choices = getattr(response, "choices", None)
    if not choices:
        extra = getattr(response, "model_extra", None) or {}
        error = getattr(response, "error", None) or extra.get("error")
        raise NoChoices(f"{where}response has no choices (provider error: {error!r})")
    choice = choices[0]
    content = getattr(choice.message, "content", None)
    if content is None:
        refusal = getattr(choice.message, "refusal", None)
        raise EmptyCompletion(
            f"{where}empty content (finish_reason={choice.finish_reason!r}, refusal={refusal!r})")
    return content


_clients: dict[str, AsyncOpenAI] = {}


def client_for(route: Route) -> AsyncOpenAI | None:
    """A cached client for the route, or None when its key is not set."""
    key = os.environ.get(route.key_env, "").strip()
    if not key:
        return None
    if route.name not in _clients:
        _clients[route.name] = AsyncOpenAI(
            base_url=route.base_url, api_key=key,
            timeout=LLM_TIMEOUT_SECONDS, max_retries=3,
        )
    return _clients[route.name]


_native: AsyncAnthropic | None = None


def native_anthropic() -> AsyncAnthropic:
    """Anthropic's own Messages API, for calls that set an effort.

    The OpenAI-compatible endpoint ignores `reasoning_effort` (measured
    2026-09-27: Opus 5.5 produced the same ~3,150 output tokens with it set
    to low or left unset) and rejects adaptive thinking outright, so effort
    only takes hold here: ~1,280 tokens for the same digest at low.
    """
    global _native
    if _native is None:
        _native = AsyncAnthropic(api_key=os.environ.get(ROUTES["anthropic"].key_env, ""),
                                 timeout=LLM_TIMEOUT_SECONDS, max_retries=3)
    return _native


async def _anthropic_native(model: str, messages: list[dict], max_tokens: int, effort: str):
    """One native call, returned in the chat-completions shape the rest expects."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    msg = await native_anthropic().messages.create(
        model=model, max_tokens=max_tokens,
        messages=[m for m in messages if m["role"] != "system"],
        output_config={"effort": effort}, **({"system": system} if system else {}))
    text = "".join(b.text for b in msg.content if b.type == "text")
    finish = {"end_turn": "stop", "max_tokens": "length"}.get(msg.stop_reason, msg.stop_reason)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text or None, refusal=None),
                                 finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=msg.usage.input_tokens,
                              completion_tokens=msg.usage.output_tokens))


def _native_effort(route: Route, reasoning: dict | None) -> str | None:
    """The effort to send natively, for an anthropic-route call that sets one."""
    if route.name != "anthropic" or not reasoning or reasoning.get("off"):
        return None
    effort = reasoning.get("effort")
    return effort if effort and effort != "none" else None


def _reasoning_kwargs(route: Route, reasoning: dict | None, min_effort: str | None = None) -> dict:
    """Translate the neutral reasoning setting into what this route expects."""
    if not reasoning:
        return {}
    off = reasoning.get("off") or reasoning.get("effort") == "none"
    if off and min_effort:
        reasoning, off = {"effort": min_effort}, False
    if route.name == "openai":
        if off:
            return {"reasoning_effort": "none"}
        if "budget" in reasoning:
            return {"reasoning_effort": "low"}
        return {"reasoning_effort": reasoning["effort"]}
    if route.name == "openrouter":
        if off:
            return {"extra_body": {"reasoning": {"enabled": False}}}
        if "budget" in reasoning:
            return {"extra_body": {"reasoning": {"max_tokens": reasoning["budget"]}}}
        return {"extra_body": {"reasoning": {"effort": reasoning["effort"]}}}
    # Anthropic's OpenAI-compatible endpoint takes no reasoning setting that
    # works; a call with an effort goes to the native API instead
    # (`_native_effort`), and anything else is sent without one.
    return {}


def _kwargs(route: Route, target: Target, messages: list[dict], max_tokens: int,
            temperature: float | None, reasoning: dict | None) -> dict:
    kw: dict = {"model": target.model, "messages": messages, route.max_tokens_param: max_tokens}
    if temperature is not None and route.accepts_temperature:
        kw["temperature"] = temperature
    kw.update(_reasoning_kwargs(route, reasoning if reasoning is not None else target.reasoning,
                                target.min_effort))
    return kw


@dataclass
class Completion:
    text: str
    finish_reason: str | None
    target: Target
    role: str   # the role the call was made for; credit() compares with its primary
    usage: object = None

    def credit(self) -> dict:
        """Who wrote this, for the email and the database.

        `backup` means a different model from the role's primary. The same
        model on another account reads the same, so it is not flagged here
        (the fallback section of the email still lists the switch).
        """
        primary = ROLES[self.role][0].model
        return {"model": self.target.model, "route": self.target.route, "primary": primary,
                "backup": model_name(self.target.model) != model_name(primary)}


async def complete(role: str, messages: list[dict], *, max_tokens: int, label: str = "",
                   client=None, temperature: float | None = None,
                   reasoning: dict | None = None, fallback_on_empty: bool = True,
                   check: Callable[[str], str | None] | None = None) -> Completion:
    """Run one chat completion for `role`, falling back along its target list.

    `client` pins the call to one client with no fallback: tests use it. Such
    a client is assumed to be OpenRouter's, so the role's first OpenRouter
    target is used — for the bullets role that is `openai/gpt-6.1-sol`, not
    the OpenAI direct spelling. `reasoning` overrides the target's default for
    this call.

    `fallback_on_empty=False` lets an empty reply (choices present, no text)
    propagate instead of trying the next target: the checker's first attempt
    wants to retry with reasoning off, because a budget eaten by hidden
    reasoning is not the model being down. A reply with no choices at all is
    the provider failing and falls back regardless.

    `check` reads a reply's text and returns why it is unusable, or None. An
    unusable reply is treated like an empty one: the next target is tried.

    Raises the last error when every target fails, and EmptyCompletion when
    the text is missing, so callers keep their existing handling. Only a
    provider's failure moves on to the next target (`PROVIDER_ERRORS`); a
    request it rejects as malformed (`rejected_request`) and any other
    exception, a bug in our own code, raise at once.
    """
    targets = ROLES[role]
    where = label or role
    if client is not None:
        target = pinned_target(role)
        response = await client.chat.completions.create(
            **_kwargs(ROUTES["openrouter"], target, messages, max_tokens, temperature, reasoning))
        return _checked(_completion(response, target, role, where), check, where)

    last: Exception | None = None
    tried: list[str] = []
    for target in targets:
        route = ROUTES[target.route]
        if route.name in dead_routes:
            last = last or dead_routes[route.name]
            tried.append(f"{target.label}: skipped, {route.name} account unavailable this run")
            continue
        api = client_for(route)
        if api is None:
            # Counts as a fallback: a primary whose key is missing in CI would
            # otherwise be served by its backup for weeks without a word.
            tried.append(f"{target.label}: skipped, {route.key_env} not set")
            print(f"    {where}: {tried[-1]}")
            continue
        try:
            effort = _native_effort(route, reasoning if reasoning is not None else target.reasoning)
            if effort:
                response = await _anthropic_native(target.model, messages, max_tokens, effort)
            else:
                response = await api.chat.completions.create(
                    **_kwargs(route, target, messages, max_tokens, temperature, reasoning))
            done = _checked(_completion(response, target, role, where), check, where)
        except EmptyCompletion as e:
            if not fallback_on_empty and not isinstance(e, NoChoices):
                # The caller will retry from the top; record any switch that
                # happened on the way here so it still reaches the report.
                if tried:
                    notices.add(f"{where}: reached {target.label} (empty) after " + "; ".join(tried))
                raise
            last = e
            tried.append(f"{target.label}: {type(e).__name__}: {str(e)[:160]}")
            print(f"    {where}: {tried[-1]}")
            continue
        except PROVIDER_ERRORS as e:
            if rejected_request(e):
                print(f"    {where}: {target.label} rejected the request, not trying a backup: "
                      f"{type(e).__name__}: {str(e)[:160]}")
                if tried:
                    notices.add(f"{where}: reached {target.label} (rejected) after " + "; ".join(tried))
                raise
            last = e
            tried.append(f"{target.label}: {type(e).__name__}: {str(e)[:160]}")
            print(f"    {where}: {tried[-1]}")
            if account_failure(e):
                _mark_dead(route, e)
                print(f"    {where}: {route.name} account unusable; skipping it for the rest of the run")
            continue
        if tried:
            note = f"{where}: served by {target.label} after " + "; ".join(tried)
            notices.add(note)
            print(f"    {note}")
        return done
    if last is None:
        raise RuntimeError(f"{where}: no route for role {role!r} has an API key set "
                           f"({'; '.join(tried)})")
    raise last


def pinned_target(role: str) -> Target:
    """The target a pinned (OpenRouter) client is sent: the role's first OpenRouter one."""
    targets = ROLES[role]
    return next((t for t in targets if t.route == "openrouter"), targets[0])


def _checked(done: Completion, check, where: str) -> Completion:
    problem = check(done.text) if check else None
    if problem:
        raise EmptyCompletion(f"{where}: {problem}")
    return done


def _completion(response, target: Target, role: str, where: str) -> Completion:
    text = completion_text(response, where)
    choice = response.choices[0]
    finish = getattr(choice, "finish_reason", None)
    if finish == "error":
        # OpenRouter's word for a provider that died mid-reply: the text is a
        # fragment. Gemini returned 88% of a 17,859-char batch this way
        # (2026-10-10), and only "length" was ever checked.
        raise NoChoices(f"{where}: reply cut off by a provider error after {len(text):,} chars")
    return Completion(text=text, finish_reason=finish, target=target, role=role,
                      usage=getattr(response, "usage", None))
