"""Project CRUD. Enough to drive curl in Phase 1 and the Phase 2 dashboard.

Every handler is scoped by `user.id`. There is no endpoint here that takes an id
and trusts it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import User, require_user
from ..cache import project_cache
from ..config import Settings, get_settings
from ..deps import get_store
from ..gitops import (
    GitOpsError,
    client_for_user,
    disable_builds,
    enable_builds,
    validate_build_settings,
)
from ..github import GitHubError, split_repo
from ..store import Conflict, is_valid_slug, slugify
from ..urls import site_url

log = logging.getLogger("minivercel.projects")

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProject(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=63)


class PatchProject(BaseModel):
    """The two independent switches, plus the build settings they control.

    Every field is optional: the dashboard sends only what the user touched, so
    toggling auto-deploy cannot accidentally rewrite a build command.
    """

    auto_deploy_enabled: bool | None = None
    builds_enabled: bool | None = None
    build_command: str | None = Field(default=None, max_length=200)
    output_dir: str | None = Field(default=None, max_length=100)


def _project_response(project: dict, settings: Settings) -> dict:
    return {
        "id": project["id"],
        "name": project["name"],
        "slug": project["slug"],
        "live_deployment_id": project.get("live_deployment_id"),
        "created_at": project.get("created_at"),
        "url": site_url(settings, project["slug"]),
        # Phase 3/4 state. Note what is absent: `webhook_secret` and
        # `deploy_token_sha256` are secrets and never leave the server.
        "repo_full_name": project.get("repo_full_name"),
        "repo_branch": project.get("repo_branch"),
        "auto_deploy_enabled": bool(project.get("auto_deploy_enabled", True)),
        "builds_enabled": bool(project.get("builds_enabled", False)),
        "build_command": project.get("build_command") or "npm run build",
        "output_dir": project.get("output_dir") or "dist",
        "webhook_registered": project.get("webhook_id") is not None,
        "last_webhook": {
            "at": project.get("last_webhook_at"),
            "status": project.get("last_webhook_status"),
            "detail": project.get("last_webhook_detail"),
            "sha": project.get("last_webhook_sha"),
        }
        if project.get("last_webhook_at")
        else None,
    }


@router.get("")
async def list_projects(
    user: User = Depends(require_user), settings: Settings = Depends(get_settings)
):
    """The dashboard's project list: live URL, last deploy time, status.

    The status and timestamp come from one batched query rather than one per
    project - see store.latest_deployment_per_project.
    """
    store = get_store()
    projects = await store.list_projects(user.id)
    latest = await store.latest_deployment_per_project(
        [project["id"] for project in projects]
    )

    body = []
    for project in projects:
        row = _project_response(project, settings)
        deployment = latest.get(project["id"])
        row["last_deployment"] = (
            {
                "id": deployment["id"],
                "status": deployment["status"],
                "created_at": deployment["created_at"],
                "size_bytes": deployment.get("size_bytes", 0),
                "file_count": deployment.get("file_count", 0),
                "error": deployment.get("error"),
                "is_live": deployment["id"] == project.get("live_deployment_id"),
            }
            if deployment
            else None
        )
        body.append(row)
    return body


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: CreateProject,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    slug = (payload.slug or slugify(payload.name)).lower()
    if payload.slug is not None and not is_valid_slug(slug):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Slug must be 3-63 characters of lowercase letters, digits and hyphens.",
        )
    try:
        project = await get_store().create_project(
            user.id, payload.name, slug=slug if payload.slug is not None else None
        )
    except Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _project_response(project, settings)


@router.get("/{slug}")
async def get_project(
    slug: str,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    store = get_store()
    project = await store.get_owned_project(user.id, slug)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")
    deployments = await store.list_deployments(project["id"])
    body = _project_response(project, settings)
    body["deployments"] = deployments
    return body


@router.patch("/{slug}")
async def patch_project(
    slug: str,
    payload: PatchProject,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    """The two switches, independently.

    `auto_deploy_enabled` is a database flag and nothing more: the webhook stays
    registered either way, because re-registering one later needs the OAuth
    token and can fail silently, leaving a project that looks connected and
    never deploys.

    `builds_enabled` is not a flag - it owns a deploy token, a repository secret
    and a committed workflow file - so it is delegated to the same code the
    dedicated endpoints use rather than written directly.
    """
    store = get_store()
    project = await store.get_owned_project(user.id, slug)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")

    try:
        validate_build_settings(payload.build_command, payload.output_dir)
    except GitOpsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    patch: dict = {}
    if payload.auto_deploy_enabled is not None:
        patch["auto_deploy_enabled"] = payload.auto_deploy_enabled
    if payload.build_command is not None:
        patch["build_command"] = payload.build_command
    if payload.output_dir is not None:
        patch["output_dir"] = payload.output_dir
    if patch:
        await store.update_project_settings(project["id"], patch)
        project = {**project, **patch}

    if payload.builds_enabled is not None and payload.builds_enabled != bool(
        project.get("builds_enabled")
    ):
        try:
            if payload.builds_enabled:
                await enable_builds(store, settings, project)
            else:
                await disable_builds(store, settings, project)
        except GitOpsError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        except GitHubError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    elif payload.builds_enabled and patch.get("build_command") is not None:
        # Builds were already on and the command changed: the committed
        # workflow is now stale, so rewrite it.
        try:
            await enable_builds(store, settings, {**project, **patch})
        except (GitOpsError, GitHubError) as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    fresh = await store.get_owned_project(user.id, slug)
    assert fresh is not None
    return _project_response(fresh, settings)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    slug: str,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    """Delete the webhook, then every storage object, then the row.

    That order is deliberate. Storage is NOT covered by `ON DELETE CASCADE` -
    the database knows nothing about the bucket - so dropping the row first
    would orphan every object with no remaining record of which keys to remove,
    against a 1 GB quota. And a webhook left registered on a deleted project
    delivers pushes to a 401 for ever.
    """
    store = get_store()
    project = await store.get_owned_project(user.id, slug)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")

    # 1. The webhook, and any build wiring in the user's repository.
    if project.get("repo_full_name"):
        try:
            client = await client_for_user(store, settings, user.id)
            owner, name = split_repo(project["repo_full_name"])
            try:
                if project.get("webhook_id"):
                    await client.delete_webhook(owner, name, int(project["webhook_id"]))
                if project.get("builds_enabled"):
                    # Otherwise a workflow keeps firing at a project that is gone.
                    await disable_builds(store, settings, project)
            finally:
                await client.aclose()
        except (GitOpsError, GitHubError) as exc:
            # Not fatal: the user asked us to delete their project, and a
            # revoked GitHub token must not make that impossible.
            log.warning("could not clean up GitHub for %s: %s", slug, exc)

    # 2. Every storage object for every deployment.
    deployments = await store.list_deployments(project["id"], limit=500)
    for deployment in deployments:
        try:
            await store.db.remove_prefix(deployment["id"])
        except Exception:  # pragma: no cover - keep deleting the rest
            log.exception("could not remove objects for deployment %s", deployment["id"])

    # 3. The row.
    await store.delete_project(user.id, project["id"])
    project_cache.invalidate(slug)
    return None
