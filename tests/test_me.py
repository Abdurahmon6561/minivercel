"""`/api/me` - identity, quota, and the GitHub provider token.

The token tests carry most of the weight here. A `repo`-scoped GitHub token is
write access to every repository the user can see, so "never leaves the server"
and "never stored in plaintext" both need to be assertions, not intentions.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.config import get_settings
from app.crypto import EncryptionUnavailable, decrypt, encrypt
from app.main import app

from .conftest import OTHER_USER_ID, USER_ID, auth_headers, deploy, make_zip

TOKEN = "gho_16C7e42F292c6912E7710c838347Ae178B4a"


# -- identity and quota -------------------------------------------------------


async def test_me_reports_identity_and_limits(client):
    body = (await client.get("/api/me", headers=auth_headers())).json()
    assert body["id"] == USER_ID
    assert body["email"] == "dev@example.com"
    assert body["usage"]["bytes_limit"] == get_settings().max_user_bytes
    assert body["usage"]["bytes_used"] == 0
    assert body["github"]["connected"] is False


async def test_me_usage_tracks_deployments(client):
    await deploy(client, make_zip({"index.html": "x" * 400}), slug="usage-demo")
    body = (await client.get("/api/me", headers=auth_headers())).json()
    assert body["usage"]["bytes_used"] > 0


async def test_me_requires_auth(client):
    assert (await client.get("/api/me")).status_code == 401


# -- the GitHub provider token ------------------------------------------------


async def test_token_is_stored_encrypted_never_plaintext(client, supabase):
    response = await client.post(
        "/api/me/github-token",
        headers=auth_headers(),
        json={"provider_token": TOKEN, "scopes": "public_repo", "github_login": "octocat"},
    )
    assert response.status_code == 204

    row = supabase.tables["github_tokens"][0]
    assert row["user_id"] == USER_ID
    assert TOKEN not in row["encrypted_token"]
    assert TOKEN not in str(row), "the raw token must not appear anywhere in the row"
    assert decrypt(row["encrypted_token"], get_settings()) == TOKEN


async def test_token_is_never_returned_by_any_endpoint(client):
    await client.post(
        "/api/me/github-token",
        headers=auth_headers(),
        json={"provider_token": TOKEN, "scopes": "public_repo", "github_login": "octocat"},
    )

    for path in ("/api/me", "/api/projects"):
        response = await client.get(path, headers=auth_headers())
        assert TOKEN not in response.text, path


async def test_me_reports_the_connection_without_the_secret(client):
    await client.post(
        "/api/me/github-token",
        headers=auth_headers(),
        json={"provider_token": TOKEN, "scopes": "public_repo", "github_login": "octocat"},
    )
    github = (await client.get("/api/me", headers=auth_headers())).json()["github"]
    assert github == {
        "connected": True,
        "login": "octocat",
        "scopes": "public_repo",
        "updated_at": github["updated_at"],
    }
    assert "token" not in str(github).lower()


async def test_storing_twice_replaces_rather_than_duplicates(client, supabase):
    for token in (TOKEN, "gho_second_token_value_here_padded"):
        response = await client.post(
            "/api/me/github-token",
            headers=auth_headers(),
            json={"provider_token": token, "scopes": "repo"},
        )
        assert response.status_code == 204

    assert len(supabase.tables["github_tokens"]) == 1
    row = supabase.tables["github_tokens"][0]
    assert decrypt(row["encrypted_token"], get_settings()) == "gho_second_token_value_here_padded"
    assert row["scopes"] == "repo"


async def test_tokens_are_per_user(client, supabase):
    await client.post(
        "/api/me/github-token",
        headers=auth_headers(USER_ID),
        json={"provider_token": TOKEN, "scopes": "public_repo"},
    )
    other = await client.get("/api/me", headers=auth_headers(OTHER_USER_ID))
    assert other.json()["github"]["connected"] is False
    assert len(supabase.tables["github_tokens"]) == 1


async def test_token_can_be_disconnected(client, supabase):
    await client.post(
        "/api/me/github-token",
        headers=auth_headers(),
        json={"provider_token": TOKEN, "scopes": "public_repo"},
    )
    assert (
        await client.delete("/api/me/github-token", headers=auth_headers())
    ).status_code == 204
    assert supabase.tables["github_tokens"] == []
    assert (await client.get("/api/me", headers=auth_headers())).json()["github"][
        "connected"
    ] is False


async def test_storing_a_token_requires_auth(client):
    response = await client.post(
        "/api/me/github-token", json={"provider_token": TOKEN}
    )
    assert response.status_code == 401


async def test_refuses_to_store_when_no_encryption_key_is_configured(client, supabase):
    """Fail closed. A missing env var must never mean 'write it in plaintext'."""
    keyless = dataclasses.replace(get_settings(), github_token_key="")
    app.dependency_overrides[get_settings] = lambda: keyless
    try:
        response = await client.post(
            "/api/me/github-token",
            headers=auth_headers(),
            json={"provider_token": TOKEN, "scopes": "repo"},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 503
    assert supabase.tables["github_tokens"] == [], "nothing may be written"
    assert TOKEN not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"provider_token": ""},
        {"provider_token": "short"},
        {"provider_token": "x" * 501},
    ],
)
async def test_malformed_token_payloads_are_rejected(client, payload):
    response = await client.post(
        "/api/me/github-token", headers=auth_headers(), json=payload
    )
    assert response.status_code == 422


# -- the crypto layer itself --------------------------------------------------


def test_encrypt_round_trips():
    settings = get_settings()
    assert decrypt(encrypt(TOKEN, settings), settings) == TOKEN


def test_ciphertext_differs_each_time():
    """Fernet includes a timestamp and IV, so identical input differs."""
    settings = get_settings()
    assert encrypt(TOKEN, settings) != encrypt(TOKEN, settings)


def test_encrypt_without_a_key_raises():
    keyless = dataclasses.replace(get_settings(), github_token_key="")
    with pytest.raises(EncryptionUnavailable, match="GITHUB_TOKEN_KEY"):
        encrypt(TOKEN, keyless)


def test_a_malformed_key_raises_rather_than_silently_working():
    bad = dataclasses.replace(get_settings(), github_token_key="not-a-fernet-key")
    with pytest.raises(EncryptionUnavailable, match="valid Fernet key"):
        encrypt(TOKEN, bad)


def test_decrypting_with_a_rotated_key_is_recoverable_not_fatal():
    settings = get_settings()
    ciphertext = encrypt(TOKEN, settings)
    rotated = dataclasses.replace(
        settings, github_token_key="Ck9pkjaWkKI9ZMlUEg8kzQZbfmBAmt2LR1UPRWCM3Xk="
    )
    with pytest.raises(EncryptionUnavailable, match="reconnect GitHub"):
        decrypt(ciphertext, rotated)
