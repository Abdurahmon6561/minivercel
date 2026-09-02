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

from . import deps
from .config import get_settings
from .routers import deployments, health, projects, serve
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
    else:
        log.warning(
            "SUPABASE_URL / SUPABASE_SERVICE_KEY are not set. "
            "/health will answer but nothing else will work."
        )
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

_settings = get_settings()
if _settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.cors_origins,
        allow_credentials=False,  # we authenticate with a bearer token, not cookies
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Commit-Sha"],
        max_age=600,
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


app.include_router(health.router)
app.include_router(projects.router)
app.include_router(deployments.router)
app.include_router(serve.router)
