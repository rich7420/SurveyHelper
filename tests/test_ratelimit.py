"""Cross-process (DB-backed) rate limiter. Integration: needs the Postgres up."""

import time

import pytest

from surveyhelper.db import get_pool
from surveyhelper.ratelimit import INTERVALS, RateLimiter


async def _require_db():
    try:
        return await get_pool()
    except Exception as exc:  # pragma: no cover - env without DB
        pytest.skip(f"DB unavailable: {exc}")


def test_intervals_configured():
    assert INTERVALS["arxiv"] == 4.0
    assert {"s2", "github", "crossref"} <= set(INTERVALS)


@pytest.mark.asyncio
async def test_db_limiter_paces_across_calls():
    pool = await _require_db()
    await pool.execute("DELETE FROM rate_limit WHERE source='test_pace'")
    rl = RateLimiter(intervals={"test_pace": 0.1})
    t0 = time.monotonic()
    for _ in range(3):
        await rl.acquire("test_pace")
    elapsed = time.monotonic() - t0
    # first call fires immediately, then two ~0.1s waits
    assert elapsed >= 0.18
    await pool.execute("DELETE FROM rate_limit WHERE source='test_pace'")


@pytest.mark.asyncio
async def test_unknown_source_not_paced():
    await _require_db()
    rl = RateLimiter()
    t0 = time.monotonic()
    await rl.acquire("does-not-exist")
    assert time.monotonic() - t0 < 0.05
