"""Full-text cache — second access hits the cache, no re-fetch. Integration: needs DB."""

import pytest

from surveyhelper.db import get_pool, papers
from surveyhelper.models import PaperMeta


async def _db():
    try:
        return await get_pool()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"DB unavailable: {exc}")


@pytest.mark.asyncio
async def test_fulltext_is_cached(monkeypatch):
    pool = await _db()
    await pool.execute("DELETE FROM papers WHERE arxiv_id='7777.00700'")
    pid = await papers.upsert(PaperMeta(arxiv_id="7777.00700", title="FT"))

    import surveyhelper.fulltext as ft
    calls = {"n": 0}

    async def fake_fetch(aid, *, max_chars=120_000):
        calls["n"] += 1
        return "SOME REAL FULL TEXT CONTENT " * 50

    monkeypatch.setattr(ft.arxiv, "fetch_fulltext", fake_fetch)

    t1 = await ft.get_fulltext(pid, "7777.00700")
    t2 = await ft.get_fulltext(pid, "7777.00700")
    assert t1 and t2 == t1
    assert calls["n"] == 1                    # second call served from cache, no re-fetch

    cached = await pool.fetchval("SELECT chars FROM paper_fulltext WHERE paper_id=$1", pid)
    assert cached and cached > 0
    await pool.execute("DELETE FROM papers WHERE id=$1", pid)   # cascades the cache row
