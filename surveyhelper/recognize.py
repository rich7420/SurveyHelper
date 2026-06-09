"""Cheap graph recognition for ambient conversation (roadmap Theme A).

Given a free-text mention, decide if it's a paper already in our graph and return
what we know — with NO LLM and NO external API (only local DB + local embedding). This
is what the OpenClaw `before_prompt_build` hook calls on every message, so it must be
fast and side-effect-free.
"""

from __future__ import annotations

import re
from typing import Any

from . import config
from .db import analysis, graph, papers, personal
from .db import embeddings as emb_db
from .sources.identifiers import parse_identifier

EMBED_MATCH_THRESHOLD = 0.70   # cosine; below this a free-text mention isn't "in graph"


async def recognize(mention: str) -> dict[str, Any]:
    paper = await _resolve(mention)
    if paper is None:
        return {"in_graph": False}

    pid = paper["id"]
    a = await analysis.get(pid, config.PIPELINE_VERSION)
    state = await personal.get_state(pid)
    step_status = (a["step_status"] if a else None) or {}

    connections = []
    if await emb_db.has_paper(pid):
        connections = [{"paper_id": r["id"], "title": r["title"],
                        "sim": round(float(r["sim"]), 2)}
                       for r in await emb_db.similar_to_paper(pid, k=3)]

    # A3: graph distance to what you've already read ("2 hops from [X you read]")
    in_your_reading = [{"paper_id": r["id"], "title": r["title"],
                        "hops": r["hops"], "state": r["state"]}
                       for r in await graph.nearest_read_papers(pid, max_hops=2)]

    return {
        "in_graph": True,
        "paper_id": pid,
        "title": paper["title"],
        "arxiv_id": paper["arxiv_id"],
        "tldr": a["purpose"] if a else None,
        "user_state": state["state"] if state else None,
        "deep_analyzed": step_status.get("2") == "ok",
        "references": await papers.count_references(pid),
        "connections": connections,
        "in_your_reading": in_your_reading,
    }


async def _resolve(mention: str):
    """Best-effort: exact external id → title match → embedding nearest."""
    ref = parse_identifier(mention)
    if ref.kind in ("arxiv", "doi", "s2"):
        alias = {"arxiv": f"arxiv:{ref.value}", "doi": f"doi:{ref.value.lower()}",
                 "s2": f"s2:{ref.value}"}[ref.kind]
        p = await papers.find_by_alias(alias)
        if p:
            return p

    # free text: title-substring, then method-name tokens, then semantic nearest
    p = await papers.find_by_title_like(mention)
    if p:
        return p

    # Conversational mentions ("I'm reading the BERT paper by Devlin et al") dilute the
    # embedding below threshold, so first match distinctive method-name tokens (>=2 capitals:
    # BERT, ELMo, GPT, FlashAttention, RoBERTa) against a title PREFIX — the method name.
    for token in _name_tokens(mention):
        p = await papers.find_by_title_prefix(token)
        if p:
            return p

    try:
        from . import embeddings
        vec = await embeddings.embed_one(mention[:500])
        hits = await emb_db.similar(vec, k=1)
        if hits and float(hits[0]["sim"]) >= EMBED_MATCH_THRESHOLD:
            return await papers.get(hits[0]["id"])
    except Exception:
        pass
    return None


def _name_tokens(mention: str) -> list[str]:
    """Distinctive method-name tokens: length >= 3 with >= 2 uppercase letters (BERT, ELMo,
    GPT, RoBERTa, FlashAttention). Excludes ordinary words and author names (one capital)."""
    seen, out = set(), []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", mention):
        if sum(c.isupper() for c in tok) >= 2 and tok.lower() not in seen:
            seen.add(tok.lower())
            out.append(tok)
    return out
