"""Semantic Scholar Graph API client.

Provides tldr, abstract, external ids, and references with isInfluential
(plan.md §2/§3). Metadata only — never full text. Paced + keyed if a key is set.
"""

from __future__ import annotations

from typing import Optional

from .. import config, http
from ..models import Candidate, PaperMeta, Reference

_BASE = "https://api.semanticscholar.org/graph/v1"
_PAPER_FIELDS = (
    "paperId,title,abstract,year,venue,authors,externalIds,"
    "tldr,openAccessPdf,influentialCitationCount"
)
_REF_FIELDS = "isInfluential,citedPaper.paperId,citedPaper.title,citedPaper.year,citedPaper.externalIds"


def _headers() -> dict[str, str]:
    return {"x-api-key": config.SEMANTIC_SCHOLAR_API_KEY} if config.SEMANTIC_SCHOLAR_API_KEY else {}


def s2_lookup_id(kind: str, value: str) -> str:
    if kind == "arxiv":
        return f"ARXIV:{value}"
    if kind == "doi":
        return f"DOI:{value}"
    return value  # s2 id


async def fetch_paper(lookup_id: str) -> Optional[PaperMeta]:
    resp = await http.request("s2", "GET", f"{_BASE}/paper/{lookup_id}",
                              params={"fields": _PAPER_FIELDS}, headers=_headers())
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    d = resp.json()
    ext = d.get("externalIds") or {}
    return PaperMeta(
        s2_id=d.get("paperId"),
        title=d.get("title"),
        abstract=d.get("abstract"),
        year=d.get("year"),
        venue=d.get("venue"),
        authors=[a.get("name") for a in d.get("authors") or [] if a.get("name")],
        arxiv_id=ext.get("ArXiv"),
        doi=ext.get("DOI"),
        tldr=(d.get("tldr") or {}).get("text"),
        oa_pdf_url=(d.get("openAccessPdf") or {}).get("url"),
        influential_citation_count=d.get("influentialCitationCount"),
    )


async def search_title(query: str, limit: int = 5) -> list[Candidate]:
    """Fuzzy title search -> candidate papers for one-line disambiguation (plan §12)."""
    resp = await http.request(
        "s2", "GET", f"{_BASE}/paper/search",
        params={"query": query, "limit": str(limit),
                "fields": "paperId,title,year,authors,externalIds,venue"},
        headers=_headers(),
    )
    if resp.status_code != 200:
        return []
    out: list[Candidate] = []
    for d in resp.json().get("data") or []:
        ext = d.get("externalIds") or {}
        out.append(Candidate(
            s2_id=d.get("paperId"), title=d.get("title"), year=d.get("year"),
            venue=d.get("venue"),
            authors=[a.get("name") for a in d.get("authors") or [] if a.get("name")],
            arxiv_id=ext.get("ArXiv"), doi=ext.get("DOI"),
        ))
    return out


async def fetch_references(lookup_id: str, limit: int = 50) -> list[Reference]:
    """Backward references (intellectual lineage). Capped to `limit`."""
    resp = await http.request(
        "s2", "GET", f"{_BASE}/paper/{lookup_id}/references",
        params={"fields": _REF_FIELDS, "limit": str(limit)}, headers=_headers(),
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    out: list[Reference] = []
    for item in resp.json().get("data") or []:
        cited = item.get("citedPaper") or {}
        if not cited.get("paperId"):
            continue  # skip non-paper / unresolved references (plan §17)
        ext = cited.get("externalIds") or {}
        out.append(Reference(
            s2_id=cited.get("paperId"), title=cited.get("title"), year=cited.get("year"),
            arxiv_id=ext.get("ArXiv"), doi=ext.get("DOI"),
            is_influential=bool(item.get("isInfluential")),
        ))
    return out
