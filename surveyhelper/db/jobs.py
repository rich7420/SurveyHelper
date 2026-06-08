"""research_jobs queue (plan §18). Postgres-as-queue, drained FOR UPDATE SKIP LOCKED.

This is the seam between the MCP server (enqueues) and the worker (claims + runs).
Job types: analyze | expand | synthesize | proactive_scan.
"""

from __future__ import annotations

from typing import Any, Optional

import asyncpg

from . import get_pool


async def enqueue(job_type: str, *, root_paper_id: int | None = None,
                  requested_depth: int | None = None, triggered_by: str | None = None,
                  budget: dict | None = None, parent_job_id: int | None = None) -> int:
    pool = await get_pool()
    return await pool.fetchval(
        """INSERT INTO research_jobs
               (type, root_paper_id, requested_depth, triggered_by, budget, parent_job_id, status)
           VALUES ($1,$2,$3,$4,$5,$6,'pending') RETURNING id""",
        job_type, root_paper_id, requested_depth, triggered_by, budget, parent_job_id,
    )


async def claim_next() -> Optional[asyncpg.Record]:
    """Atomically claim one due pending job (run_after <= now). None if none due."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT * FROM research_jobs
                   WHERE status = 'pending' AND run_after <= now()
                   ORDER BY run_after
                   FOR UPDATE SKIP LOCKED
                   LIMIT 1"""
            )
            if row is None:
                return None
            await conn.execute(
                "UPDATE research_jobs SET status='running', updated_at=now() WHERE id=$1",
                row["id"],
            )
            return row


async def set_status(job_id: int, status: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE research_jobs SET status=$2, updated_at=now() WHERE id=$1", job_id, status
    )


async def reschedule(job_id: int, delay_seconds: float) -> None:
    """Defer a job for a later retry (e.g. an upstream API was throttled)."""
    pool = await get_pool()
    await pool.execute(
        """UPDATE research_jobs
           SET status='pending', attempts = attempts + 1,
               run_after = now() + ($2 || ' seconds')::interval, updated_at=now()
           WHERE id=$1""",
        job_id, str(delay_seconds),
    )


async def get(job_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM research_jobs WHERE id = $1", job_id)


# ── frontier (resumable BFS, DECISIONS.md §D #6) ─────────────────────────────
async def add_frontier(job_id: int, paper_id: int, depth: int, tier: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO job_papers (job_id, paper_id, depth, tier, status)
           VALUES ($1,$2,$3,$4,'queued')
           ON CONFLICT (job_id, paper_id) DO NOTHING""",
        job_id, paper_id, depth, tier,
    )


async def claim_frontier(job_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT * FROM job_papers
                   WHERE job_id=$1 AND status='queued'
                   ORDER BY depth FOR UPDATE SKIP LOCKED LIMIT 1""",
                job_id,
            )
            if row is None:
                return None
            await conn.execute(
                "UPDATE job_papers SET status='analyzing' WHERE job_id=$1 AND paper_id=$2",
                job_id, row["paper_id"],
            )
            return row


async def set_frontier_status(job_id: int, paper_id: int, status: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE job_papers SET status=$3 WHERE job_id=$1 AND paper_id=$2",
        job_id, paper_id, status,
    )
