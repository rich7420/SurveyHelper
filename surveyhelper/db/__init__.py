"""Postgres access layer (asyncpg). The DB *is* the cache (plan §9).

Submodules are thin repositories: `papers`, `analysis`, `jobs`, `notifications`.
"""

from __future__ import annotations

import json
from typing import Optional

import asyncpg

from .. import config

_pool: Optional[asyncpg.Pool] = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    for typ in ("jsonb", "json"):
        await conn.set_type_codec(
            typ, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(config.DSN, init=_init_conn, min_size=1, max_size=8)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
