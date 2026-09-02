from __future__ import annotations

import dataclasses
import io
import os
import time
import zipfile

# Configure before anything imports app.config (its settings are lru_cached).
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "service-role-key-for-tests")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-long-enough-for-hs256-abcdef")
os.environ.setdefault("SUPABASE_BUCKET", "sites")
os.environ.setdefault("PUBLIC_BASE_URL", "https://minivercel.test")
os.environ.setdefault("UPLOAD_RATE_LIMIT_PER_HOUR", "1000")
os.environ.setdefault("SERVE_RATE_LIMIT_PER_MIN", "1000")
os.environ.setdefault(
    "GITHUB_TOKEN_KEY", "aTHZLdgs0oUdF4kXbTb2cCiZ7pdOoGWMU9Hs3sOhSbo="
)
# Without this the CORS middleware is never installed (main.py adds it only when
# CORS_ORIGINS is non-empty), so no test could see a preflight - which is how a
# missing PATCH in allow_methods reached production.
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,https://minivercel.vercel.app")

import httpx  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402

from app import cache, deps  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.store import Store  # noqa: E402

from .fake_supabase import FakeSupabase  # noqa: E402

USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"


def make_token(subject: str = USER_ID, **overrides) -> str:
    claims = {
        "sub": subject,
        "aud": "authenticated",
        "role": "authenticated",
        "email": "dev@example.com",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    claims.update(overrides)
    return jwt.encode(claims, os.environ["SUPABASE_JWT_SECRET"], algorithm="HS256")


def auth_headers(subject: str = USER_ID) -> dict[str, str]:
    return {"Authorization": "Bearer " + make_token(subject)}


def make_zip(files: dict[str, bytes | str], *, compression=zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as zf:
        for name, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            zf.writestr(name, data)
    return buffer.getvalue()


@pytest.fixture
def override_settings():
    """Swap in modified Settings for one test.

    Settings is a frozen dataclass behind an lru_cache, so it cannot be mutated;
    FastAPI's dependency_overrides is the supported seam.
    """

    def apply(**changes):
        replaced = dataclasses.replace(get_settings(), **changes)
        app.dependency_overrides[get_settings] = lambda: replaced
        return replaced

    yield apply
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def supabase() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture(autouse=True)
def wired(supabase: FakeSupabase):
    """Point the app at the in-memory backend and reset all process state."""
    cache.clear_all()
    deps.reset_limiters()
    deps.set_store(Store(supabase))
    yield supabase
    deps.set_store(None)
    cache.clear_all()
    deps.reset_limiters()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client


async def deploy(client, zip_bytes: bytes, *, slug: str = "demo", subject: str = USER_ID, **fields):
    """Helper: POST a zip the way the SPEC.md curl example does."""
    data = {"slug": slug}
    data.update(fields)
    return await client.post(
        "/api/deployments",
        headers=auth_headers(subject),
        files={"file": ("site.zip", zip_bytes, "application/zip")},
        data=data,
    )
