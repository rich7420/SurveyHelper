"""Boot-time preflight: make first-run failures legible.

Logs the resolved config, warns loudly if the selected LLM backend has no key, and FAILS
FAST with a one-line fix if the database is unreachable — instead of a cryptic error on the
first background job.
"""

from __future__ import annotations

import os
import re

from . import config
from .db import get_pool
from .llm import BACKEND
from .logging_setup import get

log = get("preflight")

_KEYS_FOR = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def _safe_dsn() -> str:
    return re.sub(r"://([^:/]+):[^@]+@", r"://\1:***@", config.DSN)


def llm_key_problem() -> str | None:
    """Return a human fix-it string if the selected backend has no usable key, else None."""
    keys = _KEYS_FOR.get(BACKEND)
    if keys and not any(os.environ.get(k) for k in keys):
        return (f"LLM backend '{BACKEND}' is selected but none of {'/'.join(keys)} is set — "
                f"deep analysis/synthesis will fail. Set the key, or SURVEYHELPER_LLM_BACKEND=cli.")
    return None


async def run_preflight(*, service: str) -> None:
    log.info("surveyHelper %s | llm=%s flagship=%s summary=%s analyze=%s verify=%s",
             service, BACKEND, config.LLM_MODEL, config.LLM_SUMMARY_MODEL,
             config.ANALYZE_MODEL, config.VERIFY_MODEL)

    problem = llm_key_problem()
    if problem:
        log.error("%s", problem)            # loud, but non-fatal: the no-LLM card path still works
    elif BACKEND == "cli":
        log.info("LLM backend 'cli' → `claude -p` in container '%s' (no API key)", config.LLM_CONTAINER)

    try:
        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        log.info("database reachable: %s", _safe_dsn())
    except Exception as exc:                 # fatal — nothing works without the DB
        log.error("DATABASE UNREACHABLE (%s): %s", _safe_dsn(), exc)
        raise SystemExit("surveyHelper cannot start: database unreachable. Check SURVEYHELPER_DSN, "
                         "or run `docker compose up -d db`.") from exc
