"""surveyHelper MCP server — the front door OpenClaw calls (plan §12).

Returns the instant card synchronously (steps 0/1/3/7) and enqueues deep work for
the worker. HTTP (streamable-http) transport so a Dockerized OpenClaw can reach it
via host.docker.internal.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import config
from .db import jobs as jobs_repo
from .db import notifications, papers
from .logging_setup import get
from .pipeline.card import _assemble, survey as _survey

log = get("mcp")

mcp = FastMCP("surveyHelper", host=config.MCP_HOST, port=config.MCP_PORT)


@mcp.tool()
async def survey(identifier: str, references_limit: int = 50) -> dict[str, Any]:
    """Survey a paper: return an instant card (purpose, references, code) in seconds.

    `identifier` may be an arXiv id (e.g. "2310.01889" or "arXiv:2310.01889"), a DOI,
    a Semantic Scholar id, a paper URL, or a paper title. A fuzzy title returns
    candidates to disambiguate. Deep grounded analysis is queued and fills in later.
    """
    res = await _survey(identifier, references_limit=references_limit)
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


def main() -> None:
    log.info("surveyHelper MCP server on http://%s:%s (streamable-http)",
             config.MCP_HOST, config.MCP_PORT)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
