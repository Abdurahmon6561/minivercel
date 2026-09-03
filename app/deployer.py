"""The deployment pipeline, shared by every source of a zip.

Phase 1 had one entry point: a user POSTing an archive. Phase 3 adds two more -
a GitHub zipball on import, and the same on every push - and Phase 4 adds a
fourth, a GitHub Actions runner POSTing built output. All four must go through
*identical* validation. That is why this lives here instead of inside an HTTP
handler: there is exactly one copy of the rules, and no route can accidentally
skip one.

The order is SPEC.md's "Upload flow", unchanged:

    validate every entry  ->  extract  ->  upload  ->  mark ready
                                  |
                          any failure: mark failed, remove objects,
                          leave the previous deployment live

NON-NEGOTIABLE #1: nothing in this module executes anything from the archive.
NON-NEGOTIABLE #6: /tmp is cleaned in a `finally`, on every path.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass

from . import gc
from .config import Settings
from .mimemap import content_type_for
from .store import Store
from .zipvalidate import (
    BUILD_OUTPUT_DIRS,
    ZipRejected,
    extract,
    inspect,
    select_site_root,
    strip_redundant_root,
)

log = logging.getLogger("minivercel.deployer")

# Storage has no batch upload, so concurrency is the only lever on deploy time.
UPLOAD_CONCURRENCY = 8

#: Written from BUILD_OUTPUT_DIRS rather than spelled out, so the message can
#: never name a directory the code does not actually look in.
_SEARCHED = ", ".join(directory + "/" for directory in BUILD_OUTPUT_DIRS)

NO_STATIC_OUTPUT = (
    "No index.html found. Searched the repository root and then %s. "
    "If this project needs a build step, enable builds on the project page: "
    "GitHub Actions will run your build command and deploy its output "
    "directory. If it is already a static site, check that index.html is at "
    "the root of the repository or of one of those directories." % _SEARCHED
)

NO_INDEX_IN_ZIP = (
    "No index.html found at the root of the archive. Zip the *contents* of "
    "your site folder, not the folder itself - `cd site && zip -r ../site.zip "
    ".` rather than `zip -r site.zip site`. If your site needs a build step, "
    "import the repository from GitHub instead and enable builds."
)


class QuotaExceeded(Exception):
    """The user is out of storage. Carries a message safe to show them."""


@dataclass
class DeployResult:
    deployment_id: str
    size_bytes: int
    file_count: int
    site_root: str | None  # the subdirectory we deployed, if not the archive root


async def _upload_files(
    store: Store, deployment_id: str, root: str, entries
) -> tuple[int, list[str]]:
    semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY)
    total = 0
    paths: list[str] = []
    lock = asyncio.Lock()

    async def push(relpath: str) -> None:
        nonlocal total
        with open(os.path.join(root, *relpath.split("/")), "rb") as handle:
            payload = handle.read()
        # Content-type from our whitelist keyed on the extension, never from the
        # archive (SPEC.md step 5).
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


def cleanup(*paths: str) -> None:
    """NON-NEGOTIABLE #6. Never raises."""
    for path in paths:
        if not path:
            continue
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                os.unlink(path)
        except OSError as exc:  # pragma: no cover - defensive
            log.warning("could not clean up %s: %s", path, exc)


async def verify_served_content_type(store: Store, deployment_id: str) -> None:
    """Read back index.html and check Storage kept the type we sent.

    One HEAD per deploy, never fatal. The failure it catches is invisible from
    this side: the upload returns 200 and the logs look perfect while the
    browser renders the page as plain text.
    """
    expected = content_type_for("index.html")
    try:
        served = await store.db.stored_content_type("%s/index.html" % deployment_id)
    except Exception as exc:  # pragma: no cover - diagnostics must not break a deploy
        log.warning("content-type read-back failed for %s: %s", deployment_id, exc)
        return

    if served is None:
        log.warning(
            "content-type read-back: %s/index.html could not be fetched", deployment_id
        )
    elif served.split(";")[0].strip().lower() != expected.split(";")[0].strip().lower():
        log.error(
            "CONTENT-TYPE MISMATCH on %s/index.html: sent %r, Storage serves %r.",
            deployment_id,
            expected,
            served,
        )


def quota_message(used: int, incoming: int, limit: int) -> str:
    """One wording for every quota refusal, wherever it is raised.

    Says the three things the user needs in order to act: how much they are
    using, what the ceiling is, and that deployments - not only whole projects -
    can be deleted to get under it. The earlier message offered "delete a
    project first", which is drastic advice when the fix is usually one stale
    deployment.
    """
    mb = 1024 * 1024
    return (
        "Storage quota exceeded. You are using %.1f MB of your %.1f MB limit "
        "and this deployment needs another %.1f MB. Delete a project, or "
        "delete old deployments you no longer need - MiniVercel keeps the live "
        "deployment plus the five most recent working ones per project and "
        "clears the rest after seven days, so this usually frees itself."
        % (used / mb, limit / mb, incoming / mb)
    )


async def enforce_quota(used: int, incoming: int, settings: Settings) -> None:
    """NON-NEGOTIABLE #5: the free tier will not warn you before it breaks."""
    if used + incoming <= settings.max_user_bytes:
        return
    raise QuotaExceeded(quota_message(used, incoming, settings.max_user_bytes))


async def publish(
    store: Store,
    settings: Settings,
    *,
    project: dict,
    deployment_id: str,
    zip_path: str,
    extract_root: str,
    owner_id: str,
    allow_build_output_dirs: bool = False,
) -> DeployResult:
    """Validate, extract, upload and publish one archive.

    `allow_build_output_dirs` is the single behavioural difference between a
    user's hand-made zip and a GitHub repository. A zip is expected to *be* the
    site; a repository usually contains one. Turning it on for uploads would
    silently deploy a `dist/` folder someone happened to include.

    On success the caller's project becomes live. On any failure the deployment
    is marked failed and its objects removed, and `projects.live_deployment_id`
    is left exactly where it was - a broken push must never take a working site
    down.
    """
    uploaded_any = False
    try:
        # --- validate everything before extracting anything ----------------
        entries = inspect(
            zip_path,
            extraction_root=extract_root,
            max_files=settings.max_files_per_deployment,
            max_bytes=settings.max_deployment_bytes,
        )
        # GitHub wraps every zipball in `{owner}-{repo}-{sha}/`.
        entries = strip_redundant_root(entries)

        site_root = None
        if allow_build_output_dirs:
            entries, site_root = select_site_root(entries)

        if not any(entry.path == "index.html" for entry in entries):
            raise ZipRejected(
                NO_STATIC_OUTPUT if allow_build_output_dirs else NO_INDEX_IN_ZIP
            )

        # Quota against the uncompressed total, before a single object is written.
        used = await store.user_bytes_used(owner_id)
        await enforce_quota(used, sum(entry.size for entry in entries), settings)

        # --- extract and upload --------------------------------------------
        extract(zip_path, entries, extract_root, max_bytes=settings.max_deployment_bytes)
        uploaded_any = True
        size_bytes, paths = await _upload_files(
            store, deployment_id, extract_root, entries
        )

        await store.mark_deployment_ready(
            deployment_id,
            size_bytes=size_bytes,
            file_count=len(paths),
            file_paths=sorted(paths),
        )
        await verify_served_content_type(store, deployment_id)

        # Only now does the project point at this deployment.
        await store.set_live_deployment(project["id"], deployment_id)

        log.info(
            "deployed %s (%d files, %d bytes%s) to %s",
            deployment_id,
            len(paths),
            size_bytes,
            ", root=%s" % site_root if site_root else "",
            project["slug"],
        )

        # Render's free plan has no cron (SPEC.md Phase 5), so collection rides
        # on the event that creates the garbage. Scoped to this project, after
        # the deployment is live, and unable to fail the deploy.
        await gc.collect_after_deploy(store, {**project, "live_deployment_id": deployment_id})

        return DeployResult(deployment_id, size_bytes, len(paths), site_root)

    except Exception:
        await fail(store, deployment_id, uploaded_any)
        raise


async def fail(store: Store, deployment_id: str | None, uploaded_any: bool) -> None:
    """Remove any objects already written. Never raises."""
    if deployment_id is None:
        return
    if uploaded_any:
        try:
            await store.db.remove_prefix(deployment_id)
        except Exception:  # pragma: no cover - cleanup must not mask the real error
            log.exception("could not remove objects for failed deployment %s", deployment_id)


async def mark_failed(store: Store, deployment_id: str, reason: str) -> None:
    try:
        await store.mark_deployment_failed(deployment_id, reason)
    except Exception:  # pragma: no cover
        log.exception("could not mark deployment %s failed", deployment_id)
