"""Project CRUD. Enough to drive curl in Phase 1 and the Phase 2 dashboard.

Every handler is scoped by `user.id`. There is no endpoint here that takes an id
and trusts it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import gc
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
from ..projectops import delete_project_fully
from ..store import Conflict, is_valid_slug, slugify
from ..urls import preview_url, site_url

from ._errors import as_http

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


def _deployment_response(deployment: dict, project: dict, settings: Settings) -> dict:
    """One deployment row as the dashboard needs it.

    Built field by field rather than passed through, for two reasons: the
    manifest column (`file_paths`, up to 500 entries) and the build log must
    never ride along in a list response, and the row carries two things the
    dashboard cannot work out for itself - whether this is the live deployment,
    and where to preview it.
    """
    return {
        "id": deployment["id"],
        "status": deployment["status"],
        "size_bytes": deployment.get("size_bytes", 0),
        "file_count": deployment.get("file_count", 0),
        "error": deployment.get("error"),
        "commit_sha": deployment.get("commit_sha"),
        "created_at": deployment.get("created_at"),
        "is_live": deployment["id"] == project.get("live_deployment_id"),
        # Only a `ready` deployment has a complete set of objects to serve.
        "preview_url": (
            preview_url(settings, project["slug"], deployment["id"])
            if deployment.get("status") == "ready"
            else None
        ),
        # Whether a log exists, not the log itself: the panel is collapsed by
        # default and fetches the text only when it is opened.
        "has_build_log": bool(deployment.get("build_log_at")),
    }


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
    # AUTODEPLOY.md section 6: a worker killed mid-deploy leaves a `pending` row
    # that never resolves, and this list is where the user sees it spinning.
    # Throttled to once a minute per process - the rows it looks for are at
    # least ten minutes old.
    await gc.maybe_reap(store)

    projects = await store.list_projects(user.id)
    latest = await store.latest_deployment_per_project(
        [project["id"] for project in projects]
    )

    body = []
    for project in projects:
        row = _project_response(project, settings)
        deployment = latest.get(project["id"])
        row["last_deployment"] = (
            _deployment_response(deployment, project, settings) if deployment else None
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
    # The dashboard polls this route every two seconds while a deploy is
    # pending, which is exactly when a dead row would be on screen.
    await gc.maybe_reap(store)

    project = await store.get_owned_project(user.id, slug)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")
    deployments = await store.list_deployments(project["id"])
    body = _project_response(project, settings)
    body["deployments"] = [
        _deployment_response(deployment, project, settings) for deployment in deployments
    ]
    return body


@router.post("/{slug}/deployments/{deployment_id}/promote")
async def promote_deployment(
    slug: str,
    deployment_id: str,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    """Roll back (or forward) by moving `live_deployment_id`. Nothing else.

    This is a pointer change and it must stay one: no object is copied, moved or
    deleted, so promoting is instant and costs nothing against the 1 GB Storage
    quota. Every deployment's files already sit under its own key prefix, which
    is exactly what makes this possible - see SPEC.md Phase 5.

    Two refusals, both of which are about not breaking a working site:

      * a deployment that is not `ready` has partial objects or none, so
        promoting it would replace a working site with a broken one;
      * a deployment belonging to another project is answered 404, not 403 -
        the same answer as a deployment that does not exist, so this route
        cannot be used to discover which ids are real.
    """
    store = get_store()
    project = await store.get_owned_project(user.id, slug)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")

    deployment = await store.get_deployment(deployment_id)
    if deployment is None or deployment.get("project_id") != project["id"]:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That deployment does not belong to this project."
        )

    if deployment.get("status") != "ready":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only a deployment that finished successfully can be promoted. This "
            "one is %s%s."
            % (
                deployment.get("status") or "in an unknown state",
                " - " + deployment["error"] if deployment.get("error") else "",
            ),
        )

    if project.get("live_deployment_id") == deployment_id:
        # Not an error: the dashboard may be a few seconds stale, and doing
        # nothing is the correct outcome either way.
        return {
            "live_deployment_id": deployment_id,
            "url": site_url(settings, project["slug"]),
            "changed": False,
        }

    previous = project.get("live_deployment_id")
    await store.set_live_deployment(project["id"], deployment_id)
    # The serving path caches slug -> project for 15 seconds; drop it so the
    # promotion is visible on the very next request rather than eventually.
    project_cache.invalidate(project["slug"])

    log.info(
        "promoted %s to live on %s (was %s)", deployment_id, project["slug"], previous
    )
    return {
        "live_deployment_id": deployment_id,
        "previous_deployment_id": previous,
        "url": site_url(settings, project["slug"]),
        "changed": True,
    }


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
        except (GitOpsError, GitHubError) as exc:
            # Not a blanket 502. A token without the `workflow` scope is the
            # single most common failure here, and GitHub reports it as a 404;
            # `as_http` turns that into a 403 that names the missing scope,
            # because "Bad Gateway" tells the user nothing they can act on.
            raise as_http(exc) from exc
    elif payload.builds_enabled and patch.get("build_command") is not None:
        # Builds were already on and the command changed: the committed
        # workflow is now stale, so rewrite it.
        try:
            await enable_builds(store, settings, {**project, **patch})
        except (GitOpsError, GitHubError) as exc:
            raise as_http(exc) from exc

    fresh = await store.get_owned_project(user.id, slug)
    assert fresh is not None
    return _project_response(fresh, settings)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    slug: str,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    """Remove the GitHub wiring, the storage objects, and the row.

    The ordering and its reasoning live in app/projectops.py, which deleting an
    account also uses - one project deleted from here and one deleted as part
    of a whole account must clean up identically.
    """
    store = get_store()
    project = await store.get_owned_project(user.id, slug)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")

    await delete_project_fully(store, settings, user.id, project)
    return None
