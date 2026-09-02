"""Shared singletons and FastAPI dependencies."""

from __future__ import annotations

from .config import get_settings
from .ratelimit import RateLimiter
from .store import Store
from .supabase import SupabaseClient

_client: SupabaseClient | None = None
_store: Store | None = None

_serve_limiter: RateLimiter | None = None
_upload_limiter: RateLimiter | None = None


def get_client() -> SupabaseClient:
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store(get_client())
    return _store


def set_store(store: Store | None) -> None:
    """Test seam. Production never calls this."""
    global _store, _client
    _store = store
    _client = store.db if store is not None else None


def serve_limiter() -> RateLimiter:
    global _serve_limiter
    if _serve_limiter is None:
        _serve_limiter = RateLimiter(get_settings().serve_rate_limit_per_min, 60.0)
    return _serve_limiter


def upload_limiter() -> RateLimiter:
    global _upload_limiter
    if _upload_limiter is None:
        _upload_limiter = RateLimiter(get_settings().upload_rate_limit_per_hour, 3600.0)
    return _upload_limiter


def reset_limiters() -> None:
    global _serve_limiter, _upload_limiter
    _serve_limiter = None
    _upload_limiter = None


def set_limiters(serve: RateLimiter | None = None, upload: RateLimiter | None = None) -> None:
    """Test seam. Production never calls this."""
    global _serve_limiter, _upload_limiter
    if serve is not None:
        _serve_limiter = serve
    if upload is not None:
        _upload_limiter = upload


async def shutdown() -> None:
    global _client, _store
    if _client is not None:
        await _client.aclose()
    _client = None
    _store = None
