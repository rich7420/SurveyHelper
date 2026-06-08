"""Usage/cost tracking (plan §13). Every LLM call lands here for the cost dashboard."""

from __future__ import annotations

from typing import Any

from . import get_pool


async def add(*, job_id: int | None, source: str, calls: int, tokens: int,
              cost_usd: float) -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO usage_log (job_id, source, calls, tokens, cost_usd)
           VALUES ($1,$2,$3,$4,$5)""",
        job_id, source, calls, tokens, cost_usd,
    )


async def today_cost() -> float:
    pool = await get_pool()
    return float(await pool.fetchval(
        "SELECT coalesce(sum(cost_usd),0) FROM usage_log WHERE at::date = now()::date"))


async def totals() -> dict[str, Any]:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT coalesce(sum(calls),0) calls, coalesce(sum(tokens),0) tokens, "
        "coalesce(sum(cost_usd),0) cost FROM usage_log")
    return {"calls": row["calls"], "tokens": row["tokens"], "cost_usd": float(row["cost"])}
