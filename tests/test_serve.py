"""Tests for GET /s/{slug}/{path} - resolution, redirects, and what we refuse."""

from __future__ import annotations

import pytest

from app import cache, deps
from app.ratelimit import RateLimiter
from app.store import Store

from .conftest import auth_headers, deploy, make_zip
from .fake_supabase import FakeSupabase

SITE = {
    "index.html": "<h1>home</h1>",
    "about.html": "<h1>about</h1>",
    "docs/index.html": "<h1>docs</h1>",
    "assets/app.css": "body{}",
    "404.html": "<h1>gone</h1>",
}

STORAGE = "https://fake.supabase.co/storage/v1/object/public/sites"


async def deployed(client, files=None, slug="demo"):
    response = await deploy(client, make_zip(files or SITE), slug=slug)
    assert response.status_code == 201, response.text
    cache.clear_all()
    return response.json()["id"]


# -- resolution -------------------------------------------------------------


@pytest.mark.parametrize(
    "path, expected",
    [
        ("", "index.html"),
        ("index.html", "index.html"),
        ("about.html", "about.html"),
        ("about", "about.html"),            # clean URL -> {path}.html
        ("docs", "docs/index.html"),        # clean URL -> {path}/index.html
        ("docs/", "docs/index.html"),       # trailing slash -> index.html
        ("assets/app.css", "assets/app.css"),
    ],
)
async def test_path_resolution(client, path, expected):
    deployment_id = await deployed(client)
    response = await client.get("/s/demo/" + path)
    assert response.status_code == 307
    assert response.headers["location"] == "%s/%s/%s" % (STORAGE, deployment_id, expected)


async def test_redirect_carries_the_security_headers(client):
    await deployed(client)
    response = await client.get("/s/demo/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "must-revalidate" in response.headers["cache-control"]


async def test_bytes_are_never_proxied(client):
    """NON-NEGOTIABLE #2: the response is a redirect, never the file itself."""
    await deployed(client)
    response = await client.get("/s/demo/index.html")
    assert response.status_code == 307
    assert response.content == b""
    assert "<h1>home</h1>" not in response.text


async def test_missing_path_falls_back_to_404_html(client):
    deployment_id = await deployed(client)
    response = await client.get("/s/demo/nope/deeper")
    assert response.status_code == 307
    assert response.headers["location"].endswith("/%s/404.html" % deployment_id)
    assert response.headers["x-minivercel-fallback"] == "404"


async def test_plain_404_when_the_site_has_no_404_page(client):
    await deployed(client, {"index.html": "hi"})
    response = await client.get("/s/demo/missing")
    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_unknown_slug_is_404(client):
    response = await client.get("/s/no-such-site/")
    assert response.status_code == 404


async def test_invalid_slug_is_404_without_touching_the_database(client, supabase):
    response = await client.get("/s/NOT_A_SLUG!!/")
    assert response.status_code == 404


async def test_project_without_a_live_deployment_is_404(client, supabase):
    await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "Empty", "slug": "empty"}
    )
    cache.clear_all()
    response = await client.get("/s/empty/")
    assert response.status_code == 404
    assert "no live deployment" in response.text.lower()


async def test_no_trailing_slash_redirects_to_the_root(client):
    await deployed(client)
    response = await client.get("/s/demo")
    assert response.status_code == 308
    assert response.headers["location"] == "/s/demo/"


@pytest.mark.parametrize(
    "path", ["%2e%2e/secret", "%2e%2e%2f%2e%2e%2fsecret", "docs/%2e%2e/%2e%2e/secret"]
)
async def test_percent_encoded_traversal_is_refused(client, path):
    """Percent-encoded dots survive every proxy and land on us as `..`."""
    await deployed(client)
    response = await client.get("/s/demo/" + path)
    assert response.status_code == 404
    assert "location" not in response.headers


async def test_literal_traversal_is_refused(client):
    """A bare `../secret` never reaches the app through an HTTP client - httpx,
    browsers and proxies all normalise it away - so drive the handler directly.
    """
    from starlette.requests import Request

    from app.routers.serve import serve

    await deployed(client)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/s/demo/../secret",
            "headers": [],
            "query_string": b"",
            "client": ("203.0.113.7", 1234),
        }
    )
    response = await serve("demo", "../secret", request)
    assert response.status_code == 404
    assert "location" not in response.headers


async def test_redeploy_is_visible_immediately(client):
    first = await deployed(client)
    second = await deployed(client, {"index.html": "v2", "404.html": "x"})
    assert first != second
    response = await client.get("/s/demo/")
    assert second in response.headers["location"]


# -- manifest fallback ------------------------------------------------------


async def test_serving_works_without_the_manifest_column(client):
    """db/002_file_manifest.sql not applied: fall back to probing Storage."""
    legacy = FakeSupabase(supports_manifest=False)
    deps.set_store(Store(legacy))
    cache.clear_all()

    deployment_id = await deployed(client)
    assert legacy.tables["deployments"][0]["file_paths"] is None

    response = await client.get("/s/demo/about")
    assert response.status_code == 307
    assert response.headers["location"].endswith("/%s/about.html" % deployment_id)

    missing = await client.get("/s/demo/nope")
    assert missing.headers["location"].endswith("/%s/404.html" % deployment_id)


# -- rate limiting ----------------------------------------------------------


async def test_rate_limit_kicks_in(client):
    await deployed(client)
    deps.set_limiters(serve=RateLimiter(3, 60.0))

    codes = [(await client.get("/s/demo/")).status_code for _ in range(5)]
    assert codes[:3] == [307, 307, 307]
    assert codes[3:] == [429, 429]

    limited = await client.get("/s/demo/")
    assert int(limited.headers["retry-after"]) >= 1


# -- upstream outages -------------------------------------------------------


async def test_supabase_outage_is_503_not_404(client, supabase, monkeypatch):
    """A Supabase blip must not tell the world every site was deleted."""
    await deployed(client)

    async def broken(*args, **kwargs):
        raise RuntimeError("getaddrinfo failed")

    monkeypatch.setattr(supabase, "select", broken)
    response = await client.get("/s/demo/")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"


async def test_an_outage_is_never_cached_as_missing(client, supabase, monkeypatch):
    await deployed(client)
    real = supabase.select
    down = {"yes": True}

    async def flaky(table, params):
        if down["yes"]:
            raise RuntimeError("getaddrinfo failed")
        return await real(table, params)

    monkeypatch.setattr(supabase, "select", flaky)
    assert (await client.get("/s/demo/")).status_code == 503

    down["yes"] = False
    assert (await client.get("/s/demo/")).status_code == 307
