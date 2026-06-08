"""Global, cross-process rate limiter (plan.md §9).

ONE global per-source bucket shared by EVERY process — the MCP server (foreground
card requests) and the worker (background BFS/scan) draw from the SAME bucket, so a
burst of foreground use automatically slows the background instead of both colliding
into 429s. This is the *single egress pacer* for paper APIs (DECISIONS.md §H).

Implementation: an atomic "slot ticket" in Postgres. Each acquire reserves the next
allowed firing time for its source via a single upsert (`next_slot` advanced by the
source's min interval), then sleeps until that time — outside any lock, so arXiv's
4 s spacing is enforced across processes without holding a DB lock while waiting.
This also gives arXiv single-flight for free (only one call fires per 4 s window,
process-wide).
"""

from __future__ import annotations

import asyncio

from .db import get_pool

# Per-source minimum interval (seconds), sized to DECISIONS.md §E / plan §9 limits.
INTERVALS: dict[str, float] = {
    "arxiv": 4.0,        # documented 1/3s but 429s reported even so (2026) -> 1/4s
    "s2": 1.1,           # keyed ~1 RPS; unauth shared pool -> conservative
    "openalex": 0.2,     # key-required (Feb 2026); unused in Phase 0-1
    "unpaywall": 0.2,    # free, 100k/day
    "crossref": 0.2,     # read live x-rate-limit headers; polite-ish default
    "github": 1.0,       # 5000/hr with token
}

# Reserve the next slot and return how long THIS caller must wait for it.
_RESERVE_SQL = """
    INSERT INTO rate_limit (source, next_slot)
    VALUES ($1, now() + make_interval(secs => $2))
    ON CONFLICT (source) DO UPDATE
        SET next_slot = GREATEST(now(), rate_limit.next_slot) + make_interval(secs => $2)
    RETURNING EXTRACT(EPOCH FROM (rate_limit.next_slot - make_interval(secs => $2) - now()))
"""


class RateLimiter:
    """DB-backed cross-process pacer. Same `acquire(source)` interface as before."""

    def __init__(self, intervals: dict[str, float] | None = None):
        self.intervals = intervals if intervals is not None else INTERVALS

    async def acquire(self, source: str) -> None:
        interval = self.intervals.get(source)
        if interval is None:          # unknown source -> no pacing
            return
        pool = await get_pool()
        delay = await pool.fetchval(_RESERVE_SQL, source, float(interval))
        if delay and delay > 0:
            await asyncio.sleep(float(delay))


# Process-wide singleton (the pacing state itself lives in Postgres, shared by all).
limiter = RateLimiter()
