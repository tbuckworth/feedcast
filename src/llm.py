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

# Back-compat aliases; prefer the role names above.
MODEL_STRONG = MODEL_WRITER
MODEL_CHEAP = MODEL_WRITER


# The SDK default is 600s x 2 retries, so one wedged request can stall a run
# for ~30 min. Flash calls finish in well under a minute; bound them.
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "180"))


def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=3,
    )
