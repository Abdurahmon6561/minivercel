"""GitHub-driven deployments and build enablement.

Sits between the routers and `app/github.py`, and owns the two flows that need
more than one API call to be correct:

  * deploy_from_repo - download a zipball, run it through the Phase 1 pipeline
  * enable_builds / disable_builds - deploy token, Actions secret, workflow file

Phase 4's whole point (SPEC.md): **we never run `npm install`.** The workflow
committed here runs on GitHub's runner, paid for by GitHub, with no access to
our database. We receive only a zip of static output, through the same validated
endpoint as everything else.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import tempfile
import uuid

from . import deploytoken
from .config import Settings
from .crypto import EncryptionUnavailable, decrypt
from .deployer import QuotaExceeded, cleanup, mark_failed, publish
from .github import (
    SECRET_SCOPES,
    WORKFLOW_SCOPES,
    GitHubClient,
    GitHubError,
    has_scope,
    missing_scope_message,
    split_repo,
)
from .store import Store
from .urls import api_base_url
from .zipvalidate import ZipRejected

log = logging.getLogger("minivercel.gitops")

WORKFLOW_PATH = ".github/workflows/minivercel.yml"
SECRET_NAME = "MINIVERCEL_TOKEN"

# The build command runs on the user's own runner in the user's own repo, so
# this is not a cross-tenant boundary - but a newline would break out of the
# YAML scalar and rewrite the workflow, so both fields are constrained.
BUILD_COMMAND_RE = re.compile(r"^[A-Za-z0-9 _.,:/@=+\-]{1,200}$")
OUTPUT_DIR_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,99}$")


class GitOpsError(Exception):
    """Message is safe to show the user."""


def validate_build_settings(build_command: str | None, output_dir: str | None) -> None:
    if build_command is not None and not BUILD_COMMAND_RE.match(build_command):
        raise GitOpsError(
            "Build command may only contain letters, digits, spaces and "
            "._,:/@=+- and must be under 200 characters."
        )
    if output_dir is not None:
        if not OUTPUT_DIR_RE.match(output_dir):
            raise GitOpsError(
                "Output directory must be a relative path of letters, digits "
                "and ._/- characters."
            )
        if output_dir.startswith("/") or ".." in output_dir.split("/"):
            raise GitOpsError("Output directory must stay inside the repository.")


async def client_for_user(store: Store, settings: Settings, user_id: str) -> GitHubClient:
    """Decrypt the stored provider token and open a client with it."""
    row = await store.get_github_token_row(user_id)
    if row is None:
        raise GitOpsError(
            "GitHub is not connected. Sign out and sign in again to reconnect."
        )
    try:
        token = decrypt(row["encrypted_token"], settings)
    except EncryptionUnavailable as exc:
        raise GitOpsError(
            "The stored GitHub token could not be read. Sign out and sign in "
            "again to reconnect."
        ) from exc
    return GitHubClient(token)


def new_webhook_secret() -> str:
    return secrets.token_hex(32)


# -- deploying from a repository ---------------------------------------------


async def deploy_from_repo(
    store: Store,
    settings: Settings,
    *,
    project: dict,
    commit_sha: str | None = None,
    deployment_id: str | None = None,
) -> str | None:
    """Download the repo at its branch and publish it. Returns a deployment id.

    `deployment_id` lets the caller create the row *before* handing this to a
    BackgroundTask, so it can return the id in the 202 and the dashboard has
    something to poll (AUTODEPLOY.md section 8). When omitted the row is created
    here.

    Safe to run as a BackgroundTask: it never raises. Every failure is written
    to the deployment row, where the dashboard shows it.

    A failure leaves `projects.live_deployment_id` untouched - a broken push
    must not take a working site down.
    """
    repo_full_name = project.get("repo_full_name")
    if not repo_full_name:
        return None

    tmp_dir = tempfile.gettempdir()
    zip_path = os.path.join(tmp_dir, "mv-repo-%s.zip" % uuid.uuid4().hex)
    extract_root = ""

    try:
        owner, name = split_repo(repo_full_name)
        branch = project.get("repo_branch") or "main"

        if deployment_id is None:
            deployment_id = (await store.create_deployment(project["id"], commit_sha))["id"]
        extract_root = os.path.join(tmp_dir, "mv-%s" % deployment_id)

        client = await client_for_user(store, settings, project["owner_id"])
        try:
            size = await client.download_zipball(
                owner, name, commit_sha or branch, zip_path
            )
        finally:
            await client.aclose()

        log.info(
            "downloaded %s@%s (%d bytes) for deployment %s",
            repo_full_name,
            commit_sha or branch,
            size,
            deployment_id,
        )

        await publish(
            store,
            settings,
            project=project,
            deployment_id=deployment_id,
            zip_path=zip_path,
            extract_root=extract_root,
            owner_id=project["owner_id"],
            # A repository is not a website: look for dist/ build/ public/ _site/.
            allow_build_output_dirs=True,
        )
        return deployment_id

    except (ZipRejected, QuotaExceeded, GitOpsError, GitHubError) as exc:
        log.warning("repo deploy failed for %s: %s", repo_full_name, exc)
        if deployment_id:
            await mark_failed(store, deployment_id, str(exc))
        return deployment_id
    except Exception as exc:
        log.exception("unexpected failure deploying %s", repo_full_name)
        if deployment_id:
            await mark_failed(
                store, deployment_id, "Internal error while deploying from GitHub."
            )
        del exc
        return deployment_id
    finally:
        cleanup(zip_path, extract_root)


# -- Phase 4: builds ----------------------------------------------------------


def render_workflow(
    *,
    branch: str,
    build_command: str,
    output_dir: str,
    api_base_url: str,
    slug: str,
) -> str:
    """The workflow committed to the user's repository.

    Deliberately minimal and readable: the user can see exactly what runs in
    their repo, and it does nothing beyond build, zip, and POST.
    """
    return f"""# Managed by MiniVercel. Regenerated whenever builds are re-enabled.
# Deploys {slug} from the {output_dir}/ directory on every push to {branch}.
name: Deploy to MiniVercel

on:
  push:
    branches: [{branch}]
  workflow_dispatch:

concurrency:
  group: minivercel-{slug}
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: |
          if [ -f package-lock.json ]; then
            npm ci --no-audit --no-fund
          else
            npm install --no-audit --no-fund
          fi

      - name: Build
        run: {build_command}

      - name: Package {output_dir}
        run: |
          if [ ! -f "{output_dir}/index.html" ]; then
            echo "::error::No index.html in {output_dir}/ after the build."
            exit 1
          fi
          cd "{output_dir}" && zip -qr "$RUNNER_TEMP/site.zip" .

      - name: Upload to MiniVercel
        env:
          DEPLOY_TOKEN: ${{{{ secrets.{SECRET_NAME} }}}}
        run: |
          if [ -z "$DEPLOY_TOKEN" ]; then
            echo "::error::{SECRET_NAME} is not set. Re-enable builds in MiniVercel."
            exit 1
          fi
          curl -f -sS -X POST "{api_base_url}/api/deployments" \\
            -H "Authorization: Bearer $DEPLOY_TOKEN" \\
            -H "X-Commit-Sha: ${{{{ github.sha }}}}" \\
            -F "file=@$RUNNER_TEMP/site.zip"
"""


async def enable_builds(store: Store, settings: Settings, project: dict) -> dict:
    """Issue a deploy token, store it as a repo secret, commit the workflow.

    Order matters. The secret goes in before the workflow, so a workflow can
    never run without the token it needs. The database records the token hash
    before either, so a token that reaches GitHub is always one we recognise.
    """
    repo_full_name = project.get("repo_full_name")
    if not repo_full_name:
        raise GitOpsError(
            "This project is not linked to a GitHub repository. Import it from "
            "GitHub first."
        )

    owner, name = split_repo(repo_full_name)
    branch = project.get("repo_branch") or "main"
    build_command = project.get("build_command") or "npm run build"
    output_dir = project.get("output_dir") or "dist"
    validate_build_settings(build_command, output_dir)

    client = await client_for_user(store, settings, project["owner_id"])

    # Learn the granted scopes before writing anything. `repo` does NOT imply
    # `workflow`, so a user who reconnected to fix webhooks can still be unable
    # to commit the workflow file - and GitHub reports that as a 404 halfway
    # through, after the deploy token is already live in their repo.
    try:
        await client.get_repo(owner, name)
        for scopes, doing in (
            (SECRET_SCOPES, "store the deploy token as a repository secret"),
            (WORKFLOW_SCOPES, "commit the build workflow to .github/workflows/"),
        ):
            if not has_scope(client.granted_scopes, scopes):
                raise GitOpsError(missing_scope_message(scopes, doing))
    except Exception:
        await client.aclose()
        raise

    token = deploytoken.generate()
    await store.set_deploy_token(project["id"], deploytoken.fingerprint(token))

    try:
        await client.put_actions_secret(owner, name, SECRET_NAME, token)
        await client.put_file(
            owner,
            name,
            WORKFLOW_PATH,
            render_workflow(
                branch=branch,
                build_command=build_command,
                output_dir=output_dir,
                api_base_url=api_base_url(settings),
                slug=project["slug"],
            ),
            "Add MiniVercel deploy workflow",
            branch,
        )
    except Exception:
        # Do not leave a live token behind for a workflow that was never
        # committed.
        await store.set_deploy_token(project["id"], None)
        raise
    finally:
        await client.aclose()

    await store.update_project_settings(project["id"], {"builds_enabled": True})
    # The raw token is now only in GitHub's secret store. We hold sha256 and
    # nothing else, and it is never logged.
    log.info(
        "builds enabled for %s (%s), token %s",
        project["slug"],
        repo_full_name,
        deploytoken.redact(token),
    )
    return {"workflow_path": WORKFLOW_PATH, "secret_name": SECRET_NAME}


async def disable_builds(store: Store, settings: Settings, project: dict) -> None:
    """Revoke the token, remove the secret and the workflow.

    The token is revoked first and unconditionally: it is the part that grants
    access, and it must stop working even if GitHub is unreachable for the rest.
    """
    await store.set_deploy_token(project["id"], None)
    await store.update_project_settings(project["id"], {"builds_enabled": False})

    repo_full_name = project.get("repo_full_name")
    if not repo_full_name:
        return

    owner, name = split_repo(repo_full_name)
    branch = project.get("repo_branch") or "main"
    try:
        client = await client_for_user(store, settings, project["owner_id"])
    except GitOpsError as exc:
        log.warning(
            "builds disabled for %s but GitHub cleanup was skipped: %s",
            project["slug"],
            exc,
        )
        return

    try:
        await client.delete_actions_secret(owner, name, SECRET_NAME)
        await client.delete_file(
            owner, name, WORKFLOW_PATH, "Remove MiniVercel deploy workflow", branch
        )
    except GitHubError as exc:
        # The token is already dead, so the workflow can no longer deploy even
        # if it is still present. Report, do not fail the request.
        log.warning("could not fully clean up builds for %s: %s", project["slug"], exc)
    finally:
        await client.aclose()
