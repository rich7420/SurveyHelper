"""Graph-synthesis repository (plan §6). One row per reduce over a paper set."""

from __future__ import annotations

from typing import Any, Optional

import asyncpg

from . import get_pool


async def save(*, scope: str, root_or_topic: str, paper_set: list, lineage: Any,
               open_problems: Any, contradictions: Any, map: Any,
               pipeline_version: str) -> int:
    pool = await get_pool()
    return await pool.fetchval(
        """INSERT INTO syntheses
               (scope, root_or_topic, paper_set, lineage, open_problems,
                contradictions, map, pipeline_version)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
        scope, root_or_topic, paper_set, lineage, open_problems,
        contradictions, map, pipeline_version,
    )


async def get_latest(root_or_topic: str) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow(
        """SELECT * FROM syntheses WHERE root_or_topic = $1
           ORDER BY created_at DESC LIMIT 1""", root_or_topic)
