"""Entry point for the scheduled daily proactive scan (launchd).

Enqueues a `proactive_scan` job and exits; the always-on worker runs it. Keeping the
trigger separate from the worker means the schedule is just "enqueue once a day".
"""

from __future__ import annotations

import asyncio

from .db import close_pool, jobs
from .logging_setup import get

log = get("scan")


def main() -> None:
    async def _amain() -> None:
        jid = await jobs.enqueue("proactive_scan", triggered_by="scheduled")
        log.info("enqueued proactive_scan job %s", jid)
        await close_pool()

    asyncio.run(_amain())


if __name__ == "__main__":
    main()
