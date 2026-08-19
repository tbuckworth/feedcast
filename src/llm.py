"""OpenRouter LLM client for Gemini models."""

import os

from openai import AsyncOpenAI

MODEL_STRONG = "google/gemini-3-flash-preview"
MODEL_CHEAP = "google/gemini-3-flash-preview"


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
