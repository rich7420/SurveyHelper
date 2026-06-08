"""Notifications repository (plan §12 HEARTBEAT). digest_key groups batches (§17)."""

from __future__ import annotations

from typing import Any

from . import get_pool


async def add(kind: str, payload: dict, *, job_id: int | None = None,
              digest_key: str | None = None) -> int:
    pool = await get_pool()
    return await pool.fetchval(
        """INSERT INTO notifications (job_id, kind, payload, digest_key)
           VALUES ($1,$2,$3,$4) RETURNING id""",
        job_id, kind, payload, digest_key,
    )


async def pending() -> list[dict[str, Any]]:
    """Undelivered notifications; mark them delivered as they're read."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """SELECT * FROM notifications WHERE delivered = FALSE
                   ORDER BY created_at FOR UPDATE SKIP LOCKED"""
            )
            if rows:
                await conn.execute(
                    "UPDATE notifications SET delivered=TRUE WHERE id = ANY($1::bigint[])",
                    [r["id"] for r in rows],
                )
    return [
        {"id": r["id"], "kind": r["kind"], "payload": r["payload"],
         "digest_key": r["digest_key"], "created_at": r["created_at"].isoformat()}
        for r in rows
    ]
