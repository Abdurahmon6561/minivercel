"""End-to-end tests for POST /api/deployments."""

from __future__ import annotations

import dataclasses
import glob
import os
import tempfile

import pytest

from app.config import get_settings
from app.main import app
from app.supabase import SupabaseError

from .conftest import OTHER_USER_ID, USER_ID, auth_headers, deploy, make_zip

SITE = {
    "index.html": "<h1>hello</h1>",
    "about.html": "<h1>about</h1>",
    "docs/index.html": "<h1>docs</h1>",
    "assets/app.css": "body{margin:0}",
    "assets/logo.png": b"\x89PNG\r\n\x1a\n",
}


@pytest.fixture
def override_settings():
    applied = []

    def apply(**changes):
        replaced = dataclasses.replace(get_settings(), **changes)
        app.dependency_overrides[get_settings] = lambda: replaced
        applied.append(True)
        return replaced

    yield apply
    app.dependency_overrides.pop(get_settings, None)


# -- auth -------------------------------------------------------------------


async def test_anonymous_upload_is_rejected(client):
    response = await client.post(
        "/api/deployments", files={"file": ("site.zip", make_zip(SITE), "application/zip")}
    )
    assert response.status_code == 401


async def test_garbage_token_is_rejected(client):
    response = await client.post(
        "/api/deployments",
        headers={"Authorization": "Bearer not-a-jwt"},
        files={"file": ("site.zip", make_zip(SITE), "application/zip")},
    )
    assert response.status_code == 401


# -- happy path -------------------------------------------------------------


async def test_upload_creates_a_ready_deployment(client, supabase):
    response = await deploy(client, make_zip(SITE))
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["status"] == "ready"
    assert body["file_count"] == 5
    assert body["size_bytes"] > 0
    assert body["url"] == "https://minivercel.test/s/demo/"

    deployment_id = body["id"]
    assert set(supabase.objects) == {
        "%s/%s" % (deployment_id, path) for path in SITE
    }

    project = supabase.tables["projects"][0]
    assert project["live_deployment_id"] == deployment_id
    assert project["owner_id"] == USER_ID


async def test_content_types_come_from_the_whitelist(client, supabase):
    await deploy(
        client,
        make_zip(
            {
                "index.html": "<h1>hi</h1>",
                "app.js": "console.log(1)",
                "data.weird": b"\x00\x01",
                "font.woff2": b"wOF2",
            }
        ),
    )
    by_extension = {key.rsplit(".", 1)[1]: ct for key, ct in supabase.upload_calls}
    assert by_extension["html"] == "text/html; charset=utf-8"
    assert by_extension["js"] == "text/javascript; charset=utf-8"
    assert by_extension["woff2"] == "font/woff2"
    # Unknown extension must not become something the browser will execute.
    assert by_extension["weird"] == "application/octet-stream"


async def test_commit_sha_header_is_recorded(client, supabase):
    response = await client.post(
        "/api/deployments",
        headers={**auth_headers(), "X-Commit-Sha": "a" * 40},
        files={"file": ("site.zip", make_zip(SITE), "application/zip")},
        data={"slug": "demo"},
    )
    assert response.status_code == 201
    assert supabase.tables["deployments"][0]["commit_sha"] == "a" * 40


async def test_wrapping_folder_is_stripped(client, supabase):
    response = await deploy(
        client, make_zip({"mysite/index.html": "hi", "mysite/a.css": "body{}"})
    )
    assert response.status_code == 201
    deployment_id = response.json()["id"]
    assert set(supabase.objects) == {
        deployment_id + "/index.html",
        deployment_id + "/a.css",
    }


async def test_redeploy_moves_the_live_pointer(client, supabase):
    first = (await deploy(client, make_zip(SITE))).json()
    second = (await deploy(client, make_zip(SITE))).json()
    assert first["id"] != second["id"]
    assert supabase.tables["projects"][0]["live_deployment_id"] == second["id"]
    assert len(supabase.tables["deployments"]) == 2


# -- rejections -------------------------------------------------------------


async def test_missing_index_html_is_rejected(client):
    response = await deploy(client, make_zip({"readme.txt": "nothing to serve"}))
    assert response.status_code == 422
    assert "index.html" in response.json()["detail"]


async def test_traversal_archive_is_rejected_and_nothing_is_stored(client, supabase):
    response = await deploy(
        client, make_zip({"index.html": "hi", "../../etc/passwd": "root:x:0:0"})
    )
    assert response.status_code == 422
    assert supabase.objects == {}
    assert supabase.tables["deployments"][0]["status"] == "failed"
    assert supabase.tables["deployments"][0]["error"]


async def test_zip_bomb_is_rejected(client, supabase, override_settings):
    override_settings(max_deployment_bytes=1024 * 1024)
    payload = make_zip({"index.html": b"\0" * (8 * 1024 * 1024)})
    assert len(payload) < 1024 * 1024, "fixture must slip past the transfer-size check"

    response = await deploy(client, payload)
    assert response.status_code == 422
    assert "uncompressed" in response.json()["detail"]
    assert supabase.objects == {}


async def test_too_many_files_is_rejected(client, override_settings):
    override_settings(max_files_per_deployment=10)
    payload = {"index.html": "hi"}
    payload.update({"page%02d.html" % index: "x" for index in range(20)})
    response = await deploy(client, make_zip(payload))
    assert response.status_code == 422
    assert "limit is 10" in response.json()["detail"]


async def test_oversize_upload_is_rejected_while_streaming(client, override_settings):
    override_settings(max_deployment_bytes=4096)
    # Incompressible payload, so the transfer itself is over the cap.
    response = await deploy(client, make_zip({"index.html": os.urandom(64 * 1024)}))
    assert response.status_code == 413
    assert "limit" in response.json()["detail"]


async def test_quota_is_enforced(client, supabase, override_settings):
    override_settings(max_user_bytes=1)
    response = await deploy(client, make_zip(SITE))
    assert response.status_code == 413
    assert "quota" in response.json()["detail"].lower()
    assert supabase.objects == {}


async def test_request_without_a_file_part_is_rejected(client):
    response = await client.post(
        "/api/deployments", headers=auth_headers(), data={"slug": "demo"}
    )
    assert response.status_code == 400


async def test_not_a_zip_is_rejected(client):
    response = await deploy(client, b"PK not really a zip at all")
    assert response.status_code == 422


# -- failure cleanup --------------------------------------------------------


async def test_partial_upload_failure_removes_objects_and_marks_failed(
    client, supabase, monkeypatch
):
    real_upload = supabase.upload
    calls = {"n": 0}

    async def flaky(key, data, content_type):
        calls["n"] += 1
        if calls["n"] == 3:
            raise SupabaseError("storage exploded", 500)
        await real_upload(key, data, content_type)

    monkeypatch.setattr(supabase, "upload", flaky)

    response = await deploy(client, make_zip(SITE))
    assert response.status_code == 503
    assert supabase.objects == {}, "objects from a failed deploy must be removed"
    assert supabase.tables["deployments"][0]["status"] == "failed"


async def test_tmp_is_always_cleaned_up(client):
    before = set(glob.glob(os.path.join(tempfile.gettempdir(), "mv-*")))
    await deploy(client, make_zip(SITE))
    await deploy(client, make_zip({"index.html": "hi", "../evil": "x"}))
    await deploy(client, b"not a zip")
    after = set(glob.glob(os.path.join(tempfile.gettempdir(), "mv-*")))
    assert after == before


# -- reading deployments ----------------------------------------------------


async def test_deployment_is_not_readable_by_another_user(client):
    deployment_id = (await deploy(client, make_zip(SITE))).json()["id"]

    mine = await client.get("/api/deployments/" + deployment_id, headers=auth_headers())
    assert mine.status_code == 200

    theirs = await client.get(
        "/api/deployments/" + deployment_id, headers=auth_headers(OTHER_USER_ID)
    )
    assert theirs.status_code == 404


async def test_deployment_response_never_leaks_the_service_key(client):
    response = await deploy(client, make_zip(SITE))
    assert get_settings().supabase_service_key not in response.text


async def test_quota_counts_uncompressed_size_not_transfer_size(
    client, supabase, override_settings
):
    """A small zip that expands past the quota must be refused before upload."""
    override_settings(max_user_bytes=1024 * 1024, max_deployment_bytes=50 * 1024 * 1024)
    payload = make_zip({"index.html": b"\0" * (8 * 1024 * 1024)})
    assert len(payload) < 1024 * 1024, "the transfer itself is well under quota"

    response = await deploy(client, payload)
    assert response.status_code == 413
    assert "quota" in response.json()["detail"].lower()
    assert supabase.objects == {}


async def test_quota_accumulates_across_deployments(client, override_settings):
    override_settings(max_user_bytes=4096)
    first = await deploy(client, make_zip({"index.html": "x" * 3000}), slug="one")
    assert first.status_code == 201

    second = await deploy(client, make_zip({"index.html": "y" * 3000}), slug="two")
    assert second.status_code == 413
