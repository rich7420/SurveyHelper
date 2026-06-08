"""Typed domain models — every cross-module boundary speaks these, not raw dicts."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

RefKind = Literal["arxiv", "doi", "s2", "title"]
StepStatus = Literal["ok", "partial", "failed", "skipped"]
Step1Source = Literal["tldr", "abstract_extractive", "none"]


class Ref(BaseModel):
    """A parsed identifier."""
    kind: RefKind
    value: str
    raw: str


class PaperMeta(BaseModel):
    """Normalized metadata merged across arXiv + S2 (pipeline step 0)."""
    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    abstract: Optional[str] = None
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    s2_id: Optional[str] = None
    openalex_id: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    oa_pdf_url: Optional[str] = None
    text_coverage: Optional[str] = None      # full | oa_pdf | abstract_only
    tldr: Optional[str] = None
    github_urls: list[str] = Field(default_factory=list)
    influential_citation_count: Optional[int] = None

    def aliases(self) -> list[str]:
        """External-id aliases for dedup (plan §10 paper_aliases)."""
        out: list[str] = []
        if self.arxiv_id:
            out.append(f"arxiv:{self.arxiv_id}")
        if self.s2_id:
            out.append(f"s2:{self.s2_id}")
        if self.doi:
            out.append(f"doi:{self.doi.lower()}")
        if self.openalex_id:
            out.append(f"openalex:{self.openalex_id}")
        return out


class Reference(BaseModel):
    """A backward reference (pipeline step 3)."""
    title: Optional[str] = None
    year: Optional[int] = None
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    s2_id: Optional[str] = None
    is_influential: bool = False

    def aliases(self) -> list[str]:
        out: list[str] = []
        if self.arxiv_id:
            out.append(f"arxiv:{self.arxiv_id}")
        if self.s2_id:
            out.append(f"s2:{self.s2_id}")
        if self.doi:
            out.append(f"doi:{self.doi.lower()}")
        return out


class CodeInfo(BaseModel):
    """Step 7 result."""
    found: bool = False
    repo: Optional[str] = None
    url: Optional[str] = None
    stars: Optional[int] = None
    archived: Optional[bool] = None


class Candidate(BaseModel):
    """A disambiguation candidate for a fuzzy title (plan §12)."""
    s2_id: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    venue: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None


class Card(BaseModel):
    """The instant card — pipeline steps 0/1/3/7, no LLM (plan §5)."""
    paper_id: int
    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    s2_id: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None

    # step 1 (purpose/pain point), no LLM — tldr ladder
    summary: Optional[str] = None
    step1_source: Step1Source = "none"

    # step 3 (references)
    references: list[Reference] = Field(default_factory=list)
    references_count: int = 0

    # step 7 (code)
    code: CodeInfo = Field(default_factory=CodeInfo)

    step_status: dict[str, StepStatus] = Field(default_factory=dict)
    cached: bool = False
    deep_analysis_status: str = "not_requested"   # not_requested | queued | ready


class SurveyResult(BaseModel):
    """What the `survey` MCP tool returns: either a card, or candidates to disambiguate."""
    status: Literal["card", "candidates", "not_found"]
    card: Optional[Card] = None
    candidates: list[Candidate] = Field(default_factory=list)
    message: Optional[str] = None
