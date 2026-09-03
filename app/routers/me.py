"""`/api/me` - who the dashboard is signed in as, and its GitHub connection.

The GitHub provider token arrives here and stops here. It is encrypted before it
touches the database (app/crypto.py) and no endpoint in this file, or any other,
returns it. `GET /api/me` reports only whether one exists and what scopes it
carries, which is all the dashboard needs to render a connection state.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import gc
from ..auth import User, require_user
from ..config import Settings, get_settings
from ..crypto import EncryptionUnavailable, encrypt
from ..deps import get_store

log = logging.getLogger("minivercel.me")

router = APIRouter(prefix="/api/me", tags=["me"])


class GithubToken(BaseModel):
    provider_token: str = Field(min_length=8, max_length=500)
    scopes: str | None = Field(default=None, max_length=200)
    github_login: str | None = Field(default=None, max_length=100)


@router.get("")
async def read_me(
    user: User = Depends(require_user), settings: Settings = Depends(get_settings)
):
    store = get_store()
    # AUTODEPLOY.md section 6: a `pending` row left by a dead worker still
    # counts its (usually zero) bytes and, more importantly, keeps the
    # dashboard showing a deploy that will never finish. Throttled; see
    # gc.maybe_reap.
    await gc.maybe_reap(store)

    # The live figure, recomputed on every call rather than cached: it is the
    # number the quota bar draws, and garbage collection moves it downwards
    # without the browser knowing (SPEC.md Phase 5). Counts every deployment
    # that is not `failed`, across every project this user owns - a failed
    # deployment has already had its objects removed.
    used = await store.user_bytes_used(user.id)
    token_row = await store.get_github_token_row(user.id)

    return {
        "id": user.id,
        "email": user.email,
        "usage": {
            "bytes_used": used,
            "bytes_limit": settings.max_user_bytes,
            "bytes_available": max(settings.max_user_bytes - used, 0),
            "max_deployment_bytes": settings.max_deployment_bytes,
            "max_files_per_deployment": settings.max_files_per_deployment,
            # What the collector will and will not remove, so the dashboard can
            # explain the bar instead of only drawing it. `keep_recent_ready`
            # counts working deployments: a failed one can never be promoted, so
            # it holds no rollback slot (app/gc.py rule 2).
            "retention": {
                "keep_recent_ready": gc.KEEP_RECENT_READY,
                "max_age_days": gc.MAX_AGE_DAYS,
            },
        },
        "github": {
            # Never the token itself.
            "connected": token_row is not None,
            "login": (token_row or {}).get("github_login"),
            "scopes": (token_row or {}).get("scopes"),
            "updated_at": (token_row or {}).get("updated_at"),
        },
    }


@router.post("/github-token", status_code=status.HTTP_204_NO_CONTENT)
async def store_github_token(
    payload: GithubToken,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    """Accept the provider token supabase-js hands the browser after OAuth.

    Supabase returns `provider_token` exactly once, on the sign-in event, and
    never refreshes it. The dashboard therefore posts it here immediately; Phase
    3 reads it back to call the GitHub API on the user's behalf.
    """
    try:
        encrypted = encrypt(payload.provider_token, settings)
    except EncryptionUnavailable as exc:
        log.error("refusing to store a GitHub token: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "GitHub connection is not configured on this server.",
        ) from exc

    await get_store().save_github_token(
        user.id,
        encrypted,
        scopes=payload.scopes,
        github_login=payload.github_login,
    )
    log.info("stored GitHub token for %s (scopes=%s)", user.id, payload.scopes)
    return None


@router.delete("/github-token", status_code=status.HTTP_204_NO_CONTENT)
async def forget_github_token(user: User = Depends(require_user)):
    await get_store().delete_github_token(user.id)
    log.info("removed GitHub token for %s", user.id)
    return None
