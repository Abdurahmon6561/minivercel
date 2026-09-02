"""URL construction (AUTODEPLOY.md section 1).

The point of `app/urls.py` is that moving sites from a path to a subdomain is
two environment variables rather than a search for inline f-strings. These tests
are what keeps that true.
"""

from __future__ import annotations

import dataclasses

from app.config import get_settings
from app.urls import api_base_url, site_url, webhook_url


def settings_with(**overrides):
    return dataclasses.replace(get_settings(), **overrides)


def test_path_mode_is_the_default():
    settings = settings_with(
        public_base_url="https://minivercel.onrender.com", url_mode="path"
    )
    assert site_url(settings, "blue-forest-4821") == (
        "https://minivercel.onrender.com/s/blue-forest-4821/"
    )


def test_subdomain_mode_moves_sites_off_the_api_origin():
    settings = settings_with(
        public_base_url="https://minivercel.onrender.com",
        url_mode="subdomain",
        site_domain="example.com",
    )
    assert site_url(settings, "blue-forest-4821") == "https://blue-forest-4821.example.com/"


def test_subdomain_mode_without_a_domain_falls_back_to_paths():
    """A half-configured switch must not produce `https://slug./`."""
    settings = settings_with(
        public_base_url="https://minivercel.onrender.com",
        url_mode="subdomain",
        site_domain="",
    )
    assert site_url(settings, "demo") == "https://minivercel.onrender.com/s/demo/"


def test_the_webhook_stays_on_the_api_origin_in_both_modes():
    """It is our endpoint, not a served site: it must not move with the sites."""
    for mode in ("path", "subdomain"):
        settings = settings_with(
            public_base_url="https://minivercel.onrender.com",
            url_mode=mode,
            site_domain="example.com",
        )
        assert webhook_url(settings) == (
            "https://minivercel.onrender.com/api/webhooks/github"
        )
        assert api_base_url(settings) == "https://minivercel.onrender.com"


async def test_every_api_response_uses_the_same_builder(client):
    """No handler may build a site URL of its own."""
    from .conftest import auth_headers

    created = await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "URL check", "slug": "url-check"}
    )
    expected = site_url(get_settings(), "url-check")

    assert created.json()["url"] == expected
    listed = await client.get("/api/projects", headers=auth_headers())
    assert next(p for p in listed.json() if p["slug"] == "url-check")["url"] == expected
    detail = await client.get("/api/projects/url-check", headers=auth_headers())
    assert detail.json()["url"] == expected
