"""POST /api/admin/gc - run the storage sweep by hand.

Render's free plan has no cron and SPEC.md rules out a second free service, so
garbage collection normally rides on the event that creates the garbage: the end
of every successful deploy, scoped to the project that just deployed
(app/deployer.py). That covers the common case and costs nothing.

It does not cover two cases, which is what this endpoint is for:

  * a project that stopped deploying still holds every deployment it ever made,
    and nothing will ever collect them because nothing will deploy it again;
  * a sweep needs running now - after restoring a backup, after the 1 GB alarm,
    or from an external scheduler if you ever add one (a HetrixTools monitor or
    a GitHub Actions cron can hit this URL as easily as `/health`).

Authentication is a single shared secret in ADMIN_TOKEN, compared with
`hmac.compare_digest`. Not `==`: a byte-by-byte comparison returns as soon as
two bytes differ, so response time leaks how much of a guessed token was
correct, and that turns forging one into a search over 32 attempts per byte
rather than over the whole space. The same reasoning as the webhook signature
in app/routers/webhooks.py, and it applies here for the same reason - this is a
secret an attacker can guess at repeatedly.

If ADMIN_TOKEN is unset the endpoint answers 503 and does nothing. An unset
secret must never be read as "no check required".
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .. import gc
from ..config import Settings, get_settings
from ..deps import get_store

log = logging.getLogger("minivercel.admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _presented_token(request: Request) -> str:
    """`Authorization: Bearer <token>`, or `X-Admin-Token: <token>`.

    Both, because a scheduler that can only set one custom header is common and
    there is no security difference between them.
    """
    header = request.headers.get("authorization") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return (request.headers.get("x-admin-token") or "").strip()


def require_admin(request: Request, settings: Settings = Depends(get_settings)) -> None:
    expected = settings.admin_token
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Administrative endpoints are disabled: ADMIN_TOKEN is not set on "
            "this server.",
        )

    presented = _presented_token(request)
    # compare_digest on both sides, and only after the "is it configured at all"
    # check above - so an empty presented token can never match an empty secret.
    if not presented or not hmac.compare_digest(presented, expected):
        log.warning("rejected admin request from %s", request.client.host if request.client else "?")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "A valid ADMIN_TOKEN is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/gc", dependencies=[Depends(require_admin)])
async def run_gc():
    """Sweep every project, then reap stuck `pending` rows.

    Reports bytes reclaimed, which is the number worth watching against the 1 GB
    Storage limit - it is also written to the log on every run, so the history
    survives in Render's log even though nothing here is persisted.
    """
    store = get_store()
    result = await gc.collect_all(store)
    reaped = await gc.reap_stuck(store)

    body = result.as_dict()
    body["stuck_deployments_failed"] = reaped
    return body
