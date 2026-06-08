"""Postgres access layer (asyncpg).

The DB *is* the cache (plan.md §9): a stored paper/edge is never re-fetched.
Dedup authority is `paper_aliases` — every external id maps to one canonical paper
(plan.md §10), so arXiv-vs-DOI duplication collapses to a single row.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import asyncpg

from . import config

_pool: Optional[asyncpg.Pool] = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    # Encode/decode jsonb transparently via json.
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(config.DSN, init=_init_conn, min_size=1, max_size=8)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ── dedup / identity ─────────────────────────────────────────────────────────
async def find_paper_by_alias(alias_id: str) -> Optional[asyncpg.Record]:
    """DB-as-cache lookup: return the canonical paper for an external id, or None."""
    pool = await get_pool()
    return await pool.fetchrow(
        """
        SELECT p.* FROM papers p
        JOIN paper_aliases a ON a.paper_id = p.id
        WHERE a.alias_id = $1
        """,
        alias_id,
    )


async def get_paper(paper_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM papers WHERE id = $1", paper_id)


async def list_aliases(paper_id: int) -> list[str]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT alias_id FROM paper_aliases WHERE paper_id = $1", paper_id)
    return [r["alias_id"] for r in rows]


_PAPER_COLS = (
    "title", "authors", "year", "venue", "abstract", "arxiv_id", "doi",
    "s2_id", "openalex_id", "url", "pdf_url", "text_coverage", "status",
    "min_depth", "retracted",
)


async def upsert_paper(fields: dict[str, Any], aliases: list[str]) -> int:
    """Insert-or-update a paper and (re)map its aliases. Returns canonical paper_id.

    Dedup: if any alias already points at a paper, that paper wins; otherwise insert.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1) find an existing canonical paper via any alias
            paper_id: Optional[int] = None
            if aliases:
                row = await conn.fetchrow(
                    "SELECT paper_id FROM paper_aliases WHERE alias_id = ANY($1::text[]) LIMIT 1",
                    aliases,
                )
                if row:
                    paper_id = row["paper_id"]

            authors = fields.get("authors")
            vals = {k: fields.get(k) for k in _PAPER_COLS}
            vals["authors"] = authors  # jsonb codec handles list/dict

            if paper_id is None:
                cols = ", ".join(_PAPER_COLS)
                placeholders = ", ".join(f"${i+1}" for i in range(len(_PAPER_COLS)))
                paper_id = await conn.fetchval(
                    f"INSERT INTO papers ({cols}) VALUES ({placeholders}) RETURNING id",
                    *[vals[k] for k in _PAPER_COLS],
                )
            else:
                # update only non-null incoming fields (don't clobber known data with null)
                sets, args = [], []
                for k in _PAPER_COLS:
                    if vals[k] is not None:
                        args.append(vals[k])
                        sets.append(f"{k} = ${len(args)}")
                if sets:
                    args.append(paper_id)
                    await conn.execute(
                        f"UPDATE papers SET {', '.join(sets)}, updated_at = now() WHERE id = ${len(args)}",
                        *args,
                    )

            # 2) map aliases (idempotent)
            for alias in aliases:
                await conn.execute(
                    """
                    INSERT INTO paper_aliases (alias_id, paper_id) VALUES ($1, $2)
                    ON CONFLICT (alias_id) DO UPDATE SET paper_id = EXCLUDED.paper_id
                    """,
                    alias, paper_id,
                )
            return paper_id


async def add_citation(src: int, dst: int, edge_type: str = "reference",
                       is_influential: bool = False) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO citations (src, dst, edge_type, is_influential)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (src, dst, edge_type)
        DO UPDATE SET is_influential = citations.is_influential OR EXCLUDED.is_influential
        """,
        src, dst, edge_type, is_influential,
    )


async def count_references(paper_id: int) -> int:
    pool = await get_pool()
    return await pool.fetchval(
        "SELECT count(*) FROM citations WHERE src = $1 AND edge_type = 'reference'", paper_id
    )


# ── derived analysis (the card) ──────────────────────────────────────────────
async def save_analysis(paper_id: int, pipeline_version: str, *, step_status: dict,
                        purpose: str | None = None, pain_point: str | None = None,
                        code: dict | None = None, provenance: dict | None = None,
                        model_used: str | None = None) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO paper_analysis
            (paper_id, pipeline_version, step_status, purpose, pain_point, code, provenance, model_used)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        ON CONFLICT (paper_id, pipeline_version) DO UPDATE SET
            step_status = EXCLUDED.step_status,
            purpose     = EXCLUDED.purpose,
            pain_point  = EXCLUDED.pain_point,
            code        = EXCLUDED.code,
            provenance  = EXCLUDED.provenance,
            model_used  = EXCLUDED.model_used,
            analyzed_at = now()
        """,
        paper_id, pipeline_version, step_status, purpose, pain_point, code, provenance, model_used,
    )


async def get_analysis(paper_id: int, pipeline_version: str) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow(
        "SELECT * FROM paper_analysis WHERE paper_id = $1 AND pipeline_version = $2",
        paper_id, pipeline_version,
    )
