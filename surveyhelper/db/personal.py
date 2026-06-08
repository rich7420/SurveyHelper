"""Personal-layer repository (plan §7/§11) — what makes it *memory*, not a cache.

- `paper_user_state` — per-paper state (seen/read/understood/dismissed) + *why* it was
  triggered. Drives personal dedup: don't resurface dismissed/read papers.
- `corrections` — human overrides of analysis fields, overlaid on every read (plan §11).
- `interests` — the research lines you follow (embedding column unused until Phase 6b).
"""

from __future__ import annotations

from typing import Any, Optional

import asyncpg

from . import get_pool

VALID_STATES = {"seen", "read", "understood", "dismissed"}


# ── per-paper state ──────────────────────────────────────────────────────────
async def set_state(paper_id: int, state: str, *, why: str | None = None,
                    interest_id: int | None = None) -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO paper_user_state (paper_id, state, why, interest_id)
           VALUES ($1,$2,$3,$4)
           ON CONFLICT (paper_id) DO UPDATE SET
               state = EXCLUDED.state,
               why = COALESCE(EXCLUDED.why, paper_user_state.why),
               interest_id = COALESCE(EXCLUDED.interest_id, paper_user_state.interest_id),
               updated_at = now()""",
        paper_id, state, why, interest_id,
    )


async def get_state(paper_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM paper_user_state WHERE paper_id = $1", paper_id)


async def dismissed_ids() -> set[int]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT paper_id FROM paper_user_state WHERE state = 'dismissed'")
    return {r["paper_id"] for r in rows}


async def list_by_state(state: str | None = None) -> list[asyncpg.Record]:
    pool = await get_pool()
    if state:
        return await pool.fetch(
            """SELECT s.state, s.why, s.updated_at, p.id, p.title, p.arxiv_id, p.year
               FROM paper_user_state s JOIN papers p ON p.id = s.paper_id
               WHERE s.state = $1 ORDER BY s.updated_at DESC""", state)
    return await pool.fetch(
        """SELECT s.state, s.why, s.updated_at, p.id, p.title, p.arxiv_id, p.year
           FROM paper_user_state s JOIN papers p ON p.id = s.paper_id
           ORDER BY s.updated_at DESC""")


# ── corrections (overlaid on reads) ──────────────────────────────────────────
async def add_correction(paper_id: int, field: str, value: Any, note: str | None = None) -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO corrections (paper_id, field, corrected_value, note)
           VALUES ($1,$2,$3,$4)""",
        paper_id, field, value, note,
    )


async def corrections_for(paper_id: int) -> dict[str, Any]:
    """Latest corrected value per field, for overlay on a card."""
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT DISTINCT ON (field) field, corrected_value
           FROM corrections WHERE paper_id = $1
           ORDER BY field, created_at DESC""", paper_id)
    return {r["field"]: r["corrected_value"] for r in rows}


# ── interests ────────────────────────────────────────────────────────────────
async def add_interest(label: str) -> int:
    pool = await get_pool()
    return await pool.fetchval(
        "INSERT INTO interests (label) VALUES ($1) RETURNING id", label)


async def list_interests(active_only: bool = True) -> list[asyncpg.Record]:
    pool = await get_pool()
    if active_only:
        return await pool.fetch(
            "SELECT id, label, active, created_at FROM interests WHERE active ORDER BY created_at")
    return await pool.fetch(
        "SELECT id, label, active, created_at FROM interests ORDER BY created_at")
