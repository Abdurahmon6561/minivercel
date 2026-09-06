"""Host-based routing (app/hostrouting.py), the getdropbin.xyz migration.

URL_MODE=path (every other test file in this suite) never touches this code
path at all - see the first test below, which is the guarantee that matters
most: turning the feature on must never turn it off elsewhere by accident.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from .conftest import auth_headers


def make_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("index.html", "<h1>hi</h1>")
    return buffer.getvalue()


async def deploy_project(client, slug: str) -> None:
    # Host: api.getdropbin.xyz so this still lands on the API when the
    # `subdomain` fixture is active; harmless (and unused) in path mode.
    response = await client.post(
        "/api/deployments",
        headers={**auth_headers(), "Host": "api.getdropbin.xyz"},
        files={"file": ("site.zip", make_zip(), "application/zip")},
        data={"slug": slug, "name": slug},
    )
    assert response.status_code == 201, response.text


@pytest.fixture
def subdomain(override_settings):
    return override_settings(url_mode="subdomain", site_domain="getdropbin.xyz")


# -- path mode is unaffected --------------------------------------------------


async def test_path_mode_ignores_the_host_header_entirely(client):
    """The default. A Host that would mean something in subdomain mode must
    not change how a path-mode request is answered."""
    response = await client.get("/health", headers={"Host": "some-slug.getdropbin.xyz"})
    assert response.status_code == 200


# -- api.getdropbin.xyz --------------------------------------------------------


async def test_api_host_serves_api_routes(client, subdomain):
    response = await client.get(
        "/health", headers={"Host": "api.getdropbin.xyz"}
    )
    assert response.status_code == 200


async def test_api_host_redirects_legacy_site_paths_rather_than_serving_them(
    client, subdomain
):
    """/s/{slug}/... is reachable on the API host only as a 301 to the site's
    own subdomain - never served here, so the API origin is not a second way
    to reach a site's content."""
    response = await client.get(
        "/s/whatever/", headers={"Host": "api.getdropbin.xyz"}, follow_redirects=False
    )
    assert response.status_code == 301
    assert response.headers["location"] == "https://whatever.getdropbin.xyz/"


async def test_api_host_404s_a_path_outside_the_api_surface(client, subdomain):
    response = await client.get(
        "/definitely-not-a-route", headers={"Host": "api.getdropbin.xyz"}
    )
    assert response.status_code == 404


async def test_api_host_serves_docs(client, subdomain):
    response = await client.get("/openapi.json", headers={"Host": "api.getdropbin.xyz"})
    assert response.status_code == 200


# -- app.getdropbin.xyz --------------------------------------------------------


async def test_app_host_without_a_build_answers_503(client, subdomain, tmp_path):
    """A missing dashboard build (DASHBOARD_DIST_DIR unset or `npm run build`
    never ran into it) is an honest 503, not a stack trace or a silent 404.

    Points DASHBOARD_DIST_DIR at a directory that deliberately has no
    index.html, rather than relying on the ambient working directory not
    having a build lying around - true in CI, not guaranteed anywhere a
    developer might run this suite from a checkout with `web/dist` built.
    """
    from dataclasses import replace

    from app.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: replace(
        subdomain, dashboard_dist_dir=str(tmp_path)
    )
    try:
        response = await client.get("/", headers={"Host": "app.getdropbin.xyz"})
        assert response.status_code == 503
    finally:
        app.dependency_overrides.pop(get_settings, None)


async def test_app_host_serves_the_built_dashboard(client, subdomain, tmp_path):
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>dash</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")

    override = subdomain
    from dataclasses import replace

    from app.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: replace(
        override, dashboard_dist_dir=str(tmp_path)
    )
    try:
        root = await client.get("/", headers={"Host": "app.getdropbin.xyz"})
        assert root.status_code == 200
        assert b"dash" in root.content

        deep_link = await client.get(
            "/projects/some-project", headers={"Host": "app.getdropbin.xyz"}
        )
        assert deep_link.status_code == 200
        assert b"dash" in deep_link.content  # SPA fallback to index.html

        asset = await client.get(
            "/assets/app.js", headers={"Host": "app.getdropbin.xyz"}
        )
        assert asset.status_code == 200
        assert asset.content == b"console.log(1)"
        assert "immutable" in asset.headers.get("cache-control", "")
    finally:
        app.dependency_overrides.pop(get_settings, None)


# -- getdropbin.xyz (bare) -----------------------------------------------------


async def test_bare_domain_serves_the_dashboard_bundle(client, subdomain, tmp_path):
    """The apex serves the build rather than redirecting to app.{SITE_DOMAIN}.

    It is the same bundle the app subdomain gets, byte for byte, including the
    SPA fallback: the apex renders the marketing landing at `/`, and which page
    a path means is decided by the React router inside that one build.
    """
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>dash</title>")

    from dataclasses import replace

    from app.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: replace(
        subdomain, dashboard_dist_dir=str(tmp_path)
    )
    try:
        root = await client.get(
            "/", headers={"Host": "getdropbin.xyz"}, follow_redirects=False
        )
        assert root.status_code == 200
        assert b"dash" in root.content

        # Any unknown path falls back to the shell, same as on app.{SITE_DOMAIN}.
        deep = await client.get(
            "/pricing", headers={"Host": "getdropbin.xyz"}, follow_redirects=False
        )
        assert deep.status_code == 200
        assert b"dash" in deep.content
    finally:
        app.dependency_overrides.pop(get_settings, None)


# -- {slug}.getdropbin.xyz -----------------------------------------------------


async def test_slug_subdomain_serves_the_site(client, subdomain):
    await deploy_project(client, "blue-forest-4821")
    response = await client.get(
        "/", headers={"Host": "blue-forest-4821.getdropbin.xyz"}
    )
    assert response.status_code == 200
    assert b"hi" in response.content


async def test_unknown_slug_subdomain_is_404(client, subdomain):
    response = await client.get(
        "/", headers={"Host": "no-such-project.getdropbin.xyz"}
    )
    assert response.status_code == 404


async def test_reserved_word_subdomain_is_404_not_a_lookup(client, subdomain):
    """`www`, `admin`, etc. must never reach the project lookup at all."""
    response = await client.get("/", headers={"Host": "admin.getdropbin.xyz"})
    assert response.status_code == 404


# -- anything else --------------------------------------------------------------


async def test_an_unrelated_host_is_404(client, subdomain):
    response = await client.get("/", headers={"Host": "evil.example"})
    assert response.status_code == 404


async def test_health_check_ignores_the_host_header(client, subdomain):
    """Render's health check and any uptime pinger hit this container with
    whatever Host their infrastructure sends, not api.{SITE_DOMAIN} - liveness
    must not depend on getting that right."""
    response = await client.get("/health", headers={"Host": "10.0.4.17"})
    assert response.status_code == 200


# -- local dev falls back to path-based routing --------------------------------


async def test_localhost_falls_back_to_path_routing(client, subdomain):
    await deploy_project(client, "local-check")
    response = await client.get(
        "/s/local-check/", headers={"Host": "localhost:8000"}
    )
    assert response.status_code == 200
    assert b"hi" in response.content


# -- /s/{slug}/... redirects to the subdomain in subdomain mode ----------------


async def test_path_route_redirects_to_the_subdomain(client, subdomain):
    await deploy_project(client, "moved-project")
    response = await client.get(
        "/s/moved-project/about.html",
        headers={"Host": "api.getdropbin.xyz"},
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"] == (
        "https://moved-project.getdropbin.xyz/about.html"
    )
