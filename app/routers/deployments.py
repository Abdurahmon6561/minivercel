"""POST /api/deployments - the upload pipeline.

Follows SPEC.md "Upload flow" step for step:

  1. authenticate, reject anonymous                  -> require_user
  2. stream to /tmp/{uuid}.zip, reject at 50 MB      -> upload_stream.receive_upload
  3. create the deployments row as `pending`         -> store.create_deployment
  4. validate every zip entry BEFORE extracting      -> zipvalidate.inspect
  5. extract, upload with whitelisted content-types  -> zipvalidate.extract + storage
  6. ready / failed, set live_deployment_id          -> _finish / _fail
  7. delete /tmp in `finally`, always                -> _cleanup in the finally block

NON-NEGOTIABLE #1: nothing here executes anything from the archive. The only
operations performed on user bytes are "read them" and "PUT them at a key".
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth import User, require_user
from ..cache import project_cache
from ..config import Settings, get_settings
from ..deps import get_store, upload_limiter
from ..mimemap import content_type_for
from ..store import Conflict, Store, is_valid_slug, slugify
from ..supabase import SupabaseError
from ..upload_stream import MalformedUpload, UploadTooLarge, receive_upload
from ..zipvalidate import ZipRejected, extract, inspect, strip_redundant_root

log = logging.getLogger("minivercel.deployments")

router = APIRouter(prefix="/api", tags=["deployments"])

# How many objects we push to Storage at once. Storage has no batch upload, so
# this is the only lever on wall-clock deploy time. Eight is comfortable inside
# a free dyno's connection budget.
UPLOAD_CONCURRENCY = 8


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
    store: Store, user: User, fields: dict[str, str]
) -> dict:
    """Find or create the project this upload belongs to.

    Accepts `project_id`, `slug`, or `name` as a multipart field. With none of
    them we mint one with a generated name, so a bare curl still works.
    """
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


async def _upload_files(
    store: Store, deployment_id: str, root: str, entries
) -> tuple[int, list[str]]:
    """Push every extracted file to Storage under `{deployment_id}/{path}`."""
    semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY)
    total = 0
    paths: list[str] = []
    lock = asyncio.Lock()

    async def push(relpath: str) -> None:
        nonlocal total
        local_path = os.path.join(root, *relpath.split("/"))
        with open(local_path, "rb") as handle:
            payload = handle.read()
        # Content-type comes from our whitelist keyed on the extension - never
        # from the archive (SPEC.md step 5).
        await store.db.upload(
            "%s/%s" % (deployment_id, relpath), payload, content_type_for(relpath)
        )
        async with lock:
            total += len(payload)
            paths.append(relpath)

    async def guarded(relpath: str) -> None:
        async with semaphore:
            await push(relpath)

    await asyncio.gather(*(guarded(entry.path) for entry in entries))
    return total, paths


async def _verify_served_content_type(store: Store, deployment_id: str) -> None:
    """Read back index.html and check Storage kept the type we sent.

    One HEAD per deploy. It exists because the failure it catches is invisible
    from this side: the upload returns 200 and the logs look perfect while the
    browser renders the page as plain text. Never fatal - a deployment whose
    bytes are all in place is a good deployment, and a read-back that fails
    tells us about the read-back, not the deploy.
    """
    expected = content_type_for("index.html")
    try:
        served = await store.db.stored_content_type("%s/index.html" % deployment_id)
    except Exception as exc:  # pragma: no cover - diagnostics must never break a deploy
        log.warning("content-type read-back failed for %s: %s", deployment_id, exc)
        return

    if served is None:
        log.warning(
            "content-type read-back: %s/index.html could not be fetched from Storage",
            deployment_id,
        )
    elif served.split(";")[0].strip().lower() != expected.split(";")[0].strip().lower():
        log.error(
            "CONTENT-TYPE MISMATCH on %s/index.html: sent %r, Storage serves %r. "
            "The bytes uploaded fine; Storage did not keep the type. Check the "
            "bucket's allowed_mime_types, and whether a CDN response is cached.",
            deployment_id,
            expected,
            served,
        )
    else:
        log.info(
            "content-type read-back ok: %s/index.html serves %s", deployment_id, served
        )


def _enforce_quota(used: int, incoming: int, settings: Settings) -> None:
    """NON-NEGOTIABLE #5: the free tier will not warn you before it breaks."""
    if used + incoming <= settings.max_user_bytes:
        return
    mb = 1024 * 1024
    raise HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        "Storage quota exceeded: %d MB used of %d MB, and this deployment needs "
        "%d MB. Delete a project first."
        % (used // mb, settings.max_user_bytes // mb, incoming // mb),
    )


def _cleanup(*paths: str) -> None:
    """NON-NEGOTIABLE #6. Never raises."""
    for path in paths:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                os.unlink(path)
        except OSError as exc:  # pragma: no cover - defensive
            log.warning("could not clean up %s: %s", path, exc)


@router.post("/deployments", status_code=status.HTTP_201_CREATED)
async def create_deployment(
    request: Request,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    limit = upload_limiter().check("user:" + user.id)
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
    project: dict | None = None
    uploaded_any = False

    try:
        # --- 2. stream to disk, rejecting oversize while streaming ---------
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

        # --- quota, first pass (NON-NEGOTIABLE #5) -------------------------
        # The zip is compressed, so its transfer size is a lower bound on what
        # the deployment will occupy. Cheap enough to run before we create any
        # rows, and it turns away the obviously-over case immediately. The real
        # check runs below, once the uncompressed total is known.
        used = await store.user_bytes_used(user.id)
        _enforce_quota(used, upload.size, settings)

        project = await _resolve_project(store, user, upload.fields)

        # --- 3. pending row ------------------------------------------------
        commit_sha = (
            request.headers.get("x-commit-sha") or upload.fields.get("commit_sha") or ""
        ).strip()
        deployment = await store.create_deployment(project["id"], commit_sha or None)
        deployment_id = deployment["id"]
        extract_root = os.path.join(tmp_dir, "mv-%s" % deployment_id)

        # --- 4. validate everything before extracting anything -------------
        entries = inspect(
            zip_path,
            extraction_root=extract_root,
            max_files=settings.max_files_per_deployment,
            max_bytes=settings.max_deployment_bytes,
        )
        entries = strip_redundant_root(entries)

        if not any(entry.path == "index.html" for entry in entries):
            raise ZipRejected(
                "No index.html at the root of the archive. Zip the *contents* of "
                "your site folder, not the folder itself."
            )

        # --- quota, real check ---------------------------------------------
        # What lands in Storage is the *uncompressed* content. A 5 MB zip that
        # expands to 90 MB would sail past the transfer-size check above, so
        # re-check against the declared total before writing a single object.
        _enforce_quota(used, sum(entry.size for entry in entries), settings)

        # --- 5. extract and upload -----------------------------------------
        extract(zip_path, entries, extract_root, max_bytes=settings.max_deployment_bytes)
        uploaded_any = True
        size_bytes, paths = await _upload_files(store, deployment_id, extract_root, entries)
        await _verify_served_content_type(store, deployment_id)

        # --- 6. ready ------------------------------------------------------
        await store.mark_deployment_ready(
            deployment_id,
            size_bytes=size_bytes,
            file_count=len(paths),
            file_paths=sorted(paths),
        )
        await store.set_live_deployment(project["id"], deployment_id)
        project_cache.invalidate(project["slug"])

        deployment.update(
            {"status": "ready", "size_bytes": size_bytes, "file_count": len(paths)}
        )
        log.info(
            "deployed %s (%d files, %d bytes) to project %s",
            deployment_id,
            len(paths),
            size_bytes,
            project["slug"],
        )
        return _deployment_response(deployment, project, settings)

    except ZipRejected as exc:
        await _fail(store, deployment, str(exc), uploaded_any)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except HTTPException as exc:
        await _fail(store, deployment, str(exc.detail), uploaded_any)
        raise
    except (SupabaseError, httpx.HTTPError) as exc:
        # Supabase is down or throttling us. Not the user's archive's fault, and
        # not a bug on our side: say 503 so a CI deploy step can retry.
        log.error("supabase unavailable during deploy: %s", exc)
        await _fail(store, deployment, "Upstream storage was unavailable.", uploaded_any)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Upstream storage is temporarily unavailable.",
            headers={"Retry-After": "30"},
        ) from exc
    except Exception as exc:
        log.exception("deployment failed")
        await _fail(store, deployment, "Internal error while deploying.", uploaded_any)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal error while deploying."
        ) from exc
    finally:
        # --- 7. always ------------------------------------------------------
        _cleanup(zip_path, extract_root)


async def _fail(
    store: Store, deployment: dict | None, reason: str, uploaded_any: bool
) -> None:
    """Mark failed and remove any objects we already pushed (SPEC.md step 6)."""
    if deployment is None:
        return
    try:
        if uploaded_any:
            await store.db.remove_prefix(deployment["id"])
    except Exception:  # pragma: no cover - cleanup must not mask the real error
        log.exception("could not remove objects for failed deployment %s", deployment["id"])
    try:
        await store.mark_deployment_failed(deployment["id"], reason)
    except Exception:  # pragma: no cover
        log.exception("could not mark deployment %s failed", deployment["id"])


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
