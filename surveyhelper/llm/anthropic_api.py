"""Anthropic API completion adapter — the portable backend (just needs ANTHROPIC_API_KEY).

A single `POST /v1/messages` per call via the official async SDK. No tools (the worker only
wants a completion over untrusted paper text — the system prompt pins it as data). Thinking is
left off: these are high-volume, grounded extraction/verification calls, not open-ended reasoning.

Prompt caching: a caller may pass `cache_context` — a large block repeated across several calls
(e.g. one paper's full text reused by analyze's 4 extraction steps + the faithfulness check). It
is sent as a cached prefix, so every call after the first reads it at ~0.1x input cost instead of
re-paying for the whole paper. Cost is computed from reported usage incl. cache read/write tiers.
"""

from __future__ import annotations

from .. import config
from ..logging_setup import get
from .base import Completion, LLMError

log = get("llm.api")

# USD per 1M tokens (input, output). Cache reads bill ~0.1x input, cache writes ~1.25x input.
_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0), "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0), "claude-opus-4-5": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0), "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_DEFAULT_PRICE = (3.0, 15.0)   # unknown model → assume sonnet-tier

_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMError("anthropic SDK not installed — `uv sync` or set "
                           "SURVEYHELPER_LLM_BACKEND=cli") from exc
        _client = AsyncAnthropic()   # reads ANTHROPIC_API_KEY from the environment
    return _client


def _usage_cost(model: str, u) -> tuple[int, float]:
    """Return (total_input_tokens, cost_usd) from a usage object, accounting for cache tiers."""
    pin, pout = _PRICES.get(model, _DEFAULT_PRICE)
    inp = int(getattr(u, "input_tokens", 0) or 0)
    read = int(getattr(u, "cache_read_input_tokens", 0) or 0)
    write = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    out = int(getattr(u, "output_tokens", 0) or 0)
    cost = (inp * pin + write * pin * 1.25 + read * pin * 0.1 + out * pout) / 1_000_000
    return inp + read + write, cost


async def complete(prompt: str, *, model: str | None = None, system: str | None = None,
                   timeout: float = 180.0, cache_context: str | None = None) -> Completion:
    model = model or config.LLM_SUMMARY_MODEL
    client = _get_client()

    if cache_context:
        content = [
            {"type": "text", "text": cache_context, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": prompt},
        ]
    else:
        content = prompt

    kwargs: dict = {"model": model, "max_tokens": config.LLM_MAX_TOKENS,
                    "messages": [{"role": "user", "content": content}]}
    if system:
        kwargs["system"] = system

    try:
        msg = await client.with_options(timeout=timeout, max_retries=3).messages.create(**kwargs)
    except Exception as exc:   # surface every SDK/HTTP error as our own type
        raise LLMError(f"anthropic api: {exc}") from exc

    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    total_in, cost = _usage_cost(model, msg.usage)
    return Completion(text=text, input_tokens=total_in,
                      output_tokens=int(getattr(msg.usage, "output_tokens", 0) or 0),
                      cost_usd=cost, model=model)
