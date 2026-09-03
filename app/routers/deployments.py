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
one, create one, or reach any other endpoint - `_resolve_project` resolves it to
a single row and every field that would otherwise select a project is ignored.

Phase 5 adds the build-log routes, which are the other half of making a failed
build legible:

    POST /api/deployments/{id}/logs    runner or owner: attach the log tail
    GET  /api/deployments/{id}/logs    owner: read it back
    POST /api/deployments/build-failed runner only: record a build that died
                                       before it ever produced a zip

The last one exists because without it a failed `npm run build` produces no row
at all - the workflow never reaches the upload step - and the dashboard shows
the previous successful deploy as though nothing had happened.
"""

from __future__ import annotations

import json
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
from ..deployer import (
    QuotaExceeded,
    cleanup,
    fail,
    mark_failed,
    publish,
    quota_message,
)
from ..deps import get_store, upload_limiter
from ..store import Conflict, Store, is_valid_slug, slugify
from ..supabase import SupabaseError
from ..urls import site_url
from ..upload_stream import MalformedUpload, UploadTooLarge, receive_upload
from ..zipvalidate import ZipRejected

log = logging.getLogger("minivercel.deployments")

router = APIRouter(prefix="/api", tags=["deployments"])

#: Ceiling on a POSTed build log *before* truncation. The workflow already
#: sends only `tail -n 200`, so anything larger is a mistake or an attempt to
#: use this endpoint as free storage; read this much and no more.
MAX_LOG_UPLOAD_BYTES = 512 * 1024

BUILD_FAILED_ERROR = (
    "The build failed on GitHub Actions before any files were produced. Open "
    "the build log below for the error, or the run in the repository's Actions "
    "tab for the full output."
)


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


async def _read_log_body(request: Request) -> str:
    """The log text, from a text/plain body or a JSON `{"log": "..."}`.

    Read with a cap rather than `await request.body()`: this endpoint is
    reachable with a deploy token from a machine we do not control, and a 512 MB
    dyno must not hold whatever it decides to send.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_LOG_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "Build log exceeds %d KB. Send only the tail - the workflow "
                "MiniVercel commits uses `tail -n 200`."
                % (MAX_LOG_UPLOAD_BYTES // 1024),
            )
        chunks.append(chunk)

    raw = b"".join(chunks)
    if not raw.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Build log body is empty.")

    text = raw.decode("utf-8", "replace")
    if (request.headers.get("content-type") or "").startswith("application/json"):
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Body is not valid JSON. Send the log as text/plain, or as "
                'JSON of the form {"log": "..."}.',
            ) from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("log"), str):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                'JSON body must be an object with a string "log" field.',
            )
        text = parsed["log"]

    return text


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
        "url": site_url(settings, project["slug"]),
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
            # Same wording as the deep check in deployer.enforce_quota: which of
            # the two refuses an upload is an implementation detail, and the
            # user needs the same three facts either way.
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                quota_message(used, upload.size, settings.max_user_bytes),
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


async def _deployment_for_principal(
    store: Store, principal: Principal, deployment_id: str
) -> tuple[dict, dict]:
    """(deployment, project), or 404. Both principal kinds, one check.

    A deploy token may only touch deployments of its own project; a user may
    only touch deployments of a project they own. Anything else is answered 404
    rather than 403, so neither can enumerate deployment ids that exist.
    """
    deployment = await store.get_deployment(deployment_id)
    if deployment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown deployment.")

    if principal.token_project is not None:
        project = principal.token_project
        if deployment.get("project_id") != project["id"]:
            log.warning(
                "deploy token for %s tried to reach deployment %s",
                project["slug"],
                deployment_id,
            )
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown deployment.")
        return deployment, project

    assert principal.user is not None
    project = await store.get_owned_project_by_id(
        principal.user.id, deployment["project_id"]
    )
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown deployment.")
    return deployment, project


@router.post("/deployments/{deployment_id}/logs", status_code=status.HTTP_202_ACCEPTED)
async def post_deployment_log(
    deployment_id: str,
    request: Request,
    principal: Principal = Depends(require_upload_principal),
):
    """Attach the tail of a build log to a deployment (SPEC.md Phase 5).

    Posted by the workflow with the same deploy token it uses to upload the
    zip - no new credential, no new scope. The body is text, and it is never
    interpreted: stored as-is, truncated to the last 200 lines, and rendered as
    text in the dashboard. NON-NEGOTIABLE #1 is untouched; this endpoint reads
    bytes and writes a column.
    """
    store = get_store()
    deployment, project = await _deployment_for_principal(
        store, principal, deployment_id
    )
    text = await _read_log_body(request)

    if not await store.set_build_log(deployment_id, text):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Build logs are not available on this server: db/006_phase5.sql has "
            "not been applied.",
        )

    log.info(
        "stored build log for deployment %s (%s), %d bytes received",
        deployment_id,
        project["slug"],
        len(text.encode("utf-8", "replace")),
    )
    return {"stored": True, "deployment_id": deployment_id}


@router.get("/deployments/{deployment_id}/logs")
async def get_deployment_log(
    deployment_id: str,
    user: User = Depends(require_user),
):
    """Read a stored build log back. Owner only - a deploy token cannot read.

    Fetched lazily by the dashboard when someone opens the collapsed panel,
    which is why it is a route of its own rather than a field on the deployment
    list: fifty deployments would otherwise mean fifty logs on the wire to draw
    fifty closed disclosure triangles.
    """
    store = get_store()
    deployment = await store.get_deployment(deployment_id)
    if deployment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown deployment.")
    project = await store.get_owned_project_by_id(user.id, deployment["project_id"])
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown deployment.")

    row = await store.get_build_log(deployment_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No build log for this deployment. Logs are posted by the GitHub "
            "Actions workflow, so uploads made by hand do not have one.",
        )

    text = row["build_log"] or ""
    return {
        "deployment_id": deployment_id,
        "log": text,
        "line_count": text.count("\n") + 1 if text else 0,
        "received_at": row.get("build_log_at"),
    }


@router.post("/deployments/build-failed", status_code=status.HTTP_201_CREATED)
async def report_build_failure(
    request: Request,
    principal: Principal = Depends(require_upload_principal),
    settings: Settings = Depends(get_settings),
):
    """Record a build that died before it produced anything to upload.

    Without this, a failed `npm run build` is invisible here: the workflow never
    reaches the upload step, so no deployment row is ever created, and the
    dashboard goes on showing the last successful deploy. The user's only clue
    that their push did nothing is a red tick in the Actions tab.

    Deploy token only. A user's JWT is refused because there is no legitimate
    reason for a browser to invent a failed deployment, and the row it creates
    is not one the user could otherwise have made.

    The row owns no storage objects and, being `failed`, counts nothing against
    the quota (see store.user_bytes_used).
    """
    if principal.token_project is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This endpoint is for the GitHub Actions workflow and accepts only a "
            "project deploy token.",
        )

    limit = upload_limiter().check(principal.rate_limit_key)
    if not limit.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many build reports. Try again shortly.",
            headers={"Retry-After": str(limit.retry_after)},
        )

    project = principal.token_project
    text = await _read_log_body(request)
    commit_sha = (request.headers.get("x-commit-sha") or "").strip()

    store = get_store()
    deployment = await store.create_failed_deployment(
        project["id"], commit_sha=commit_sha or None, error=BUILD_FAILED_ERROR
    )
    # Best effort: the row is the point, the log is the detail. If db/006 has
    # not been applied the deployment is still recorded as failed.
    await store.set_build_log(deployment["id"], text)

    log.info(
        "recorded failed build for %s at %s -> deployment %s",
        project["slug"],
        commit_sha[:7] or "?",
        deployment["id"],
    )
    return _deployment_response(deployment, project, settings)
