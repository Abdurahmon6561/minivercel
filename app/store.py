"""Database access. Every PostgREST call in the app goes through here.

We talk to PostgREST with the service_role key, which bypasses RLS. The policies
in db/001_init.sql are the second line of defence (they protect anything that
ever talks to Supabase with a user token, including the Phase 2 dashboard); the
first line is that every function here that reads or writes on behalf of a user
takes an `owner_id` and filters on it. Never add a function that takes an id
from a request and skips that filter.
"""

from __future__ import annotations

import logging
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from .naming import generate_slug, is_reserved
from .supabase import SupabaseClient, SupabaseError

log = logging.getLogger("minivercel.store")

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_NON_SLUG = re.compile(r"[^a-z0-9]+")

# Quota accounting bounds. A free-tier user capped at 100 MB cannot get near
# these; they exist so a pathological account cannot turn one upload into an
# unbounded scan.
MAX_PROJECTS = 1000
MAX_DEPLOYMENTS_SCANNED = 5000
PROJECT_ID_BATCH = 100

PROJECT_COLUMNS = (
    "id,name,slug,owner_id,live_deployment_id,created_at,"
    "repo_full_name,repo_branch,webhook_id,webhook_secret,auto_deploy_enabled,"
    "builds_enabled,build_command,output_dir,deploy_token_sha256,"
    "last_webhook_at,last_webhook_status,last_webhook_detail,last_webhook_sha"
)
DEPLOYMENT_COLUMNS = (
    "id,project_id,status,size_bytes,file_count,error,commit_sha,created_at"
)
#: `build_log_at` is selected alongside the columns above so a list can say
#: whether a log exists without carrying every log. `build_log` itself is only
#: ever fetched one deployment at a time.
DEPLOYMENT_COLUMNS_WITH_LOG = DEPLOYMENT_COLUMNS + ",build_log_at"

# The tail is what matters: a build fails at the end. 200 lines is SPEC-stated;
# the byte cap is the backstop for a single line of minified nonsense.
BUILD_LOG_MAX_LINES = 200
BUILD_LOG_MAX_BYTES = 64 * 1024


class Conflict(Exception):
    """A uniqueness constraint rejected the write."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(name: str, *, fallback: str = "site") -> str:
    normalised = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = _NON_SLUG.sub("-", normalised.lower()).strip("-")
    slug = slug[:48].strip("-")
    if len(slug) < 3:
        slug = (slug + "-" + fallback).strip("-")[:48]
    if is_reserved(slug):
        # A repository called `docs` or `app` is ordinary; taking that slug is
        # not. Give it a generated one instead of refusing the import.
        return generate_slug()
    return slug


def is_valid_slug(slug: str) -> bool:
    """Shape, and then the reserved list (AUTODEPLOY.md section 2).

    Reserved words are rejected rather than silently rewritten: someone asking
    for `admin` should be told no, not handed `admin-3f2a` and left wondering.
    """
    return bool(SLUG_RE.match(slug)) and not is_reserved(slug)


def truncate_build_log(text: str) -> str:
    """Keep the tail: the last BUILD_LOG_MAX_LINES lines, then a byte cap.

    A build fails at the end, so the head of the log is the part nobody needs.
    The byte cap runs second because 200 lines of minified bundler output can
    still be megabytes, and this column lives in a 500 MB database.
    """
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    tail = "\n".join(normalised.split("\n")[-BUILD_LOG_MAX_LINES:]).strip("\n")

    encoded = tail.encode("utf-8", "replace")
    if len(encoded) <= BUILD_LOG_MAX_BYTES:
        return tail
    # Cut from the front and let the decoder drop a partial leading character.
    clipped = encoded[-BUILD_LOG_MAX_BYTES:].decode("utf-8", "ignore")
    return "[log truncated]\n" + clipped


class Store:
    def __init__(self, client: SupabaseClient) -> None:
        self.db = client
        #: Set false the first time PostgREST rejects `build_log_at`, i.e. when
        #: db/006_phase5.sql has not been applied. Everything else keeps
        #: working; only build logs are unavailable.
        self._supports_build_log = True

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
        """Newest first. Carries `build_log_at`, never `build_log` itself.

        The dashboard needs to know *whether* a deployment has a log in order to
        render a collapsed disclosure; it fetches the text only when someone
        opens one. Selecting `build_log` here would put fifty build logs on the
        wire to render fifty triangles.
        """
        params = {
            "project_id": "eq." + project_id,
            "order": "created_at.desc,id.desc",
            "limit": str(limit),
        }
        if self._supports_build_log:
            try:
                return await self.db.select(
                    "deployments", {**params, "select": DEPLOYMENT_COLUMNS_WITH_LOG}
                )
            except SupabaseError:
                # db/006_phase5.sql not applied. Say so once, then stop asking.
                self._supports_build_log = False
                log.warning(
                    "deployments.build_log_at is missing; build logs are "
                    "disabled until db/006_phase5.sql is applied"
                )
        return await self.db.select(
            "deployments", {**params, "select": DEPLOYMENT_COLUMNS}
        )

    async def delete_deployment(self, deployment_id: str) -> None:
        """Remove one deployment row.

        Storage objects are NOT touched here and must already be gone: Postgres
        knows nothing about the bucket, so a row deleted first is a set of keys
        nobody can ever enumerate again (AUTODEPLOY.md section 7). Every caller
        deletes objects first - see app/gc.py.
        """
        await self.db.delete("deployments", {"id": "eq." + deployment_id})

    async def set_build_log(self, deployment_id: str, text: str) -> bool:
        """Attach the tail of a build log. False if the column does not exist."""
        if not self._supports_build_log:
            return False
        try:
            await self.db.update(
                "deployments",
                {"id": "eq." + deployment_id},
                {"build_log": truncate_build_log(text), "build_log_at": _now_iso()},
            )
        except SupabaseError:
            self._supports_build_log = False
            log.warning(
                "could not store a build log; apply db/006_phase5.sql to enable them"
            )
            return False
        return True

    async def get_build_log(self, deployment_id: str) -> dict | None:
        """The stored log for one deployment, or None if there is none."""
        if not self._supports_build_log:
            return None
        try:
            rows = await self.db.select(
                "deployments",
                {
                    "select": "id,build_log,build_log_at",
                    "id": "eq." + deployment_id,
                    "limit": "1",
                },
            )
        except SupabaseError:
            self._supports_build_log = False
            return None
        if not rows or not rows[0].get("build_log"):
            return None
        return rows[0]

    async def create_failed_deployment(
        self, project_id: str, *, commit_sha: str | None, error: str
    ) -> dict:
        """A deployment that failed before it ever reached us.

        A GitHub Actions build that dies during `npm run build` never POSTs a
        zip, so without this there is no row - and the dashboard shows the last
        successful deploy as if nothing had happened. The row owns no storage
        objects and, being `failed`, counts nothing against the quota.
        """
        row: dict[str, Any] = {
            "project_id": project_id,
            "status": "failed",
            "error": error[:500],
        }
        if commit_sha:
            row["commit_sha"] = commit_sha[:64]
        return await self.db.insert("deployments", row)

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

    async def latest_deployment_per_project(
        self, project_ids: list[str]
    ) -> dict[str, dict]:
        """Newest deployment for each project, in two queries not N+1.

        The dashboard's project list needs a status dot and a "last deployed"
        time per row. Asking per project would be one round-trip per row on a
        0.1 CPU dyno; instead pull them all, newest first, and keep the first
        seen for each project.
        """
        if not project_ids:
            return {}

        latest: dict[str, dict] = {}
        for start in range(0, len(project_ids), PROJECT_ID_BATCH):
            batch = project_ids[start : start + PROJECT_ID_BATCH]
            params = {
                "project_id": "in.(%s)" % ",".join(batch),
                # id breaks a created_at tie, so "newest" is never decided
                # by row order coming back from PostgREST.
                "order": "created_at.desc,id.desc",
                "limit": str(MAX_DEPLOYMENTS_SCANNED),
            }
            # Same columns as list_deployments, including `build_log_at`, so
            # `has_build_log` means the same thing on the project list as it
            # does on the project page rather than being silently false there.
            rows = None
            if self._supports_build_log:
                try:
                    rows = await self.db.select(
                        "deployments", {**params, "select": DEPLOYMENT_COLUMNS_WITH_LOG}
                    )
                except SupabaseError:
                    self._supports_build_log = False
            if rows is None:
                rows = await self.db.select(
                    "deployments", {**params, "select": DEPLOYMENT_COLUMNS}
                )
            for row in rows:
                latest.setdefault(row["project_id"], row)
        return latest

    async def reap_stuck_pending(self, older_than_minutes: int = 10) -> int:
        """Fail deployments left `pending` by a worker that died mid-deploy.

        Render restarts the dyno on deploy, on spin-down, and on OOM. A request
        interrupted between "insert pending" and "mark ready" leaves a row that
        will never resolve, and the dashboard shows an amber dot for ever.
        Nothing is retried here: the objects, if any, were never marked live, so
        the previous deployment is still serving.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        rows = await self.db.update(
            "deployments",
            {"status": "eq.pending", "created_at": "lt." + cutoff.isoformat()},
            {"status": "failed", "error": "worker restarted"},
        )
        return len(rows)

    async def all_projects(self, limit: int = MAX_PROJECTS) -> list[dict]:
        """Every project, for the garbage-collection sweep.

        The only function here that is deliberately not scoped to an owner. It
        is reachable from exactly one place - the ADMIN_TOKEN-guarded sweep in
        app/routers/admin.py - and it returns rows for deletion accounting, not
        for any response body.
        """
        return await self.db.select(
            "projects",
            {
                "select": "id,slug,owner_id,live_deployment_id",
                "order": "created_at.asc",
                "limit": str(limit),
            },
        )

    # -- github integration -------------------------------------------------

    async def set_project_repo(
        self,
        project_id: str,
        *,
        repo_full_name: str,
        repo_branch: str,
        webhook_id: int | None,
        webhook_secret: str | None,
    ) -> None:
        await self.db.update(
            "projects",
            {"id": "eq." + project_id},
            {
                "repo_full_name": repo_full_name,
                "repo_branch": repo_branch,
                "webhook_id": webhook_id,
                "webhook_secret": webhook_secret,
            },
        )

    async def projects_for_repo(self, repo_full_name: str) -> list[dict]:
        """Every project wired to this repository.

        More than one is legitimate: two users can import the same public repo,
        and each has its own webhook secret. The caller verifies the signature
        against each candidate and takes the one that matches.
        """
        return await self.db.select(
            "projects",
            {
                "select": PROJECT_COLUMNS,
                "repo_full_name": "eq." + repo_full_name,
                "limit": "50",
            },
        )

    async def update_project_settings(self, project_id: str, patch: dict) -> dict | None:
        rows = await self.db.update("projects", {"id": "eq." + project_id}, patch)
        return rows[0] if rows else None

    async def record_webhook_delivery(
        self, project_id: str, *, status: str, detail: str, sha: str | None = None
    ) -> None:
        """So the dashboard can answer "did my push arrive?" honestly."""
        await self.db.update(
            "projects",
            {"id": "eq." + project_id},
            {
                "last_webhook_at": _now_iso(),
                "last_webhook_status": status[:32],
                "last_webhook_detail": detail[:300],
                "last_webhook_sha": (sha or "")[:64] or None,
            },
        )

    # -- deploy tokens ------------------------------------------------------

    async def project_for_deploy_token(self, token_sha256: str) -> dict | None:
        rows = await self.db.select(
            "projects",
            {
                "select": PROJECT_COLUMNS,
                "deploy_token_sha256": "eq." + token_sha256,
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def set_deploy_token(self, project_id: str, token_sha256: str | None) -> None:
        await self.db.update(
            "projects", {"id": "eq." + project_id}, {"deploy_token_sha256": token_sha256}
        )

    # -- github tokens -----------------------------------------------------

    async def save_github_token(
        self,
        user_id: str,
        encrypted_token: str,
        *,
        scopes: str | None,
        github_login: str | None,
    ) -> None:
        """Upsert. PostgREST does this with Prefer: resolution=merge-duplicates."""
        await self.db.upsert(
            "github_tokens",
            {
                "user_id": user_id,
                "encrypted_token": encrypted_token,
                "scopes": scopes,
                "github_login": github_login,
                "updated_at": _now_iso(),
            },
            on_conflict="user_id",
        )

    async def get_github_token_row(self, user_id: str) -> dict | None:
        rows = await self.db.select(
            "github_tokens",
            {
                "select": "user_id,encrypted_token,scopes,github_login,updated_at",
                "user_id": "eq." + user_id,
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def delete_github_token(self, user_id: str) -> None:
        await self.db.delete("github_tokens", {"user_id": "eq." + user_id})

    # -- project environment variables -------------------------------------
    #
    # Values arrive here already encrypted (app/crypto.py) and leave the same
    # way: this layer never sees plaintext, exactly as with github_tokens.
    # Callers are responsible for having resolved the project through
    # `get_owned_project` first - nothing below re-checks ownership.

    ENV_VAR_COLUMNS = "id,project_id,key,value_encrypted,created_at,updated_at"

    async def list_env_vars(self, project_id: str) -> list[dict]:
        return await self.db.select(
            "project_env_vars",
            {
                "select": self.ENV_VAR_COLUMNS,
                "project_id": "eq." + project_id,
                "order": "key.asc",
            },
        )

    async def get_env_var(self, project_id: str, var_id: str) -> dict | None:
        """Scoped by project_id as well as id, so a var id from one project
        cannot be used to reach into another."""
        rows = await self.db.select(
            "project_env_vars",
            {
                "select": self.ENV_VAR_COLUMNS,
                "id": "eq." + var_id,
                "project_id": "eq." + project_id,
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def create_env_var(
        self, project_id: str, key: str, value_encrypted: str
    ) -> dict:
        """Raises Conflict if the key already exists on this project.

        The unique index on (project_id, key) is what decides that, not a
        read-then-write here: two concurrent POSTs of the same key would both
        pass a pre-check and only the index would stop the second.
        """
        now = _now_iso()
        try:
            return await self.db.insert(
                "project_env_vars",
                {
                    "project_id": project_id,
                    "key": key,
                    "value_encrypted": value_encrypted,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        except SupabaseError as exc:
            if exc.status_code == 409 or "duplicate key" in str(exc).lower():
                raise Conflict(f"{key} is already set on this project.") from exc
            raise

    async def update_env_var(
        self, project_id: str, var_id: str, value_encrypted: str
    ) -> dict | None:
        """Value only. The key is immutable: renaming one is deleting it and
        creating another, and pretending otherwise hides that the old name
        stops being injected."""
        rows = await self.db.update(
            "project_env_vars",
            {"id": "eq." + var_id, "project_id": "eq." + project_id},
            {"value_encrypted": value_encrypted, "updated_at": _now_iso()},
        )
        return rows[0] if rows else None

    async def delete_env_var(self, project_id: str, var_id: str) -> None:
        await self.db.delete(
            "project_env_vars", {"id": "eq." + var_id, "project_id": "eq." + project_id}
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
