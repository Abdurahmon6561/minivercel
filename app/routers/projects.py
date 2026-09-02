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
from ..store import Conflict, is_valid_slug, slugify

log = logging.getLogger("minivercel.projects")

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProject(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=63)


def _project_response(project: dict, settings: Settings) -> dict:
    return {
        "id": project["id"],
        "name": project["name"],
        "slug": project["slug"],
        "live_deployment_id": project.get("live_deployment_id"),
        "created_at": project.get("created_at"),
        "url": "%s/s/%s/" % (settings.public_base_url, project["slug"]),
    }


@router.get("")
async def list_projects(
    user: User = Depends(require_user), settings: Settings = Depends(get_settings)
):
    projects = await get_store().list_projects(user.id)
    return [_project_response(project, settings) for project in projects]


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


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(slug: str, user: User = Depends(require_user)):
    store = get_store()
    project = await store.get_owned_project(user.id, slug)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")

    deployments = await store.list_deployments(project["id"], limit=500)
    for deployment in deployments:
        try:
            await store.db.remove_prefix(deployment["id"])
        except Exception:  # pragma: no cover - keep deleting the rest
            log.exception("could not remove objects for deployment %s", deployment["id"])

    await store.delete_project(user.id, project["id"])
    project_cache.invalidate(slug)
    return None
