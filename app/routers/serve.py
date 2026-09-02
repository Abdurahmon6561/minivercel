"""GET /s/{slug}/{path} - the serving flow.

NON-NEGOTIABLE #2, and its one exception:

Everything is served by 307 redirect to Supabase's public CDN URL, so the dyno's
CPU and bandwidth are untouched by the payload - EXCEPT HTML, which is streamed
through this process.

That exception is forced on us. Supabase Storage deliberately serves `text/html`
as `text/plain` on public URLs (supabase/storage#186, discussions #2557 and
#39110). It is anti-phishing policy for the shared `*.supabase.co` origin, not a
bug, and not something an upload header can defeat: our objects carry the right
`metadata->>'mimetype'` and are still downgraded on the way out. A redirect
therefore cannot render a page, which makes redirect-only serving incompatible
with the product. HTML is the whole of the exception; css, js, images and fonts
come back from Supabase with correct types and keep the redirect.

Consequences that follow from proxying HTML, and are dealt with here:

  * user HTML now executes on OUR origin, not on supabase.co. That is precisely
    the risk Supabase declined to take. Nothing on this domain may ever set a
    cookie or hold a session - see README "Known limitations".
  * HTML bytes cross the dyno twice (Supabase -> us -> browser), counting
    against Render bandwidth and Supabase egress. Capped per response by
    MAX_PROXY_BYTES, and HTML is the small half of a static site.
  * proxying lets us return a real status code, so a deployment's 404.html is
    finally served *as* a 404 instead of a 200.

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

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse

from ..cache import MISSING, manifest_cache, project_cache
from ..config import Settings, get_settings
from ..deps import get_store, serve_limiter
from ..mimemap import content_type_for, has_known_extension
from ..ratelimit import client_ip
from ..store import is_valid_slug

log = logging.getLogger("minivercel.serve")

router = APIRouter(tags=["serve"])

PROXY_CHUNK = 64 * 1024

# Types Supabase downgrades on public URLs, and which therefore have to be
# proxied. Both are document types the browser renders and scripts run in;
# everything else in the whitelist comes back from Supabase intact.
PROXIED_TYPES = ("text/html", "application/xhtml+xml")


def _must_proxy(key: str) -> bool:
    return content_type_for(key).startswith(PROXIED_TYPES)

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


async def _proxy_html(key: str, status_code: int, max_bytes: int) -> Response:
    """Stream one HTML object through this process with the right type.

    Streamed, never buffered: a 5 MB cap on a 512 MB dyno is only safe if the
    bytes are not all resident at once, and several concurrent requests for the
    same large page would otherwise be enough to matter.
    """
    store = get_store()
    try:
        upstream = await store.db.open_object_stream(key)
    except Exception as exc:
        log.warning("could not open %s for proxying: %s", key, exc)
        return _unavailable()

    if upstream.status_code != 200:
        await upstream.aclose()
        log.warning("proxy fetch of %s returned %s", key, upstream.status_code)
        return _not_found("Not found.")

    # Storage sends Content-Length, so oversize is normally refused before a
    # single byte is streamed. The counter below is the backstop for when it is
    # absent - by then headers are already sent and truncation is all that is
    # left, so this path is loud in the log.
    declared = upstream.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        await upstream.aclose()
        log.error(
            "refusing to proxy %s: %s bytes exceeds the %d byte cap",
            key,
            declared,
            max_bytes,
        )
        return PlainTextResponse(
            "This page is too large to serve.",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )

    async def body():
        sent = 0
        try:
            async for chunk in upstream.aiter_bytes(PROXY_CHUNK):
                sent += len(chunk)
                if sent > max_bytes:
                    log.error(
                        "truncating %s at %d bytes: no Content-Length and the "
                        "response ran past the %d byte cap",
                        key,
                        sent,
                        max_bytes,
                    )
                    return
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        body(),
        status_code=status_code,
        media_type=content_type_for(key),
        headers={
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            # Same reasoning as the redirect: a redeploy must be visible on the
            # next request, so nothing pins this response.
            "Cache-Control": "public, max-age=0, must-revalidate",
        },
    )


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
async def serve(
    slug: str,
    path: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
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

    object_key = "%s/%s" % (deployment_id, key)

    # HTML: proxy, because a redirect would hand the browser text/plain. The
    # 404.html fallback finally gets to be an actual 404.
    if _must_proxy(key):
        return await _proxy_html(
            object_key,
            status.HTTP_404_NOT_FOUND if is_fallback else status.HTTP_200_OK,
            settings.max_proxy_bytes,
        )

    # Everything else: redirect, and never touch the bytes.
    headers = dict(REDIRECT_HEADERS)
    if is_fallback:
        headers["X-MiniVercel-Fallback"] = "404"
    return RedirectResponse(
        get_store().db.public_url(object_key),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers=headers,
    )
