"""deep_dive auto-chain: count_unfinished tracks sibling analyses by triggered_by tag."""

import pytest

from surveyhelper.db import get_pool, jobs

TAG = "expand:test-chain-xyz"


async def _db():
    try:
        return await get_pool()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"DB unavailable: {exc}")


@pytest.mark.asyncio
async def test_count_unfinished_tracks_sibling_analyses():
    pool = await _db()
    await pool.execute("DELETE FROM research_jobs WHERE triggered_by=$1", TAG)

    j1 = await jobs.enqueue("analyze", triggered_by=TAG, priority=80)
    j2 = await jobs.enqueue("analyze", triggered_by=TAG, priority=80)
    await jobs.enqueue("synthesize", triggered_by=TAG, priority=90)   # different type, not counted

    assert await jobs.count_unfinished(TAG, "analyze") == 2
    await jobs.set_status(j1, "done")
    assert await jobs.count_unfinished(TAG, "analyze") == 1
    await jobs.set_status(j2, "done")
    assert await jobs.count_unfinished(TAG, "analyze") == 0    # gate opens → synthesize proceeds

    await pool.execute("DELETE FROM research_jobs WHERE triggered_by=$1", TAG)
