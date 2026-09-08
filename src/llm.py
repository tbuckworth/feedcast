"""OpenRouter LLM client for Gemini models."""

import os

from openai import AsyncOpenAI

# Two roles, deliberately not one model.
#
# MODEL_WRITER produces prose a person listens to — summaries, the daily
# briefing, table descriptions. Measured against Gemini 3 Flash on a real maths
# post, Flash emitted 14 raw LaTeX expressions into the spoken script ("denoted
# as $D$"), which the TTS reads aloud as "dollar sign D dollar sign"; Opus 4.6
# emitted none. See data/model_comparison.json.
MODEL_WRITER = "anthropic/claude-opus-4.6"

# MODEL_NORMALIZER only transforms: "45%" -> "forty-five percent". It writes
# nothing. It is also the single largest consumer of tokens in the pipeline —
# ~47%, because it is the only call that takes the whole episode in AND emits
# the whole episode back out.
#
# A stronger model is not better here, and is arguably worse: the instruction
# is "preserve ALL other text exactly as-is", and a reasoning model handed a
# whole episode has more capacity to decide something could be phrased better.
# Gemini 3 Flash did this job for 168 episodes without incident.
MODEL_NORMALIZER = "google/gemini-3-flash-preview"

# MODEL_CHECKER reads a finished script against its source and lists what is
# contradicted, distorted or unsupported (src/verify.py). Verification is a
# narrower task than writing, so a mid-tier model does it well at a fraction
# of the price; a different model from the writer also means its blind
# spots are not the same ones.
MODEL_CHECKER = "anthropic/claude-sonnet-5"

# Back-compat aliases; prefer the role names above.
MODEL_STRONG = MODEL_WRITER
MODEL_CHEAP = MODEL_WRITER


# The SDK default is 600s x 2 retries, so one wedged request can stall a run
# for ~30 min. Flash calls finish in well under a minute; bound them.
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "180"))


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


def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=3,
    )
