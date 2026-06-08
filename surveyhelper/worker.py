"""Background worker daemon (plan §3).

Owns paced execution: claims jobs from research_jobs (FOR UPDATE SKIP LOCKED) and
runs them. Independent of whether OpenClaw is up. Phase 0-1 implements the loop and
the `analyze` handler stub; `expand`/`synthesize`/`proactive_scan` arrive in later
phases. The handler registry makes adding them a one-line change.
"""

from __future__ import annotations

import asyncio
import signal
from typing import Awaitable, Callable

import asyncpg

from . import http
from .db import close_pool, jobs, notifications
from .logging_setup import get

log = get("worker")

Handler = Callable[[asyncpg.Record], Awaitable[None]]

IDLE_SLEEP = 2.0          # seconds between empty polls
MAX_ENRICH_ATTEMPTS = 8   # give up after this many deferred retries


class RetryLater(Exception):
    """Raise to defer a job (e.g. upstream API throttled) instead of failing it."""

    def __init__(self, delay_seconds: float):
        super().__init__(f"retry in {delay_seconds:.0f}s")
        self.delay_seconds = delay_seconds


def _backoff_seconds(attempts: int) -> float:
    """Capped exponential backoff: 1, 2, 4, 8, 16, 30, 30 ... minutes."""
    return min(30 * 60, 60 * (2 ** attempts))


async def _handle_analyze(job: asyncpg.Record) -> None:
    """Deep grounded steps (1-refine/2/4/5/6) via PaperQA2 — Phase 2.

    Phase 0-1: the instant card is already built synchronously by the MCP server,
    so there is nothing to do here yet. Mark done without noise.
    """
    log.info("analyze job %s for paper %s — deep steps are Phase 2 (no-op for now)",
             job["id"], job["root_paper_id"])


async def _handle_enrich(job: asyncpg.Record) -> None:
    """Fill the card's S2 tldr + references in the background (plan §5).

    If S2 is throttled, defer (RetryLater) with backoff rather than dead-lettering,
    so enrichment completes once S2 is reachable.
    """
    from .pipeline.enrich import enrich
    res = await enrich(job["root_paper_id"])

    if res.get("retryable"):
        attempts = job["attempts"] or 0
        if attempts < MAX_ENRICH_ATTEMPTS:
            raise RetryLater(_backoff_seconds(attempts))
        log.warning("enrich job %s giving up after %d attempts (%s)",
                    job["id"], attempts, res.get("reason"))

    if res.get("enriched"):
        await notifications.add(
            "enriched",
            {"paper_id": job["root_paper_id"], "title": res.get("title"),
             "tldr": res.get("tldr"), "references": res.get("references")},
            job_id=job["id"], digest_key=f"enrich:{job['root_paper_id']}",
        )
    elif not res.get("retryable"):
        log.info("enrich job %s not completed: %s", job["id"], res.get("reason"))


async def _handle_unimplemented(job: asyncpg.Record) -> None:
    log.info("job %s type=%s not implemented yet", job["id"], job["type"])
    await notifications.add("unimplemented", {"job_id": job["id"], "type": job["type"]},
                            job_id=job["id"])


HANDLERS: dict[str, Handler] = {
    "enrich": _handle_enrich,             # S2 tldr + references (Phase 0-1, async)
    "analyze": _handle_analyze,           # deep grounded steps (Phase 2)
    # "expand": _handle_expand,           # Phase 4
    # "synthesize": _handle_synthesize,   # Phase 5
    # "proactive_scan": _handle_scan,     # Phase 7
}


async def _run_one(job: asyncpg.Record) -> None:
    handler = HANDLERS.get(job["type"], _handle_unimplemented)
    try:
        await handler(job)
        await jobs.set_status(job["id"], "done")
    except RetryLater as r:
        await jobs.reschedule(job["id"], r.delay_seconds)
        log.info("job %s deferred %.0fs (attempt %d)",
                 job["id"], r.delay_seconds, (job["attempts"] or 0) + 1)
    except Exception as exc:  # dead-letter (plan §17)
        log.exception("job %s failed: %s", job["id"], exc)
        await jobs.set_status(job["id"], "failed")
        await notifications.add("job_failed", {"job_id": job["id"], "reason": str(exc)},
                                job_id=job["id"])


async def run(stop: asyncio.Event) -> None:
    log.info("worker started")
    while not stop.is_set():
        job = await jobs.claim_next()
        if job is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=IDLE_SLEEP)
            except asyncio.TimeoutError:
                pass
            continue
        log.info("claimed job %s type=%s", job["id"], job["type"])
        await _run_one(job)
    log.info("worker stopping")


def main() -> None:
    stop = asyncio.Event()

    async def _amain() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                pass
        try:
            await run(stop)
        finally:
            await http.aclose()
            await close_pool()

    asyncio.run(_amain())


if __name__ == "__main__":
    main()
