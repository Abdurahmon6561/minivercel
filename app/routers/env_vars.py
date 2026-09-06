"""Build-time environment variables for a project.

The shape follows `routers/projects.py`: every handler resolves the project by
(slug, owner_id) first, so there is no endpoint here that takes an id and
trusts it. A variable id from another user's project resolves to nothing,
because `get_env_var` is scoped by project_id as well as id.

Two rules the whole module exists to keep:

  1. The plaintext value is never returned. GET masks it. There is no endpoint
     that reads one back - not even to the owner - because the only consumer
     that needs the real value is the build runner, which gets it through its
     own token-authenticated route (added with the workflow change).
  2. The value is encrypted with the same helper and the same key as the GitHub
     provider token (app/crypto.py, GITHUB_TOKEN_KEY). No second key, no second
     scheme.

Fail-closed on a missing key, exactly as `routers/me.py` does when storing a
GitHub token: without encryption available, writing is refused rather than
silently storing plaintext.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ..auth import User, require_user
from ..config import Settings, get_settings
from ..crypto import EncryptionUnavailable, decrypt, encrypt
from ..deps import get_store
from ..store import Conflict

log = logging.getLogger("minivercel.env_vars")

router = APIRouter(prefix="/api/projects/{slug}/env", tags=["env"])

#: Uppercase snake_case, not starting with a digit. This is the POSIX
#: environment-variable convention, and it is enforced rather than normalised:
#: silently upcasing `api_key` to `API_KEY` would mean the name in the UI is not
#: the name the build sees.
KEY_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")
KEY_MAX = 64

#: Enough for a certificate or a long JWT, bounded so a single row cannot be
#: used to push the encrypted column to an unreasonable size.
VALUE_MAX = 4096


class CreateEnvVar(BaseModel):
    key: str = Field(min_length=1, max_length=KEY_MAX)
    value: str = Field(max_length=VALUE_MAX)

    @field_validator("key")
    @classmethod
    def _valid_key(cls, value: str) -> str:
        if not KEY_PATTERN.match(value):
            raise ValueError(
                "Use uppercase letters, digits and underscores, starting with a "
                "letter or underscore - for example API_TOKEN."
            )
        return value


class UpdateEnvVar(BaseModel):
    """Value only.

    The key is immutable by design: renaming one is deleting it and creating
    another, and the build stops seeing the old name either way. Making that
    explicit is more honest than an in-place rename that silently breaks a
    build referencing the previous spelling.
    """

    value: str = Field(max_length=VALUE_MAX)


#: Fixed width, so the mask never leaks the length of the real value.
FULL_MASK = "••••••••"

#: Below this, a "first two characters" hint would be most of the secret.
MIN_LENGTH_TO_HINT = 6


def mask(value_encrypted: str, settings: Settings) -> str:
    """What the dashboard shows in place of the value.

    The first two characters plus a fixed run of dots. The hint is what lets
    someone tell two tokens apart in a list without revealing either.

    Three things this deliberately does NOT do:

      * It never hints at a short value. Two characters of a six-character
        secret is a third of it; anything under MIN_LENGTH_TO_HINT is masked
        whole.
      * It never varies the number of dots with the real length, which would
        turn every row into a length oracle.
      * It never fails the request. A rotated GITHUB_TOKEN_KEY makes every
        stored value unreadable, and the list must still render - the user
        needs to see which keys exist in order to re-enter them.

    The cost is that rendering the list decrypts every row server-side. That is
    accepted: the plaintext exists only for the length of this call and is never
    serialised into the response.
    """
    try:
        value = decrypt(value_encrypted, settings)
    except EncryptionUnavailable:
        return FULL_MASK
    if len(value) < MIN_LENGTH_TO_HINT:
        return FULL_MASK
    return value[:2] + FULL_MASK


def _response(row: dict, settings: Settings) -> dict:
    return {
        "id": row["id"],
        "key": row["key"],
        "value_masked": mask(row["value_encrypted"], settings),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def _owned_project(slug: str, user: User) -> dict:
    """The single authorisation point for this router."""
    project = await get_store().get_owned_project(user.id, slug)
    if project is None:
        # 404 rather than 403: a project belonging to someone else must not be
        # distinguishable from one that does not exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown project.")
    return project


def _encrypt_or_503(value: str, settings: Settings) -> str:
    try:
        return encrypt(value, settings)
    except EncryptionUnavailable as exc:
        log.error("refusing to store an environment variable: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Environment variables are not configured on this server.",
        ) from exc


@router.get("")
async def list_env_vars(
    slug: str,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    project = await _owned_project(slug, user)
    rows = await get_store().list_env_vars(project["id"])
    return [_response(row, settings) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_env_var(
    slug: str,
    payload: CreateEnvVar,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    project = await _owned_project(slug, user)
    encrypted = _encrypt_or_503(payload.value, settings)
    try:
        row = await get_store().create_env_var(project["id"], payload.key, encrypted)
    except Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    # The key, never the value.
    log.info("env var %s created on %s", payload.key, slug)
    return _response(row, settings)


@router.patch("/{var_id}")
async def update_env_var(
    slug: str,
    var_id: str,
    payload: UpdateEnvVar,
    user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
):
    project = await _owned_project(slug, user)
    encrypted = _encrypt_or_503(payload.value, settings)
    row = await get_store().update_env_var(project["id"], var_id, encrypted)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown environment variable.")
    log.info("env var %s updated on %s", row["key"], slug)
    return _response(row, settings)


@router.delete("/{var_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_env_var(slug: str, var_id: str, user: User = Depends(require_user)):
    project = await _owned_project(slug, user)
    store = get_store()

    # Read first so the response can distinguish "deleted" from "was never
    # there", and so the log line can name the key.
    existing = await store.get_env_var(project["id"], var_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown environment variable.")

    await store.delete_env_var(project["id"], var_id)
    log.info("env var %s deleted from %s", existing["key"], slug)
    return None
