"""Phase 5: rollback, garbage collection, build logs, and delete correctness.

Four features that share one property: they are the parts of the system that
*remove* things or *change what is live*, which makes them the parts where a bug
is expensive and silent. Storage is not covered by `ON DELETE CASCADE`
(AUTODEPLOY.md section 7), so every deletion path here is asserted against the
object store, not only against the rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import gc
from app.config import get_settings
from app.store import BUILD_LOG_MAX_LINES, truncate_build_log

from .conftest import OTHER_USER_ID, auth_headers, deploy, make_zip
from .fake_supabase import FakeSupabase

# The Phase 3/4 GitHub stub, reused here for the build-log tests: a deploy token
# only exists once builds have been enabled on a repository. Imported rather
# than reimplemented so both suites exercise the same fake.
from .test_github import connect_github, github  # noqa: F401  (pytest fixture)


def site(version: str) -> bytes:
    return make_zip({"index.html": "<h1>%s</h1>" % version, "assets/app.css": "b{}"})


async def deploy_versions(client, count: int, *, slug: str = "demo") -> list[str]:
    """`count` successive deployments of one project, oldest first."""
    ids = []
    for index in range(count):
        response = await deploy(client, site("v%d" % index), slug=slug)
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    return ids


def age_deployment(supabase: FakeSupabase, deployment_id: str, *, days: float) -> None:
    """Backdate a row, because a test cannot wait seven days.

    Shifts the row's own `created_at` rather than assigning `now - days`.
    Windows' clock has ~15 ms resolution, so several rows aged in one loop would
    otherwise land on an identical timestamp, "newest" would be decided by the
    `id.desc` tiebreak, and the test would assert against whichever UUID sorted
    lowest - which is not what any of these tests mean.
    """
    for row in supabase.tables["deployments"]:
        if row["id"] == deployment_id:
            created = datetime.fromisoformat(row["created_at"])
            row["created_at"] = (created - timedelta(days=days)).isoformat()
            return
    raise AssertionError("no such deployment: " + deployment_id)


def objects_for(supabase: FakeSupabase, deployment_id: str) -> list[str]:
    prefix = deployment_id + "/"
    return [key for key in supabase.objects if key.startswith(prefix)]


# =============================================================================
# 1. Rollback: preview a past deployment, then promote it
# =============================================================================


async def test_every_deployment_is_kept_and_previewable(client, supabase):
    """A redeploy must not delete what it replaces - that is the whole basis of
    rollback. The old objects stay, under their own key prefix."""
    first, second = await deploy_versions(client, 2)

    assert objects_for(supabase, first), "the previous deployment was destroyed"
    assert objects_for(supabase, second)

    # The live site serves the newest.
    live = await client.get("/s/demo/")
    assert live.status_code == 200
    assert b"v1" in live.content

    # The preview URL serves the older one, unchanged.
    preview = await client.get("/s/demo/_d/%s/" % first)
    assert preview.status_code == 200
    assert b"v0" in preview.content
    # A preview is the same content at a different point in time; it must not
    # compete with the live URL in a search index.
    assert "noindex" in preview.headers["x-robots-tag"]


async def test_preview_uses_the_same_resolution_as_the_live_site(client, supabase):
    """Clean URLs and the asset redirect have to behave identically, or a
    preview is not a preview of anything."""
    response = await deploy(
        client,
        make_zip(
            {
                "index.html": "<h1>home</h1>",
                "about.html": "<h1>about</h1>",
                "assets/app.css": "body{margin:0}",
            }
        ),
    )
    deployment_id = response.json()["id"]

    clean = await client.get("/s/demo/_d/%s/about" % deployment_id)
    assert clean.status_code == 200
    assert b"about" in clean.content

    asset = await client.get("/s/demo/_d/%s/assets/app.css" % deployment_id)
    assert asset.status_code == 307
    assert "supabase.co" in asset.headers["location"]


async def test_preview_without_a_trailing_slash_redirects(client):
    deployment_id = (await deploy_versions(client, 1))[0]
    response = await client.get("/s/demo/_d/%s" % deployment_id)
    assert response.status_code == 308
    assert response.headers["location"] == "/s/demo/_d/%s/" % deployment_id


async def test_preview_refuses_another_projects_deployment(client, supabase):
    """Otherwise any slug is an oracle for every deployment id in the bucket."""
    mine = (await deploy_versions(client, 1, slug="mine"))[0]
    await deploy_versions(client, 1, slug="theirs")

    response = await client.get("/s/theirs/_d/%s/" % mine)
    assert response.status_code == 404
    # Same wording as a deployment that does not exist at all.
    assert "No such deployment" in response.text


async def test_preview_refuses_a_failed_deployment(client, supabase):
    """A failed deployment has partial objects or none; showing it would show a
    broken site and blame the user for it."""
    deployment_id = (await deploy_versions(client, 1))[0]
    for row in supabase.tables["deployments"]:
        row["status"] = "failed"

    response = await client.get("/s/demo/_d/%s/" % deployment_id)
    assert response.status_code == 404
    assert "failed" in response.text


async def test_the_preview_route_is_not_shadowed_by_the_catch_all(client, supabase):
    """`/s/{slug}/{path:path}` matches `_d/...` too. Registration order is what
    keeps the preview route reachable, so assert it rather than trust it."""
    deployment_id = (await deploy_versions(client, 1))[0]
    response = await client.get("/s/demo/_d/%s/index.html" % deployment_id)
    assert response.status_code == 200
    assert b"v0" in response.content


async def test_promote_moves_the_live_pointer(client, supabase):
    first, second = await deploy_versions(client, 2)
    before = dict(supabase.objects)

    response = await client.post(
        "/api/projects/demo/deployments/%s/promote" % first, headers=auth_headers()
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["live_deployment_id"] == first
    assert body["previous_deployment_id"] == second
    assert body["changed"] is True

    project = supabase.tables["projects"][0]
    assert project["live_deployment_id"] == first

    # A pointer change, and nothing else. Not one object moved, copied or gone.
    assert supabase.objects == before

    # And the site actually serves the older version now.
    live = await client.get("/s/demo/")
    assert live.status_code == 200
    assert b"v0" in live.content


async def test_promote_is_idempotent(client, supabase):
    """The dashboard can be a few seconds stale. Promoting what is already live
    is a no-op, not an error."""
    deployment_id = (await deploy_versions(client, 1))[0]
    response = await client.post(
        "/api/projects/demo/deployments/%s/promote" % deployment_id,
        headers=auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["changed"] is False


async def test_promote_refuses_a_deployment_that_is_not_ready(client, supabase):
    first, second = await deploy_versions(client, 2)
    for row in supabase.tables["deployments"]:
        if row["id"] == first:
            row["status"] = "failed"
            row["error"] = "npm run build exited 1"

    response = await client.post(
        "/api/projects/demo/deployments/%s/promote" % first, headers=auth_headers()
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "failed" in detail
    assert "npm run build exited 1" in detail, "say why it cannot be promoted"

    assert supabase.tables["projects"][0]["live_deployment_id"] == second


async def test_promote_refuses_a_deployment_from_another_project(client, supabase):
    other = (await deploy_versions(client, 1, slug="other"))[0]
    mine = (await deploy_versions(client, 1, slug="mine"))[0]

    response = await client.post(
        "/api/projects/mine/deployments/%s/promote" % other, headers=auth_headers()
    )
    assert response.status_code == 404

    project = next(p for p in supabase.tables["projects"] if p["slug"] == "mine")
    assert project["live_deployment_id"] == mine


async def test_promote_refuses_another_users_project(client, supabase):
    deployment_id = (await deploy_versions(client, 1))[0]
    response = await client.post(
        "/api/projects/demo/deployments/%s/promote" % deployment_id,
        headers=auth_headers(OTHER_USER_ID),
    )
    assert response.status_code == 404


async def test_promote_requires_authentication(client):
    deployment_id = (await deploy_versions(client, 1))[0]
    response = await client.post(
        "/api/projects/demo/deployments/%s/promote" % deployment_id
    )
    assert response.status_code == 401


async def test_deployment_rows_carry_a_preview_url_and_live_flag(client, supabase):
    first, second = await deploy_versions(client, 2)
    body = (await client.get("/api/projects/demo", headers=auth_headers())).json()

    rows = {row["id"]: row for row in body["deployments"]}
    assert rows[second]["is_live"] is True
    assert rows[first]["is_live"] is False
    assert rows[first]["preview_url"] == (
        "https://minivercel.test/s/demo/_d/%s/" % first
    )


# =============================================================================
# 2. Garbage collection
# =============================================================================


def make_rows(
    count: int, *, age_days: float, status: str = "ready", prefix: str = "d"
) -> list[dict]:
    """Deployment dicts newest first, as `list_deployments` returns them."""
    now = datetime.now(timezone.utc)
    return [
        {
            "id": "%s%d" % (prefix, index),
            "status": status,
            "size_bytes": 1000,
            "created_at": (now - timedelta(days=age_days, seconds=index)).isoformat(),
        }
        for index in range(count)
    ]


def plan(rows, live, *, now=None):
    """{id: (remove_objects, remove_row)} for the rows the planner acts on."""
    actions = gc.plan_collection(rows, live, now or datetime.now(timezone.utc))
    return {
        action.deployment["id"]: (action.remove_objects, action.remove_row)
        for action in actions
    }


def test_the_live_deployment_is_never_collected_however_old():
    assert "d3" not in plan(make_rows(10, age_days=400), "d3")


def test_the_five_most_recent_ready_deployments_are_kept():
    # d0 is live; d1..d5 hold the five rollback slots; d6..d9 are collectable.
    assert set(plan(make_rows(10, age_days=400), "d0")) == {"d6", "d7", "d8", "d9"}


def test_a_ready_deployment_inside_the_grace_period_is_kept():
    assert plan(make_rows(10, age_days=3), "d0") == {}


def test_a_timestamp_that_cannot_be_read_keeps_the_deployment():
    """Failing towards deletion would destroy data on a formatting change."""
    rows = make_rows(10, age_days=400)
    for row in rows:
        row["created_at"] = "not a date"
    assert plan(rows, "d0") == {}


def test_failed_deployments_do_not_hold_rollback_slots():
    """The rule this is here to enforce.

    Five failures from today plus one working version from ten days ago. Under a
    plain "five most recent non-live", the failures take every slot and the only
    version anyone can actually roll back to is collected. It must survive.
    """
    live = {"id": "live", "status": "ready", "size_bytes": 10, "created_at": _iso(0)}
    failures = [
        {"id": "f%d" % index, "status": "failed", "size_bytes": 0, "created_at": _iso(0)}
        for index in range(5)
    ]
    working = {"id": "old-ready", "status": "ready", "size_bytes": 10, "created_at": _iso(10)}

    decided = plan([live] + failures + [working], "live")

    assert "old-ready" not in decided, "the only rollback target was collected"
    # The failures lose their objects now and their rows in seven days.
    for index in range(5):
        assert decided["f%d" % index] == (True, False)


def test_a_failed_deployment_loses_its_objects_immediately():
    """It is never served, so any objects a partial upload left are pure waste."""
    rows = [{"id": "f0", "status": "failed", "size_bytes": 0, "created_at": _iso(0)}]
    assert plan(rows, "live") == {"f0": (True, False)}


def test_a_failed_deployment_keeps_its_row_for_seven_days():
    """The row is the error message the user is reading."""
    fresh = [{"id": "f0", "status": "failed", "size_bytes": 0, "created_at": _iso(1)}]
    assert plan(fresh, "live")["f0"] == (True, False)

    stale = [{"id": "f0", "status": "failed", "size_bytes": 0, "created_at": _iso(8)}]
    assert plan(stale, "live")["f0"] == (True, True)


def test_a_pending_deployment_is_never_touched():
    """It may be uploading right now; deleting its objects corrupts a live
    deploy. `reap_stuck` turns a dead one into `failed` after ten minutes."""
    rows = [{"id": "p0", "status": "pending", "size_bytes": 0, "created_at": _iso(90)}]
    assert plan(rows, "live") == {}


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


async def test_gc_deletes_storage_before_the_row(client, supabase):
    """The order is the point of the module. A row deleted first is a set of
    object keys nobody can enumerate again (AUTODEPLOY.md section 7)."""
    order: list[str] = []
    real_remove = supabase.remove
    real_delete = supabase.delete

    async def track_remove(keys):
        keys = list(keys)
        for key in keys:
            order.append("storage:" + key.split("/", 1)[0])
        await real_remove(keys)

    async def track_delete(table, params):
        if table == "deployments":
            order.append("row:" + params["id"].removeprefix("eq."))
        await real_delete(table, params)

    ids = await deploy_versions(client, 7)
    victim = ids[0]
    for deployment_id in ids[:2]:
        age_deployment(supabase, deployment_id, days=30)

    supabase.remove = track_remove
    supabase.delete = track_delete

    from app.deps import get_store

    result = await gc.collect_project(get_store(), supabase.tables["projects"][0])

    assert result.deployments_deleted == 1, "only the seventh-oldest is expired"
    assert order.index("storage:" + victim) < order.index("row:" + victim)


async def test_gc_reclaims_bytes_and_reports_them(client, supabase):
    from app.deps import get_store

    ids = await deploy_versions(client, 7)
    expired = ids[0]
    for deployment_id in ids[:2]:
        age_deployment(supabase, deployment_id, days=30)

    size = next(
        row["size_bytes"] for row in supabase.tables["deployments"] if row["id"] == expired
    )
    assert size > 0

    result = await gc.collect_project(get_store(), supabase.tables["projects"][0])

    assert result.bytes_reclaimed == size
    assert objects_for(supabase, expired) == []
    assert expired not in {row["id"] for row in supabase.tables["deployments"]}


async def test_gc_never_touches_the_live_deployment(client, supabase):
    """Even when it is the oldest thing in the project by a wide margin."""
    from app.deps import get_store

    ids = await deploy_versions(client, 8)
    live = ids[0]
    await client.post(
        "/api/projects/demo/deployments/%s/promote" % live, headers=auth_headers()
    )
    for deployment_id in ids:
        age_deployment(supabase, deployment_id, days=99)

    await gc.collect_project(
        get_store(), next(iter(supabase.tables["projects"]))
    )

    assert objects_for(supabase, live), "the live site was deleted from storage"
    assert live in {row["id"] for row in supabase.tables["deployments"]}

    served = await client.get("/s/demo/")
    assert served.status_code == 200


async def test_gc_runs_after_a_successful_deploy(client, supabase):
    """Render's free plan has no cron, so collection has to ride on the deploy
    that creates the garbage."""
    ids = await deploy_versions(client, 6)
    for deployment_id in ids:
        age_deployment(supabase, deployment_id, days=30)

    # A seventh deploy pushes the oldest past "live plus five most recent".
    await deploy_versions(client, 1)

    surviving = {row["id"] for row in supabase.tables["deployments"]}
    assert ids[0] not in surviving, "the opportunistic sweep did not run"
    assert objects_for(supabase, ids[0]) == []
    assert len(surviving) == 6


async def test_a_sweep_keeps_the_working_deployment_over_five_failures(
    client, supabase
):
    """The end-to-end version of `test_failed_deployments_do_not_hold_slots`.

    A project with five failed deployments from today and one ready deployment
    from ten days ago must still have the ready one after a sweep - it is the
    only thing left to roll back to.
    """
    from app.deps import get_store

    live, working = await deploy_versions(client, 2)
    age_deployment(supabase, working, days=10)
    age_deployment(supabase, live, days=10)
    # Promote the newest so `working` is a non-live rollback target well past
    # the seven-day grace period.
    await client.post(
        "/api/projects/demo/deployments/%s/promote" % live, headers=auth_headers()
    )

    project = supabase.tables["projects"][0]
    for _ in range(5):
        await get_store().create_failed_deployment(
            project["id"], commit_sha=None, error="npm run build exited 1"
        )

    result = await gc.collect_project(get_store(), project)

    surviving = {row["id"] for row in supabase.tables["deployments"]}
    assert working in surviving, "the only rollback target was collected"
    assert objects_for(supabase, working), "its files were deleted"
    assert live in surviving

    # The five failures are still listed (they are the error messages) and
    # nothing was deleted, because none of them is seven days old yet.
    assert len(surviving) == 7
    assert result.deployments_deleted == 0


async def test_a_sweep_removes_orphaned_objects_from_a_failed_deployment(
    client, supabase
):
    """A worker killed mid-upload leaves objects with nothing to clean them:
    `deployer.fail` never ran, and the row is only marked failed later by the
    reaper. Those bytes are never served, so they go on sight."""
    from app.deps import get_store

    live, orphan = await deploy_versions(client, 2)
    await client.post(
        "/api/projects/demo/deployments/%s/promote" % live, headers=auth_headers()
    )
    for row in supabase.tables["deployments"]:
        if row["id"] == orphan:
            row["status"] = "failed"
            row["error"] = "worker restarted"

    assert objects_for(supabase, orphan), "precondition: partial upload survives"

    result = await gc.collect_project(get_store(), supabase.tables["projects"][0])

    assert objects_for(supabase, orphan) == []
    assert result.objects_removed == 2
    # The row stays: it is one day old, and it is what tells the user why.
    assert orphan in {row["id"] for row in supabase.tables["deployments"]}
    assert result.deployments_deleted == 0


async def test_a_sweep_deletes_a_failed_row_once_it_is_a_week_old(client, supabase):
    from app.deps import get_store

    live, stale = await deploy_versions(client, 2)
    await client.post(
        "/api/projects/demo/deployments/%s/promote" % live, headers=auth_headers()
    )
    for row in supabase.tables["deployments"]:
        if row["id"] == stale:
            row["status"] = "failed"
    age_deployment(supabase, stale, days=8)

    await gc.collect_project(get_store(), supabase.tables["projects"][0])

    assert stale not in {row["id"] for row in supabase.tables["deployments"]}
    assert objects_for(supabase, stale) == []


async def test_a_sweep_never_touches_a_pending_deployment(client, supabase):
    """It may be uploading right now."""
    from app.deps import get_store

    live, uploading = await deploy_versions(client, 2)
    await client.post(
        "/api/projects/demo/deployments/%s/promote" % live, headers=auth_headers()
    )
    for row in supabase.tables["deployments"]:
        if row["id"] == uploading:
            row["status"] = "pending"
    age_deployment(supabase, uploading, days=99)

    await gc.collect_project(get_store(), supabase.tables["projects"][0])

    assert uploading in {row["id"] for row in supabase.tables["deployments"]}
    assert objects_for(supabase, uploading), "a deploy in flight was truncated"


async def test_gc_leaves_the_row_alone_when_storage_deletion_fails(client, supabase):
    """The row is the only remaining record of which keys to remove. Losing it
    while the objects survive is exactly the unreclaimable state to avoid."""
    from app.deps import get_store

    ids = await deploy_versions(client, 7)
    for deployment_id in ids[:2]:
        age_deployment(supabase, deployment_id, days=30)

    async def boom(prefix):
        raise RuntimeError("storage is down")

    supabase.list_prefix = boom
    result = await gc.collect_project(get_store(), supabase.tables["projects"][0])

    assert result.deployments_deleted == 0
    assert result.errors
    assert ids[0] in {row["id"] for row in supabase.tables["deployments"]}


# =============================================================================
# 3. POST /api/admin/gc
# =============================================================================


ADMIN_TOKEN = "s3cret-admin-token-for-tests"


async def test_admin_gc_is_disabled_when_no_token_is_configured(client, override_settings):
    override_settings(admin_token="")
    response = await client.post(
        "/api/admin/gc", headers={"Authorization": "Bearer anything"}
    )
    assert response.status_code == 503
    assert "ADMIN_TOKEN" in response.json()["detail"]


async def test_admin_gc_rejects_a_wrong_token(client, override_settings):
    override_settings(admin_token=ADMIN_TOKEN)
    response = await client.post(
        "/api/admin/gc", headers={"Authorization": "Bearer wrong"}
    )
    assert response.status_code == 401


async def test_admin_gc_rejects_an_empty_token_against_an_empty_secret(
    client, override_settings
):
    """The failure mode this guards: `presented == expected` with both empty is
    True, which would open the endpoint precisely when it is unconfigured."""
    override_settings(admin_token="")
    response = await client.post("/api/admin/gc", headers={"Authorization": "Bearer "})
    assert response.status_code == 503


async def test_admin_gc_accepts_either_header(client, supabase, override_settings):
    override_settings(admin_token=ADMIN_TOKEN)
    ids = await deploy_versions(client, 7)
    for deployment_id in ids[:2]:
        age_deployment(supabase, deployment_id, days=30)

    response = await client.post(
        "/api/admin/gc", headers={"X-Admin-Token": ADMIN_TOKEN}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deployments_deleted"] == 1
    assert body["bytes_reclaimed"] > 0
    assert body["projects_scanned"] == 1


async def test_admin_gc_uses_a_constant_time_comparison():
    """`==` returns as soon as two bytes differ, which leaks how much of a
    guessed token was right. Assert the call, because the timing itself cannot
    be asserted reliably in a test."""
    import inspect

    from app.routers import admin

    source = inspect.getsource(admin)
    assert "hmac.compare_digest" in source
    assert "presented == expected" not in source


async def test_admin_gc_also_reaps_stuck_pending_deployments(
    client, supabase, override_settings
):
    override_settings(admin_token=ADMIN_TOKEN)
    await deploy_versions(client, 1)
    supabase.tables["deployments"][0].update(
        {
            "status": "pending",
            "created_at": (
                datetime.now(timezone.utc) - timedelta(minutes=45)
            ).isoformat(),
        }
    )

    response = await client.post(
        "/api/admin/gc", headers={"Authorization": "Bearer " + ADMIN_TOKEN}
    )
    assert response.status_code == 200
    assert response.json()["stuck_deployments_failed"] == 1
    assert supabase.tables["deployments"][0]["status"] == "failed"
    assert supabase.tables["deployments"][0]["error"] == "worker restarted"


# =============================================================================
# 4. Stuck `pending` deployments
# =============================================================================


async def test_a_deployment_pending_for_ten_minutes_is_marked_failed(client, supabase):
    """AUTODEPLOY.md section 6: a background task killed mid-deploy leaves a row
    that never resolves, and the dashboard polls it for ever."""
    gc.reset_reap_throttle()
    await deploy_versions(client, 1)
    supabase.tables["deployments"][0].update(
        {
            "status": "pending",
            "created_at": (
                datetime.now(timezone.utc) - timedelta(minutes=11)
            ).isoformat(),
        }
    )

    body = (await client.get("/api/projects", headers=auth_headers())).json()

    assert body[0]["last_deployment"]["status"] == "failed"
    assert body[0]["last_deployment"]["error"] == "worker restarted"


async def test_a_recent_pending_deployment_is_left_alone(client, supabase):
    """A deploy in progress must not be shot in the head at nine minutes."""
    gc.reset_reap_throttle()
    await deploy_versions(client, 1)
    supabase.tables["deployments"][0].update(
        {
            "status": "pending",
            "created_at": (
                datetime.now(timezone.utc) - timedelta(minutes=2)
            ).isoformat(),
        }
    )

    body = (await client.get("/api/projects", headers=auth_headers())).json()
    assert body[0]["last_deployment"]["status"] == "pending"


async def test_the_reaper_is_throttled(client, supabase):
    """It runs from a route the dashboard polls every two seconds."""
    gc.reset_reap_throttle()
    from app.deps import get_store

    calls = []
    real_update = supabase.update

    async def counting_update(table, params, patch):
        if patch.get("error") == "worker restarted":
            calls.append(1)
        return await real_update(table, params, patch)

    supabase.update = counting_update

    for _ in range(5):
        await gc.maybe_reap(get_store())
    assert len(calls) == 1


# =============================================================================
# 5. Build logs
# =============================================================================


def test_truncate_keeps_the_tail_not_the_head():
    """A build fails at the end. The head of the log is `npm ci` chatter."""
    text = "\n".join("line %d" % index for index in range(1000))
    result = truncate_build_log(text)

    lines = result.split("\n")
    assert len(lines) == BUILD_LOG_MAX_LINES
    assert lines[-1] == "line 999"
    assert "line 0" not in lines


def test_truncate_caps_bytes_as_well_as_lines():
    """200 lines of minified bundler output can still be megabytes."""
    result = truncate_build_log("x" * 500_000)
    assert len(result.encode()) < 70_000
    assert result.startswith("[log truncated]")


def test_truncate_normalises_windows_line_endings():
    assert truncate_build_log("a\r\nb\r\nc") == "a\nb\nc"


async def enable_token(client, supabase, github, slug: str = "demo") -> str:
    """Turn on builds for a project and return the raw deploy token."""
    await connect_github(client, supabase)
    await deploy_versions(client, 1, slug=slug)
    project = next(p for p in supabase.tables["projects"] if p["slug"] == slug)
    project["repo_full_name"] = "octocat/hello-world"
    project["repo_branch"] = "main"

    response = await client.post(
        "/api/projects/%s/builds" % slug, headers=auth_headers()
    )
    assert response.status_code == 200, response.text
    # The raw token only ever exists in GitHub's secret store. Open the sealed
    # box the way GitHub would, which is exactly what a runner reads back as
    # `secrets.MINIVERCEL_TOKEN`.
    return github.open_secret("MINIVERCEL_TOKEN")


async def test_a_runner_can_post_a_build_log_with_its_deploy_token(
    client, supabase, github
):
    token = await enable_token(client, supabase, github)
    deployment_id = supabase.tables["deployments"][0]["id"]

    response = await client.post(
        "/api/deployments/%s/logs" % deployment_id,
        headers={"Authorization": "Bearer " + token, "Content-Type": "text/plain"},
        content=b"npm ci\nnpm run build\nDone in 4.2s",
    )
    assert response.status_code == 202, response.text

    row = supabase.tables["deployments"][0]
    assert "Done in 4.2s" in row["build_log"]
    assert row["build_log_at"]


async def test_a_posted_log_is_truncated_to_two_hundred_lines(client, supabase, github):
    token = await enable_token(client, supabase, github)
    deployment_id = supabase.tables["deployments"][0]["id"]

    await client.post(
        "/api/deployments/%s/logs" % deployment_id,
        headers={"Authorization": "Bearer " + token, "Content-Type": "text/plain"},
        content="\n".join("l%d" % index for index in range(500)).encode(),
    )
    stored = supabase.tables["deployments"][0]["build_log"]
    assert len(stored.split("\n")) == BUILD_LOG_MAX_LINES
    assert stored.endswith("l499")


async def test_a_deploy_token_cannot_write_to_another_projects_deployment(
    client, supabase, github
):
    token = await enable_token(client, supabase, github, slug="mine")
    other = (await deploy_versions(client, 1, slug="theirs"))[0]

    response = await client.post(
        "/api/deployments/%s/logs" % other,
        headers={"Authorization": "Bearer " + token, "Content-Type": "text/plain"},
        content=b"nothing to see",
    )
    assert response.status_code == 404, "and 404, not 403 - do not confirm the id"


async def test_an_oversized_log_body_is_refused(client, supabase, github):
    token = await enable_token(client, supabase, github)
    deployment_id = supabase.tables["deployments"][0]["id"]

    response = await client.post(
        "/api/deployments/%s/logs" % deployment_id,
        headers={"Authorization": "Bearer " + token, "Content-Type": "text/plain"},
        content=b"x" * (600 * 1024),
    )
    assert response.status_code == 413


async def test_the_owner_can_read_a_build_log_back(client, supabase, github):
    token = await enable_token(client, supabase, github)
    deployment_id = supabase.tables["deployments"][0]["id"]
    await client.post(
        "/api/deployments/%s/logs" % deployment_id,
        headers={"Authorization": "Bearer " + token, "Content-Type": "text/plain"},
        content=b"error TS2304: Cannot find name 'foo'.",
    )

    response = await client.get(
        "/api/deployments/%s/logs" % deployment_id, headers=auth_headers()
    )
    assert response.status_code == 200
    assert "TS2304" in response.json()["log"]


async def test_another_user_cannot_read_a_build_log(client, supabase, github):
    token = await enable_token(client, supabase, github)
    deployment_id = supabase.tables["deployments"][0]["id"]
    await client.post(
        "/api/deployments/%s/logs" % deployment_id,
        headers={"Authorization": "Bearer " + token, "Content-Type": "text/plain"},
        content=b"secrets in build output",
    )

    response = await client.get(
        "/api/deployments/%s/logs" % deployment_id,
        headers=auth_headers(OTHER_USER_ID),
    )
    assert response.status_code == 404


async def test_the_deployment_list_says_a_log_exists_without_carrying_it(
    client, supabase, github
):
    token = await enable_token(client, supabase, github)
    deployment_id = supabase.tables["deployments"][0]["id"]
    await client.post(
        "/api/deployments/%s/logs" % deployment_id,
        headers={"Authorization": "Bearer " + token, "Content-Type": "text/plain"},
        content=b"a log",
    )

    body = (await client.get("/api/projects/demo", headers=auth_headers())).json()
    row = next(d for d in body["deployments"] if d["id"] == deployment_id)
    assert row["has_build_log"] is True
    assert "build_log" not in row, "the list must not carry log text"


async def test_a_build_that_never_produced_a_zip_is_still_recorded(
    client, supabase, github
):
    """Before this, a failed `npm run build` left no row at all and the
    dashboard went on showing the last successful deploy."""
    token = await enable_token(client, supabase, github)
    before = len(supabase.tables["deployments"])

    response = await client.post(
        "/api/deployments/build-failed",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "text/plain",
            "X-Commit-Sha": "a" * 40,
        },
        content=b"npm ERR! Missing script: build",
    )
    assert response.status_code == 201, response.text

    assert len(supabase.tables["deployments"]) == before + 1
    row = supabase.tables["deployments"][-1]
    assert row["status"] == "failed"
    assert row["commit_sha"] == "a" * 40
    assert "npm ERR!" in row["build_log"]
    assert "GitHub Actions" in row["error"]

    # It owns no objects and, being failed, costs the user no quota.
    assert objects_for(supabase, row["id"]) == []
    me = (await client.get("/api/me", headers=auth_headers())).json()
    assert me["usage"]["bytes_used"] == sum(
        d["size_bytes"] for d in supabase.tables["deployments"] if d["status"] != "failed"
    )


async def test_a_user_jwt_cannot_report_a_build_failure(client, supabase):
    """A browser has no business inventing a failed deployment."""
    await deploy_versions(client, 1)
    response = await client.post(
        "/api/deployments/build-failed",
        headers={**auth_headers(), "Content-Type": "text/plain"},
        content=b"pretend this failed",
    )
    assert response.status_code == 403


async def test_build_logs_degrade_gracefully_without_the_migration(client):
    """db/006_phase5.sql not applied: everything else must keep working."""
    from app import cache, deps
    from app.store import Store

    supabase = FakeSupabase(supports_build_log=False)
    cache.clear_all()
    deps.set_store(Store(supabase))

    response = await deploy(client, site("v0"))
    assert response.status_code == 201, "a deploy must not depend on build logs"

    body = (await client.get("/api/projects/demo", headers=auth_headers())).json()
    assert body["deployments"][0]["has_build_log"] is False


# =============================================================================
# 6. Delete correctness
# =============================================================================


async def test_deleting_a_project_leaves_no_storage_objects_behind(client, supabase):
    """The four steps of AUTODEPLOY.md section 7, and the one that gets skipped.

    Storage is NOT covered by `ON DELETE CASCADE` - Postgres has no idea those
    files exist - so a project deleted without step 2 leaves every object of
    every deployment in a 1 GB bucket with nothing left to name them.
    """
    ids = await deploy_versions(client, 3)
    assert len(ids) == 3
    assert len(supabase.objects) == 6, "three deployments of two files each"
    for deployment_id in ids:
        assert objects_for(supabase, deployment_id)

    response = await client.delete("/api/projects/demo", headers=auth_headers())
    assert response.status_code == 204

    # 2. every object of every deployment, not only the live one.
    assert supabase.objects == {}, "orphaned storage objects after delete"
    # 3. the rows.
    assert supabase.tables["projects"] == []
    assert supabase.tables["deployments"] == []
    # 4. the slug is free again.
    again = await deploy(client, site("v0"), slug="demo")
    assert again.status_code == 201


async def test_deleting_a_project_removes_the_github_webhook_first(
    client, supabase, github
):
    """Step 1. A hook left registered delivers pushes to a 401 for ever."""
    await connect_github(client, supabase)
    imported = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": "octocat/hello-world"}
    )
    assert imported.status_code == 201
    slug = imported.json()["slug"]

    response = await client.delete(
        "/api/projects/%s" % slug, headers=auth_headers()
    )
    assert response.status_code == 204
    assert github.deleted_hooks, "the push webhook was left registered"
    assert supabase.objects == {}


async def test_deleting_another_users_project_is_a_404(client, supabase):
    await deploy_versions(client, 1)
    response = await client.delete(
        "/api/projects/demo", headers=auth_headers(OTHER_USER_ID)
    )
    assert response.status_code == 404
    assert supabase.objects, "nothing may be deleted on a 404"


# =============================================================================
# 7. Quota reporting
# =============================================================================


async def test_me_reports_bytes_used_against_the_limit(client, supabase):
    await deploy_versions(client, 2)
    body = (await client.get("/api/me", headers=auth_headers())).json()

    stored = sum(
        row["size_bytes"]
        for row in supabase.tables["deployments"]
        if row["status"] != "failed"
    )
    assert body["usage"]["bytes_used"] == stored
    assert body["usage"]["bytes_limit"] == get_settings().max_user_bytes
    assert body["usage"]["bytes_available"] == (
        get_settings().max_user_bytes - stored
    )
    assert body["usage"]["retention"]["keep_recent_ready"] == gc.KEEP_RECENT_READY
    assert body["usage"]["retention"]["max_age_days"] == gc.MAX_AGE_DAYS


async def test_bytes_used_falls_after_collection(client, supabase):
    """The quota bar has to move when GC frees space, or the user is told they
    are full when they are not."""
    from app.deps import get_store

    ids = await deploy_versions(client, 7)
    for deployment_id in ids[:2]:
        age_deployment(supabase, deployment_id, days=30)

    before = (await client.get("/api/me", headers=auth_headers())).json()
    await gc.collect_project(get_store(), supabase.tables["projects"][0])
    after = (await client.get("/api/me", headers=auth_headers())).json()

    assert after["usage"]["bytes_used"] < before["usage"]["bytes_used"]


async def test_quota_refusal_says_what_to_do(client, supabase, override_settings):
    override_settings(max_user_bytes=64)
    response = await deploy(client, site("v0"))

    assert response.status_code == 413
    detail = response.json()["detail"]
    assert "MB used" in detail or "MB of your" in detail
    assert "0.0 MB limit" in detail
    assert "delete old deployments" in detail.lower()
