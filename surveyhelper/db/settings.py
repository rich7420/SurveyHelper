"""Settings repository — the setup-interview answers + small operational state (plan §9)."""

from __future__ import annotations

from typing import Any, Optional

from . import get_pool


async def get(key: str) -> Optional[Any]:
    pool = await get_pool()
    return await pool.fetchval("SELECT value FROM settings WHERE key = $1", key)


async def set(key: str, value: Any) -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO settings (key, value) VALUES ($1, $2)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
        key, value,
    )
