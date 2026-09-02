"""Regression tests for the quota query and for non-2xx handling.

Both cover the same incident: `user_bytes_used` embedded `projects!inner(...)`,
PostgREST could not tell which of the two foreign keys between `deployments` and
`projects` the embed meant, and answered `300 Multiple Choices`. The client only
treated `>= 400` as failure, so a JSON object describing the ambiguity was
returned as if it were rows and the caller died with `'str' object has no
attribute 'get'` several frames away from the cause.
"""

from __future__ import annotations

import httpx
import pytest

from app.store import PROJECT_ID_BATCH, Store
from app.supabase import SupabaseClient, SupabaseError

from .conftest import OTHER_USER_ID, USER_ID, deploy, make_zip

SITE = {"index.html": "<h1>hi</h1>"}


# -- the client must reject every non-2xx ------------------------------------


@pytest.fixture
def raw_client():
    client = SupabaseClient()
    yield client


@pytest.mark.parametrize("status_code", [300, 301, 302, 304, 400, 404, 409, 500, 503])
def test_non_2xx_raises(raw_client, status_code):
    response = httpx.Response(status_code, text='{"message":"nope"}')
    with pytest.raises(SupabaseError) as caught:
        raw_client._check(response, "select deployments")
    assert caught.value.status_code == status_code


@pytest.mark.parametrize("status_code", [200, 201, 204, 206])
def test_2xx_passes(raw_client, status_code):
    assert raw_client._check(httpx.Response(status_code), "select x") is not None


def test_300_message_names_the_status_and_body(raw_client):
    """The whole point: the error has to say what happened."""
    body = '{"message":"Could not embed because more than one relationship was found"}'
    with pytest.raises(SupabaseError, match="300"):
        raw_client._check(httpx.Response(300, text=body), "select deployments")


def test_error_text_never_carries_the_service_key(raw_client):
    key = raw_client.settings.supabase_service_key
    with pytest.raises(SupabaseError) as caught:
        raw_client._check(httpx.Response(400, text="leaked " + key), "select x")
    assert key not in str(caught.value)


# -- the quota query itself ---------------------------------------------------


async def test_quota_sums_across_a_users_projects(client, supabase):
    await deploy(client, make_zip(SITE), slug="one")
    await deploy(client, make_zip({"index.html": "x" * 500}), slug="two")

    store = Store(supabase)
    expected = sum(
        row["size_bytes"] for row in supabase.tables["deployments"] if row["size_bytes"]
    )
    assert await store.user_bytes_used(USER_ID) == expected
    assert expected > 0


async def test_quota_ignores_other_users(client, supabase):
    await deploy(client, make_zip(SITE), slug="mine")
    await deploy(client, make_zip(SITE), slug="theirs", subject=OTHER_USER_ID)

    store = Store(supabase)
    mine = await store.user_bytes_used(USER_ID)
    theirs = await store.user_bytes_used(OTHER_USER_ID)
    assert mine > 0 and theirs > 0
    assert mine + theirs == sum(
        row["size_bytes"] for row in supabase.tables["deployments"]
    )


async def test_quota_ignores_failed_deployments(client, supabase):
    await deploy(client, make_zip(SITE), slug="site-ok")
    good = await Store(supabase).user_bytes_used(USER_ID)

    # A failed deployment has already had its objects removed; it owns no bytes.
    await deploy(client, make_zip({"index.html": "hi", "../escape": "x"}), slug="site-ok")
    assert any(d["status"] == "failed" for d in supabase.tables["deployments"])
    assert await Store(supabase).user_bytes_used(USER_ID) == good


async def test_quota_is_zero_for_a_user_with_no_projects(supabase):
    calls = []
    real = supabase.select

    async def counting(table, params):
        calls.append(table)
        return await real(table, params)

    supabase.select = counting
    assert await Store(supabase).user_bytes_used(USER_ID) == 0
    assert calls == ["projects"], "no projects means no second query"


async def test_quota_batches_large_project_counts(supabase):
    """More projects than one `in.(...)` should carry."""
    count = PROJECT_ID_BATCH * 2 + 5
    for index in range(count):
        project = await supabase.insert(
            "projects",
            {"owner_id": USER_ID, "name": "p%d" % index, "slug": "p%d" % index},
        )
        await supabase.insert(
            "deployments",
            {"project_id": project["id"], "status": "ready", "size_bytes": 10},
        )

    batches = []
    real = supabase.select

    async def counting(table, params):
        if table == "deployments":
            batches.append(params["project_id"])
        return await real(table, params)

    supabase.select = counting
    assert await Store(supabase).user_bytes_used(USER_ID) == count * 10
    assert len(batches) == 3
    assert all(chunk.count(",") < PROJECT_ID_BATCH for chunk in batches)


async def test_quota_still_gates_uploads(client):
    """The end-to-end path that broke: an upload must reach a real number."""
    first = await deploy(client, make_zip(SITE), slug="site-a")
    assert first.status_code == 201
    second = await deploy(client, make_zip(SITE), slug="site-b")
    assert second.status_code == 201
