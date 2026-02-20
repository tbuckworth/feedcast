"""OpenRouter LLM client for Gemini models."""

import os

from openai import AsyncOpenAI

MODEL_STRONG = "google/gemini-3-flash-preview"
MODEL_CHEAP = "google/gemini-2.5-flash"


def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
    )
