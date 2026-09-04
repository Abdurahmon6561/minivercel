"""scripts/reimport_all.py - the PUBLIC_BASE_URL migration script.

Drives `_reimport_one` directly against the same fake Supabase (conftest.py)
and fake GitHub (test_github.py) harnesses the rest of the suite uses, so this
exercises the real webhook-update and workflow-commit calls without a network.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.crypto import encrypt  # noqa: E402
from app.deploytoken import fingerprint, generate as generate_deploy_token  # noqa: E402
from app.gitops import WORKFLOW_PATH  # noqa: E402

from .conftest import USER_ID, auth_headers  # noqa: E402
from .test_github import REPO, connect_github  # noqa: E402
from .test_github import github  # noqa: E402,F401  (pytest fixture, used implicitly)

from scripts.reimport_all import _reimport_one  # noqa: E402


async def _imported_project(client, supabase, github, *, builds_enabled=False):
    await connect_github(client, supabase)
    response = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
    )
    assert response.status_code == 201, response.text
    project = supabase.tables["projects"][0]

    if builds_enabled:
        # Mirrors what POST /api/projects/{slug}/builds does, without a second
        # round trip through the app: a token, its fingerprint, the flag.
        token = generate_deploy_token()
        project["deploy_token_sha256"] = fingerprint(token)
        project["builds_enabled"] = True
        project["build_command"] = "npm run build"
        project["output_dir"] = "dist"
        github.hooks.setdefault(project["webhook_id"], {"config": {}})
        github.files[WORKFLOW_PATH] = "# stale workflow, old PUBLIC_BASE_URL\n"

    return project


async def test_reimport_updates_the_webhook_url(client, supabase, github):
    from app.deps import get_store

    project = await _imported_project(client, supabase, github)
    old_url = github.hooks[project["webhook_id"]]["config"]["url"]

    new_settings = dataclasses.replace(
        get_settings(), public_base_url="https://api.getdropbin.xyz"
    )
    outcome, detail = await _reimport_one(
        get_store(), new_settings, project, dry_run=False
    )

    assert outcome == "updated", detail
    new_config = github.hooks[project["webhook_id"]]["config"]
    assert new_config["url"] == "https://api.getdropbin.xyz/api/webhooks/github"
    assert new_config["url"] != old_url
    # The secret must survive the update untouched - see app/github.py
    # `update_webhook_url`'s docstring for why this is checked explicitly.
    assert new_config["secret"] == old_config_secret_for(supabase, project)


def old_config_secret_for(supabase, project) -> str:
    from app.config import get_settings
    from app.crypto import decrypt

    return decrypt(project["webhook_secret"], get_settings())


async def test_reimport_updates_the_workflow_when_builds_are_enabled(
    client, supabase, github
):
    from app.deps import get_store

    project = await _imported_project(client, supabase, github, builds_enabled=True)
    assert github.files[WORKFLOW_PATH].startswith("# stale")

    new_settings = dataclasses.replace(
        get_settings(), public_base_url="https://api.getdropbin.xyz"
    )
    outcome, detail = await _reimport_one(
        get_store(), new_settings, project, dry_run=False
    )

    assert outcome == "updated", detail
    assert "https://api.getdropbin.xyz/api/deployments" in github.files[WORKFLOW_PATH]
    assert "workflow -> https://api.getdropbin.xyz" in detail


async def test_dry_run_touches_nothing(client, supabase, github):
    from app.deps import get_store

    project = await _imported_project(client, supabase, github)
    before = dict(github.hooks[project["webhook_id"]]["config"])

    new_settings = dataclasses.replace(
        get_settings(), public_base_url="https://api.getdropbin.xyz"
    )
    outcome, detail = await _reimport_one(
        get_store(), new_settings, project, dry_run=True
    )

    assert outcome == "updated", detail  # reports what *would* change
    assert github.hooks[project["webhook_id"]]["config"] == before


async def test_a_project_with_no_repo_is_skipped(client, supabase):
    from app.deps import get_store

    created = await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "no-repo"}
    )
    project = supabase.tables["projects"][0]
    assert created.status_code == 201

    outcome, detail = await _reimport_one(
        get_store(), get_settings(), project, dry_run=False
    )
    assert outcome == "skipped"


async def test_a_revoked_github_connection_is_reported_not_raised(
    client, supabase, github
):
    from app.deps import get_store

    project = await _imported_project(client, supabase, github)
    await supabase_delete_token(supabase, USER_ID)

    outcome, detail = await _reimport_one(
        get_store(), get_settings(), project, dry_run=False
    )
    assert outcome == "failed"
    assert "GitHub" in detail


async def supabase_delete_token(supabase, user_id: str) -> None:
    supabase.tables["github_tokens"] = [
        row for row in supabase.tables["github_tokens"] if row.get("user_id") != user_id
    ]
