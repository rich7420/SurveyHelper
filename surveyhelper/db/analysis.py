"""Derived-analysis repository (the card and, later, deep steps).

Versioned by `pipeline_version` — a better model later adds a row, never a silent
overwrite (plan §4). Corrections are overlaid on read (plan §11) — TODO Phase 6.
"""

from __future__ import annotations

from typing import Optional

import asyncpg

from . import get_pool


async def save(paper_id: int, pipeline_version: str, *, step_status: dict,
               purpose: str | None = None, pain_point: str | None = None,
               code: dict | None = None, provenance: dict | None = None,
               model_used: str | None = None) -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO paper_analysis
               (paper_id, pipeline_version, step_status, purpose, pain_point,
                code, provenance, model_used)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
           ON CONFLICT (paper_id, pipeline_version) DO UPDATE SET
               step_status = EXCLUDED.step_status,
               purpose     = EXCLUDED.purpose,
               pain_point  = EXCLUDED.pain_point,
               code        = EXCLUDED.code,
               provenance  = EXCLUDED.provenance,
               model_used  = EXCLUDED.model_used,
               analyzed_at = now()""",
        paper_id, pipeline_version, step_status, purpose, pain_point,
        code, provenance, model_used,
    )


async def get(paper_id: int, pipeline_version: str) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow(
        "SELECT * FROM paper_analysis WHERE paper_id = $1 AND pipeline_version = $2",
        paper_id, pipeline_version,
    )
