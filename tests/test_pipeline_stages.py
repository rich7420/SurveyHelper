"""Per-stage pipeline correctness — sources mocked, real test DB.

Verifies each stage produces the right data: step 0 resolve, the step-1 ladder,
step 3 references, dedup/cache, and enrich (tldr upgrade + reference edges).
"""

import pytest

from surveyhelper import config
from surveyhelper.db import analysis, get_pool, papers
from surveyhelper.models import PaperMeta, Reference


async def _db():
    try:
        return await get_pool()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"DB unavailable: {exc}")


async def _cleanup(pool, *arxiv_ids, s2_ids=()):
    for aid in arxiv_ids:
        await pool.execute("DELETE FROM papers WHERE arxiv_id=$1", aid)
    for sid in s2_ids:
        await pool.execute("DELETE FROM papers WHERE s2_id=$1", sid)


@pytest.mark.asyncio
async def test_survey_card_steps_0_1_3_7(monkeypatch):
    """Step 0 (resolve) + step 1 ladder (abstract fallback) + step 7 (no code)."""
    pool = await _db()
    await _cleanup(pool, "7777.00001")
    from surveyhelper.sources import arxiv as arxiv_mod

    async def fake_meta(aid):
        return PaperMeta(arxiv_id="7777.00001", title="Mock Paper", authors=["A. Author"],
                         year=2024, abstract="First sentence. Second sentence. Third one.",
                         github_urls=[])
    monkeypatch.setattr(arxiv_mod, "fetch_metadata", fake_meta)

    from surveyhelper.pipeline.card import survey
    res = await survey("7777.00001", enqueue_enrich=False)
    assert res.status == "card"
    c = res.card
    assert c.title == "Mock Paper" and c.year == 2024
    assert c.step_status["0"] == "ok"
    # step 1 ladder: no tldr -> first two sentences of the abstract
    assert c.step1_source == "abstract_extractive"
    assert c.summary == "First sentence. Second sentence."
    assert c.step_status["7"] == "skipped"      # no github url
    await _cleanup(pool, "7777.00001")


@pytest.mark.asyncio
async def test_survey_dedup_is_cached(monkeypatch):
    """Second survey of the same id returns the cached card (no re-resolve)."""
    pool = await _db()
    await _cleanup(pool, "7777.00009")
    from surveyhelper.sources import arxiv as arxiv_mod
    calls = {"n": 0}

    async def fake_meta(aid):
        calls["n"] += 1
        return PaperMeta(arxiv_id="7777.00009", title="Dedup Paper", year=2024, abstract="X.")
    monkeypatch.setattr(arxiv_mod, "fetch_metadata", fake_meta)

    from surveyhelper.pipeline.card import survey
    first = await survey("7777.00009", enqueue_enrich=False)
    second = await survey("7777.00009", enqueue_enrich=False)
    assert first.card.cached is False and second.card.cached is True
    assert first.card.paper_id == second.card.paper_id
    assert calls["n"] == 1                        # second call hit cache, no resolve
    await _cleanup(pool, "7777.00009")


@pytest.mark.asyncio
async def test_enrich_tldr_and_references(monkeypatch):
    """Enrich upgrades step 1 to tldr and adds step-3 reference edges."""
    pool = await _db()
    await _cleanup(pool, "7777.00002", s2_ids=("s2ref1",))
    pid = await papers.upsert(PaperMeta(arxiv_id="7777.00002", title="Root", year=2024))
    await analysis.save(pid, config.PIPELINE_VERSION,
                        step_status={"0": "ok", "1": "partial", "3": "partial"},
                        purpose="abstract snippet")

    from surveyhelper.sources import s2 as s2_mod

    async def fake_paper(lookup):
        return PaperMeta(s2_id="s2root", arxiv_id="7777.00002", tldr="A crisp tldr.")

    async def fake_refs(s2id, limit):
        return [Reference(s2_id="s2ref1", title="Ref One", is_influential=True)]

    monkeypatch.setattr(s2_mod, "fetch_paper", fake_paper)
    monkeypatch.setattr(s2_mod, "fetch_references", fake_refs)

    from surveyhelper.pipeline.enrich import enrich
    res = await enrich(pid)
    assert res["tldr"] is True and res["references"] == 1

    row = await analysis.get(pid, config.PIPELINE_VERSION)
    assert row["purpose"] == "A crisp tldr."       # step 1 upgraded
    assert row["step_status"]["1"] == "ok"
    assert row["step_status"]["3"] == "ok"
    refs = await papers.references_of(pid)
    assert len(refs) == 1 and refs[0]["title"] == "Ref One" and refs[0]["is_influential"]
    await _cleanup(pool, "7777.00002", s2_ids=("s2ref1", "s2root"))


@pytest.mark.asyncio
async def test_expand_bfs_skips_dismissed(monkeypatch):
    """Expand pushes references to the next depth but skips dismissed papers (§7 dedup)."""
    pool = await _db()
    await _cleanup(pool, "7777.00100", "7777.00101", "7777.00102")
    from surveyhelper.db import jobs, personal
    import surveyhelper.pipeline.expand as ex

    root = await papers.upsert(PaperMeta(arxiv_id="7777.00100", title="Root"))
    keep = await papers.upsert(PaperMeta(arxiv_id="7777.00101", title="Keep"))
    drop = await papers.upsert(PaperMeta(arxiv_id="7777.00102", title="Drop"))
    await papers.add_citation(root, keep, "reference", True)
    await papers.add_citation(root, drop, "reference", False)
    await personal.set_state(drop, "dismissed")

    async def _noop(pid):
        return None
    monkeypatch.setattr(ex, "_ensure_analyzed", _noop)
    monkeypatch.setattr(ex, "MAX_PAPERS_PER_JOB", 5)

    jid = await jobs.enqueue("expand", root_paper_id=root, requested_depth=2)
    await jobs.set_status(jid, "running")          # so the live worker won't claim it
    await ex.run_expand(await jobs.get(jid))

    frontier = {r["paper_id"] for r in
                await pool.fetch("SELECT paper_id FROM job_papers WHERE job_id=$1", jid)}
    assert root in frontier and keep in frontier and drop not in frontier
    await _cleanup(pool, "7777.00100", "7777.00101", "7777.00102")


@pytest.mark.asyncio
async def test_proactive_dedups_known_papers(monkeypatch):
    """Proactive scan surfaces only papers not already tracked."""
    pool = await _db()
    await _cleanup(pool, "7777.00200", "7777.00201")
    from surveyhelper.db import personal
    from surveyhelper.models import Card, SurveyResult
    import surveyhelper.pipeline.proactive as pro

    await papers.upsert(PaperMeta(arxiv_id="7777.00200", title="Existing"))   # already known
    await personal.add_interest("test-interest-xyz")

    async def fake_search(query, *, max_results=25, since=None):
        return [PaperMeta(arxiv_id="7777.00200", title="Existing"),
                PaperMeta(arxiv_id="7777.00201", title="Brand New")]

    async def fake_survey(ident, **kw):
        pid = await papers.upsert(PaperMeta(arxiv_id=ident, title="Brand New"))
        return SurveyResult(status="card", card=Card(paper_id=pid, title="Brand New", arxiv_id=ident))

    monkeypatch.setattr(pro.arxiv, "search_recent", fake_search)
    monkeypatch.setattr(pro, "survey", fake_survey)

    res = await pro.run_scan()
    assert res["new"] == 1          # existing deduped; only the brand-new surfaced
    await pool.execute("DELETE FROM interests WHERE label='test-interest-xyz'")
    await _cleanup(pool, "7777.00200", "7777.00201")
