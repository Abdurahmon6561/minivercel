"""Token verification. Everything here must end in 401."""

from __future__ import annotations

import dataclasses
import os
import time

import jwt
import pytest

from app.config import get_settings
from app.main import app

from .conftest import USER_ID, make_token, make_zip

SECRET = os.environ["SUPABASE_JWT_SECRET"]


def encode(claims: dict, key: str = SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


BASE_CLAIMS = {
    "sub": USER_ID,
    "aud": "authenticated",
    "role": "authenticated",
    "exp": int(time.time()) + 3600,
}


async def probe(client, token: str | None):
    headers = {"Authorization": "Bearer " + token} if token else {}
    return await client.get("/api/projects", headers=headers)


async def test_valid_token_is_accepted(client):
    assert (await probe(client, make_token())).status_code == 200


@pytest.mark.parametrize(
    "name, token_factory",
    [
        ("expired", lambda: encode({**BASE_CLAIMS, "exp": int(time.time()) - 60})),
        ("wrong signature", lambda: encode(BASE_CLAIMS, key="a-different-secret-entirely")),
        ("wrong audience", lambda: encode({**BASE_CLAIMS, "aud": "anon"})),
        ("no subject", lambda: encode({k: v for k, v in BASE_CLAIMS.items() if k != "sub"})),
        ("no expiry", lambda: encode({k: v for k, v in BASE_CLAIMS.items() if k != "exp"})),
        ("not a jwt", lambda: "just-some-string"),
        ("empty", lambda: "."),
    ],
)
async def test_bad_tokens_are_rejected(client, name, token_factory):
    response = await probe(client, token_factory())
    assert response.status_code == 401, name


async def test_alg_none_is_rejected(client):
    """The classic: re-sign with `alg: none` and drop the signature."""
    forged = jwt.encode(BASE_CLAIMS, key="", algorithm="none")
    assert (await probe(client, forged)).status_code == 401


async def test_hs256_is_rejected_when_no_shared_secret_is_configured(client):
    """With asymmetric signing keys, an HS256 token is an attacker's forgery."""
    without_secret = dataclasses.replace(get_settings(), supabase_jwt_secret="")
    app.dependency_overrides[get_settings] = lambda: without_secret
    try:
        assert (await probe(client, make_token())).status_code == 401
    finally:
        app.dependency_overrides.pop(get_settings, None)


async def test_missing_and_malformed_authorization_headers(client):
    assert (await probe(client, None)).status_code == 401
    assert (
        await client.get("/api/projects", headers={"Authorization": make_token()})
    ).status_code == 401
    assert (
        await client.get(
            "/api/projects", headers={"Authorization": "Basic " + make_token()}
        )
    ).status_code == 401
    assert (
        await client.get("/api/projects", headers={"Authorization": "Bearer "})
    ).status_code == 401


async def test_401_responses_advertise_bearer(client):
    response = await probe(client, None)
    assert response.headers["www-authenticate"] == "Bearer"


async def test_every_write_endpoint_requires_a_token(client):
    assert (await client.get("/api/projects")).status_code == 401
    assert (await client.post("/api/projects", json={"name": "x"})).status_code == 401
    assert (await client.delete("/api/projects/demo")).status_code == 401
    assert (
        await client.post(
            "/api/deployments",
            files={"file": ("s.zip", make_zip({"index.html": "x"}), "application/zip")},
        )
    ).status_code == 401
