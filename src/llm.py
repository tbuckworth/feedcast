"""LLM roles, routes and fallbacks. Every model call in the pipeline goes through `complete()`.

Four roles, each an ordered list of (route, model) targets. A call tries the
first target; if the request fails or comes back empty it moves to the next,
logs the switch, and the run report says which one served. The routes are the
three API accounts the pipeline can bill: OpenRouter (the default for the
Anthropic models), OpenAI direct, and Anthropic direct. All three speak the
OpenAI chat-completions shape, so one SDK covers them; the per-route quirks
(parameter names, what "reasoning" is called) live in `Route`.

Roles, and why each model:

- writer (Claude Opus 4.6): prose a person listens to — summaries, the daily
  briefing, table descriptions, the one-shot revision after the fidelity
  check. Measured against Gemini 3 Flash on a real maths post, Flash emitted
  14 raw LaTeX expressions into the spoken script; Opus emitted none. Compared
  with GPT-5.6 Sol on 2026-09-16, Opus wrote the more concrete, listenable
  script (the figures, names and examples a listener remembers).
- checker (Claude Sonnet 5): reads a finished script against its source and
  lists what is contradicted, distorted or unsupported (src/verify.py). A
  different model from the writer, so its blind spots are not the same ones.
- bullets (GPT-5.6 Sol, OpenAI direct, reasoning off): turns the checked
  script into the email's bullets. Chosen on 2026-09-16 after a side-by-side:
  Sol's bullets were as faithful as Opus's at about three-quarters of the
  price, and the email is meant to restate the audio, so it works from the
  script and never the source. OpenRouter lists Sol at half OpenAI's price but
  billed ~3x that in testing, so direct is primary and OpenRouter the backup.
- normalizer (Gemini 3 Flash): only transforms, "45%" -> "forty-five percent".
  ~47% of all tokens; a stronger model is not better at "preserve everything
  else exactly", and Flash did it for 168 episodes without incident.
"""

import os
from dataclasses import dataclass

from openai import AsyncOpenAI


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
    "anthropic": Route("anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/"),
}


@dataclass(frozen=True)
class Target:
    """A model on a route, plus the default reasoning setting for it.

    `reasoning` is provider-neutral: {"off": True}, {"effort": "low"} or
    {"budget": 4000} (a thinking-token ceiling). Each route translates it.
    """

    route: str
    model: str
    reasoning: dict | None = None

    @property
    def label(self) -> str:
        return f"{self.model} via {self.route}"


# Same model on the other account where possible, so a fallback does not
# change the product; a sibling model only as the last resort. The Anthropic
# direct route is listed second for the Claude roles: it is the one backup that
# still works if the OpenRouter account itself is the problem.
ROLES: dict[str, tuple[Target, ...]] = {
    "writer": (
        Target("openrouter", "anthropic/claude-opus-4.6"),
        Target("anthropic", "claude-opus-4-6"),
        Target("openrouter", "anthropic/claude-opus-5"),
    ),
    "checker": (
        Target("openrouter", "anthropic/claude-sonnet-5"),
        Target("anthropic", "claude-sonnet-5"),
        Target("openrouter", "anthropic/claude-sonnet-4.6"),
    ),
    "bullets": (
        Target("openai", "gpt-5.6-sol", {"off": True}),
        Target("openrouter", "openai/gpt-5.6-sol", {"off": True}),
        Target("openrouter", "anthropic/claude-opus-4.6"),
    ),
    "normalizer": (
        Target("openrouter", "google/gemini-3-flash-preview"),
    ),
}

# The primary model of each role, for logs, bundles and tests.
MODEL_WRITER = ROLES["writer"][0].model
MODEL_CHECKER = ROLES["checker"][0].model
MODEL_BULLETS = ROLES["bullets"][0].model
MODEL_NORMALIZER = ROLES["normalizer"][0].model
# Back-compat aliases; prefer the role names above.
MODEL_STRONG = MODEL_WRITER
MODEL_CHEAP = MODEL_WRITER

# The SDK default is 600s x 2 retries, so one wedged request can stall a run
# for ~30 min. Flash calls finish in well under a minute; bound them.
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "180"))

# Every switch to a backup target this run, in order, for the run report.
fallback_log: list[str] = []


class EmptyCompletion(RuntimeError):
    """The model returned no text, though the HTTP call itself succeeded.

    OpenRouter reports a provider-side failure (a filtered response, an upstream
    error, a quota) as a 200 whose body has `error` set and `choices` absent;
    the SDK parses that into a ChatCompletion with `choices=None`, and the SDK's
    own retries never fire because nothing failed at the transport layer.
    `response.choices[0]` on that object is the "'NoneType' object is not
    subscriptable" that took out an ACX book review twice (2026-09-06, -08),
    with nothing in the log to say which call or why.
    """


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
        raise EmptyCompletion(f"{where}response has no choices (provider error: {error!r})")
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


def get_client() -> AsyncOpenAI:
    """The OpenRouter client. Kept for callers that manage their own calls."""
    return AsyncOpenAI(
        base_url=ROUTES["openrouter"].base_url,
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=3,
    )


def _reasoning_kwargs(route: Route, reasoning: dict | None) -> dict:
    """Translate the neutral reasoning setting into what this route expects."""
    if not reasoning:
        return {}
    off = reasoning.get("off") or reasoning.get("effort") == "none"
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
    # Anthropic's OpenAI-compatible endpoint: thinking is off unless asked for,
    # and the pipeline never needs it on. Untested past authentication (the
    # account was at its monthly cap on 2026-09-16), so nothing extra is sent.
    return {}


def _kwargs(route: Route, target: Target, messages: list[dict], max_tokens: int,
            temperature: float | None, reasoning: dict | None) -> dict:
    kw: dict = {"model": target.model, "messages": messages, route.max_tokens_param: max_tokens}
    if temperature is not None and route.accepts_temperature:
        kw["temperature"] = temperature
    kw.update(_reasoning_kwargs(route, reasoning if reasoning is not None else target.reasoning))
    return kw


@dataclass
class Completion:
    text: str
    finish_reason: str | None
    target: Target
    usage: object = None


async def complete(role: str, messages: list[dict], *, max_tokens: int, label: str = "",
                   client=None, temperature: float | None = None,
                   reasoning: dict | None = None, fallback_on_empty: bool = True) -> Completion:
    """Run one chat completion for `role`, falling back along its target list.

    `client` pins the call to one client with no fallback: tests use it, and
    so does anything that manages its own client. Such a client is assumed to
    be OpenRouter's (`get_client()`), so the role's first OpenRouter target is
    used — for the bullets role that is `openai/gpt-5.6-sol`, not the OpenAI
    direct spelling. `reasoning` overrides the target's default for this call.

    `fallback_on_empty=False` lets an empty reply (EmptyCompletion) propagate
    instead of trying the next target: the checker's first attempt wants to
    retry the *same* model with reasoning off, because a budget eaten by
    hidden reasoning is not the model being down.

    Raises the last error when every target fails, and EmptyCompletion when
    the text is missing, so callers keep their existing handling.
    """
    targets = ROLES[role]
    where = label or role
    if client is not None:
        target = next((t for t in targets if t.route == "openrouter"), targets[0])
        response = await client.chat.completions.create(
            **_kwargs(ROUTES["openrouter"], target, messages, max_tokens, temperature, reasoning))
        return _completion(response, target, where)

    last: Exception | None = None
    tried: list[str] = []
    for target in targets:
        route = ROUTES[target.route]
        api = client_for(route)
        if api is None:
            # Counts as a fallback: a primary whose key is missing in CI would
            # otherwise be served by its backup for weeks without a word.
            tried.append(f"{target.label}: skipped, {route.key_env} not set")
            print(f"    {where}: {tried[-1]}")
            continue
        try:
            response = await api.chat.completions.create(
                **_kwargs(route, target, messages, max_tokens, temperature, reasoning))
            done = _completion(response, target, where)
        except EmptyCompletion as e:
            if not fallback_on_empty:
                raise
            last = e
            tried.append(f"{target.label}: {type(e).__name__}: {str(e)[:160]}")
            print(f"    {where}: {tried[-1]}")
            continue
        except Exception as e:  # noqa: BLE001 — any failure means try the next target
            last = e
            tried.append(f"{target.label}: {type(e).__name__}: {str(e)[:160]}")
            print(f"    {where}: {tried[-1]}")
            continue
        if tried:
            note = f"{where}: served by {target.label} after " + "; ".join(tried)
            fallback_log.append(note)
            print(f"    {note}")
        return done
    if last is None:
        raise RuntimeError(f"{where}: no route for role {role!r} has an API key set "
                           f"({'; '.join(tried)})")
    raise last


def _completion(response, target: Target, where: str) -> Completion:
    text = completion_text(response, where)
    choice = response.choices[0]
    return Completion(text=text, finish_reason=getattr(choice, "finish_reason", None),
                      target=target, usage=getattr(response, "usage", None))
