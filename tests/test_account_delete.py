"""DELETE /api/me - closing an account.

The property that matters is that nothing is left behind and nothing external
can prevent it. A user whose GitHub token was revoked, or who lost admin on a
repository, must still be able to leave.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.crypto import encrypt
from app.github import GitHubError

from .conftest import USER_ID, auth_headers, deploy, make_zip

OTHER_USER = "22222222-2222-4222-8222-222222222222"

pytestmark = pytest.mark.anyio


async def make_project(client, slug: str, subject: str = USER_ID):
    response = await deploy(
        client, make_zip({"index.html": "<h1>hi</h1>"}), slug=slug, subject=subject
    )
    assert response.status_code == 201, response.text
    return response.json()


async def add_env_var(client, slug: str, key: str, subject: str = USER_ID):
    response = await client.post(
        f"/api/projects/{slug}/env",
        headers=auth_headers(subject),
        json={"key": key, "value": "secret-value"},
    )
    assert response.status_code == 201, response.text


def connect_github(supabase, user_id: str = USER_ID, *, webhook_id: int = 4242):
    """Give the user a stored token and point a project at a repository."""
    supabase.tables["github_tokens"].append(
        {
            "user_id": user_id,
            "encrypted_token": encrypt("ghp_test", get_settings()),
            "scopes": "repo,workflow",
            "github_login": "octocat",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    )
    for project in supabase.tables["projects"]:
        if project["owner_id"] == user_id:
            project["repo_full_name"] = "octocat/hello-world"
            project["repo_branch"] = "main"
            project["webhook_id"] = webhook_id


# -- happy path ----------------------------------------------------------------


async def test_deletes_projects_deployments_env_vars_token_and_the_user(
    client, supabase
):
    await make_project(client, "alpha")
    await make_project(client, "beta")
    await add_env_var(client, "alpha", "API_TOKEN")
    await add_env_var(client, "beta", "OTHER_TOKEN")
    supabase.tables["github_tokens"].append(
        {
            "user_id": USER_ID,
            "encrypted_token": encrypt("ghp_test", get_settings()),
            "scopes": "repo",
            "github_login": "octocat",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    )

    assert len(supabase.tables["projects"]) == 2
    assert len(supabase.tables["deployments"]) == 2
    assert len(supabase.tables["project_env_vars"]) == 2
    assert supabase.objects  # storage has files in it

    response = await client.delete("/api/me", headers=auth_headers())
    assert response.status_code == 204, response.text

    assert supabase.tables["projects"] == []
    assert supabase.tables["deployments"] == []
    assert supabase.tables["github_tokens"] == []
    assert supabase.objects == {}, "storage objects were orphaned"
    # The auth user itself, not just its rows.
    assert supabase.deleted_auth_users == [USER_ID]


async def test_deleting_an_account_with_nothing_in_it_succeeds(client, supabase):
    response = await client.delete("/api/me", headers=auth_headers())
    assert response.status_code == 204
    assert supabase.deleted_auth_users == [USER_ID]


async def test_env_vars_go_with_their_projects(client, supabase):
    """They cascade on the project row rather than being deleted separately."""
    await make_project(client, "alpha")
    await add_env_var(client, "alpha", "API_TOKEN")
    assert len(supabase.tables["project_env_vars"]) == 1

    assert (await client.delete("/api/me", headers=auth_headers())).status_code == 204
    assert supabase.tables["project_env_vars"] == []


# -- external failures must not trap the user ----------------------------------


async def test_a_failing_github_webhook_removal_does_not_block_deletion(
    client, supabase, monkeypatch
):
    """GitHub being unreachable cannot make an account undeletable."""
    await make_project(client, "alpha")
    connect_github(supabase)

    called = []

    async def explode(*args, **kwargs):
        called.append(True)
        raise GitHubError("github is down", status_code=503)

    # Patched where it is USED, not where it is defined: projectops does
    # `from .gitops import client_for_user`, so patching app.gitops would
    # rebind a name this code no longer looks at and the test would pass
    # without ever reaching the failure path.
    monkeypatch.setattr("app.projectops.client_for_user", explode)

    response = await client.delete("/api/me", headers=auth_headers())
    assert response.status_code == 204, response.text
    assert called, "the GitHub cleanup path was never reached"
    assert supabase.tables["projects"] == []
    assert supabase.deleted_auth_users == [USER_ID]


async def test_a_revoked_github_token_does_not_block_deletion(client, supabase):
    """No stored token at all, on a project that claims a repo and a webhook."""
    await make_project(client, "alpha")
    for project in supabase.tables["projects"]:
        project["repo_full_name"] = "octocat/hello-world"
        project["webhook_id"] = 4242
    assert supabase.tables["github_tokens"] == []

    response = await client.delete("/api/me", headers=auth_headers())
    assert response.status_code == 204, response.text
    assert supabase.tables["projects"] == []
    assert supabase.deleted_auth_users == [USER_ID]


# -- ownership -----------------------------------------------------------------


async def test_deleting_my_account_leaves_everyone_else_alone(client, supabase):
    await make_project(client, "mine")
    await add_env_var(client, "mine", "MY_TOKEN")
    await make_project(client, "theirs", subject=OTHER_USER)
    await add_env_var(client, "theirs", "THEIR_TOKEN", subject=OTHER_USER)
    supabase.tables["github_tokens"].extend(
        [
            {"user_id": USER_ID, "encrypted_token": "x", "scopes": None,
             "github_login": None, "updated_at": None},
            {"user_id": OTHER_USER, "encrypted_token": "y", "scopes": None,
             "github_login": None, "updated_at": None},
        ]
    )

    response = await client.delete("/api/me", headers=auth_headers())
    assert response.status_code == 204

    remaining = supabase.tables["projects"]
    assert [p["slug"] for p in remaining] == ["theirs"]
    assert [v["key"] for v in supabase.tables["project_env_vars"]] == ["THEIR_TOKEN"]
    assert [t["user_id"] for t in supabase.tables["github_tokens"]] == [OTHER_USER]
    assert supabase.deleted_auth_users == [USER_ID]

    # And the other user is still able to use their account afterwards.
    listed = await client.get("/api/projects", headers=auth_headers(OTHER_USER))
    assert listed.status_code == 200
    assert [p["slug"] for p in listed.json()] == ["theirs"]


async def test_requires_authentication(client, supabase):
    await make_project(client, "mine")
    response = await client.delete("/api/me")
    assert response.status_code == 401
    assert supabase.tables["projects"] != []
    assert supabase.deleted_auth_users == []


async def test_a_forged_token_cannot_delete_an_account(client, supabase):
    await make_project(client, "mine")
    response = await client.delete(
        "/api/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
    assert supabase.deleted_auth_users == []
