"""Pluggable LLM access (Phase 2).

`complete()` resolves to one backend at import time, chosen by SURVEYHELPER_LLM_BACKEND:
  - "api"  → anthropic_api (official SDK + ANTHROPIC_API_KEY) — portable default
  - "cli"  → claude_cli (an OpenClaw container's `claude -p` subscription) — no key needed
  - "auto" → api if ANTHROPIC_API_KEY is set, else cli
Both expose the same signature and return a `Completion`.
"""

from __future__ import annotations

import os

from .. import config
from .base import Completion, LLMError


def _resolve() -> str:
    backend = config.LLM_BACKEND
    if backend == "auto":
        return "api" if os.environ.get("ANTHROPIC_API_KEY") else "cli"
    return backend


BACKEND = _resolve()

if BACKEND == "api":
    from .anthropic_api import complete
else:
    from .claude_cli import complete

__all__ = ["complete", "Completion", "LLMError", "BACKEND"]
