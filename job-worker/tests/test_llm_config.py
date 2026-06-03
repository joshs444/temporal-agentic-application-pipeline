"""Unit tests for the provider-agnostic LLM configuration."""

import pytest

from utils import llm_config


def test_estimate_cost_usd_uses_configured_pricing():
    cost = llm_config.estimate_cost_usd(1_000_000, 1_000_000)
    expected = llm_config.LLM_INPUT_COST_PER_1M + llm_config.LLM_OUTPUT_COST_PER_1M
    assert abs(cost - expected) < 1e-9
    assert llm_config.estimate_cost_usd(0, 0) == 0.0


def test_get_llm_client_requires_a_key(monkeypatch):
    monkeypatch.setattr(llm_config, "LLM_API_KEY", "")
    with pytest.raises(ValueError):
        llm_config.get_llm_client()


def test_get_llm_client_returns_client_when_configured(monkeypatch):
    monkeypatch.setattr(llm_config, "LLM_API_KEY", "test-key")
    client = llm_config.get_llm_client()
    assert client is not None
