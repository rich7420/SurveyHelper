"""Phase 7 — proactivity: the ambient dimension (plan §8).

A low-frequency scan: for each active interest, find new arXiv papers since the last
scan, dedup against what's already known / what you've dismissed, cheap-card the top
few, and emit ONE digest notification. Reuses the worker, rate buckets, and
notifications — no new machinery. Keyword-matched for now; embedding relevance is a
later refinement (Phase 6b).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from ..db import notifications, papers, personal, settings
from ..logging_setup import get
from ..sources import arxiv
from .card import survey

log = get("proactive")

_LAST_SCAN_KEY = "last_proactive_scan"
DEFAULT_WINDOW_DAYS = 7
MAX_PER_INTEREST = 25
CARDS_PER_INTEREST = 3


async def _since() -> _dt.datetime:
    raw = await settings.get(_LAST_SCAN_KEY)
    if raw:
        try:
            return _dt.datetime.fromisoformat(raw)
        except ValueError:
            pass
    return _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=DEFAULT_WINDOW_DAYS)


async def run_scan() -> dict[str, Any]:
    interests = await personal.list_interests()
    if not interests:
        return {"interests": 0, "new": 0, "reason": "no_interests"}

    since = await _since()
    digest: dict[str, list[dict]] = {}
    total_new = 0

    for interest in interests:
        label = interest["label"]
        try:
            results = await arxiv.search_recent(label, max_results=MAX_PER_INTEREST, since=since)
        except Exception as exc:
            log.warning("scan: arXiv search failed for '%s' (%s)", label, exc)
            continue

        carded = []
        for meta in results:
            # dedup: skip anything we already track (cards, references, dismissed)
            if await papers.find_by_alias(f"arxiv:{meta.arxiv_id}"):
                continue
            res = await survey(meta.arxiv_id, enqueue_enrich=False, enqueue_deep=False)
            if res.card:
                carded.append({"paper_id": res.card.paper_id, "title": res.card.title,
                               "arxiv_id": res.card.arxiv_id})
            if len(carded) >= CARDS_PER_INTEREST:
                break
        if carded:
            digest[label] = carded
            total_new += len(carded)

    if digest:
        await notifications.add("proactive_digest",
                                {"by_interest": digest, "total": total_new},
                                digest_key="proactive")
    await settings.set(_LAST_SCAN_KEY, _dt.datetime.now(_dt.timezone.utc).isoformat())
    log.info("proactive scan: %d interests, %d new papers surfaced", len(interests), total_new)
    return {"interests": len(interests), "new": total_new}
