"""First-run self-test (`surveyhelper-verify` / `make verify`).

Proves the install works end-to-end on the no-LLM card path: preflight → ensure schema →
survey a known arXiv paper → print the card. Exits 0 on success, 1 with a clear error otherwise.
"""

from __future__ import annotations

import asyncio
import os
import sys

from . import http
from .db import apply_schema, close_pool
from .logging_setup import get

log = get("selftest")

DEFAULT_ARXIV = os.environ.get("SURVEYHELPER_VERIFY_ARXIV", "1706.03762")  # Attention Is All You Need


async def _amain() -> int:
    from .pipeline.card import survey
    from .preflight import run_preflight

    await run_preflight(service="verify")
    await apply_schema()

    print(f"\n→ surveying arXiv:{DEFAULT_ARXIV} (instant card path, no LLM) ...")
    res = await survey(DEFAULT_ARXIV)
    if res.status != "card" or res.card is None:
        print(f"✗ expected a card, got status={res.status} ({res.message or ''})")
        return 1

    c = res.card.model_dump()
    refs = c.get("references")
    n_refs = len(refs) if isinstance(refs, list) else (refs or c.get("reference_count") or 0)
    print(f"  ✓ title:      {c.get('title')}")
    print(f"  ✓ purpose:    {(c.get('purpose') or c.get('tldr') or '—')[:110]}")
    print(f"  ✓ references: {n_refs} tracked")
    print("\n✓ surveyHelper is working.\n")
    return 0


def main() -> None:
    try:
        code = asyncio.run(_amain())
    except SystemExit as exc:                 # preflight raised (e.g. DB down) — message already shown
        print(f"✗ {exc}")
        code = 1
    except Exception as exc:
        log.exception("self-test failed")
        print(f"✗ self-test failed: {exc}")
        code = 1
    finally:
        try:
            asyncio.run(_cleanup())
        except Exception:
            pass
    sys.exit(code)


async def _cleanup() -> None:
    await http.aclose()
    await close_pool()


if __name__ == "__main__":
    main()
