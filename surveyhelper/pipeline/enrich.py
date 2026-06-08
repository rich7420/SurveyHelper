"""Background S2 enrichment (the `enrich` job).

The sync card is arXiv-only so it never blocks on S2's throttled shared pool. This
runs in the worker, off the critical path, and patiently fills in what S2 provides:
- upgrades step 1 from abstract-extractive to the S2 `tldr`
- fills step 3 backward references -> citation-graph edges
- back-links the S2 id (and DOI) onto the paper

Idempotent: safe to re-run (DB-as-cache + alias dedup).
"""

from __future__ import annotations

from typing import Any

import httpx

from .. import config
from ..db import analysis, papers
from ..logging_setup import get
from ..models import PaperMeta
from ..sources import s2

log = get("enrich")


def _s2_lookup_for(p) -> str | None:
    if p["arxiv_id"]:
        return f"ARXIV:{p['arxiv_id']}"
    if p["doi"]:
        return f"DOI:{p['doi']}"
    if p["s2_id"]:
        return p["s2_id"]
    return None


async def enrich(paper_id: int, *, references_limit: int = 50) -> dict[str, Any]:
    p = await papers.get(paper_id)
    if p is None:
        return {"enriched": False, "reason": "paper_not_found"}

    lookup = _s2_lookup_for(p)
    if lookup is None:
        return {"enriched": False, "reason": "no_external_id"}

    try:
        s2_meta = await s2.fetch_paper(lookup)   # http layer already retried with backoff
    except httpx.HTTPError as exc:
        log.warning("S2 throttled/unavailable for paper %s (%s) — will retry later", paper_id, exc)
        return {"enriched": False, "reason": "s2_unavailable", "retryable": True}
    if s2_meta is None:
        return {"enriched": False, "reason": "s2_no_result"}

    # back-link S2 id + DOI onto the canonical paper (adds s2 alias)
    await papers.upsert(PaperMeta(
        arxiv_id=p["arxiv_id"], s2_id=s2_meta.s2_id,
        doi=p["doi"] or s2_meta.doi, oa_pdf_url=s2_meta.oa_pdf_url,
    ))

    row = await analysis.get(paper_id, config.PIPELINE_VERSION)
    step_status = dict((row["step_status"] if row else None) or {})
    provenance = dict((row["provenance"] if row else None) or {})
    purpose = row["purpose"] if row else None
    code = (row["code"] if row else None)

    # step 1: upgrade to tldr if S2 has one
    if s2_meta.tldr:
        purpose = s2_meta.tldr
        provenance["step1_source"] = "tldr"
        step_status["1"] = "ok"

    # step 3: references -> graph edges (tolerate a throttle here too)
    refs_failed = False
    refs = []
    if s2_meta.s2_id:
        try:
            refs = await s2.fetch_references(s2_meta.s2_id, references_limit)
        except httpx.HTTPError as exc:
            log.warning("references throttled for paper %s (%s)", paper_id, exc)
            refs_failed = True
    for r in refs:
        stub_id = await papers.upsert_reference_stub(r)
        if stub_id:
            await papers.add_citation(paper_id, stub_id, "reference", r.is_influential)
    step_status["3"] = "ok" if refs else ("failed" if refs_failed else "partial")

    # Persist whatever we got (tldr upgrade is saved even if refs still pending).
    await analysis.save(
        paper_id, config.PIPELINE_VERSION,
        step_status=step_status, purpose=purpose, code=code,
        provenance=provenance, model_used=(row["model_used"] if row else None),
    )
    log.info("enriched paper %s: tldr=%s refs=%d (refs_failed=%s)",
             paper_id, bool(s2_meta.tldr), len(refs), refs_failed)
    # If references couldn't be fetched, ask for a later retry to complete the graph.
    return {"enriched": True, "tldr": bool(s2_meta.tldr), "references": len(refs),
            "title": p["title"], "retryable": refs_failed,
            "reason": "refs_throttled" if refs_failed else None}
