"""Global per-source rate limiter (plan.md §9).

ONE global, per-source pacer shared by every caller (foreground card requests and
background BFS/scan draw from the SAME limiter), so a burst of foreground use
automatically slows the background instead of both colliding into 429s.

Implemented as a steady-pacing limiter: each source enforces a minimum interval
between calls, with a per-source lock so arXiv stays single-flight. This is the
*single egress point* for paper APIs — per DECISIONS.md §H, even PaperQA2 must be
fed through here rather than calling S2/Crossref itself.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class _Source:
    min_interval: float           # seconds between calls
    single_flight: bool = False   # if True, only one in-flight call at a time
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _last: float = 0.0


class RateLimiter:
    """Steady per-source pacer. Sized to DECISIONS.md §E / plan §9 verified limits."""

    def __init__(self) -> None:
        self._sources: dict[str, _Source] = {
            # arXiv: documented 1/3s but 429s reported even so (2026) -> 1/4s, single-flight.
            "arxiv": _Source(min_interval=4.0, single_flight=True),
            # Semantic Scholar: keyed ~1 RPS; unauth shared pool -> stay conservative.
            "s2": _Source(min_interval=1.1),
            # OpenAlex: now key-required (Feb 2026); not used in Phase 0-1.
            "openalex": _Source(min_interval=0.2),
            # Unpaywall: free, 100k/day.
            "unpaywall": _Source(min_interval=0.2),
            # Crossref: read live x-rate-limit headers; default polite-ish.
            "crossref": _Source(min_interval=0.2),
            # GitHub: 5000/hr with token -> 1/s is comfortable.
            "github": _Source(min_interval=1.0),
        }

    async def acquire(self, source: str) -> None:
        src = self._sources.get(source)
        if src is None:  # unknown source -> no pacing
            return
        if src.single_flight:
            await src.lock.acquire()
            try:
                await self._wait(src)
            finally:
                src.lock.release()
        else:
            async with src.lock:
                await self._wait(src)

    @staticmethod
    async def _wait(src: _Source) -> None:
        now = time.monotonic()
        wait = src.min_interval - (now - src._last)
        if wait > 0:
            await asyncio.sleep(wait)
        src._last = time.monotonic()


# Process-wide singleton: the ONE limiter.
limiter = RateLimiter()
