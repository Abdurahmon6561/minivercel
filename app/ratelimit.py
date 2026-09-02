"""In-memory sliding-window rate limiting.

SPEC.md: "60 requests/minute per IP. In-memory dict is fine at this scale."
It is - with one caveat this module handles: an unbounded dict keyed by client
IP is a memory leak on a 512 MB dyno, so buckets are swept on a schedule and the
key count is capped. When the cap is hit we shed the oldest buckets rather than
refusing traffic.

One process, one dict. Render free tier runs a single instance, so there is
nothing to share across.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

MAX_TRACKED_KEYS = 20_000
SWEEP_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int  # seconds; 0 when allowed


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = float(window_seconds)
        self._hits: dict[str, deque[float]] = {}
        self._last_sweep = time.monotonic()

    def check(self, key: str) -> Decision:
        """Record a hit for `key` and say whether it is allowed."""
        if self.limit <= 0:
            return Decision(True, 0)

        now = time.monotonic()
        self._maybe_sweep(now)

        bucket = self._hits.get(key)
        if bucket is None:
            bucket = deque()
            self._hits[key] = bucket

        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= self.limit:
            retry_after = max(1, int(bucket[0] + self.window - now) + 1)
            return Decision(False, retry_after)

        bucket.append(now)
        return Decision(True, 0)

    def _maybe_sweep(self, now: float) -> None:
        if now - self._last_sweep < SWEEP_INTERVAL_SECONDS:
            if len(self._hits) <= MAX_TRACKED_KEYS:
                return
        self._last_sweep = now
        cutoff = now - self.window
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]

        # Still oversized after the sweep: drop the least recently active.
        if len(self._hits) > MAX_TRACKED_KEYS:
            ordered = sorted(self._hits.items(), key=lambda item: item[1][-1])
            for key, _ in ordered[: len(self._hits) - MAX_TRACKED_KEYS]:
                del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


def client_ip(request) -> str:
    """Best-effort client address.

    Render terminates TLS at its edge and sets X-Forwarded-For, so the direct
    peer address is always the proxy. We take the left-most entry, which is
    spoofable by the client - acceptable here because this limiter protects CPU,
    not authorisation. Nothing security-relevant keys off this value.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
