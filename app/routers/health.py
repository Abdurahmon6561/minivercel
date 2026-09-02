"""GET /health - the keep-alive endpoint HetrixTools pings every 10 minutes.

It has two jobs and they pull in opposite directions:

  * answer instantly, so the monitor never records a timeout and Render never
    counts the instance as idle;
  * touch Postgres occasionally, because Supabase pauses a free project after
    seven days with no database activity - and a health check that only proves
    the web process is alive would let the database go to sleep underneath it.

So the database probe is throttled: at most one trivial query every five
minutes, and the cached result is what the response reports. A ping costs one
round-trip twice an hour, not every ten minutes.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter

from ..deps import get_store

log = logging.getLogger("minivercel.health")

router = APIRouter(tags=["health"])

DB_PROBE_INTERVAL_SECONDS = 300.0

_last_probe = 0.0
_last_result = "unknown"


async def _probe_database() -> str:
    global _last_probe, _last_result

    now = time.monotonic()
    if _last_result != "unknown" and (now - _last_probe) < DB_PROBE_INTERVAL_SECONDS:
        return _last_result

    _last_probe = now
    try:
        await get_store().db.select("projects", {"select": "id", "limit": "1"})
        _last_result = "ok"
    except Exception as exc:
        log.warning("database probe failed: %s", exc)
        _last_result = "unreachable"
    return _last_result


@router.get("/health")
async def health():
    return {"status": "ok", "database": await _probe_database()}


@router.get("/")
async def root():
    return {
        "service": "minivercel",
        "docs": "/docs",
        "health": "/health",
    }
