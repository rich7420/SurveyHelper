"""Graph traversal over the citation edges (roadmap A3).

Kept behind the repo boundary so the backend can later move to materialized metrics
or a graph extension (Apache AGE) without touching callers. Recursive CTE is fine to
~depth 3 on a single-user graph; materialize if it grows hot.
"""

from __future__ import annotations

import asyncpg

from . import get_pool


async def nearest_read_papers(paper_id: int, *, max_hops: int = 2,
                              limit: int = 3) -> list[asyncpg.Record]:
    """Papers you've read/understood within `max_hops` of `paper_id` (undirected),
    nearest first — "this is 2 hops from [X you read]"."""
    pool = await get_pool()
    return await pool.fetch(
        """
        WITH RECURSIVE reach(id, hops) AS (
            SELECT $1::bigint, 0
          UNION
            SELECT CASE WHEN c.src = r.id THEN c.dst ELSE c.src END, r.hops + 1
            FROM reach r
            JOIN citations c ON (c.src = r.id OR c.dst = r.id)
            WHERE r.hops < $2
        )
        SELECT p.id, p.title, MIN(reach.hops) AS hops, s.state
        FROM reach
        JOIN papers p ON p.id = reach.id
        JOIN paper_user_state s ON s.paper_id = p.id AND s.state IN ('read', 'understood')
        WHERE reach.id <> $1
        GROUP BY p.id, p.title, s.state
        ORDER BY MIN(reach.hops), p.id
        LIMIT $3
        """,
        paper_id, max_hops, limit)
