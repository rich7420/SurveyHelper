"""Phase 4 — `expand`: depth-bounded BFS over the citation graph.

Pop a paper from the job's frontier, make sure it has a card + references, push its
top-K most-influential references onto the next depth, repeat. No LLM, no key — pure
citation traversal. Bounded by `max_depth` and `MAX_PAPERS_PER_JOB`, deduped via the
DB, and resumable: the frontier lives in `job_papers`, so a crash continues mid-graph.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from .. import config
from ..db import analysis, jobs, notifications, papers, personal
from ..logging_setup import get
from .card import survey
from .enrich import enrich

log = get("expand")

MAX_PAPERS_PER_JOB = 50      # budget cap (plan §5)
MAX_REFS_PER_PAPER = 15      # top-K by influence (plan §5)


async def _ensure_analyzed(paper_id: int) -> None:
    """Make sure a frontier paper has a card + references (idempotent, cache-first)."""
    p = await papers.get(paper_id)
    if p is None:
        return
    ident = p["arxiv_id"] or p["doi"] or p["s2_id"]
    if not ident:
        return   # non-paper / unresolvable reference — skip (plan §17)

    if await analysis.get(paper_id, config.PIPELINE_VERSION) is None:
        await survey(ident, enqueue_enrich=False, enqueue_deep=False)
    # ensure references exist so we can push neighbors
    if not await papers.references_of(paper_id):
        await enrich(paper_id)


async def run_expand(job: asyncpg.Record) -> dict[str, Any]:
    job_id = job["id"]
    root = job["root_paper_id"]
    max_depth = job["requested_depth"] or 2

    await jobs.add_frontier(job_id, root, 0, "full")   # seed (no-op if resuming)
    dismissed = await personal.dismissed_ids()          # personal dedup (plan §7)

    processed = 0
    while processed < MAX_PAPERS_PER_JOB:
        fp = await jobs.claim_frontier(job_id)
        if fp is None:
            break
        pid, depth = fp["paper_id"], fp["depth"]
        try:
            await _ensure_analyzed(pid)
            processed += 1
            if depth < max_depth:
                refs = await papers.references_of(pid)   # influential-first
                for r in refs[:MAX_REFS_PER_PAPER]:
                    if r["id"] in dismissed:             # don't resurface dismissed papers
                        continue
                    await jobs.add_frontier(job_id, r["id"], depth + 1, "full")
            await jobs.set_frontier_status(job_id, pid, "done")
        except Exception as exc:   # dead-letter one node, keep expanding (plan §17)
            log.warning("expand: paper %s failed (%s)", pid, exc)
            await jobs.set_frontier_status(job_id, pid, "failed")

    capped = processed >= MAX_PAPERS_PER_JOB
    edges = await papers.count_references(root)
    log.info("expand root=%s done: %d papers (depth %d)%s",
             root, processed, max_depth, " [capped]" if capped else "")
    await notifications.add(
        "expand_done",
        {"root_paper_id": root, "papers_analyzed": processed,
         "max_depth": max_depth, "capped": capped, "root_references": edges},
        job_id=job_id, digest_key=f"expand:{root}",
    )
    return {"papers_analyzed": processed, "capped": capped}
