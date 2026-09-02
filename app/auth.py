"""Supabase JWT verification.

Two signing regimes exist in the wild and we support both:

  * legacy projects sign with a shared HS256 secret -> set SUPABASE_JWT_SECRET
  * current projects sign with ES256/RS256 keys     -> leave it blank and we
    verify against {SUPABASE_URL}/auth/v1/.well-known/jwks.json

Verification is always local. We never call `/auth/v1/user` per request: that
would add a Supabase round-trip to every upload and it is the same signature
check we can do ourselves in microseconds.

SPEC.md upload flow step 1: authenticate the user, reject anonymous. There is no
anonymous path through `require_user`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status

from .config import Settings, get_settings

log = logging.getLogger("minivercel.auth")

JWKS_TTL_SECONDS = 600
ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="A valid Supabase access token is required.",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True)
class User:
    id: str
    email: str | None = None
    role: str | None = None


class _JWKSCache:
    """Cached JWKS document. One fetch per 10 minutes, shared process-wide."""

    def __init__(self) -> None:
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0

    async def key_for(self, kid: str | None, settings: Settings) -> Any:
        if self._is_stale():
            await self._refresh(settings)
        key = self._lookup(kid)
        if key is None:
            # A rotated key we have not seen: refresh once, then give up.
            await self._refresh(settings)
            key = self._lookup(kid)
        if key is None:
            raise _UNAUTHORIZED
        return key

    def _is_stale(self) -> bool:
        return not self._keys or (time.monotonic() - self._fetched_at) > JWKS_TTL_SECONDS

    def _lookup(self, kid: str | None) -> Any:
        if kid is not None:
            return self._keys.get(kid)
        if len(self._keys) == 1:
            return next(iter(self._keys.values()))
        return None

    async def _refresh(self, settings: Settings) -> None:
        url = settings.supabase_url + "/auth/v1/.well-known/jwks.json"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url, headers={"apikey": settings.supabase_service_key}
                )
                response.raise_for_status()
                document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.error("could not fetch JWKS: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is temporarily unavailable.",
            ) from exc

        keys: dict[str, Any] = {}
        for entry in document.get("keys", []):
            try:
                keys[entry.get("kid")] = jwt.PyJWK.from_dict(entry).key
            except Exception as exc:  # unsupported key type; skip it
                log.warning("skipping unusable JWK: %s", exc)
        self._keys = keys
        self._fetched_at = time.monotonic()


_jwks = _JWKSCache()


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def verify_token(token: str, settings: Settings) -> User:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise _UNAUTHORIZED

    algorithm = header.get("alg")
    options = {"require": ["exp", "sub"]}

    try:
        if settings.supabase_jwt_secret and algorithm == "HS256":
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_audience or None,
                options=options if settings.supabase_jwt_audience else {**options, "verify_aud": False},
            )
        elif algorithm in ASYMMETRIC_ALGORITHMS:
            key = await _jwks.key_for(header.get("kid"), settings)
            claims = jwt.decode(
                token,
                key,
                algorithms=ASYMMETRIC_ALGORITHMS,
                audience=settings.supabase_jwt_audience or None,
                options=options if settings.supabase_jwt_audience else {**options, "verify_aud": False},
            )
        else:
            # Includes alg=none and HS256 with no configured secret.
            raise _UNAUTHORIZED
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        log.info("rejected token: %s", exc)
        raise _UNAUTHORIZED

    subject = claims.get("sub")
    if not subject:
        raise _UNAUTHORIZED

    return User(
        id=str(subject),
        email=claims.get("email"),
        role=claims.get("role"),
    )


async def require_user(
    request: Request, settings: Settings = Depends(get_settings)
) -> User:
    token = bearer_token(request)
    if not token:
        raise _UNAUTHORIZED
    return await verify_token(token, settings)
