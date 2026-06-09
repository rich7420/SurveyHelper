"""surveyHelper MCP server — the front door OpenClaw calls (plan §12).

Returns the instant card synchronously (steps 0/1/3/7) and enqueues deep work for
the worker. HTTP (streamable-http) transport so a Dockerized OpenClaw can reach it
via host.docker.internal.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import config, http
from .db import close_pool
from .db import jobs as jobs_repo
from .db import notifications, papers, personal, syntheses, usage
from .logging_setup import get
from .pipeline.card import _assemble, survey as _survey

log = get("mcp")


@asynccontextmanager
async def _lifespan(_server: FastMCP):
    try:
        yield {}
    finally:                       # graceful shutdown: release the shared pool + client
        await http.aclose()
        await close_pool()


mcp = FastMCP("surveyHelper", host=config.MCP_HOST, port=config.MCP_PORT, lifespan=_lifespan)


@mcp.tool()
async def survey(identifier: str, depth: int = 1, references_limit: int = 50) -> dict[str, Any]:
    """Survey a paper: return an instant card (purpose, references, code) in seconds.

    `identifier` may be an arXiv id (e.g. "2310.01889" or "arXiv:2310.01889"), a DOI,
    a Semantic Scholar id, a paper URL, or a paper title. A fuzzy title returns
    candidates to disambiguate.

    `depth=2` also kicks off a background **graph expansion** (BFS over the citation
    graph) — the card returns immediately and the deeper graph fills in; check progress
    with `job_status` and view it with `get_graph`.
    """
    res = await _survey(identifier, depth=depth, references_limit=references_limit)
    return res.model_dump()


@mcp.tool()
async def get_paper(paper_id: int) -> dict[str, Any]:
    """Return the stored card for a known paper_id."""
    p = await papers.get(paper_id)
    if p is None:
        return {"status": "not_found", "paper_id": paper_id}
    card = await _assemble(paper_id, cached=True)
    return {"status": "card", "card": card.model_dump()}


@mcp.tool()
async def get_graph(paper_id: int) -> dict[str, Any]:
    """Return a paper and its backward references — the citation neighborhood.

    References are ordered most-influential first. (Depth-2 graph expansion is a
    later phase; this returns the direct reference set built by the card/enrich.)
    """
    p = await papers.get(paper_id)
    if p is None:
        return {"status": "not_found", "paper_id": paper_id}
    ref_rows = await papers.references_of(paper_id)
    refs = [{"paper_id": r["id"], "title": r["title"], "year": r["year"],
             "arxiv_id": r["arxiv_id"], "is_influential": r["is_influential"]}
            for r in ref_rows]
    return {
        "status": "graph",
        "root": {"paper_id": p["id"], "title": p["title"], "year": p["year"],
                 "arxiv_id": p["arxiv_id"]},
        "references": refs,
        "references_count": len(refs),
    }


@mcp.tool()
async def job_status(job_id: int) -> dict[str, Any]:
    """Status of a background job (analyze/expand/synthesize/proactive_scan)."""
    j = await jobs_repo.get(job_id)
    if j is None:
        return {"status": "not_found", "job_id": job_id}
    return {"job_id": j["id"], "type": j["type"], "status": j["status"],
            "root_paper_id": j["root_paper_id"],
            "created_at": j["created_at"].isoformat()}


@mcp.tool()
async def pending_notifications() -> dict[str, Any]:
    """Undelivered notifications for OpenClaw's heartbeat to surface, then mark read."""
    items = await notifications.pending()
    return {"count": len(items), "notifications": items}


# ── personal memory layer (plan §7/§11) ─────────────────────────────────────
@mcp.tool()
async def mark_paper(paper_id: int, state: str, why: str | None = None) -> dict[str, Any]:
    """Record what you did with a paper so surveyHelper remembers it.

    `state` is one of: seen | read | understood | dismissed. `why` captures the intent
    (the question/topic that prompted it). Dismissed papers won't resurface in expansion.
    """
    if state not in personal.VALID_STATES:
        return {"status": "error", "message": f"state must be one of {sorted(personal.VALID_STATES)}"}
    if await papers.get(paper_id) is None:
        return {"status": "not_found", "paper_id": paper_id}
    await personal.set_state(paper_id, state, why=why)
    return {"status": "ok", "paper_id": paper_id, "state": state}


@mcp.tool()
async def correct_paper(paper_id: int, field: str, value: str,
                        note: str | None = None) -> dict[str, Any]:
    """Override a card field (e.g. title, summary, year, venue). The correction is
    overlaid on every future read of this paper."""
    if await papers.get(paper_id) is None:
        return {"status": "not_found", "paper_id": paper_id}
    await personal.add_correction(paper_id, field, value, note)
    return {"status": "ok", "paper_id": paper_id, "field": field}


@mcp.tool()
async def add_interest(label: str) -> dict[str, Any]:
    """Add a research line you're following (used to focus proactive surfacing)."""
    iid = await personal.add_interest(label)
    try:
        from .db import embeddings as emb_db
        from .embeddings import embed_one
        await emb_db.store_interest(iid, await embed_one(label))
    except Exception as exc:
        log.warning("interest embed failed (%s)", exc)
    return {"status": "ok", "interest_id": iid, "label": label}


@mcp.tool()
async def similar_papers(paper_id: int, k: int = 8) -> dict[str, Any]:
    """Find papers semantically similar to a given paper (pgvector cosine)."""
    from .db import embeddings as emb_db
    if not await emb_db.has_paper(paper_id):
        return {"status": "no_embedding", "paper_id": paper_id}
    rows = await emb_db.similar_to_paper(paper_id, k=k)
    return {"status": "ok", "paper_id": paper_id,
            "similar": [{"paper_id": r["id"], "title": r["title"],
                         "arxiv_id": r["arxiv_id"], "sim": round(float(r["sim"]), 3)}
                        for r in rows]}


@mcp.tool()
async def list_interests() -> dict[str, Any]:
    """List the research lines you're following."""
    rows = await personal.list_interests()
    return {"interests": [{"id": r["id"], "label": r["label"]} for r in rows]}


@mcp.tool()
async def my_papers(state: str | None = None) -> dict[str, Any]:
    """List papers by your state (seen/read/understood/dismissed), or all if omitted."""
    rows = await personal.list_by_state(state)
    return {"count": len(rows),
            "papers": [{"paper_id": r["id"], "title": r["title"], "arxiv_id": r["arxiv_id"],
                        "state": r["state"], "why": r["why"]} for r in rows]}


@mcp.tool()
async def synthesize_graph(paper_id: int) -> dict[str, Any]:
    """Queue a graph synthesis for a paper's analyzed sub-graph — lineage, open problems,
    contradictions, and a landscape map across the paper + its references. Background;
    result via get_synthesis + a synthesis_ready notification."""
    if await papers.get(paper_id) is None:
        return {"status": "not_found", "paper_id": paper_id}
    jid = await jobs_repo.enqueue("synthesize", root_paper_id=paper_id, triggered_by="manual")
    return {"status": "queued", "job_id": jid, "paper_id": paper_id}


@mcp.tool()
async def get_synthesis(paper_id: int) -> dict[str, Any]:
    """Return the latest graph synthesis for a paper (lineage/open-problems/contradictions/map)."""
    s = await syntheses.get_latest(str(paper_id))
    if s is None:
        return {"status": "none", "paper_id": paper_id}
    return {"status": "synthesis", "paper_id": paper_id,
            "lineage": s["lineage"], "open_problems": s["open_problems"],
            "contradictions": s["contradictions"], "landscape": s["map"],
            "created_at": s["created_at"].isoformat()}


@mcp.tool()
async def cost_summary() -> dict[str, Any]:
    """LLM spend so far: total + today, vs the daily budget."""
    t = await usage.totals()
    return {**t, "today_usd": round(await usage.today_cost(), 4),
            "daily_budget_usd": config.DAILY_BUDGET_USD}


@mcp.tool()
async def analyze_paper(paper_id: int) -> dict[str, Any]:
    """Queue deep grounded analysis (background/architecture, method, results, limitations).
    Runs in the background (~minutes via the LLM); results land on the card + a deep_ready
    notification. The card must already exist (survey first)."""
    if await papers.get(paper_id) is None:
        return {"status": "not_found", "paper_id": paper_id}
    jid = await jobs_repo.enqueue("analyze", root_paper_id=paper_id, triggered_by="manual")
    return {"status": "queued", "job_id": jid, "paper_id": paper_id}


@mcp.tool()
async def run_proactive_scan() -> dict[str, Any]:
    """Kick off a background scan for new arXiv papers on your followed interests.
    Results arrive as a digest notification (surfaced on the next heartbeat)."""
    jid = await jobs_repo.enqueue("proactive_scan", triggered_by="manual")
    return {"status": "queued", "job_id": jid}


# ── HTTP API for the OpenClaw hook (Theme A) — cheap graph lookups, no agent turn ──
@mcp.custom_route("/recognize", methods=["GET"])
async def http_recognize(request):
    from starlette.responses import JSONResponse
    from .recognize import recognize
    mention = request.query_params.get("mention", "")
    if not mention.strip():
        return JSONResponse({"in_graph": False, "error": "empty mention"})
    return JSONResponse(await recognize(mention))


@mcp.custom_route("/deepen", methods=["POST"])
async def http_deepen(request):
    from starlette.responses import JSONResponse
    body = await request.json()
    paper_id = body.get("paper_id")
    if not paper_id or await papers.get(int(paper_id)) is None:
        return JSONResponse({"status": "not_found"}, status_code=404)
    jid = await jobs_repo.enqueue("deepen", root_paper_id=int(paper_id),
                                  triggered_by="ambient", budget=body.get("target"),
                                  priority=200)   # low priority: behind user-requested work
    return JSONResponse({"status": "queued", "job_id": jid})


@mcp.custom_route("/healthz", methods=["GET"])
async def http_health(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"ok": True})


def main() -> None:
    log.info("surveyHelper MCP server on http://%s:%s (streamable-http + /recognize)",
             config.MCP_HOST, config.MCP_PORT)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
