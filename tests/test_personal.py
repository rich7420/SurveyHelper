"""Personal layer — state, correction overlay, dismissal dedup. Integration: needs DB."""

import pytest

from surveyhelper.db import get_pool, personal
from surveyhelper.models import PaperMeta


async def _db():
    try:
        return await get_pool()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"DB unavailable: {exc}")


async def _make_paper(pool, arxiv_id: str) -> int:
    from surveyhelper.db import papers
    await pool.execute("DELETE FROM papers WHERE arxiv_id=$1", arxiv_id)
    return await papers.upsert(PaperMeta(arxiv_id=arxiv_id, title="Test Paper", year=2024))


@pytest.mark.asyncio
async def test_state_roundtrip_and_dismissed_set():
    pool = await _db()
    pid = await _make_paper(pool, "9999.00001")
    await personal.set_state(pid, "dismissed", why="not relevant")
    row = await personal.get_state(pid)
    assert row["state"] == "dismissed" and row["why"] == "not relevant"
    assert pid in await personal.dismissed_ids()
    await pool.execute("DELETE FROM papers WHERE id=$1", pid)  # cascades state


@pytest.mark.asyncio
async def test_correction_overlay_latest_wins():
    pool = await _db()
    pid = await _make_paper(pool, "9999.00002")
    await personal.add_correction(pid, "title", "Wrong Title", "first")
    await personal.add_correction(pid, "title", "Right Title", "fixed")
    corr = await personal.corrections_for(pid)
    assert corr["title"] == "Right Title"   # latest correction wins
    await pool.execute("DELETE FROM papers WHERE id=$1", pid)


@pytest.mark.asyncio
async def test_card_assemble_applies_correction():
    pool = await _db()
    from surveyhelper.db import analysis
    from surveyhelper.pipeline.card import _assemble
    from surveyhelper import config
    pid = await _make_paper(pool, "9999.00003")
    await analysis.save(pid, config.PIPELINE_VERSION, step_status={"0": "ok"}, purpose="orig")
    await personal.add_correction(pid, "summary", "corrected summary")
    card = await _assemble(pid, cached=True)
    assert card.summary == "corrected summary"
    assert "summary" in card.corrected_fields
    await pool.execute("DELETE FROM papers WHERE id=$1", pid)
