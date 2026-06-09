"""pgvector storage + similarity for paper/interest embeddings (Phase 6b)."""

from __future__ import annotations

import asyncpg

from . import get_pool
from ..embeddings import to_pgvector


async def store_paper(paper_id: int, vec: list[float], kind: str = "card") -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO paper_embeddings (paper_id, kind, embedding)
           VALUES ($1,$2,$3::vector)
           ON CONFLICT (paper_id, kind) DO UPDATE SET embedding = EXCLUDED.embedding""",
        paper_id, kind, to_pgvector(vec))


async def has_paper(paper_id: int, kind: str = "card") -> bool:
    pool = await get_pool()
    return await pool.fetchval(
        "SELECT 1 FROM paper_embeddings WHERE paper_id=$1 AND kind=$2", paper_id, kind) is not None


async def store_interest(interest_id: int, vec: list[float]) -> None:
    pool = await get_pool()
    await pool.execute("UPDATE interests SET embedding=$2::vector WHERE id=$1",
                       interest_id, to_pgvector(vec))


async def interest_embedding(interest_id: int) -> list[float] | None:
    pool = await get_pool()
    raw = await pool.fetchval("SELECT embedding::text FROM interests WHERE id=$1", interest_id)
    if not raw:
        return None
    return [float(x) for x in raw.strip("[]").split(",")]


async def similar_to_paper(paper_id: int, *, k: int = 8, kind: str = "card") -> list[asyncpg.Record]:
    """Papers nearest to a given paper's embedding."""
    pool = await get_pool()
    return await pool.fetch(
        """SELECT p.id, p.title, p.arxiv_id, 1 - (e.embedding <=> q.embedding) AS sim
           FROM paper_embeddings e
           JOIN papers p ON p.id = e.paper_id,
                (SELECT embedding FROM paper_embeddings WHERE paper_id=$1 AND kind=$2) q
           WHERE e.kind=$2 AND p.id != $1
           ORDER BY e.embedding <=> q.embedding LIMIT $3""",
        paper_id, kind, k)


async def similar(vec: list[float], *, k: int = 8, kind: str = "card",
                  exclude: int | None = None) -> list[asyncpg.Record]:
    """Nearest papers by cosine similarity (pgvector <=> is cosine distance)."""
    pool = await get_pool()
    q = ("SELECT p.id, p.title, p.arxiv_id, 1 - (e.embedding <=> $1::vector) AS sim "
         "FROM paper_embeddings e JOIN papers p ON p.id=e.paper_id WHERE e.kind=$2")
    args: list = [to_pgvector(vec), kind]
    if exclude is not None:
        q += " AND p.id != $3"
        args.append(exclude)
    q += f" ORDER BY e.embedding <=> $1::vector LIMIT {int(k)}"
    return await pool.fetch(q, *args)
