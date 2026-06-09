"""Background enrichment (the `enrich` job).

The sync card is arXiv-only so it never blocks on S2's throttled shared pool. This
runs in the worker, off the critical path, and fills in:
- step 1: upgrade abstract-extractive -> S2 `tldr` (when S2 is reachable)
- step 3: backward references -> citation-graph edges, via S2 first, then a
  keyless **arXiv-HTML fallback** so the graph survives S2 being down (the #1
  structural risk: a hard single dependency on S2).

Idempotent. If S2 is throttled and we still lack the tldr, defer (retryable) so a
later pass completes it.
"""

from __future__ import annotations

from typing import Any

import httpx

from .. import config
from ..db import analysis, papers
from ..logging_setup import get
from ..models import PaperMeta, Reference
from ..sources import arxiv, s2

log = get("enrich")


def _s2_lookup_for(p) -> str | None:
    if p["arxiv_id"]:
        return f"ARXIV:{p['arxiv_id']}"
    if p["doi"]:
        return f"DOI:{p['doi']}"
    if p["s2_id"]:
        return p["s2_id"]
    return None


async def _add_refs(paper_id: int, refs: list[Reference]) -> int:
    n = 0
    for r in refs:
        stub_id = await papers.upsert_reference_stub(r)
        if stub_id:
            await papers.add_citation(paper_id, stub_id, "reference", r.is_influential)
            n += 1
    return n


async def enrich(paper_id: int, *, references_limit: int = 50) -> dict[str, Any]:
    p = await papers.get(paper_id)
    if p is None:
        return {"enriched": False, "reason": "paper_not_found"}

    # ── S2 paper (tldr + s2 id) — best effort, never fatal ──────────────────
    s2_meta: PaperMeta | None = None
    s2_paper_failed = False
    lookup = _s2_lookup_for(p)
    if lookup:
        try:
            s2_meta = await s2.fetch_paper(lookup)
        except httpx.HTTPError as exc:
            log.warning("S2 paper throttled for %s (%s)", paper_id, exc)
            s2_paper_failed = True

    if s2_meta:
        await papers.upsert(PaperMeta(
            arxiv_id=p["arxiv_id"], s2_id=s2_meta.s2_id,
            doi=p["doi"] or s2_meta.doi, oa_pdf_url=s2_meta.oa_pdf_url,
        ))

    row = await analysis.get(paper_id, config.PIPELINE_VERSION)
    step_status = dict((row["step_status"] if row else None) or {})
    provenance = dict((row["provenance"] if row else None) or {})
    purpose = row["purpose"] if row else None
    code = (row["code"] if row else None)

    got_tldr = bool(s2_meta and s2_meta.tldr)
    if got_tldr:
        purpose = s2_meta.tldr
        provenance["step1_source"] = "tldr"
        step_status["1"] = "ok"

    # ── references: S2 first, then keyless arXiv-HTML fallback ──────────────
    refs_count = 0
    refs_source = None
    s2_id = (s2_meta.s2_id if s2_meta else None) or p["s2_id"]
    if s2_id:
        try:
            refs = await s2.fetch_references(s2_id, references_limit)
            refs_count = await _add_refs(paper_id, refs)
            if refs_count:
                refs_source = "s2"
        except httpx.HTTPError as exc:
            log.warning("S2 references throttled for %s (%s)", paper_id, exc)

    if refs_count == 0 and p["arxiv_id"]:
        html_ids = await arxiv.fetch_html_references(p["arxiv_id"])
        if html_ids:
            refs_count = await _add_refs(
                paper_id, [Reference(arxiv_id=a) for a in html_ids[:references_limit]])
            refs_source = "arxiv_html"   # degraded: arXiv-only refs, no influence flags

    if refs_count:
        step_status["3"] = "ok"
        provenance["refs_source"] = refs_source
    else:
        step_status["3"] = step_status.get("3", "partial")

    await analysis.save(
        paper_id, config.PIPELINE_VERSION,
        step_status=step_status, purpose=purpose, code=code,
        provenance=provenance, model_used=(row["model_used"] if row else None),
    )
    # Embed for semantic similarity / proactivity (Phase 6b), best-effort.
    try:
        from ..db import embeddings as emb_db
        from ..embeddings import embed_one
        blurb = f"{p['title'] or ''}. {purpose or p['abstract'] or ''}".strip(". ")
        if blurb:
            await emb_db.store_paper(paper_id, await embed_one(blurb[:1000]))
    except Exception as exc:
        log.warning("embed failed for paper %s (%s)", paper_id, exc)

    log.info("enriched paper %s: tldr=%s refs=%d (src=%s)",
             paper_id, got_tldr, refs_count, refs_source)

    # Retry later only if S2 was the blocker and we still lack the tldr.
    retryable = s2_paper_failed and not got_tldr
    return {
        "enriched": got_tldr or refs_count > 0,
        "tldr": got_tldr, "references": refs_count, "refs_source": refs_source,
        "title": p["title"], "retryable": retryable,
        "reason": "s2_unavailable" if retryable else None,
    }
