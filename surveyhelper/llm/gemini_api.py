"""Google Gemini completion adapter — a non-Claude backend (set GEMINI_API_KEY / GOOGLE_API_KEY).

One generate_content call via the official async google-genai SDK. The paper text is untrusted —
the system instruction pins it as data; no tools. The pipeline's per-call Claude model is mapped
to Gemini's flash/pro tier.
"""

from __future__ import annotations

from .. import config
from ..logging_setup import get
from .base import Completion, LLMError

log = get("llm.gemini")

# (input, output) USD per 1M tokens — approximate; override the model via env if tiers change.
_PRICES: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash": (0.30, 2.50), "gemini-3.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.30, 2.50), "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.0-flash": (0.10, 0.40),
}
_DEFAULT_PRICE = (0.30, 2.50)
_CACHED_DISCOUNT = 0.25   # cached context tokens bill at ~0.25x input

_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise LLMError("google-genai SDK not installed — `uv sync` (or pip install "
                           "google-genai)") from exc
        _client = genai.Client()   # reads GEMINI_API_KEY / GOOGLE_API_KEY from the environment
    return _client


def _model(requested: str | None) -> str:
    """Map the pipeline's Claude model to a Gemini tier (haiku/None → flash, else pro)."""
    flash = (not requested) or ("haiku" in requested)
    return config.GEMINI_SUMMARY_MODEL if flash else config.GEMINI_MODEL


def _cost(model: str, um) -> tuple[int, int, float]:
    pin, pout = _PRICES.get(model, _DEFAULT_PRICE)
    prompt = int(getattr(um, "prompt_token_count", 0) or 0)
    out = int(getattr(um, "candidates_token_count", 0) or 0)
    cached = int(getattr(um, "cached_content_token_count", 0) or 0)
    uncached = max(prompt - cached, 0)
    cost = (uncached * pin + cached * pin * _CACHED_DISCOUNT + out * pout) / 1_000_000
    return prompt, out, cost


async def complete(prompt: str, *, model: str | None = None, system: str | None = None,
                   timeout: float = 180.0, cache_context: str | None = None) -> Completion:
    from google.genai import types

    client = _get_client()
    resolved = _model(model)
    contents = f"{cache_context}\n\n{prompt}" if cache_context else prompt
    cfg = types.GenerateContentConfig(max_output_tokens=config.LLM_MAX_TOKENS,
                                      system_instruction=system or None)
    try:
        resp = await client.aio.models.generate_content(model=resolved, contents=contents, config=cfg)
    except Exception as exc:
        raise LLMError(f"gemini api: {exc}") from exc

    text = resp.text or ""
    pin, pout, cost = _cost(resolved, resp.usage_metadata)
    return Completion(text=text, input_tokens=pin, output_tokens=pout, cost_usd=cost, model=resolved)
