"""Build-time environment variables: /api/projects/{slug}/env.

The two properties worth testing here are not the CRUD - they are that the
plaintext never comes back out, and that the row on disk is ciphertext. Both
are asserted against the fake backend's raw table rather than through the API,
because an endpoint that returned the value would still pass a test that only
read the endpoint.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.crypto import decrypt

from .conftest import USER_ID, auth_headers, deploy, make_zip

OTHER_USER = "22222222-2222-4222-8222-222222222222"

pytestmark = pytest.mark.anyio


async def make_project(client, slug: str = "demo", subject: str = USER_ID):
    response = await deploy(
        client, make_zip({"index.html": "<h1>hi</h1>"}), slug=slug, subject=subject
    )
    assert response.status_code == 201, response.text
    return response.json()


async def add_var(client, slug, key, value, subject: str = USER_ID):
    return await client.post(
        f"/api/projects/{slug}/env",
        headers=auth_headers(subject),
        json={"key": key, "value": value},
    )


# -- happy path ----------------------------------------------------------------


async def test_create_list_update_delete(client, supabase):
    await make_project(client)

    created = await add_var(client, "demo", "API_TOKEN", "sk-live-123")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["key"] == "API_TOKEN"
    var_id = body["id"]

    listed = await client.get("/api/projects/demo/env", headers=auth_headers())
    assert listed.status_code == 200
    assert [v["key"] for v in listed.json()] == ["API_TOKEN"]

    updated = await client.patch(
        f"/api/projects/demo/env/{var_id}",
        headers=auth_headers(),
        json={"value": "sk-live-456"},
    )
    assert updated.status_code == 200
    stored = supabase.tables["project_env_vars"][0]
    assert decrypt(stored["value_encrypted"], get_settings()) == "sk-live-456"

    removed = await client.delete(
        f"/api/projects/demo/env/{var_id}", headers=auth_headers()
    )
    assert removed.status_code == 204
    assert supabase.tables["project_env_vars"] == []


async def test_list_is_sorted_and_empty_by_default(client):
    await make_project(client)

    empty = await client.get("/api/projects/demo/env", headers=auth_headers())
    assert empty.status_code == 200
    assert empty.json() == []

    for key in ("ZULU", "ALPHA", "MIKE"):
        assert (await add_var(client, "demo", key, "x")).status_code == 201

    listed = await client.get("/api/projects/demo/env", headers=auth_headers())
    assert [v["key"] for v in listed.json()] == ["ALPHA", "MIKE", "ZULU"]


# -- the value never comes back ------------------------------------------------


async def test_value_is_masked_everywhere_and_never_returned(client):
    await make_project(client)
    secret = "super-secret-value"

    created = await add_var(client, "demo", "API_TOKEN", secret)
    listed = await client.get("/api/projects/demo/env", headers=auth_headers())
    updated = await client.patch(
        f"/api/projects/demo/env/{created.json()['id']}",
        headers=auth_headers(),
        json={"value": secret},
    )

    for response in (created, listed, updated):
        # Neither the plaintext nor the ciphertext appears anywhere in the body.
        assert secret not in response.text
        assert "value_encrypted" not in response.text

    for body in (created.json(), listed.json()[0], updated.json()):
        # First two characters as a disambiguating hint, then a fixed run of
        # dots that says nothing about the real length.
        assert body["value_masked"] == "su••••••••"
        assert set(body) == {"id", "key", "value_masked", "created_at", "updated_at"}


@pytest.mark.parametrize("value", ["a", "short", "12345"])
async def test_short_values_are_masked_whole(client, value):
    """Two characters of a five-character secret is not a hint, it is a leak."""
    await make_project(client)
    created = await add_var(client, "demo", "PIN", value)
    assert created.json()["value_masked"] == "••••••••"


async def test_mask_does_not_leak_length(client):
    await make_project(client)
    short = await add_var(client, "demo", "SHORT_ONE", "abcdef")
    long = await add_var(client, "demo", "LONG_ONE", "abcdef" + "x" * 500)
    # Same width regardless of what is behind it.
    assert len(short.json()["value_masked"]) == len(long.json()["value_masked"])


async def test_list_still_renders_after_the_key_is_rotated(client, override_settings):
    """A rotated key must not turn the page into a 500.

    The values become unreadable to us as well, and the only way out is for the
    user to re-enter them - which needs the list of keys to be visible.
    """
    await make_project(client)
    assert (await add_var(client, "demo", "API_TOKEN", "secret-value")).status_code == 201

    override_settings(github_token_key="Ck9pkjaWkKI9ZMlUEg8kzQZbfmBAmt2LR1UPRWCM3Xk=")
    listed = await client.get("/api/projects/demo/env", headers=auth_headers())
    assert listed.status_code == 200
    assert listed.json()[0]["key"] == "API_TOKEN"
    assert listed.json()[0]["value_masked"] == "••••••••"


async def test_value_is_encrypted_at_rest(client, supabase):
    """The row on disk is ciphertext, decryptable only with GITHUB_TOKEN_KEY."""
    await make_project(client)
    secret = "sk-live-plaintext-canary"
    await add_var(client, "demo", "API_TOKEN", secret)

    stored = supabase.tables["project_env_vars"][0]
    assert stored["value_encrypted"] != secret
    assert secret not in stored["value_encrypted"]
    # Fernet tokens are versioned and start with 0x80 -> "gAAAAA" in base64url.
    assert stored["value_encrypted"].startswith("gAAAAA")
    assert decrypt(stored["value_encrypted"], get_settings()) == secret


async def test_writing_is_refused_when_the_key_is_missing(client, override_settings):
    """Fail closed, exactly as storing a GitHub token does."""
    await make_project(client)
    override_settings(github_token_key="")

    refused = await add_var(client, "demo", "API_TOKEN", "value")
    assert refused.status_code == 503
    assert "not configured" in refused.json()["detail"]


# -- key validation ------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "lowercase",
        "Mixed_Case",
        "9LEADING_DIGIT",
        "HAS-HYPHEN",
        "HAS SPACE",
        "HAS.DOT",
        "",
        "A" * 65,
    ],
)
async def test_rejects_bad_key_format(client, key):
    await make_project(client)
    response = await add_var(client, "demo", key, "value")
    assert response.status_code == 422, f"{key!r} should have been rejected"


@pytest.mark.parametrize("key", ["A", "_PRIVATE", "API_TOKEN", "PORT_8080", "A" * 64])
async def test_accepts_valid_keys(client, key):
    await make_project(client)
    assert (await add_var(client, "demo", key, "value")).status_code == 201


async def test_rejects_duplicate_key_on_the_same_project(client):
    await make_project(client)
    assert (await add_var(client, "demo", "API_TOKEN", "one")).status_code == 201

    duplicate = await add_var(client, "demo", "API_TOKEN", "two")
    assert duplicate.status_code == 409
    assert "already set" in duplicate.json()["detail"]


async def test_the_same_key_on_two_projects_is_fine(client):
    await make_project(client, slug="alpha")
    await make_project(client, slug="beta")

    assert (await add_var(client, "alpha", "API_TOKEN", "one")).status_code == 201
    assert (await add_var(client, "beta", "API_TOKEN", "two")).status_code == 201


# -- ownership -----------------------------------------------------------------


async def test_another_user_cannot_see_or_touch_the_vars(client, supabase):
    await make_project(client, slug="mine")
    created = await add_var(client, "mine", "API_TOKEN", "secret")
    var_id = created.json()["id"]
    theirs = auth_headers(OTHER_USER)

    listed = await client.get("/api/projects/mine/env", headers=theirs)
    assert listed.status_code == 404

    added = await add_var(client, "mine", "OTHER", "x", subject=OTHER_USER)
    assert added.status_code == 404

    patched = await client.patch(
        f"/api/projects/mine/env/{var_id}", headers=theirs, json={"value": "hijacked"}
    )
    assert patched.status_code == 404

    deleted = await client.delete(f"/api/projects/mine/env/{var_id}", headers=theirs)
    assert deleted.status_code == 404

    # Nothing was changed by any of the above.
    stored = supabase.tables["project_env_vars"]
    assert len(stored) == 1
    assert decrypt(stored[0]["value_encrypted"], get_settings()) == "secret"


async def test_a_var_id_from_another_project_is_not_reachable(client):
    """Scoping by id alone would let one project's id address another's row."""
    await make_project(client, slug="alpha")
    await make_project(client, slug="beta")
    created = await add_var(client, "alpha", "API_TOKEN", "secret")
    var_id = created.json()["id"]

    patched = await client.patch(
        f"/api/projects/beta/env/{var_id}", headers=auth_headers(), json={"value": "x"}
    )
    assert patched.status_code == 404

    deleted = await client.delete(
        f"/api/projects/beta/env/{var_id}", headers=auth_headers()
    )
    assert deleted.status_code == 404


async def test_unknown_project_and_unknown_var(client):
    await make_project(client)

    assert (
        await client.get("/api/projects/nope/env", headers=auth_headers())
    ).status_code == 404

    missing = await client.patch(
        "/api/projects/demo/env/11111111-1111-4111-8111-111111111111",
        headers=auth_headers(),
        json={"value": "x"},
    )
    assert missing.status_code == 404


async def test_requires_authentication(client):
    await make_project(client)
    assert (await client.get("/api/projects/demo/env")).status_code == 401
    assert (
        await client.post("/api/projects/demo/env", json={"key": "A", "value": "b"})
    ).status_code == 401
