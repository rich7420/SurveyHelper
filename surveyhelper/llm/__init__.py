"""Pluggable LLM access (Phase 2).

`complete()` resolves to one backend at import time, chosen by SURVEYHELPER_LLM_BACKEND:
  - "anthropic" (alias "api") → anthropic_api (Anthropic SDK + ANTHROPIC_API_KEY) — default
  - "openai"               → openai_api (OpenAI SDK + OPENAI_API_KEY)
  - "gemini"               → gemini_api (google-genai + GEMINI_API_KEY / GOOGLE_API_KEY)
  - "cli"                  → claude_cli (an OpenClaw container's `claude -p` subscription)
  - "auto"                 → first provider whose key is set (anthropic → openai → gemini), else cli
Every backend exposes the same signature and returns a `Completion`.
"""

from __future__ import annotations

import os

from .. import config
from .base import Completion, LLMError


def _resolve() -> str:
    backend = config.LLM_BACKEND
    if backend == "api":
        return "anthropic"
    if backend != "auto":
        return backend
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    return "cli"


BACKEND = _resolve()

if BACKEND == "anthropic":
    from .anthropic_api import complete
elif BACKEND == "openai":
    from .openai_api import complete
elif BACKEND == "gemini":
    from .gemini_api import complete
else:
    from .claude_cli import complete

__all__ = ["complete", "Completion", "LLMError", "BACKEND"]
