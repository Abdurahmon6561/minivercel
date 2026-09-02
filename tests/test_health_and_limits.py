"""Health endpoint, rate limiter, and the caches behind the serving flow."""

from __future__ import annotations

import time

import pytest

from app.cache import TTLCache
from app.ratelimit import RateLimiter
from app.routers import health


@pytest.fixture(autouse=True)
def reset_health_probe():
    health._last_probe = 0.0
    health._last_result = "unknown"
    yield


async def test_health_reports_the_database(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_health_still_answers_when_the_database_is_down(client, supabase, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("supabase is asleep")

    monkeypatch.setattr(supabase, "select", broken)
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "unreachable"


async def test_health_throttles_its_database_probe(client, supabase, monkeypatch):
    calls = {"n": 0}
    real = supabase.select

    async def counting(table, params):
        calls["n"] += 1
        return await real(table, params)

    monkeypatch.setattr(supabase, "select", counting)
    for _ in range(5):
        await client.get("/health")
    assert calls["n"] == 1, "keep-alive pings must not cost a query each"


async def test_root_endpoint(client):
    assert (await client.get("/")).json()["service"] == "minivercel"


# -- rate limiter -----------------------------------------------------------


def test_rate_limiter_counts_per_key():
    limiter = RateLimiter(2, 60.0)
    assert limiter.check("a").allowed
    assert limiter.check("a").allowed
    assert not limiter.check("a").allowed
    assert limiter.check("b").allowed, "keys are independent"


def test_rate_limiter_window_expires():
    limiter = RateLimiter(1, 0.05)
    assert limiter.check("a").allowed
    assert not limiter.check("a").allowed
    time.sleep(0.3)
    assert limiter.check("a").allowed


def test_rate_limiter_reports_retry_after():
    limiter = RateLimiter(1, 60.0)
    limiter.check("a")
    assert limiter.check("a").retry_after >= 1


def test_rate_limiter_disabled_when_limit_is_zero():
    limiter = RateLimiter(0, 60.0)
    assert all(limiter.check("a").allowed for _ in range(100))


def test_rate_limiter_does_not_grow_without_bound():
    limiter = RateLimiter(5, 0.01)
    for index in range(3000):
        limiter.check("ip-%d" % index)
    time.sleep(0.3)
    limiter.check("trigger-a-sweep")
    limiter._maybe_sweep(time.monotonic() + 1000)
    assert len(limiter._hits) < 3000


# -- cache ------------------------------------------------------------------


def test_ttl_cache_expires():
    cache = TTLCache(maxsize=10, ttl=0.05)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    time.sleep(0.3)
    assert cache.get("k") is None


def test_ttl_cache_evicts_least_recently_used():
    cache = TTLCache(maxsize=2, ttl=0.0)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")          # 'a' is now the most recently used
    cache.set("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_ttl_cache_zero_ttl_never_expires():
    cache = TTLCache(maxsize=10, ttl=0.0)
    cache.set("k", "v")
    time.sleep(0.1)
    assert cache.get("k") == "v"


async def test_health_and_root_answer_head(client):
    """Uptime monitors and platform health checks may send HEAD, not GET."""
    for path in ("/health", "/"):
        response = await client.head(path)
        assert response.status_code == 200, path


async def test_head_probe_still_reports_through_get(client):
    """HEAD carries no body, so the JSON is only observable on GET."""
    assert (await client.head("/health")).status_code == 200
    assert (await client.get("/health")).json()["status"] == "ok"
