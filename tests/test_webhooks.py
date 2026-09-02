"""POST /api/webhooks/github.

The signature check is the whole security boundary of this endpoint: the body is
attacker-controlled until it verifies, and a push triggers a deploy. Most of
what follows is that boundary from different angles.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from app import cache, deps
from app.config import get_settings
from app.crypto import encrypt
from app.routers.webhooks import signature_matches
from app.store import Store

from .conftest import USER_ID, auth_headers

SECRET = "5f2b" * 16
REPO = "octocat/hello-world"
SHA = "9" * 40


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def push_payload(*, ref: str = "refs/heads/main", after: str = SHA, **extra) -> bytes:
    payload = {
        "ref": ref,
        "after": after,
        "repository": {"full_name": REPO},
        "head_commit": {"id": after},
    }
    payload.update(extra)
    return json.dumps(payload).encode()


async def linked_project(client, supabase, **overrides):
    """A project wired to REPO, the way /api/projects/import leaves it."""
    created = await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "Hooked", "slug": "hooked"}
    )
    project_id = created.json()["id"]
    row = next(p for p in supabase.tables["projects"] if p["id"] == project_id)
    row.update(
        {
            "repo_full_name": REPO,
            "repo_branch": "main",
            "webhook_id": 12345,
            "webhook_secret": encrypt(SECRET, get_settings()),
        }
    )
    row.update(overrides)
    cache.clear_all()
    return row


async def post_hook(client, body: bytes, *, signature: str | None = None, event="push"):
    headers = {"X-GitHub-Event": event, "Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return await client.post("/api/webhooks/github", content=body, headers=headers)


# -- signature verification ---------------------------------------------------


def test_signature_matches_accepts_a_correct_signature():
    body = b'{"ref":"refs/heads/main"}'
    assert signature_matches(SECRET, body, sign(body))


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "sha1=deadbeef",                      # wrong algorithm
        "deadbeef",                           # no prefix
        "sha256=",                            # empty digest
        "sha256=" + "0" * 64,                 # wrong digest
        "sha256=not-hex-at-all",
    ],
)
def test_signature_matches_rejects_everything_else(header):
    assert not signature_matches(SECRET, b'{"a":1}', header)


def test_signature_is_body_specific():
    body = b'{"ref":"refs/heads/main"}'
    signature = sign(body)
    assert not signature_matches(SECRET, body + b" ", signature)


def test_a_wrong_secret_does_not_verify():
    """The named requirement: verification rejects a wrong secret."""
    body = push_payload()
    assert signature_matches(SECRET, body, sign(body, SECRET))
    assert not signature_matches(SECRET, body, sign(body, "the-wrong-secret"))


# -- the endpoint -------------------------------------------------------------


async def test_a_wrong_secret_is_rejected_and_deploys_nothing(client, supabase):
    await linked_project(client, supabase)
    body = push_payload()

    response = await post_hook(client, body, signature=sign(body, "wrong-secret"))
    assert response.status_code == 401
    assert supabase.tables["deployments"] == []


async def test_a_missing_signature_is_rejected(client, supabase):
    await linked_project(client, supabase)
    response = await post_hook(client, push_payload())
    assert response.status_code == 401
    assert supabase.tables["deployments"] == []


async def test_an_unknown_repository_is_rejected(client, supabase):
    await linked_project(client, supabase)
    body = json.dumps(
        {"ref": "refs/heads/main", "after": SHA, "repository": {"full_name": "who/what"}}
    ).encode()
    response = await post_hook(client, body, signature=sign(body))
    assert response.status_code == 401


async def test_ping_is_answered_without_deploying(client, supabase):
    await linked_project(client, supabase)
    body = json.dumps({"zen": "Design for failure."}).encode()
    response = await post_hook(client, body, signature=sign(body), event="ping")
    assert response.status_code == 200
    assert response.json()["status"] == "pong"
    assert supabase.tables["deployments"] == []


async def test_a_push_to_another_branch_is_ignored(client, supabase):
    await linked_project(client, supabase)
    body = push_payload(ref="refs/heads/feature-x")
    response = await post_hook(client, body, signature=sign(body))
    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert supabase.tables["deployments"] == []


async def test_a_branch_deletion_is_ignored(client, supabase):
    """A deleted branch arrives as a push whose `after` is all zeros."""
    await linked_project(client, supabase)
    body = push_payload(after="0" * 40, deleted=True)
    response = await post_hook(client, body, signature=sign(body))
    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert supabase.tables["deployments"] == []


async def test_a_non_push_event_is_ignored(client, supabase):
    await linked_project(client, supabase)
    body = push_payload()
    response = await post_hook(client, body, signature=sign(body), event="issues")
    assert response.status_code == 202
    assert response.json()["status"] == "ignored"


# -- the on/off switch --------------------------------------------------------


async def test_auto_deploy_disabled_records_the_push_and_deploys_nothing(
    client, supabase
):
    """The named requirement: a push with auto_deploy_enabled=false creates no
    deployment - and the webhook stays registered so it can be turned back on."""
    project = await linked_project(client, supabase, auto_deploy_enabled=False)
    body = push_payload()

    response = await post_hook(client, body, signature=sign(body))
    assert response.status_code == 202
    assert response.json() == {
        "status": "ignored",
        "reason": "auto-deploy disabled",
    }
    assert supabase.tables["deployments"] == []

    # Recorded, not silently dropped.
    assert project["last_webhook_status"] == "ignored"
    assert project["last_webhook_detail"] == "auto-deploy disabled"
    assert project["last_webhook_sha"] == SHA

    # And the hook is still registered.
    assert project["webhook_id"] == 12345


async def test_builds_enabled_defers_to_github_actions(client, supabase):
    """Otherwise every push produces two deployments, the second one wrong."""
    project = await linked_project(client, supabase, builds_enabled=True)
    body = push_payload()

    response = await post_hook(client, body, signature=sign(body))
    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert supabase.tables["deployments"] == []
    assert "Actions" in project["last_webhook_detail"]


async def test_an_accepted_push_answers_202_immediately(client, supabase, monkeypatch):
    """GitHub allows 10 seconds; the deploy runs in a BackgroundTask."""
    await linked_project(client, supabase)

    started = []

    async def fake_deploy(store, settings, *, project, commit_sha=None, deployment_id=None):
        started.append((commit_sha, deployment_id))
        return deployment_id

    monkeypatch.setattr("app.routers.webhooks.deploy_from_repo", fake_deploy)

    body = push_payload()
    response = await post_hook(client, body, signature=sign(body))
    assert response.status_code == 202
    assert response.json()["status"] == "queued"

    # The row exists and its id is in the 202, so the dashboard has something to
    # poll while the background task runs (AUTODEPLOY.md section 8).
    deployment_id = response.json()["deployment_id"]
    assert [row["id"] for row in supabase.tables["deployments"]] == [deployment_id]
    assert supabase.tables["deployments"][0]["commit_sha"] == SHA
    assert started == [(SHA, deployment_id)]



async def test_malformed_json_is_rejected(client, supabase):
    await linked_project(client, supabase)
    body = b"not json at all"
    response = await post_hook(client, body, signature=sign(body))
    assert response.status_code == 400


async def test_two_projects_on_one_repo_are_told_apart_by_secret(client, supabase):
    """Two users may import the same public repo; the signature disambiguates."""
    mine = await linked_project(client, supabase)

    other_secret = "abcd" * 16
    created = await client.post(
        "/api/projects",
        headers=auth_headers(),
        json={"name": "Theirs", "slug": "theirs"},
    )
    theirs = next(
        p for p in supabase.tables["projects"] if p["id"] == created.json()["id"]
    )
    theirs.update(
        {
            "repo_full_name": REPO,
            "repo_branch": "main",
            "webhook_id": 999,
            "webhook_secret": encrypt(other_secret, get_settings()),
            "auto_deploy_enabled": False,  # so we can tell which one matched
        }
    )
    cache.clear_all()

    body = push_payload()
    response = await post_hook(client, body, signature=sign(body, other_secret))
    assert response.status_code == 202
    assert response.json()["reason"] == "auto-deploy disabled"
    assert theirs["last_webhook_status"] == "ignored"
    assert mine["last_webhook_status"] is None, "the other project must be untouched"


async def test_oversized_payload_is_refused(client, supabase):
    await linked_project(client, supabase)
    body = b"x" * (3 * 1024 * 1024)
    response = await post_hook(client, body, signature=sign(body))
    assert response.status_code == 413


# -- the startup reaper -------------------------------------------------------


async def test_stuck_pending_deployments_are_failed(supabase):
    """A pending row older than 10 minutes is a dead worker, not a slow one."""
    from datetime import datetime, timedelta, timezone

    project = await supabase.insert(
        "projects", {"owner_id": USER_ID, "name": "P", "slug": "reap-me"}
    )
    for status_name in ("pending", "pending", "ready"):
        await supabase.insert(
            "deployments", {"project_id": project["id"], "status": status_name}
        )
    # `insert` returns a copy, so reach for the stored rows themselves.
    old, recent, ready = supabase.tables["deployments"]
    old["created_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=30)
    ).isoformat()

    reaped = await Store(supabase).reap_stuck_pending(10)
    assert reaped == 1
    assert old["status"] == "failed"
    assert old["error"] == "worker restarted"
    assert recent["status"] == "pending", "a fresh deploy in flight must survive"
    assert ready["status"] == "ready"


async def test_reaper_runs_without_a_database(client):
    """Startup housekeeping must never stop the service from booting."""
    deps.set_store(None)
    # The app is already constructed; just prove the call path is guarded.
    from app.main import lifespan
    from app.main import app as real_app

    async with lifespan(real_app):
        pass
    assert True
