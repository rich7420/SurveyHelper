"""Phase 5 — synthesize: the payoff of going deep (plan §6).

A *reduce* over a root paper's analyzed sub-graph. Instead of N disconnected cards it
produces the lineage of the idea, the open problems recurring across the set, the
contradictions, and a landscape map. Reduces over the compact per-paper content we
already have (tldr + structured deep fields) — so it works off the cheap card tier and
does NOT require every paper to be deep-analyzed. One LLM call.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .. import config
from ..db import analysis, notifications, papers, syntheses, usage
from ..llm.claude_cli import complete
from ..logging_setup import get
from .verify import verify_contradictions_grounded

log = get("synthesize")

MAX_PAPERS = 40
_SYSTEM = (
    "You are a research-survey analyst. Given a root paper and its references (each with a "
    "short summary), synthesize the intellectual landscape. Be specific and grounded ONLY in "
    "the provided summaries — do not invent papers or claims. Return JSON only."
)
_SCHEMA = ('{"lineage": ["<how the core idea evolved across these papers, ordered>"], '
           '"open_problems": ["<limitations/questions recurring or unsolved across the set>"], '
           '"contradictions": ["<claims or results that conflict, with which papers>"], '
           '"landscape": {"clusters": ["<theme: representative papers>"], '
           '"key_nodes": ["<the most influential/central papers and why>"]}}')

# Provenance-carrying schema: every claim cites the paper ids it draws from (B2).
_SCHEMA_PROV = (
    '{"lineage": [{"step": "<what this stage added>", "papers": [<id>, ...]}], '
    '"open_problems": [{"problem": "<recurring/unsolved across the set>", "papers": [<id>, ...]}], '
    '"contradictions": [{"claim": "<what conflicts and how>", "papers": [<id>, <id>]}], '
    '"landscape": {"clusters": ["<theme: representative titles>"], "key_nodes": [<id>, ...]}}')


def _content_blob(item: dict) -> str:
    """Compact, grounded content for a paper — what the verifier checks claims against."""
    parts = [item.get("title", ""), item.get("summary", "")]
    if item.get("core_idea"):
        parts.append(f"core: {item['core_idea']}")
    if item.get("limitations"):
        parts.append(f"limits: {item['limitations']}")
    return " | ".join(p for p in parts if p)


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


async def _gather(root_id: int) -> tuple[Any, list[dict]]:
    """Root + the references that have at least a card summary, compacted for the prompt."""
    root = await papers.get(root_id)
    rows = [(root, True)] + [(r, r["is_influential"]) for r in await papers.references_of(root_id)]
    items: list[dict] = []
    for r, influential in rows:
        a = await analysis.get(r["id"], config.PIPELINE_VERSION)
        if not a or not a["purpose"]:
            continue
        item = {"id": r["id"], "arxiv_id": r["arxiv_id"], "title": (r["title"] or "")[:160],
                "year": r["year"], "influential": bool(influential), "summary": a["purpose"][:300]}
        arch = (a["architecture"] or {}).get("data") if a["architecture"] else None
        lim = (a["limitations"] or {}).get("data") if a["limitations"] else None
        if arch and arch.get("core_idea"):
            item["core_idea"] = arch["core_idea"][:200]
        if lim:
            item["limitations"] = lim
        items.append(item)
    # prefer influential papers when capping
    items.sort(key=lambda x: (not x["influential"]))
    return root, items[:MAX_PAPERS]


async def synthesize(root_id: int, *, job_id: int | None = None) -> dict[str, Any]:
    root, items = await _gather(root_id)
    if root is None:
        return {"synthesized": False, "reason": "paper_not_found"}
    if len(items) < 3:
        return {"synthesized": False, "reason": "insufficient_analyzed_papers", "have": len(items)}
    if await usage.today_cost() >= config.DAILY_BUDGET_USD:
        await notifications.add("budget_paused", {"root_paper_id": root_id}, job_id=job_id)
        return {"synthesized": False, "reason": "daily_budget_reached"}

    payload = json.dumps(items, ensure_ascii=False)
    prompt = (f"ROOT PAPER: {root['title']}\n\nPAPER SET (root + references), as JSON — each "
              f"paper has an integer `id`:\n{payload}\n\nSynthesize the landscape across this "
              f"set. Cite the `id`s each claim draws from. Return JSON ONLY matching:\n{_SCHEMA_PROV}")
    c = await complete(prompt, model=config.LLM_MODEL, system=_SYSTEM)
    await usage.add(job_id=job_id, source="llm", calls=1,
                    tokens=c.input_tokens + c.output_tokens, cost_usd=c.cost_usd)
    data = _extract_json(c.text) or {}

    # M2a (L2): verify each contradiction against the cited papers' FULL TEXT — quote real
    # spans from both sides or abstain (tentative). Grounds trust in the source, not summaries.
    arxiv_map = {it["id"]: it["arxiv_id"] for it in items if it.get("arxiv_id")}
    contradictions, n_verified = await verify_contradictions_grounded(
        data.get("contradictions") or [], arxiv_map, job_id=job_id)

    # paper_set carries id->title so cited ids in claims are resolvable (B2 provenance).
    sid = await syntheses.save(
        scope="paper", root_or_topic=str(root_id),
        paper_set=[{"paper_id": it["id"], "title": it["title"]} for it in items],
        lineage=data.get("lineage"), open_problems=data.get("open_problems"),
        contradictions=contradictions, map=data.get("landscape"),
        pipeline_version=config.PIPELINE_VERSION,
    )
    n_contra = len(contradictions)
    log.info("synthesized root=%s over %d papers; %d/%d contradictions verified",
             root_id, len(items), n_verified, n_contra)
    await notifications.add("synthesis_ready",
                            {"root_paper_id": root_id, "title": root["title"],
                             "papers": len(items), "synthesis_id": sid,
                             "contradictions_verified": f"{n_verified}/{n_contra}"},
                            job_id=job_id, digest_key=f"synth:{root_id}")
    return {"synthesized": True, "papers": len(items), "synthesis_id": sid,
            "contradictions": n_contra, "verified": n_verified, "cost_usd": c.cost_usd}
