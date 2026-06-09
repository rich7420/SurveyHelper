"""Daily proactive-scan scheduler — the cross-platform replacement for the mac-only launchd
timer, so proactivity works under `docker compose` too.

Sleeps until the configured hour, enqueues one `proactive_scan` job (the always-on worker runs
it), and repeats. Keeping the trigger separate from the worker keeps the schedule trivial.
"""

from __future__ import annotations

import asyncio
import datetime
import os

from .db import apply_schema, close_pool, jobs
from .logging_setup import get
from .preflight import run_preflight

log = get("scheduler")

SCAN_HOUR = int(os.environ.get("SURVEYHELPER_SCAN_HOUR", "9"))   # local hour, 0–23


async def _sleep_until_hour(hour: int) -> None:
    now = datetime.datetime.now()
    nxt = now.replace(hour=hour % 24, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += datetime.timedelta(days=1)
    await asyncio.sleep(max(1.0, (nxt - now).total_seconds()))


async def run() -> None:
    await run_preflight(service="scheduler")
    await apply_schema()
    log.info("scheduler started; daily proactive_scan at %02d:00 local", SCAN_HOUR)
    while True:
        await _sleep_until_hour(SCAN_HOUR)
        jid = await jobs.enqueue("proactive_scan", triggered_by="scheduled")
        log.info("enqueued proactive_scan job %s", jid)


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            asyncio.run(close_pool())
        except Exception:
            pass


if __name__ == "__main__":
    main()
