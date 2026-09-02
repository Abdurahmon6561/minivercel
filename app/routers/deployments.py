"""POST /api/deployments - the upload endpoint.

SPEC.md "Upload flow", step for step:

  1. authenticate, reject anonymous      -> require_upload_principal
  2. stream to /tmp, abort at 50 MB      -> upload_stream.receive_upload
  3. create the deployments row pending  -> store.create_deployment
  4-6. validate, extract, upload, ready  -> deployer.publish
  7. delete /tmp in `finally`, always    -> deployer.cleanup

Two kinds of caller are accepted, and this is the only route where that is true:

  * a user's Supabase JWT (Phase 1, unchanged)
  * a per-project deploy token, presented by a GitHub Actions runner (Phase 4)

A deploy token is scoped to exactly one project. It cannot choose a different
one, create one, or reach any other endpoint - `_principal_project` resolves it
to a single row and every field that would otherwise select a project is
ignored.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from .. import deploytoken
from ..auth import User, bearer_token, require_user, verify_token
from ..cache import project_cache
from ..config import Settings, get_settings
from ..deployer import QuotaExceeded, cleanup, fail, mark_failed, publish
from ..deps import get_store, upload_limiter
from ..store import Conflict, Store, is_valid_slug, slugify
from ..supabase import SupabaseError
from ..upload_stream import MalformedUpload, UploadTooLarge, receive_upload
from ..zipvalidate import ZipRejected

log = logging.getLogger("minivercel.deployments")

router = APIRouter(prefix="/api", tags=["deployments"])


@dataclass
class Principal:
    """Who is uploading. Exactly one of these two is set."""

    user: User | None = None
    token_project: dict | None = None

    @property
    def owner_id(self) -> str:
        if self.user:
            return self.user.id
        assert self.token_project is not None
        return self.token_project["owner_id"]

    @property
    def rate_limit_key(self) -> str:
        if self.user:
            return "user:" + self.user.id
        assert self.token_project is not None
        return "project:" + self.token_project["id"]


async def require_upload_principal(
    request: Request, settings: Settings = Depends(get_settings)
) -> Principal:
    token = bearer_token(request)
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "A valid Supabase access token or deploy token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if deploytoken.looks_like_deploy_token(token):
        project = await get_store().project_for_deploy_token(
            deploytoken.fingerprint(token)
        )
        if project is None:
            # Never echo the token, not even to say it was wrong.
            log.warning("rejected unknown deploy token %s", deploytoken.redact(token))
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "This deploy token is not valid. Re-enable builds to issue a new one.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return Principal(token_project=project)

    return Principal(user=await verify_token(token, settings))


def _public_site_url(settings: Settings, slug: str) -> str:
    return "%s/s/%s/" % (settings.public_base_url, slug)


def _deployment_response(deployment: dict, project: dict, settings: Settings) -> dict:
    return {
        "id": deployment["id"],
        "status": deployment["status"],
        "size_bytes": deployment.get("size_bytes", 0),
        "file_count": deployment.get("file_count", 0),
        "error": deployment.get("error"),
        "commit_sha": deployment.get("commit_sha"),
        "created_at": deployment.get("created_at"),
        "project": {
            "id": project["id"],
            "name": project["name"],
            "slug": project["slug"],
        },
        "url": _public_site_url(settings, project["slug"]),
    }


async def _resolve_project(
    store: Store, principal: Principal, fields: dict[str, str]
) -> dict:
    """Find or create the project this upload belongs to.

    A deploy token skips all of this: it *is* a project, and the form fields
    that would name a different one are ignored rather than honoured.
    """
    if principal.token_project is not None:
        return principal.token_project

    user = principal.user
    assert user is not None

    project_id = (fields.get("project_id") or "").strip()
    if project_id:
        project = await store.get_owned_project_by_id(user.id, project_id)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")
        return project

    slug = (fields.get("slug") or fields.get("project") or "").strip().lower()
    name = (fields.get("name") or "").strip()

    if slug:
        if not is_valid_slug(slug):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Slug must be 3-63 characters of lowercase letters, digits and hyphens.",
            )
        project = await store.get_owned_project(user.id, slug)
        if project is not None:
            return project
        try:
            return await store.create_project(user.id, name or slug, slug=slug)
        except Conflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    if not name:
        name = "site-" + uuid.uuid4().hex[:8]
    try:
        return await store.create_project(user.id, name, slug=slugify(name))
    except Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/deployments", status_code=status.HTTP_201_CREATED)
async def create_deployment(
    request: Request,
    principal: Principal = Depends(require_upload_principal),
    settings: Settings = Depends(get_settings),
):
    limit = upload_limiter().check(principal.rate_limit_key)
    if not limit.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many deployments. Try again shortly.",
            headers={"Retry-After": str(limit.retry_after)},
        )

    store = get_store()
    tmp_dir = tempfile.gettempdir()
    zip_path = os.path.join(tmp_dir, "mv-%s.zip" % uuid.uuid4().hex)
    extract_root = ""
    deployment: dict | None = None

    try:
        try:
            upload = await receive_upload(
                request, zip_path, max_bytes=settings.max_deployment_bytes
            )
        except UploadTooLarge as exc:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "Deployment exceeds the %d MB limit."
                % (settings.max_deployment_bytes // (1024 * 1024)),
            ) from exc
        except MalformedUpload as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

        # Cheap pre-check on the transfer size; the real one runs in publish()
        # against the uncompressed total.
        used = await store.user_bytes_used(principal.owner_id)
        if used + upload.size > settings.max_user_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "Storage quota exceeded: %d of %d MB used. Delete a project first."
                % (used // (1024 * 1024), settings.max_user_bytes // (1024 * 1024)),
            )

        project = await _resolve_project(store, principal, upload.fields)

        commit_sha = (
            request.headers.get("x-commit-sha") or upload.fields.get("commit_sha") or ""
        ).strip()
        deployment = await store.create_deployment(project["id"], commit_sha or None)
        deployment_id = deployment["id"]
        extract_root = os.path.join(tmp_dir, "mv-%s" % deployment_id)

        result = await publish(
            store,
            settings,
            project=project,
            deployment_id=deployment_id,
            zip_path=zip_path,
            extract_root=extract_root,
            owner_id=principal.owner_id,
            # A hand-made zip is expected to *be* the site. Only a repository
            # gets the dist/ build/ public/ _site/ search.
            allow_build_output_dirs=False,
        )
        project_cache.invalidate(project["slug"])

        deployment.update(
            {
                "status": "ready",
                "size_bytes": result.size_bytes,
                "file_count": result.file_count,
            }
        )
        return _deployment_response(deployment, project, settings)

    except ZipRejected as exc:
        if deployment:
            await mark_failed(store, deployment["id"], str(exc))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except QuotaExceeded as exc:
        if deployment:
            await mark_failed(store, deployment["id"], str(exc))
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
    except HTTPException as exc:
        if deployment:
            await fail(store, deployment["id"], False)
            await mark_failed(store, deployment["id"], str(exc.detail))
        raise
    except (SupabaseError, httpx.HTTPError) as exc:
        log.error("supabase unavailable during deploy: %s", exc)
        if deployment:
            await mark_failed(store, deployment["id"], "Upstream storage was unavailable.")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Upstream storage is temporarily unavailable.",
            headers={"Retry-After": "30"},
        ) from exc
    except Exception as exc:
        log.exception("deployment failed")
        if deployment:
            await mark_failed(store, deployment["id"], "Internal error while deploying.")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal error while deploying."
        ) from exc
    finally:
        cleanup(zip_path, extract_root)


@router.get("/deployments/{deployment_id}")
async def get_deployment(
    deployment_id: str,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    store = get_store()
    deployment = await store.get_deployment(deployment_id)
    if deployment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown deployment.")
    project = await store.get_owned_project_by_id(user.id, deployment["project_id"])
    if project is None:
        # Exists, but not this user's: same answer as "does not exist".
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown deployment.")
    deployment.pop("file_paths", None)
    return _deployment_response(deployment, project, settings)
