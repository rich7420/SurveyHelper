"""Cached extracted full text repository (so grounded verification/analysis don't re-fetch)."""

from __future__ import annotations

from typing import Optional

from . import get_pool


async def get(paper_id: int) -> Optional[str]:
    pool = await get_pool()
    return await pool.fetchval("SELECT text FROM paper_fulltext WHERE paper_id = $1", paper_id)


async def store(paper_id: int, text: str, source: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO paper_fulltext (paper_id, text, source, chars)
           VALUES ($1,$2,$3,$4)
           ON CONFLICT (paper_id) DO UPDATE SET
               text = EXCLUDED.text, source = EXCLUDED.source,
               chars = EXCLUDED.chars, fetched_at = now()""",
        paper_id, text, source, len(text))
