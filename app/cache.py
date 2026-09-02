"""Two tiny in-process caches used by the serving flow.

Serving is the hot path and it must not cost a database round-trip per asset
request. Two different lifetimes:

  slug -> project        mutable (a deploy changes live_deployment_id), so a
                         short TTL. 15 seconds means a fresh deploy goes live
                         almost immediately while a busy site still gets ~99%
                         of its requests served from memory. Explicitly
                         invalidated on deploy and delete, so the TTL is only a
                         backstop for a second instance or a manual DB edit.

  deployment -> manifest immutable once `ready`, so it never expires; only the
                         LRU bound evicts it.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, maxsize: int, ttl: float) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: "OrderedDict[str, tuple[float, T]]" = OrderedDict()

    def get(self, key: str) -> T | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self.ttl and expires_at <= time.monotonic():
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: T) -> None:
        expires_at = time.monotonic() + self.ttl if self.ttl else 0.0
        self._data[key] = (expires_at, value)
        self._data.move_to_end(key)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()


# slug -> project row (or the sentinel below for a known-missing slug)
MISSING: Any = object()

project_cache: TTLCache[Any] = TTLCache(maxsize=2000, ttl=15.0)

# deployment id -> frozenset of file paths
manifest_cache: TTLCache[frozenset] = TTLCache(maxsize=500, ttl=0.0)


def clear_all() -> None:
    project_cache.clear()
    manifest_cache.clear()
