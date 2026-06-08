"""Step 0 — resolve an identifier to a canonical paper, merging arXiv + S2.

arXiv is preferred for full-text fields (abstract, pdf, github urls); S2 supplies
tldr, external-id cross-links, and the influential-citation signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from ..logging_setup import get
from ..models import Candidate, PaperMeta, Ref
from ..sources import arxiv, s2

log = get("resolve")


@dataclass
class ResolveResult:
    meta: PaperMeta | None = None
    candidates: list[Candidate] = field(default_factory=list)


def _merge(a: PaperMeta | None, s: PaperMeta | None) -> PaperMeta | None:
    if a is None and s is None:
        return None
    if a is None:
        return s
    if s is None:
        return a
    return PaperMeta(
        title=a.title or s.title,
        authors=a.authors or s.authors,
        year=a.year or s.year,
        venue=a.venue or s.venue,
        abstract=a.abstract or s.abstract,      # arXiv abstract preferred (full text)
        arxiv_id=a.arxiv_id or s.arxiv_id,
        doi=a.doi or s.doi,
        s2_id=s.s2_id or a.s2_id,
        url=a.url or s.url,
        pdf_url=a.pdf_url or s.pdf_url,
        oa_pdf_url=s.oa_pdf_url or a.oa_pdf_url,
        text_coverage=a.text_coverage or ("abstract_only" if s.abstract else None),
        tldr=s.tldr or a.tldr,
        github_urls=a.github_urls or s.github_urls,
        influential_citation_count=s.influential_citation_count,
    )


async def resolve(ref: Ref) -> ResolveResult:
    if ref.kind == "title":
        try:
            return ResolveResult(candidates=await s2.search_title(ref.value))
        except httpx.HTTPError as exc:
            log.warning("S2 title search unavailable (%s)", exc)
            return ResolveResult()

    # S2 enriches (tldr, refs, cross-ids) but must not be load-bearing for arXiv ids:
    # if S2 is throttled/down, an arXiv paper still resolves from arXiv alone (plan §4).
    s2_meta: PaperMeta | None = None
    try:
        s2_meta = await s2.fetch_paper(s2.s2_lookup_id(ref.kind, ref.value))
    except httpx.HTTPError as exc:
        log.warning("S2 unavailable for %s (%s) — degrading to arXiv-only", ref.value, exc)

    arxiv_id = ref.value if ref.kind == "arxiv" else (s2_meta.arxiv_id if s2_meta else None)
    arxiv_meta = await arxiv.fetch_metadata(arxiv_id) if arxiv_id else None

    return ResolveResult(meta=_merge(arxiv_meta, s2_meta))
