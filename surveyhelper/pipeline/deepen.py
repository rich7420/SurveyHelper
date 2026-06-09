"""Deepen-on-mention (roadmap Theme A2).

A low-priority background job triggered when an in-graph paper is discussed: if it's
shallow, deep-analyze it; if its neighborhood is thin, do a small expand. So talking
about a paper quietly makes the system know it better for next time. Budget-gated by
analyze/expand themselves.
"""

from __future__ import annotations

from typing import Any

from .. import config
from ..db import analysis, papers
from ..logging_setup import get

log = get("deepen")


async def deepen(paper_id: int, *, job_id: int | None = None) -> dict[str, Any]:
    p = await papers.get(paper_id)
    if p is None:
        return {"deepened": False, "reason": "paper_not_found"}

    a = await analysis.get(paper_id, config.PIPELINE_VERSION)
    step_status = (a["step_status"] if a else None) or {}
    did = []

    # 1) deep-analyze if we only have the cheap card
    if step_status.get("2") != "ok":
        from .analyze import analyze
        res = await analyze(paper_id, job_id=job_id)
        if res.get("analyzed"):
            did.append("analyze")
        elif res.get("reason") == "daily_budget_reached":
            return {"deepened": False, "reason": "daily_budget_reached"}

    # 2) thin neighborhood -> a small expand to depth 1
    if await papers.count_references(paper_id) < 5:
        from . import expand as ex
        prev = ex.MAX_PAPERS_PER_JOB
        ex.MAX_PAPERS_PER_JOB = 8                      # keep ambient deepens small
        try:
            await ex.run_expand({"id": job_id, "root_paper_id": paper_id, "requested_depth": 1})
            did.append("expand")
        finally:
            ex.MAX_PAPERS_PER_JOB = prev

    log.info("deepened paper %s: %s", paper_id, did or "nothing-needed")
    return {"deepened": bool(did), "did": did}
