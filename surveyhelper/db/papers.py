"""Papers + aliases + citation-edge repository.

Dedup authority is `paper_aliases` — every external id maps to one canonical
paper (plan §10), so arXiv-vs-DOI duplication collapses to a single row.
"""

from __future__ import annotations

from typing import Any, Optional

import asyncpg

from . import get_pool
from ..models import PaperMeta, Reference

_PAPER_COLS = (
    "title", "authors", "year", "venue", "abstract", "arxiv_id", "doi",
    "s2_id", "openalex_id", "url", "pdf_url", "text_coverage", "status",
    "min_depth", "retracted",
)


async def find_by_alias(alias_id: str) -> Optional[asyncpg.Record]:
    """DB-as-cache lookup: canonical paper for an external id, or None."""
    pool = await get_pool()
    return await pool.fetchrow(
        """SELECT p.* FROM papers p
           JOIN paper_aliases a ON a.paper_id = p.id
           WHERE a.alias_id = $1""",
        alias_id,
    )


async def find_by_any_alias(aliases: list[str]) -> Optional[asyncpg.Record]:
    if not aliases:
        return None
    pool = await get_pool()
    return await pool.fetchrow(
        """SELECT p.* FROM papers p
           JOIN paper_aliases a ON a.paper_id = p.id
           WHERE a.alias_id = ANY($1::text[]) LIMIT 1""",
        aliases,
    )


async def get(paper_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM papers WHERE id = $1", paper_id)


async def aliases_of(paper_id: int) -> list[str]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT alias_id FROM paper_aliases WHERE paper_id = $1", paper_id)
    return [r["alias_id"] for r in rows]


def _values_from_meta(meta: PaperMeta) -> dict[str, Any]:
    d = meta.model_dump()
    return {k: d.get(k) for k in _PAPER_COLS}


async def upsert(meta: PaperMeta, *, min_depth: int | None = None) -> int:
    """Insert-or-update a paper and (re)map its aliases. Returns canonical paper_id.

    Dedup: if any alias already points at a paper, that paper wins (update only
    non-null incoming fields); otherwise insert. Note: does not *merge* two
    pre-existing distinct papers — acceptable for v1 (DECISIONS.md, known limit).
    """
    pool = await get_pool()
    aliases = meta.aliases()
    vals = _values_from_meta(meta)
    if min_depth is not None:
        vals["min_depth"] = min_depth

    async with pool.acquire() as conn:
        async with conn.transaction():
            paper_id: Optional[int] = None
            if aliases:
                row = await conn.fetchrow(
                    "SELECT paper_id FROM paper_aliases WHERE alias_id = ANY($1::text[]) LIMIT 1",
                    aliases,
                )
                if row:
                    paper_id = row["paper_id"]

            if paper_id is None:
                cols = ", ".join(_PAPER_COLS)
                ph = ", ".join(f"${i + 1}" for i in range(len(_PAPER_COLS)))
                paper_id = await conn.fetchval(
                    f"INSERT INTO papers ({cols}) VALUES ({ph}) RETURNING id",
                    *[vals[k] for k in _PAPER_COLS],
                )
            else:
                sets, args = [], []
                for k in _PAPER_COLS:
                    if vals[k] is not None:
                        args.append(vals[k])
                        sets.append(f"{k} = ${len(args)}")
                if sets:
                    args.append(paper_id)
                    await conn.execute(
                        f"UPDATE papers SET {', '.join(sets)}, updated_at = now() "
                        f"WHERE id = ${len(args)}",
                        *args,
                    )

            for alias in aliases:
                await conn.execute(
                    """INSERT INTO paper_aliases (alias_id, paper_id) VALUES ($1, $2)
                       ON CONFLICT (alias_id) DO UPDATE SET paper_id = EXCLUDED.paper_id""",
                    alias, paper_id,
                )
            return paper_id


async def upsert_reference_stub(ref: Reference) -> Optional[int]:
    """Upsert a lightweight paper row for a reference (graph node). None if no id."""
    if not ref.aliases():
        return None
    return await upsert(PaperMeta(
        title=ref.title, year=ref.year, arxiv_id=ref.arxiv_id,
        doi=ref.doi, s2_id=ref.s2_id,
    ))


async def add_citation(src: int, dst: int, edge_type: str = "reference",
                       is_influential: bool = False) -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO citations (src, dst, edge_type, is_influential)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (src, dst, edge_type)
           DO UPDATE SET is_influential = citations.is_influential OR EXCLUDED.is_influential""",
        src, dst, edge_type, is_influential,
    )


async def count_references(paper_id: int) -> int:
    pool = await get_pool()
    return await pool.fetchval(
        "SELECT count(*) FROM citations WHERE src = $1 AND edge_type = 'reference'", paper_id
    )


async def references_of(paper_id: int) -> list[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch(
        """SELECT p.*, c.is_influential FROM citations c
           JOIN papers p ON p.id = c.dst
           WHERE c.src = $1 AND c.edge_type = 'reference'
           ORDER BY c.is_influential DESC, p.year DESC NULLS LAST""",
        paper_id,
    )
