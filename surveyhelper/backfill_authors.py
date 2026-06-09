"""One-off maintenance: backfill authors for papers that have an arXiv id but no stored authors.

Needed once after the empty-clobber fix (older rows had their authors wiped by reference-stub
re-upserts). Re-fetches arXiv metadata (paced via the shared limiter) and re-upserts (now
non-clobbering). Carded papers first (the ones you actually see). Safe to re-run.

  surveyhelper-backfill-authors [LIMIT]      # default 200
"""

from __future__ import annotations

import asyncio
import os
import sys

from . import http
from .db import close_pool, get_pool
from .db import papers as papers_db
from .logging_setup import get
from .sources import arxiv

log = get("backfill")


async def run(limit: int) -> tuple[int, int]:
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT p.id, p.arxiv_id FROM papers p
           WHERE p.arxiv_id IS NOT NULL
             AND (p.authors IS NULL OR jsonb_array_length(p.authors) = 0)
           ORDER BY EXISTS(SELECT 1 FROM paper_analysis a WHERE a.paper_id = p.id) DESC, p.id
           LIMIT $1""", limit)
    filled = 0
    for r in rows:
        try:
            meta = await arxiv.fetch_metadata(r["arxiv_id"])
        except Exception as exc:
            log.warning("fetch failed for %s: %s", r["arxiv_id"], exc)
            continue
        if meta and meta.authors:
            await papers_db.upsert(meta)
            filled += 1
            log.info("backfilled %s -> %d authors", r["arxiv_id"], len(meta.authors))
    return filled, len(rows)


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("SURVEYHELPER_BACKFILL_LIMIT", "200"))

    async def _amain() -> None:
        try:
            filled, n = await run(limit)
            print(f"backfilled authors for {filled}/{n} papers (limit={limit})")
        finally:
            await http.aclose()
            await close_pool()

    asyncio.run(_amain())


if __name__ == "__main__":
    main()
