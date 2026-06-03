"""Persist LLM-call telemetry to the ``llm_logs`` table.

Single source of truth for recording model usage (tokens, latency, cost). Cost is
computed via :func:`utils.llm_config.estimate_cost_usd` so every call site agrees.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from .database import execute
from .llm_config import estimate_cost_usd

log = logging.getLogger(__name__)


async def log_llm_call(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: Optional[int] = None,
    context_type: Optional[str] = None,
    context_id: Optional[str] = None,
) -> None:
    """Record one LLM call. Never raises — logging failures are swallowed."""
    cost_cents = round(estimate_cost_usd(prompt_tokens, completion_tokens) * 100, 4)
    try:
        await execute(
            """
            INSERT INTO llm_logs (
                model, prompt_tokens, completion_tokens, total_tokens,
                cost_cents, latency_ms, context_type, context_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            model,
            prompt_tokens,
            completion_tokens,
            prompt_tokens + completion_tokens,
            cost_cents,
            latency_ms,
            context_type,
            uuid.UUID(context_id) if context_id else None,
        )
    except Exception as exc:  # pragma: no cover - telemetry must not break callers
        log.warning("Failed to log LLM call: %s", exc)
