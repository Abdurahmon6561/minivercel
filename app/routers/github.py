"""GitHub import and build enablement (SPEC.md Phases 3 and 4).

    GET    /api/me/github/repos          repos the user can push to
    POST   /api/projects/import          import a repo, hook it up, deploy once
    POST   /api/projects/{slug}/builds   enable Actions-based builds
    DELETE /api/projects/{slug}/builds   revoke the token, remove the workflow
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import User, require_user
from ..config import Settings, get_settings
from ..crypto import EncryptionUnavailable, encrypt
from ..deps import get_store
from ..gitops import (
    GitOpsError,
    client_for_user,
    deploy_from_repo,
    disable_builds,
    enable_builds,
    new_webhook_secret,
)
from ..github import (
    HOOK_SCOPES,
    PRIVATE_REPO_SCOPES,
    GitHubError,
    has_scope,
    missing_scope_message,
    split_repo,
)
from ..store import Conflict, slugify
from ..urls import site_url, webhook_url

log = logging.getLogger("minivercel.github")

router = APIRouter(tags=["github"])


class ImportRequest(BaseModel):
    repo: str = Field(min_length=3, max_length=140)
    branch: str | None = Field(default=None, max_length=100)


def _as_http(exc: Exception) -> HTTPException:
    if isinstance(exc, GitOpsError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if isinstance(exc, GitHubError):
        code = (
            status.HTTP_404_NOT_FOUND
            if exc.status_code == 404
            else status.HTTP_401_UNAUTHORIZED
            if exc.status_code == 401
            else status.HTTP_502_BAD_GATEWAY
        )
        return HTTPException(code, str(exc))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Unexpected error.")


@router.get("/api/me/github/repos")
async def list_repos(
    user: User = Depends(require_user), settings: Settings = Depends(get_settings)
):
    """For the dashboard's repo picker. Push access only - anything else cannot
    receive a webhook or a workflow file."""
    try:
        client = await client_for_user(get_store(), settings, user.id)
    except GitOpsError as exc:
        raise _as_http(exc) from exc
    try:
        return await client.list_repos()
    except GitHubError as exc:
        raise _as_http(exc) from exc
    finally:
        await client.aclose()


@router.post("/api/projects/import", status_code=status.HTTP_201_CREATED)
async def import_repo(
    payload: ImportRequest,
    background: BackgroundTasks,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    """Import a repository: verify it, create the project, register the push
    webhook, and start a first deployment immediately.

    The first deploy runs in the background so this returns a live URL right
    away rather than holding the request open for a zipball download. The
    project exists and is watchable in the dashboard the moment this returns.
    """
    store = get_store()
    try:
        owner, name = split_repo(payload.repo)
        # Inside the try: "GitHub is not connected" is a 400 the user can act
        # on, not a 500.
        client = await client_for_user(store, settings, user.id)
    except (GitOpsError, GitHubError) as exc:
        raise _as_http(exc) from exc

    try:
        repo = await client.get_repo(owner, name)
        branch = payload.branch or repo.default_branch

        if not repo.can_admin:
            raise GitOpsError(
                "You need admin access on %s to add the push webhook that makes "
                "auto-deploy work." % repo.full_name
            )

        # Check the scope before creating the project. GitHub answers a
        # hook call made without a hook scope with 404, which reads as "the
        # repository does not exist" - so without this check the user is told
        # their repository is missing when their sign-in is simply too narrow.
        # `public_repo` is the default and does NOT cover hooks.
        if not has_scope(client.granted_scopes, HOOK_SCOPES):
            raise GitOpsError(
                missing_scope_message(HOOK_SCOPES, "register the push webhook")
            )
        if repo.private and not has_scope(client.granted_scopes, PRIVATE_REPO_SCOPES):
            raise GitOpsError(
                missing_scope_message(PRIVATE_REPO_SCOPES, "deploy a private repository")
            )

        try:
            project = await store.create_project(
                user.id, name, slug=slugify(name)
            )
        except Conflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

        # Register the webhook before recording it, so a failure leaves no row
        # claiming a hook that does not exist.
        secret = new_webhook_secret()
        try:
            hook_id = await client.create_push_webhook(
                owner, name, webhook_url(settings), secret
            )
        except GitHubError:
            await store.delete_project(user.id, project["id"])
            raise

        try:
            encrypted_secret = encrypt(secret, settings)
        except EncryptionUnavailable as exc:
            await client.delete_webhook(owner, name, hook_id)
            await store.delete_project(user.id, project["id"])
            raise GitOpsError(
                "GitHub integration is not configured on this server "
                "(GITHUB_TOKEN_KEY is missing)."
            ) from exc

        await store.set_project_repo(
            project["id"],
            repo_full_name=repo.full_name,
            repo_branch=branch,
            webhook_id=hook_id,
            webhook_secret=encrypted_secret,
        )
    except (GitOpsError, GitHubError) as exc:
        raise _as_http(exc) from exc
    finally:
        await client.aclose()

    fresh = await store.get_owned_project_by_id(user.id, project["id"])
    assert fresh is not None

    # A live URL without pushing anything (Phase 3).
    background.add_task(_first_deploy, settings, fresh)

    log.info("imported %s as %s for %s", repo.full_name, project["slug"], user.id)
    return {
        "id": fresh["id"],
        "name": fresh["name"],
        "slug": fresh["slug"],
        "url": site_url(settings, fresh["slug"]),
        "repo_full_name": repo.full_name,
        "repo_branch": branch,
        "auto_deploy_enabled": True,
        "builds_enabled": False,
        "deploying": True,
    }


async def _first_deploy(settings: Settings, project: dict) -> None:
    store = get_store()
    deployment_id = await deploy_from_repo(store, settings, project=project)
    deployment = await store.get_deployment(deployment_id) if deployment_id else None
    ready = bool(deployment and deployment.get("status") == "ready")
    await store.record_webhook_delivery(
        project["id"],
        status="deployed" if ready else "failed",
        detail=(
            "first deploy on import"
            if ready
            else (deployment or {}).get("error") or "first deploy failed"
        ),
    )


@router.post("/api/projects/{slug}/builds", status_code=status.HTTP_200_OK)
async def enable_project_builds(
    slug: str,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    store = get_store()
    project = await store.get_owned_project(user.id, slug)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")

    try:
        result = await enable_builds(store, settings, project)
    except (GitOpsError, GitHubError) as exc:
        raise _as_http(exc) from exc

    # Note what is NOT here: the deploy token. It went straight into the repo's
    # Actions secrets and we kept only sha256 of it.
    return {
        "builds_enabled": True,
        "workflow_path": result["workflow_path"],
        "secret_name": result["secret_name"],
        "build_command": project.get("build_command") or "npm run build",
        "output_dir": project.get("output_dir") or "dist",
    }


@router.delete("/api/projects/{slug}/builds", status_code=status.HTTP_200_OK)
async def disable_project_builds(
    slug: str,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    store = get_store()
    project = await store.get_owned_project(user.id, slug)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")

    try:
        await disable_builds(store, settings, project)
    except (GitOpsError, GitHubError) as exc:
        raise _as_http(exc) from exc
    return {"builds_enabled": False}
