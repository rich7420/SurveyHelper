"""The instant card — pipeline steps 0/1/3/7, no LLM (plan §5).

Step 0: resolve id (resolve.py).
Step 1: purpose/pain-point via the no-LLM ladder (DECISIONS.md #1):
        S2 tldr -> first 1-2 sentences of abstract -> none.
Step 3: backward references (capped), persisted as graph edges.
Step 7: code — GitHub URL in abstract -> verify repo.

Deep LLM steps (1-refine/2/4/5/6) are enqueued as a separate `analyze` job (Phase 2).
"""

from __future__ import annotations

import re

from .. import config
from ..db import analysis, jobs, papers
from ..logging_setup import get
from ..models import Card, CodeInfo, Reference, SurveyResult
from ..sources import github, s2
from ..sources.identifiers import parse_identifier
from .resolve import resolve

log = get("card")

_DEFAULT_REF_LIMIT = 50


def _alias_for(kind: str, value: str) -> str | None:
    if kind == "arxiv":
        return f"arxiv:{value}"
    if kind == "doi":
        return f"doi:{value.lower()}"
    if kind == "s2":
        return f"s2:{value}"
    return None


def _step1_ladder(tldr: str | None, abstract: str | None) -> tuple[str | None, str]:
    """No-LLM step 1: tldr -> abstract first 1-2 sentences -> none."""
    if tldr:
        return tldr.strip(), "tldr"
    if abstract:
        sentences = re.split(r"(?<=[.!?])\s+", abstract.strip())
        snippet = " ".join(sentences[:2]).strip()
        if snippet:
            return snippet, "abstract_extractive"
    return None, "none"


def _status_for_step1(source: str) -> str:
    return {"tldr": "ok", "abstract_extractive": "partial", "none": "skipped"}[source]


async def survey(identifier: str, *, references_limit: int = _DEFAULT_REF_LIMIT,
                 enqueue_deep: bool = True) -> SurveyResult:
    """Build (or return cached) instant card for a paper identifier."""
    ref = parse_identifier(identifier)

    # DB-as-cache fast path for concrete ids (no network if we already have the card).
    alias = _alias_for(ref.kind, ref.value)
    if alias:
        cached = await papers.find_by_alias(alias)
        if cached:
            row = await analysis.get(cached["id"], config.PIPELINE_VERSION)
            if row:
                card = await _assemble(cached["id"], cached=True)
                return SurveyResult(status="card", card=card)

    # Step 0 — resolve.
    res = await resolve(ref)
    if res.candidates:
        return SurveyResult(status="candidates", candidates=res.candidates,
                            message="Ambiguous title — pick one to survey.")
    if res.meta is None:
        return SurveyResult(status="not_found",
                            message=f"Could not resolve '{identifier}'.")

    meta = res.meta
    paper_id = await papers.upsert(meta, min_depth=0)

    # Step 1 — purpose/pain point (no LLM ladder).
    summary, step1_source = _step1_ladder(meta.tldr, meta.abstract)

    # Step 3 — backward references -> graph edges.
    refs: list[Reference] = []
    if meta.s2_id:
        refs = await s2.fetch_references(meta.s2_id, references_limit)
        for r in refs:
            stub_id = await papers.upsert_reference_stub(r)
            if stub_id:
                await papers.add_citation(paper_id, stub_id, "reference", r.is_influential)

    # Step 7 — code.
    code = await github.find_code(meta.github_urls) if meta.github_urls else CodeInfo(found=False)

    step_status = {
        "0": "ok",
        "1": _status_for_step1(step1_source),
        "3": "ok" if refs else "partial",
        "7": "ok" if code.found else "skipped",
    }
    await analysis.save(
        paper_id, config.PIPELINE_VERSION,
        step_status=step_status, purpose=summary,
        code=code.model_dump(), provenance={"step1_source": step1_source},
        model_used=None,
    )

    deep_status = "not_requested"
    if enqueue_deep:
        await jobs.enqueue("analyze", root_paper_id=paper_id, requested_depth=0,
                           triggered_by=f"survey:{identifier}")
        deep_status = "queued"

    card = await _assemble(paper_id, cached=False, deep_status=deep_status)
    return SurveyResult(status="card", card=card)


async def _assemble(paper_id: int, *, cached: bool,
                    deep_status: str = "not_requested") -> Card:
    """Build a Card purely from DB rows (shared by cached + fresh paths)."""
    p = await papers.get(paper_id)
    a = await analysis.get(paper_id, config.PIPELINE_VERSION)
    ref_rows = await papers.references_of(paper_id)

    provenance = (a["provenance"] if a else None) or {}
    code_data = (a["code"] if a else None) or {}
    references = [
        Reference(title=r["title"], year=r["year"], arxiv_id=r["arxiv_id"],
                  doi=r["doi"], s2_id=r["s2_id"], is_influential=r["is_influential"])
        for r in ref_rows
    ]
    return Card(
        paper_id=paper_id,
        title=p["title"], authors=p["authors"] or [], year=p["year"], venue=p["venue"],
        arxiv_id=p["arxiv_id"], doi=p["doi"], s2_id=p["s2_id"],
        url=p["url"], pdf_url=p["pdf_url"],
        summary=a["purpose"] if a else None,
        step1_source=provenance.get("step1_source", "none"),
        references=references, references_count=len(references),
        code=CodeInfo(**code_data) if code_data else CodeInfo(found=False),
        step_status=(a["step_status"] if a else {}) or {},
        cached=cached,
        deep_analysis_status=deep_status,
    )
