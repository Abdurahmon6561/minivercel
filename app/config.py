"""Runtime configuration, read once at import."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

MB = 1024 * 1024


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc


def _list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_service_key: str
    supabase_bucket: str
    supabase_jwt_secret: str
    supabase_jwt_audience: str
    public_base_url: str
    github_token_key: str
    #: Guards POST /api/admin/gc. Empty disables the endpoint outright rather
    #: than leaving it open - an unset secret must never mean "no check".
    admin_token: str
    # AUTODEPLOY.md section 1: flip these two to move sites onto subdomains.
    url_mode: str
    site_domain: str

    max_deployment_bytes: int
    max_files_per_deployment: int
    max_user_bytes: int
    max_proxy_bytes: int
    serve_rate_limit_per_min: int
    upload_rate_limit_per_hour: int

    cors_origins: list[str] = field(default_factory=list)

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    def require_configured(self) -> None:
        missing = [
            name
            for name, value in (
                ("SUPABASE_URL", self.supabase_url),
                ("SUPABASE_SERVICE_KEY", self.supabase_service_key),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
        supabase_service_key=os.environ.get("SUPABASE_SERVICE_KEY", ""),
        supabase_bucket=os.environ.get("SUPABASE_BUCKET", "sites"),
        supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET", ""),
        supabase_jwt_audience=os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated"),
        public_base_url=os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"),
        url_mode=os.environ.get("URL_MODE", "path").strip().lower(),
        site_domain=os.environ.get("SITE_DOMAIN", "").strip().lstrip(".").rstrip("/"),
        github_token_key=os.environ.get("GITHUB_TOKEN_KEY", ""),
        admin_token=os.environ.get("ADMIN_TOKEN", "").strip(),
        max_deployment_bytes=_int("MAX_DEPLOYMENT_BYTES", 50 * MB),
        max_files_per_deployment=_int("MAX_FILES_PER_DEPLOYMENT", 500),
        max_user_bytes=_int("MAX_USER_BYTES", 100 * MB),
        max_proxy_bytes=_int("MAX_PROXY_BYTES", 5 * MB),
        serve_rate_limit_per_min=_int("SERVE_RATE_LIMIT_PER_MIN", 60),
        upload_rate_limit_per_hour=_int("UPLOAD_RATE_LIMIT_PER_HOUR", 20),
        cors_origins=_list("CORS_ORIGINS", "http://localhost:5173"),
    )
