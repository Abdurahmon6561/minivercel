"""MiniVercel API.

A platform that serves static files a user uploaded. It never runs them.
Read SPEC.md "Non-negotiables" before changing anything in this package.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import deps, gc
from .config import get_settings
from .hostrouting import HostRoutingMiddleware
from .routers import (
    admin,
    deployments,
    github,
    health,
    me,
    projects,
    serve,
    webhooks,
)
from .supabase import SupabaseError

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("minivercel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.configured:
        deps.get_client()  # fail fast on bad configuration
        log.info(
            "minivercel up: bucket=%s limits=%dMB/deploy %d files %dMB/user",
            settings.supabase_bucket,
            settings.max_deployment_bytes // (1024 * 1024),
            settings.max_files_per_deployment,
            settings.max_user_bytes // (1024 * 1024),
        )

        # A deployment left `pending` is a worker that died mid-deploy, not a
        # slow one: Render restarts the dyno on deploy, on spin-down and on OOM
        # (AUTODEPLOY.md section 6). Left alone the row shows "Building" for
        # ever and the dashboard polls it until the tab is closed. Nothing is
        # retried - those deployments never went live, so the previous one is
        # still serving.
        #
        # This used to sit in the `else` branch below, where it ran only when
        # Supabase was NOT configured - i.e. only when it could not possibly
        # work. Startup is also not enough on its own, because the process that
        # died is usually the one that just restarted *into* this handler with
        # the row less than ten minutes old; `gc.maybe_reap` therefore also runs
        # from the project list and detail routes, which is where the stale row
        # is actually looked at.
        #
        # Never fatal: startup housekeeping must not stop the service booting.
        await gc.reap_stuck(deps.get_store())
    else:
        log.warning(
            "SUPABASE_URL / SUPABASE_SERVICE_KEY are not set. "
            "/health will answer but nothing else will work."
        )

    if settings.admin_token:
        log.info("admin endpoints enabled (POST /api/admin/gc)")
    else:
        log.info("ADMIN_TOKEN is not set: POST /api/admin/gc will answer 503")

    try:
        yield
    finally:
        await deps.shutdown()


app = FastAPI(
    title="MiniVercel",
    description="Upload a zip of static files, get a public URL.",
    version="1.0.0",
    lifespan=lifespan,
)

# Added before CORSMiddleware below, which - per the comment on that call -
# must stay the outermost layer: `add_middleware` makes the LAST call here the
# outermost one, so this line has to come first in the source, not the CORS
# block. In URL_MODE=path (the default, and what every test in this suite
# runs under) this middleware is a no-op passthrough; see app/hostrouting.py.
#
# `get_settings` is looked up through `app.dependency_overrides` on every call
# rather than passed as the bare function, so that this middleware - which
# runs outside FastAPI's routing and therefore outside its dependency
# injection - still honours a `dependency_overrides[get_settings]` swap the
# same way `Depends(get_settings)` does in every route. Tests override
# Settings exactly that way (conftest.py's `override_settings` fixture).
app.add_middleware(
    HostRoutingMiddleware,
    get_settings=lambda: app.dependency_overrides.get(get_settings, get_settings)(),
)

#: Every method this API routes, listed explicitly rather than as "*".
#:
#: A wildcard would have hidden the bug this list is here to prevent: PATCH was
#: added with the Phase 3/4 project switches and this list was not updated, so
#: the browser preflight for `PATCH /api/projects/{slug}` got a 400 "Disallowed
#: method" from CORSMiddleware and the dashboard saw "does not have HTTP ok
#: status". `test_cors.py` now asserts this covers every routed method, so the
#: next new verb fails a test instead of failing in a browser.
ALLOWED_METHODS = ["GET", "HEAD", "POST", "PATCH", "DELETE", "OPTIONS"]

#: Request headers the dashboard actually sends. `X-Commit-Sha` is for the
#: Phase 4 Actions runner, which is not a browser and needs no preflight, but it
#: costs nothing to allow and makes a browser-based test of that path possible.
ALLOWED_HEADERS = ["Authorization", "Content-Type", "X-Commit-Sha"]

_settings = get_settings()
if _settings.cors_origins:
    # Added first and, being the only middleware, outermost: a preflight is
    # answered here and never reaches routing. That is what keeps `require_user`
    # from 401ing an OPTIONS request, which browsers send without credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.cors_origins,
        allow_credentials=False,  # we authenticate with a bearer token, not cookies
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        max_age=600,
    )
else:
    log.warning(
        "CORS_ORIGINS is empty: no CORS headers will be sent and every browser "
        "request from the dashboard will be blocked."
    )


@app.exception_handler(500)
async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    """Never leak an internal message - it could contain a Supabase URL or key."""
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Internal server error."}, status_code=500)


@app.exception_handler(SupabaseError)
async def supabase_unavailable(request: Request, exc: SupabaseError) -> JSONResponse:
    """Supabase is down or rate-limiting us: that is a 503, not our bug.

    The exception message is deliberately not forwarded. It is already redacted
    (app/supabase.py) but it can still carry the project URL and PostgREST
    internals, and neither belongs in a response body.
    """
    log.error("supabase call failed on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        {"detail": "Upstream storage is temporarily unavailable."},
        status_code=503,
        headers={"Retry-After": "30"},
    )


@app.exception_handler(httpx.HTTPError)
async def upstream_unreachable(request: Request, exc: httpx.HTTPError) -> JSONResponse:
    log.error("upstream unreachable on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        {"detail": "Upstream storage is temporarily unavailable."},
        status_code=503,
        headers={"Retry-After": "30"},
    )


# Order matters. `github.router` owns the literal paths `/api/projects/import`
# and `/api/projects/{slug}/builds`; `projects.router` owns `/api/projects/{slug}`.
# FastAPI matches in registration order, so the literal routes go first -
# otherwise adding a POST /{slug} to projects later would silently swallow
# imports and the failure would look like "Unknown project".
app.include_router(health.router)
app.include_router(admin.router)
app.include_router(me.router)
app.include_router(github.router)
app.include_router(projects.router)
app.include_router(deployments.router)
app.include_router(webhooks.router)
app.include_router(serve.router)
