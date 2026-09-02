"""Project CRUD and ownership isolation."""

from __future__ import annotations

from app.store import slugify

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
