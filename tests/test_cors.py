"""CORS preflight.

The dashboard is on a different origin from the API by design (see
web/README.md), so every non-GET call it makes is preceded by an OPTIONS
preflight. A preflight that does not return 2xx blocks the real request, and the
browser reports it as "does not have HTTP ok status" without saying which check
failed.

This file exists because `PATCH /api/projects/{slug}` shipped with PATCH missing
from `allow_methods`. `test_every_routed_method_is_allowed` is the regression
guard: it fails when a new verb is routed without being allowed, which is the
mistake that caused it rather than the symptom.
"""

from __future__ import annotations

import pytest

from app.main import ALLOWED_HEADERS, ALLOWED_METHODS, app

ORIGIN = "http://localhost:5173"


def preflight(method: str, headers: str = "authorization,content-type") -> dict:
    return {
        "Origin": ORIGIN,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": headers,
    }


async def test_patch_preflight_succeeds(client):
    """The reported failure, as the browser makes it."""
    response = await client.options(
        "/api/projects/macbook-react-jsx", headers=preflight("PATCH")
    )

    assert response.status_code == 200, response.text
    allowed = response.headers["access-control-allow-methods"]
    assert "PATCH" in allowed
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
async def test_preflight_succeeds_for_every_method_the_dashboard_uses(client, method):
    response = await client.options(
        "/api/projects/some-slug", headers=preflight(method)
    )
    assert response.status_code == 200, method
    assert method in response.headers["access-control-allow-methods"]


async def test_preflight_needs_no_credentials(client):
    """A browser sends a preflight with no Authorization header.

    If auth ran before CORSMiddleware this would be a 401, and the real request
    would never be sent. CORSMiddleware is the outermost layer precisely so a
    preflight is answered before routing.
    """
    response = await client.options(
        "/api/projects/anything", headers=preflight("PATCH")
    )
    assert response.status_code == 200
    assert "www-authenticate" not in response.headers


async def test_preflight_is_not_rate_limited(client):
    """Rate limiting lives in the handlers, so it cannot see a preflight.

    Were it middleware sitting outside CORS, a burst of tab reloads would start
    answering preflights with 429 and the dashboard would break under exactly
    the load that matters.
    """
    for _ in range(60):
        response = await client.options(
            "/api/projects/hot-slug", headers=preflight("PATCH")
        )
        assert response.status_code == 200


async def test_preflight_for_an_unknown_path_still_succeeds(client):
    """Preflight is answered before routing, so a 404 path is not a CORS failure.

    Otherwise a typo'd URL would surface as an unexplained CORS error rather
    than the 404 it actually is.
    """
    response = await client.options(
        "/api/does-not-exist", headers=preflight("PATCH")
    )
    assert response.status_code == 200


async def test_an_unlisted_origin_is_refused(client):
    """allow_origins is a list, not a wildcard - the point of listing it."""
    response = await client.options(
        "/api/projects/x",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "PATCH",
        },
    )
    assert response.headers.get("access-control-allow-origin") != "https://evil.example"


async def test_an_unlisted_method_is_refused(client):
    response = await client.options(
        "/api/projects/x", headers=preflight("TRACE")
    )
    assert response.status_code != 200


async def test_the_real_patch_carries_the_origin_header(client):
    """The preflight passing is only half of it: the actual response needs the
    header too, or the browser discards a perfectly good 200."""
    from .conftest import auth_headers

    await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "CORS", "slug": "cors-check"}
    )
    response = await client.patch(
        "/api/projects/cors-check",
        headers={**auth_headers(), "Origin": ORIGIN},
        json={"auto_deploy_enabled": False},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_every_routed_method_is_allowed():
    """The regression guard.

    PATCH was routed and not allowed, and nothing failed until a browser tried
    it. Any new verb now fails here instead.
    """
    routed: set[str] = set()
    for route in app.routes:
        routed |= set(getattr(route, "methods", None) or set())

    missing = routed - set(ALLOWED_METHODS)
    assert not missing, (
        "these methods are routed but missing from ALLOWED_METHODS, so a browser "
        "preflight for them returns 400: %s" % sorted(missing)
    )


def test_the_headers_the_dashboard_sends_are_allowed():
    lowered = {header.lower() for header in ALLOWED_HEADERS}
    # Authorization on every call; Content-Type on every JSON body.
    assert {"authorization", "content-type"} <= lowered
