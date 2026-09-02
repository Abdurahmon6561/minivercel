"""Project CRUD and ownership isolation."""

from __future__ import annotations

import re

import pytest

from app.naming import generate_slug, is_reserved
from app.store import is_valid_slug, slugify

from .conftest import OTHER_USER_ID, USER_ID, auth_headers, deploy, make_zip

SITE = {"index.html": "<h1>hi</h1>"}


async def test_create_list_and_get(client):
    created = await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "My Site"}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["slug"] == "my-site"
    assert body["url"] == "https://minivercel.test/s/my-site/"

    listed = await client.get("/api/projects", headers=auth_headers())
    assert [p["slug"] for p in listed.json()] == ["my-site"]

    fetched = await client.get("/api/projects/my-site", headers=auth_headers())
    assert fetched.json()["deployments"] == []


async def test_duplicate_name_gets_a_distinct_slug(client):
    first = await client.post("/api/projects", headers=auth_headers(), json={"name": "Site"})
    second = await client.post("/api/projects", headers=auth_headers(), json={"name": "Site"})
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["slug"] != second.json()["slug"]
    assert second.json()["slug"].startswith("site-")


async def test_explicit_slug_conflict_is_a_409(client):
    await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "A", "slug": "taken"}
    )
    clash = await client.post(
        "/api/projects", headers=auth_headers(OTHER_USER_ID), json={"name": "B", "slug": "taken"}
    )
    assert clash.status_code == 409


async def test_invalid_slug_is_rejected(client):
    response = await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "A", "slug": "NO_GOOD!"}
    )
    assert response.status_code == 400


async def test_another_user_cannot_see_or_delete_a_project(client):
    await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "Mine", "slug": "mine"}
    )

    assert (
        await client.get("/api/projects", headers=auth_headers(OTHER_USER_ID))
    ).json() == []
    assert (
        await client.get("/api/projects/mine", headers=auth_headers(OTHER_USER_ID))
    ).status_code == 404
    assert (
        await client.delete("/api/projects/mine", headers=auth_headers(OTHER_USER_ID))
    ).status_code == 404


async def test_deleting_a_project_removes_its_objects(client, supabase):
    await deploy(client, make_zip(SITE), slug="doomed")
    assert supabase.objects

    response = await client.delete("/api/projects/doomed", headers=auth_headers())
    assert response.status_code == 204
    assert supabase.objects == {}
    assert supabase.tables["projects"] == []
    assert supabase.tables["deployments"] == []


async def test_project_history_lists_deployments_newest_first(client):
    await deploy(client, make_zip(SITE), slug="hist")
    await deploy(client, make_zip(SITE), slug="hist")

    body = (await client.get("/api/projects/hist", headers=auth_headers())).json()
    assert len(body["deployments"]) == 2
    assert all(d["status"] == "ready" for d in body["deployments"])


async def test_upload_can_target_a_project_by_id(client, supabase):
    project = (
        await client.post(
            "/api/projects", headers=auth_headers(), json={"name": "By Id", "slug": "by-id"}
        )
    ).json()

    response = await client.post(
        "/api/deployments",
        headers=auth_headers(),
        files={"file": ("site.zip", make_zip(SITE), "application/zip")},
        data={"project_id": project["id"]},
    )
    assert response.status_code == 201
    assert response.json()["project"]["slug"] == "by-id"


async def test_upload_cannot_target_someone_elses_project(client):
    project = (
        await client.post(
            "/api/projects", headers=auth_headers(), json={"name": "Mine", "slug": "mine"}
        )
    ).json()

    response = await client.post(
        "/api/deployments",
        headers=auth_headers(OTHER_USER_ID),
        files={"file": ("site.zip", make_zip(SITE), "application/zip")},
        data={"project_id": project["id"]},
    )
    assert response.status_code == 404


async def test_upload_without_any_project_field_still_works(client, supabase):
    response = await client.post(
        "/api/deployments",
        headers=auth_headers(),
        files={"file": ("site.zip", make_zip(SITE), "application/zip")},
    )
    assert response.status_code == 201
    assert supabase.tables["projects"][0]["owner_id"] == USER_ID


def test_slugify():
    assert slugify("My Cool Site!") == "my-cool-site"
    assert slugify("  ---  ") == "site"
    assert slugify("Ünïcödé Nâmes") == "unicode-names"
    assert slugify("a") == "a-site"
    assert len(slugify("x" * 200)) <= 48


# -- the dashboard's project list ---------------------------------------------


async def test_list_includes_last_deployment_for_the_status_dot(client):
    await deploy(client, make_zip(SITE), slug="listed")
    rows = (await client.get("/api/projects", headers=auth_headers())).json()

    row = next(r for r in rows if r["slug"] == "listed")
    assert row["last_deployment"]["status"] == "ready"
    assert row["last_deployment"]["is_live"] is True
    assert row["last_deployment"]["created_at"]
    assert row["url"] == "https://minivercel.test/s/listed/"


async def test_list_reports_none_for_a_project_never_deployed(client):
    await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "Empty", "slug": "empty"}
    )
    rows = (await client.get("/api/projects", headers=auth_headers())).json()
    assert rows[0]["last_deployment"] is None


async def test_list_shows_the_newest_deployment_not_the_first(client, supabase):
    await deploy(client, make_zip(SITE), slug="newest")
    second = (await deploy(client, make_zip(SITE), slug="newest")).json()

    rows = (await client.get("/api/projects", headers=auth_headers())).json()
    assert rows[0]["last_deployment"]["id"] == second["id"]


async def test_list_surfaces_a_failed_deployment(client):
    await deploy(client, make_zip(SITE), slug="broken")
    await deploy(client, make_zip({"index.html": "hi", "../evil": "x"}), slug="broken")

    rows = (await client.get("/api/projects", headers=auth_headers())).json()
    row = next(r for r in rows if r["slug"] == "broken")
    assert row["last_deployment"]["status"] == "failed"
    assert row["last_deployment"]["is_live"] is False, "a failed deploy is not live"
    assert row["last_deployment"]["error"]


async def test_list_does_not_scale_queries_with_project_count(client, supabase):
    """One query for projects, one batch for deployments - not N+1."""
    for index in range(6):
        await deploy(client, make_zip(SITE), slug="proj-%d" % index)

    calls = []
    real = supabase.select

    async def counting(table, params):
        calls.append(table)
        return await real(table, params)

    supabase.select = counting
    rows = (await client.get("/api/projects", headers=auth_headers())).json()
    assert len(rows) == 6
    assert calls == ["projects", "deployments"]


# -- reserved slugs (AUTODEPLOY.md section 2) ---------------------------------


@pytest.mark.parametrize(
    "slug", ["api", "admin", "www", "app", "docs", "assets", "health", "static"]
)
async def test_reserved_slugs_are_refused(client, slug):
    """RESERVED is a security control, not decoration.

    In path mode `/s/api/` is harmless. In the addendum's subdomain mode a
    project called `api` becomes `api.yourdomain.com` and hijacks the API.
    """
    response = await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "X", "slug": slug}
    )
    assert response.status_code == 400


async def test_a_reserved_name_gets_a_generated_slug_instead(client):
    """A repository called `docs` is ordinary; taking the slug `docs` is not."""
    response = await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "docs"}
    )
    assert response.status_code == 201
    slug = response.json()["slug"]
    assert slug != "docs"
    assert not is_reserved(slug)
    # adjective-noun-NNNN
    assert re.match(r"^[a-z]+-[a-z]+-\d{4}$", slug), slug


def test_generated_slugs_are_valid_and_never_reserved():
    for _ in range(500):
        slug = generate_slug()
        assert is_valid_slug(slug)
        assert not is_reserved(slug)


def test_reserved_covers_our_own_route_segments():
    # Anything we serve from the API origin would collide in subdomain mode.
    for segment in ("api", "s", "health", "docs", "openapi"):
        assert is_reserved(segment)
