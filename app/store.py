"""Database access. Every PostgREST call in the app goes through here.

We talk to PostgREST with the service_role key, which bypasses RLS. The policies
in db/001_init.sql are the second line of defence (they protect anything that
ever talks to Supabase with a user token, including the Phase 2 dashboard); the
first line is that every function here that reads or writes on behalf of a user
takes an `owner_id` and filters on it. Never add a function that takes an id
from a request and skips that filter.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from typing import Any

from .supabase import SupabaseClient, SupabaseError

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_NON_SLUG = re.compile(r"[^a-z0-9]+")

# Quota accounting bounds. A free-tier user capped at 100 MB cannot get near
# these; they exist so a pathological account cannot turn one upload into an
# unbounded scan.
MAX_PROJECTS = 1000
MAX_DEPLOYMENTS_SCANNED = 5000
PROJECT_ID_BATCH = 100

PROJECT_COLUMNS = "id,name,slug,owner_id,live_deployment_id,created_at"
DEPLOYMENT_COLUMNS = (
    "id,project_id,status,size_bytes,file_count,error,commit_sha,created_at"
)


class Conflict(Exception):
    """A uniqueness constraint rejected the write."""


def slugify(name: str, *, fallback: str = "site") -> str:
    normalised = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = _NON_SLUG.sub("-", normalised.lower()).strip("-")
    slug = slug[:48].strip("-")
    if len(slug) < 3:
        slug = (slug + "-" + fallback).strip("-")[:48]
    return slug


def is_valid_slug(slug: str) -> bool:
    return bool(SLUG_RE.match(slug))


class Store:
    def __init__(self, client: SupabaseClient) -> None:
        self.db = client

    # -- projects ----------------------------------------------------------

    async def list_projects(self, owner_id: str) -> list[dict]:
        return await self.db.select(
            "projects",
            {
                "select": PROJECT_COLUMNS,
                "owner_id": "eq." + owner_id,
                "order": "created_at.desc",
                "limit": "200",
            },
        )

    async def get_project_by_slug(self, slug: str) -> dict | None:
        """Public lookup used by the serving flow. No owner filter by design."""
        rows = await self.db.select(
            "projects", {"select": PROJECT_COLUMNS, "slug": "eq." + slug, "limit": "1"}
        )
        return rows[0] if rows else None

    async def get_owned_project(self, owner_id: str, slug: str) -> dict | None:
        rows = await self.db.select(
            "projects",
            {
                "select": PROJECT_COLUMNS,
                "slug": "eq." + slug,
                "owner_id": "eq." + owner_id,
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def get_owned_project_by_id(self, owner_id: str, project_id: str) -> dict | None:
        rows = await self.db.select(
            "projects",
            {
                "select": PROJECT_COLUMNS,
                "id": "eq." + project_id,
                "owner_id": "eq." + owner_id,
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def create_project(self, owner_id: str, name: str, slug: str | None = None) -> dict:
        base = slug or slugify(name)
        if not is_valid_slug(base):
            raise Conflict("Invalid project slug: " + base)

        candidate = base
        for attempt in range(6):
            try:
                return await self.db.insert(
                    "projects",
                    {"owner_id": owner_id, "name": name[:120], "slug": candidate},
                )
            except SupabaseError as exc:
                if exc.status_code != 409:
                    raise
                if slug is not None:
                    # The caller asked for this exact slug; do not silently move it.
                    raise Conflict("That slug is already taken.") from exc
                candidate = ("%s-%s" % (base[:40], secrets.token_hex(2 + attempt // 2)))[:63]
        raise Conflict("Could not allocate a unique slug.")

    async def set_live_deployment(self, project_id: str, deployment_id: str) -> None:
        await self.db.update(
            "projects", {"id": "eq." + project_id}, {"live_deployment_id": deployment_id}
        )

    async def clear_live_deployment(self, project_id: str) -> None:
        await self.db.update(
            "projects", {"id": "eq." + project_id}, {"live_deployment_id": None}
        )

    async def delete_project(self, owner_id: str, project_id: str) -> None:
        # live_deployment_id references deployments, and deployments reference
        # the project: break the cycle before deleting.
        await self.clear_live_deployment(project_id)
        await self.db.delete(
            "projects", {"id": "eq." + project_id, "owner_id": "eq." + owner_id}
        )

    # -- deployments -------------------------------------------------------

    async def create_deployment(self, project_id: str, commit_sha: str | None) -> dict:
        row: dict[str, Any] = {"project_id": project_id, "status": "pending"}
        if commit_sha:
            row["commit_sha"] = commit_sha[:64]
        return await self.db.insert("deployments", row)

    async def get_deployment(self, deployment_id: str) -> dict | None:
        rows = await self.db.select(
            "deployments",
            {
                "select": DEPLOYMENT_COLUMNS + ",file_paths",
                "id": "eq." + deployment_id,
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def list_deployments(self, project_id: str, limit: int = 50) -> list[dict]:
        return await self.db.select(
            "deployments",
            {
                "select": DEPLOYMENT_COLUMNS,
                "project_id": "eq." + project_id,
                "order": "created_at.desc",
                "limit": str(limit),
            },
        )

    async def mark_deployment_ready(
        self, deployment_id: str, *, size_bytes: int, file_count: int, file_paths: list[str]
    ) -> None:
        patch: dict[str, Any] = {
            "status": "ready",
            "size_bytes": size_bytes,
            "file_count": file_count,
            "error": None,
            "file_paths": file_paths,
        }
        try:
            await self.db.update("deployments", {"id": "eq." + deployment_id}, patch)
        except SupabaseError:
            # db/002_file_manifest.sql not applied: fall back to the spec schema.
            patch.pop("file_paths")
            await self.db.update("deployments", {"id": "eq." + deployment_id}, patch)

    async def mark_deployment_failed(self, deployment_id: str, error: str) -> None:
        await self.db.update(
            "deployments",
            {"id": "eq." + deployment_id},
            {"status": "failed", "error": error[:500]},
        )

    # -- quota -------------------------------------------------------------

    async def user_bytes_used(self, owner_id: str) -> int:
        """Bytes this user currently occupies in Storage.

        Counts everything that is not `failed`: a failed deployment has already
        had its objects removed, anything else still owns bytes.

        Two plain queries rather than one embedded join. `projects!inner(...)`
        looks tidier but it is ambiguous: there are two foreign keys between
        these tables - `deployments.project_id -> projects.id` and
        `projects.live_deployment_id -> deployments.id` - so PostgREST cannot
        tell which relationship the embed means and answers `300 Multiple
        Choices`. Naming the constraint would disambiguate it, at the cost of
        hard-coding a database identifier into application code that then breaks
        silently if the constraint is ever renamed. Two queries have no such
        coupling.
        """
        projects = await self.db.select(
            "projects",
            {"select": "id", "owner_id": "eq." + owner_id, "limit": str(MAX_PROJECTS)},
        )
        project_ids = [row["id"] for row in projects if row.get("id")]
        if not project_ids:
            return 0

        total = 0
        # `in.(...)` goes in the query string, so chunk it rather than risk a
        # URL long enough for PostgREST or an intermediary to reject.
        for start in range(0, len(project_ids), PROJECT_ID_BATCH):
            batch = project_ids[start : start + PROJECT_ID_BATCH]
            rows = await self.db.select(
                "deployments",
                {
                    "select": "size_bytes",
                    "project_id": "in.(%s)" % ",".join(batch),
                    "status": "neq.failed",
                    "limit": str(MAX_DEPLOYMENTS_SCANNED),
                },
            )
            total += sum(int(row.get("size_bytes") or 0) for row in rows)
        return total
