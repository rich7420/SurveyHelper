"""Pluggable LLM backend: pricing math + backend selection (pure, no network)."""

import os

from surveyhelper.llm.anthropic_api import _usage_cost


class _Usage:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_cost_plain_input_output():
    total_in, cost = _usage_cost("claude-haiku-4-5",
                                 _Usage(input_tokens=1_000_000, output_tokens=1_000_000))
    assert total_in == 1_000_000
    assert abs(cost - (1.0 + 5.0)) < 1e-9          # haiku: $1 in + $5 out per 1M


def test_cache_read_is_cheap_and_counts_toward_input():
    total_in, cost = _usage_cost("claude-haiku-4-5",
                                 _Usage(input_tokens=0, cache_read_input_tokens=1_000_000,
                                        cache_creation_input_tokens=0, output_tokens=0))
    assert total_in == 1_000_000                   # cached reads still count as input volume
    assert abs(cost - 0.1) < 1e-9                  # but bill at ~0.1x input


def test_cache_write_premium():
    _, cost = _usage_cost("claude-sonnet-4-6",
                          _Usage(input_tokens=0, cache_creation_input_tokens=1_000_000,
                                 output_tokens=0))
    assert abs(cost - (3.0 * 1.25)) < 1e-9         # sonnet write: $3 * 1.25 per 1M


def test_unknown_model_falls_back_to_sonnet_price():
    _, cost = _usage_cost("some-future-model", _Usage(input_tokens=1_000_000, output_tokens=0))
    assert abs(cost - 3.0) < 1e-9


def _reload_backend(monkeypatch, backend, **keys):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in keys.items():
        monkeypatch.setenv(k, v)
    import surveyhelper.config as cfg
    monkeypatch.setattr(cfg, "LLM_BACKEND", backend)
    import importlib
    import surveyhelper.llm as llm
    importlib.reload(llm)
    return llm.BACKEND


def test_auto_prefers_anthropic(monkeypatch):
    assert _reload_backend(monkeypatch, "auto", ANTHROPIC_API_KEY="x") == "anthropic"


def test_auto_falls_to_openai_then_gemini(monkeypatch):
    assert _reload_backend(monkeypatch, "auto", OPENAI_API_KEY="x") == "openai"
    assert _reload_backend(monkeypatch, "auto", GEMINI_API_KEY="x") == "gemini"
    assert _reload_backend(monkeypatch, "auto", GOOGLE_API_KEY="x") == "gemini"


def test_auto_falls_to_cli_without_any_key(monkeypatch):
    assert _reload_backend(monkeypatch, "auto") == "cli"


def test_api_alias_is_anthropic(monkeypatch):
    assert _reload_backend(monkeypatch, "api", ANTHROPIC_API_KEY="x") == "anthropic"
