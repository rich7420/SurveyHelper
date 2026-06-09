"""Postgres access layer (asyncpg). The DB *is* the cache (plan §9).

Submodules are thin repositories: `papers`, `analysis`, `jobs`, `notifications`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import asyncpg

from .. import config
from ..logging_setup import get

_pool: Optional[asyncpg.Pool] = None


async def apply_schema() -> bool:
    """Apply schema.sql idempotently (every statement is IF NOT EXISTS) so upgrades that add
    tables never break an existing install. Safe to call on every boot."""
    candidates = [Path(__file__).resolve().parents[2] / "schema.sql",
                  Path("/app/schema.sql"), Path("schema.sql")]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        get("db").warning("schema.sql not found (looked in %s); skipping auto-apply",
                          ", ".join(str(p) for p in candidates))
        return False
    pool = await get_pool()
    await pool.execute(path.read_text())     # multi-statement script via simple query protocol
    get("db").info("schema applied (idempotent) from %s", path)
    return True


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
