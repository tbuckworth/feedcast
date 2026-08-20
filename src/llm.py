"""OpenRouter LLM client for Gemini models."""

import os

from openai import AsyncOpenAI

# Opus 4.6 writes everything Titus actually hears. Measured against Gemini 3
# Flash on a real maths post, Flash emitted 14 raw LaTeX expressions into the
# spoken script ("denoted as $D$"), which the TTS reads out as "dollar sign D
# dollar sign"; Opus 4.6 emitted none. See data/model_comparison.json.
MODEL_STRONG = "anthropic/claude-opus-4.6"
MODEL_CHEAP = "anthropic/claude-opus-4.6"


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
