"""OpenAI completion adapter — a non-Claude backend (set OPENAI_API_KEY).

One chat-completion per call via the official async SDK. No tools (the worker only wants a
completion over untrusted paper text — the system message pins it as data). The pipeline's
per-call Claude model is mapped to OpenAI's summary/main tier. OpenAI caches long prompt
prefixes automatically, so a repeated `cache_context` block is billed cheaper on reuse.
"""

from __future__ import annotations

from .. import config
from ..logging_setup import get
from .base import Completion, LLMError

log = get("llm.openai")

# (input, output) USD per 1M tokens — approximate; override the model via env if tiers change.
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.5, 10.0), "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.0, 8.0), "gpt-4.1-mini": (0.40, 1.60),
    "gpt-5": (1.25, 10.0), "gpt-5-mini": (0.25, 2.0),
}
_DEFAULT_PRICE = (2.5, 10.0)
_CACHED_DISCOUNT = 0.5   # cached prompt tokens bill at ~0.5x input

_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMError("openai SDK not installed — `uv sync` (or pip install openai)") from exc
        _client = AsyncOpenAI()   # reads OPENAI_API_KEY from the environment
    return _client


def _model(requested: str | None) -> str:
    """Map the pipeline's Claude model to an OpenAI tier (haiku/None → summary, else main)."""
    summary = (not requested) or ("haiku" in requested)
    return config.OPENAI_SUMMARY_MODEL if summary else config.OPENAI_MODEL


def _cost(model: str, u) -> tuple[int, int, float]:
    pin, pout = _PRICES.get(model, _DEFAULT_PRICE)
    prompt = int(getattr(u, "prompt_tokens", 0) or 0)
    completion = int(getattr(u, "completion_tokens", 0) or 0)
    details = getattr(u, "prompt_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0) if details is not None else 0
    uncached = max(prompt - cached, 0)
    cost = (uncached * pin + cached * pin * _CACHED_DISCOUNT + completion * pout) / 1_000_000
    return prompt, completion, cost


async def complete(prompt: str, *, model: str | None = None, system: str | None = None,
                   timeout: float = 180.0, cache_context: str | None = None) -> Completion:
    client = _get_client()
    resolved = _model(model)
    user = f"{cache_context}\n\n{prompt}" if cache_context else prompt   # prefix auto-caches
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    try:
        resp = await client.with_options(timeout=timeout, max_retries=3).chat.completions.create(
            model=resolved, messages=messages, max_tokens=config.LLM_MAX_TOKENS)
    except Exception as exc:
        raise LLMError(f"openai api: {exc}") from exc

    text = resp.choices[0].message.content or ""
    pin, pout, cost = _cost(resolved, resp.usage)
    return Completion(text=text, input_tokens=pin, output_tokens=pout, cost_usd=cost, model=resolved)
