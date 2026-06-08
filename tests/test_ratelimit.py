"""Rate-limiter pacing — pure logic, no network."""

import asyncio
import time

import pytest

from surveyhelper.ratelimit import RateLimiter


@pytest.mark.asyncio
async def test_paces_calls_min_interval():
    rl = RateLimiter()
    rl._sources["t"] = type(rl._sources["s2"])(min_interval=0.1)
    t0 = time.monotonic()
    for _ in range(3):
        await rl.acquire("t")
    elapsed = time.monotonic() - t0
    # 3 calls at 0.1s spacing -> >= ~0.2s (first is free, then 2 waits)
    assert elapsed >= 0.18


@pytest.mark.asyncio
async def test_unknown_source_no_pacing():
    rl = RateLimiter()
    t0 = time.monotonic()
    await rl.acquire("does-not-exist")
    assert time.monotonic() - t0 < 0.05


@pytest.mark.asyncio
async def test_arxiv_single_flight_serializes():
    rl = RateLimiter()
    rl._sources["arxiv"].min_interval = 0.1
    order: list[str] = []

    async def call(tag: str):
        await rl.acquire("arxiv")
        order.append(tag)

    await asyncio.gather(call("a"), call("b"), call("c"))
    assert sorted(order) == ["a", "b", "c"]
