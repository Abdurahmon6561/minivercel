"""Host-based routing for the getdropbin.xyz migration (AUTODEPLOY.md section 1).

URL_MODE=subdomain moves the platform off `/s/{slug}/` and onto real
subdomains, all under one wildcard certificate:

    Host: api.{SITE_DOMAIN}     -> this API      (/api/*, /auth/*, /webhooks/*,
                                                    /health, /docs, /redoc,
                                                    /openapi.json)
    Host: app.{SITE_DOMAIN}     -> the dashboard  (static files, SPA)
    Host: {SITE_DOMAIN}         -> 301 to https://app.{SITE_DOMAIN}
    Host: {slug}.{SITE_DOMAIN}  -> that project's live site, same resolution
                                    as GET /s/{slug}/... today
    anything else                -> 404
    Host: localhost / 127.0.0.1  -> unchanged: falls through to path-based
                                    routing, so local dev needs no wildcard DNS

URL_MODE=path (the default) makes this middleware a pure no-op: every request
is passed straight through to CORS and the router below, unexamined. That is
what keeps the existing test suite - none of which sets URL_MODE - and every
existing path-mode deployment working exactly as before. Read the branch below
for "subdomain mode" as entirely new code paths that path mode never touches.

This is plain ASGI, not `@app.middleware("http")` (BaseHTTPMiddleware).
`app/routers/serve.py` streams HTML through a StreamingResponse (see its
module docstring - Supabase serves text/html as text/plain on public URLs, so
HTML is proxied rather than redirected) and the slug branch below calls
straight into that same code. A Starlette Response is already an ASGI app;
`await response(scope, receive, send)` sends it as-is, so there is nothing to
buffer and no reason to route it through BaseHTTPMiddleware's request/response
translation.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import Settings
from .store import is_valid_slug

log = logging.getLogger("minivercel.hostrouting")

#: Path prefixes and exact paths that belong to the API. Anything else on the
#: api.{SITE_DOMAIN} host is a 404 rather than falling through to routes meant
#: for other hosts (there is only one FastAPI app underneath, and it still
#: knows how to serve /s/{slug}/... on this host unless this module stops it).
#:
#: `/s/` is here too, but only ever as a redirect: PUBLIC_BASE_URL is
#: `https://api.{SITE_DOMAIN}` in subdomain mode, so a bookmarked or shared
#: `/s/{slug}/...` link arrives on this host, and app/routers/serve.py answers
#: every such request with a 301 to `{slug}.{SITE_DOMAIN}` rather than serving
#: it here - see `_host_redirect_target` there. It never serves site content
#: on this host, so this is not a second way to reach a site through the API
#: origin.
API_PATH_PREFIXES = ("/api/", "/auth/", "/webhooks/", "/s/")
API_EXACT_PATHS = ("/api", "/auth", "/webhooks", "/health", "/docs", "/redoc", "/openapi.json")


def _is_api_path(path: str) -> bool:
    return path in API_EXACT_PATHS or any(path.startswith(p) for p in API_PATH_PREFIXES)


def _host_only(scope: Scope) -> str:
    for name, value in scope.get("headers") or ():
        if name == b"host":
            return value.decode("latin-1").split(":", 1)[0].strip().lower()
    return ""


def _plain(status_code: int, message: str, headers: dict[str, str] | None = None) -> Response:
    return PlainTextResponse(
        message, status_code=status_code, headers={"X-Content-Type-Options": "nosniff", **(headers or {})}
    )


def _not_found() -> Response:
    return _plain(404, "Not found.")


def _match_preview(path: str) -> tuple[str, str] | None:
    """`_d/{deployment_id}/{rest}` -> (deployment_id, rest), else None.

    Mirrors the two-route split in serve.py (`_d/{id}` vs `_d/{id}/{path}`),
    collapsed into one check because there is no router here to register two
    patterns with. A bare `_d/{id}` with no trailing slash - which
    `urls.preview_url` never produces - falls through to `serve_project` as an
    ordinary (and harmless, always-404) file path instead of getting the
    trailing-slash nudge `/s/{slug}/_d/{id}` gives in path mode; that route is
    reached only by a hand-typed URL, and it can be added if that ever matters.
    """
    if not path.startswith("_d/"):
        return None
    deployment_id, sep, rest = path[len("_d/") :].partition("/")
    if not sep or not deployment_id:
        return None
    return deployment_id, rest


class DashboardStatic:
    """Serve the built dashboard (web/dist) for Host: app.{SITE_DOMAIN}.

    Plain SPA static serving: a request path that matches a real file under
    the build directory - the hashed, long-cache `assets/*.js` and `*.css`
    Vite produces, `favicon.ico`, and so on - is served as-is. Anything else,
    including a client-side route like `/p/blue-forest-4821` or a typo, gets
    `index.html`, and the React router already bundled into it decides what
    that means. This is the same rewrite web/vercel.json used on Vercel, so
    the dashboard behaves identically served from here.
    """

    def __init__(self, directory: str) -> None:
        self._directory = os.path.abspath(directory)

    def _resolve_file(self, path: str) -> str | None:
        """Absolute path to an existing, in-bounds static file, or None.

        Refuses to leave `directory` for the same reason
        `serve._serve_from` refuses to leave a deployment's own key prefix:
        `path` is attacker-controlled right up until this check runs.
        """
        relative = path.lstrip("/")
        if not relative or ".." in relative.split("/") or "\x00" in relative:
            return None
        candidate = os.path.abspath(os.path.join(self._directory, *relative.split("/")))
        if not candidate.startswith(self._directory + os.sep):
            return None
        return candidate if os.path.isfile(candidate) else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["method"] not in ("GET", "HEAD"):
            await _plain(405, "Method not allowed.")(scope, receive, send)
            return

        index = os.path.join(self._directory, "index.html")
        if not os.path.isfile(index):
            # Not a user-facing bug: the operator's build step didn't run.
            log.error(
                "dashboard build not found at %s - DASHBOARD_DIST_DIR is unset "
                "or `npm run build` was not run into it",
                self._directory,
            )
            await _plain(503, "The dashboard is not built into this deployment.")(
                scope, receive, send
            )
            return

        found = self._resolve_file(scope["path"])
        if found and found != index:
            headers = (
                {"Cache-Control": "public, max-age=31536000, immutable"}
                if "/assets/" in scope["path"]
                else {}
            )
            await FileResponse(found, headers=headers)(scope, receive, send)
            return

        # The SPA shell. Never cached: it is what points at the (cacheable,
        # hashed) assets, so a stale copy would pin a user to an old bundle.
        await FileResponse(index, headers={"Cache-Control": "no-cache"})(scope, receive, send)


class HostRoutingMiddleware:
    """Outermost-but-one ASGI layer (see main.py) that dispatches on Host.

    Takes a `get_settings` callable rather than importing `.config.get_settings`
    directly, so that main.py can hand it one that honours
    `app.dependency_overrides` the same way FastAPI's own `Depends(get_settings)`
    does - tests swap Settings in exactly that way (see conftest.py's
    `override_settings`), and this middleware runs outside FastAPI's dependency
    injection entirely, so without this indirection it would never see an
    override a test installed.

    `DashboardStatic` is rebuilt on every request into `app.{SITE_DOMAIN}`
    rather than cached: it is a thin wrapper around one directory path, and
    `dashboard_dist_dir` can only change via `get_settings`, which the caller
    already controls the caching (or overriding) of.
    """

    def __init__(self, app: ASGIApp, get_settings: Callable[[], Settings]) -> None:
        self._app = app
        self._get_settings = get_settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        settings = self._get_settings()
        if settings.url_mode != "subdomain" or not settings.site_domain:
            await self._app(scope, receive, send)
            return

        if scope["path"] == "/health":
            # Render's own health check (render.yaml healthCheckPath) and any
            # external uptime ping (AUTODEPLOY.md section 6's "keep it warm"
            # ping) hit this container directly and send whatever Host header
            # their infrastructure uses - almost certainly not
            # api.{SITE_DOMAIN}. Liveness has to work no matter what Host
            # says, or the service gets marked unhealthy and cycled right
            # after this migration ships.
            await self._app(scope, receive, send)
            return

        host = _host_only(scope)
        if host.startswith("localhost") or host.startswith("127.0.0.1"):
            await self._app(scope, receive, send)
            return

        domain = settings.site_domain
        path = scope["path"]

        if host == domain:
            response: Response = RedirectResponse(
                "https://app.%s%s" % (domain, path or "/"), status_code=301
            )
            await response(scope, receive, send)
            return

        if host == "api." + domain:
            if _is_api_path(path):
                await self._app(scope, receive, send)
            else:
                await _not_found()(scope, receive, send)
            return

        if host == "app." + domain:
            await DashboardStatic(settings.dashboard_dist_dir)(scope, receive, send)
            return

        if not host.endswith("." + domain):
            # Some other host entirely - a stray DNS record, a bot probing by
            # IP, a domain squatting on this wildcard's SSL cert never applies
            # to. Not our problem to explain; just 404.
            await _not_found()(scope, receive, send)
            return

        slug = host[: -(len(domain) + 1)]
        if not is_valid_slug(slug):
            await _not_found()(scope, receive, send)
            return

        # Same resolution as `GET /s/{slug}/{path}` in path mode. Imported
        # lazily: app/routers/serve.py imports app/config.py, and importing it
        # at module load time here would run before `app.main` has finished
        # building the app the router functions close over indirectly via
        # `deps.get_store()` - deferring the import avoids caring about that
        # ordering at all.
        from .routers.serve import serve_project, serve_project_preview

        request = Request(scope, receive=receive)
        rest = path.lstrip("/")
        preview = _match_preview(rest)
        try:
            if preview is not None:
                deployment_id, tail = preview
                response = await serve_project_preview(
                    slug, deployment_id, tail, request, settings
                )
            else:
                response = await serve_project(slug, rest, request, settings)
        except HTTPException as exc:
            # serve_project's rate limiter raises HTTPException the normal
            # FastAPI way; there is no router here to catch it for us.
            response = _plain(exc.status_code, str(exc.detail), dict(exc.headers or {}))

        await response(scope, receive, send)
