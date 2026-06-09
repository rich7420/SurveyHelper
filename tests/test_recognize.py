"""Ambient recognition — graph lookup by id and by title (no LLM/network)."""

import pytest

from surveyhelper import config
from surveyhelper.db import analysis, get_pool, papers, personal
from surveyhelper.models import PaperMeta
from surveyhelper.recognize import recognize


async def _db():
    try:
        return await get_pool()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"DB unavailable: {exc}")


@pytest.mark.asyncio
async def test_recognize_by_arxiv_id_with_state_and_depth():
    pool = await _db()
    await pool.execute("DELETE FROM papers WHERE arxiv_id='7777.00400'")
    pid = await papers.upsert(PaperMeta(arxiv_id="7777.00400", title="Recognizable Paper"))
    await analysis.save(pid, config.PIPELINE_VERSION,
                        step_status={"0": "ok", "1": "ok", "2": "ok"}, purpose="a crisp tldr")
    await personal.set_state(pid, "read")

    r = await recognize("let's revisit arXiv:7777.00400")
    assert r["in_graph"] and r["paper_id"] == pid
    assert r["tldr"] == "a crisp tldr" and r["user_state"] == "read"
    assert r["deep_analyzed"] is True
    await pool.execute("DELETE FROM papers WHERE id=$1", pid)


@pytest.mark.asyncio
async def test_recognize_by_title_substring():
    pool = await _db()
    await pool.execute("DELETE FROM papers WHERE arxiv_id='7777.00401'")
    pid = await papers.upsert(PaperMeta(arxiv_id="7777.00401",
                                        title="Blockwise Parallel Transformer XYZZY"))
    await analysis.save(pid, config.PIPELINE_VERSION, step_status={"0": "ok"}, purpose="t")
    r = await recognize("what did you think of the Blockwise Parallel Transformer XYZZY paper?")
    assert r["in_graph"] and r["paper_id"] == pid
    await pool.execute("DELETE FROM papers WHERE id=$1", pid)


@pytest.mark.asyncio
async def test_recognize_unknown_is_not_in_graph():
    await _db()
    r = await recognize("arXiv:9999.99999")
    assert r["in_graph"] is False
