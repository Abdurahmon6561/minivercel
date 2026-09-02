"""GET /s/{slug}/{path} - the serving flow.

NON-NEGOTIABLE #2: this router never reads a user's file bytes. It resolves a
request path to a storage key and returns a 307 pointing at Supabase's public
CDN URL. The dyno's CPU and bandwidth are untouched by the payload.

Path resolution (SPEC.md "Serving flow" step 2):

    ""  or  "docs/"      ->  docs/index.html
    "about"              ->  about.html, then about/index.html   (clean URLs)
    anything unresolved  ->  404.html if the deployment has one, else plain 404

Existence is answered from the deployment's file manifest, cached in memory and
immutable for the life of the deployment (see db/002_file_manifest.sql). If the
manifest column is absent we fall back to HEAD requests against Storage.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse, RedirectResponse

from ..cache import MISSING, manifest_cache, project_cache
from ..deps import get_store, serve_limiter
from ..mimemap import has_known_extension
from ..ratelimit import client_ip
from ..store import is_valid_slug

log = logging.getLogger("minivercel.serve")

router = APIRouter(tags=["serve"])

# Redirects are cheap but they must not pin a stale deployment in a CDN or
# browser cache: a redeploy has to take effect on the next request.
REDIRECT_HEADERS = {
    "Cache-Control": "public, max-age=0, must-revalidate",
    # SPEC.md "Response headers". Known limitation: this header rides on the
    # redirect, not on the object Supabase ultimately serves. Supabase sets the
    # content-type we chose from the whitelist in mimemap.py, so a user file is
    # never sniffed into being something else; but user sites are still
    # untrusted content on this origin. Do not put cookies or auth on this
    # domain - see README "Known limitations".
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


class Unavailable(Exception):
    """Supabase could not be reached. Distinct from "this site does not exist"."""


async def _load_project(slug: str):
    cached = project_cache.get(slug)
    if cached is not None:
        return None if cached is MISSING else cached

    try:
        project = await get_store().get_project_by_slug(slug)
    except Exception as exc:
        # Never cache a failure: a 30-second Supabase blip must not pin every
        # site on this instance to "missing" for the life of the TTL.
        log.warning("lookup failed for slug %s: %s", slug, exc)
        raise Unavailable from exc

    project_cache.set(slug, project if project is not None else MISSING)
    return project


async def _load_manifest(deployment_id: str) -> frozenset | None:
    """File paths in this deployment, or None when no manifest is stored."""
    cached = manifest_cache.get(deployment_id)
    if cached is not None:
        return cached if cached else frozenset()

    deployment = await get_store().get_deployment(deployment_id)
    if deployment is None or deployment.get("status") != "ready":
        return None

    paths = deployment.get("file_paths")
    if paths is None:
        return None

    manifest = frozenset(paths)
    manifest_cache.set(deployment_id, manifest)
    return manifest


def _candidates(path: str) -> list[str]:
    """Keys to try, in order, for a request path."""
    if path == "" or path.endswith("/"):
        return [path + "index.html"]

    tries = [path]
    if not has_known_extension(path):
        tries.append(path + ".html")
        tries.append(path + "/index.html")
    return tries


async def _resolve(deployment_id: str, path: str) -> tuple[str | None, bool]:
    """Return (storage relative path, is_404_fallback)."""
    manifest = await _load_manifest(deployment_id)
    store = get_store()

    if manifest is not None:
        for candidate in _candidates(path):
            if candidate in manifest:
                return candidate, False
        if "404.html" in manifest:
            return "404.html", True
        return None, False

    # No manifest stored (db/002 not applied): probe Storage directly.
    for candidate in _candidates(path):
        if await store.db.object_exists("%s/%s" % (deployment_id, candidate)):
            return candidate, False
    if await store.db.object_exists("%s/404.html" % deployment_id):
        return "404.html", True
    return None, False


def _not_found(message: str) -> PlainTextResponse:
    return PlainTextResponse(
        message,
        status_code=status.HTTP_404_NOT_FOUND,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


def _unavailable() -> PlainTextResponse:
    """Supabase is unreachable. Say so honestly instead of claiming a 404.

    A 503 keeps search engines and the browser from concluding the site is gone,
    and it does not leak anything about why.
    """
    return PlainTextResponse(
        "This site is temporarily unavailable.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Retry-After": "30",
        },
    )


@router.get("/s/{slug}")
async def serve_root_no_slash(slug: str) -> Response:
    """Send `/s/slug` to `/s/slug/` so relative asset URLs resolve correctly."""
    return RedirectResponse(
        "/s/%s/" % slug, status_code=status.HTTP_308_PERMANENT_REDIRECT
    )


@router.get("/s/{slug}/{path:path}")
async def serve(slug: str, path: str, request: Request) -> Response:
    decision = serve_limiter().check(client_ip(request))
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded.",
            headers={"Retry-After": str(decision.retry_after)},
        )

    slug = slug.lower()
    if not is_valid_slug(slug):
        return _not_found("No such site.")

    try:
        project = await _load_project(slug)
    except Unavailable:
        return _unavailable()

    if project is None:
        return _not_found("No such site.")

    deployment_id = project.get("live_deployment_id")
    if not deployment_id:
        return _not_found("This site has no live deployment yet.")

    # A request path can only ever be appended to a key prefix we own, but
    # normalise anyway so `..` cannot appear in the URL we hand to Supabase.
    if ".." in path.split("/") or path.startswith("/") or "\x00" in path:
        return _not_found("Not found.")

    try:
        key, is_fallback = await _resolve(deployment_id, path)
    except Exception as exc:
        log.warning("could not resolve %s in deployment %s: %s", path, deployment_id, exc)
        return _unavailable()

    if key is None:
        return _not_found("Not found.")

    url = get_store().db.public_url("%s/%s" % (deployment_id, key))
    headers = dict(REDIRECT_HEADERS)
    if is_fallback:
        headers["X-MiniVercel-Fallback"] = "404"
    return RedirectResponse(
        url, status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers=headers
    )
