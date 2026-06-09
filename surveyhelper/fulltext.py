"""Cached full-text access — one fetch shared across analyze + verify (and reused forever).

A paper's extracted text is fetched once (via the rate-limited arXiv layer) and cached in
`paper_fulltext`; later grounded verification / re-analysis read it instantly. This is what
makes verification cheap and repeatable enough to scale (expand verifiable volume).
"""

from __future__ import annotations

from typing import Optional

from .db import fulltext as cache
from .logging_setup import get
from .sources import arxiv

log = get("fulltext")

FETCH_MAX = 120_000   # cache a generous slice; callers truncate as needed


async def get_fulltext(paper_id: int, arxiv_id: str | None, *,
                       max_chars: int = FETCH_MAX) -> Optional[str]:
    """Return the paper's extracted full text — from cache if present, else fetch + cache."""
    cached = await cache.get(paper_id)
    if cached:
        return cached[:max_chars]
    if not arxiv_id:
        return None
    text = await arxiv.fetch_fulltext(arxiv_id, max_chars=FETCH_MAX)
    if text:
        await cache.store(paper_id, text, "arxiv")
        return text[:max_chars]
    return None
