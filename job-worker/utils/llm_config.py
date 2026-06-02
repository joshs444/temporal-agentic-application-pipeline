"""Central LLM configuration.

The pipeline talks to any OpenAI-compatible chat-completions endpoint. Defaults
target xAI Grok, but you can point it at OpenAI, a local vLLM/Ollama server, or
any compatible gateway purely through environment variables:

    LLM_BASE_URL    base URL of the OpenAI-compatible API (default: xAI)
    LLM_API_KEY     API key (falls back to XAI_API_KEY for backwards compat)
    LLM_MODEL       primary model for generation/matching
    LLM_LIGHT_MODEL cheaper/faster model for high-volume classification + extraction

Keeping this in one place means every activity, route, and client shares the
same configuration and there is exactly one switch to flip when changing
providers.
"""

from __future__ import annotations

import os

from openai import AsyncOpenAI

# LLM_API_KEY is the preferred name; XAI_API_KEY is honored for backwards compat.
LLM_API_KEY: str = os.getenv("LLM_API_KEY") or os.getenv("XAI_API_KEY", "")
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.x.ai/v1")
LLM_MODEL: str = os.getenv("LLM_MODEL", "grok-4-1-fast")
# Lighter/cheaper model for high-volume calls (reply classification, extraction).
LLM_LIGHT_MODEL: str = os.getenv("LLM_LIGHT_MODEL", "grok-3-fast")

# Cost logging (USD per 1M tokens). Override per provider if pricing differs.
LLM_INPUT_COST_PER_1M: float = float(os.getenv("LLM_INPUT_COST_PER_1M", "3.00"))
LLM_OUTPUT_COST_PER_1M: float = float(os.getenv("LLM_OUTPUT_COST_PER_1M", "15.00"))


def get_llm_client() -> AsyncOpenAI:
    """Return an OpenAI-compatible async client configured from the environment.

    Raises:
        ValueError: if no API key is configured (LLM_API_KEY or XAI_API_KEY).
    """
    if not LLM_API_KEY:
        raise ValueError(
            "No LLM API key configured. Set LLM_API_KEY (or XAI_API_KEY)."
        )
    return AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Estimate request cost in USD from token counts using configured pricing."""
    input_cost = (input_tokens / 1_000_000) * LLM_INPUT_COST_PER_1M
    output_cost = (output_tokens / 1_000_000) * LLM_OUTPUT_COST_PER_1M
    return input_cost + output_cost
