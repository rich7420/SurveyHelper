"""Shared HTTP egress with pacing + retry/backoff.

This is the single network entry point for paper APIs: it acquires the global
per-source limiter (plan §9) and retries on 429/5xx with exponential backoff,
honoring Retry-After (plan §9 "+ backoff"). One shared AsyncClient gives
connection reuse. Per DECISIONS.md §H, all paper-API egress flows through here.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from . import config
from .logging_setup import get
from .ratelimit import limiter

log = get("http")

_client: Optional[httpx.AsyncClient] = None

_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_BASE_BACKOFF = 2.0   # seconds


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": config.USER_AGENT},
            follow_redirects=True,
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def request(source: str, method: str, url: str, *,
                  params: dict[str, Any] | None = None,
                  headers: dict[str, str] | None = None) -> httpx.Response:
    """Paced + retried request. Raises on the final failure."""
    client = await get_client()
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        await limiter.acquire(source)
        try:
            resp = await client.request(method, url, params=params, headers=headers)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt >= _MAX_RETRIES:
                raise
            delay = _BASE_BACKOFF * (2 ** attempt)
            log.warning("%s %s transport error (%s); retry in %.1fs", source, url, exc, delay)
            await asyncio.sleep(delay)
            continue

        if resp.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
            delay = _retry_after(resp) or _BASE_BACKOFF * (2 ** attempt)
            log.warning("%s %s -> %s; retry in %.1fs (attempt %d)",
                        source, url, resp.status_code, delay, attempt + 1)
            await asyncio.sleep(delay)
            continue
        return resp
    if last_exc:
        raise last_exc
    return resp  # type: ignore[name-defined]


async def get_json(source: str, url: str, *, params=None, headers=None) -> Any:
    resp = await request(source, "GET", url, params=params, headers=headers)
    resp.raise_for_status()
    return resp.json()


async def get_text(source: str, url: str, *, params=None, headers=None) -> str:
    resp = await request(source, "GET", url, params=params, headers=headers)
    resp.raise_for_status()
    return resp.text


def _retry_after(resp: httpx.Response) -> Optional[float]:
    ra = resp.headers.get("Retry-After")
    if not ra:
        return None
    try:
        return float(ra)
    except ValueError:
        return None
