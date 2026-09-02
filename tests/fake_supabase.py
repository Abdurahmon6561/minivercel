"""In-memory stand-in for SupabaseClient.

Implements the slice of PostgREST and Storage that app/store.py actually uses,
including the embedded-filter form (`projects!inner(owner_id)`) that the quota
query depends on. Tests run with no network and no Supabase project.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.supabase import SupabaseError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeSupabase:
    def __init__(self, *, supports_manifest: bool = True) -> None:
        self.bucket = "sites"
        self.supports_manifest = supports_manifest
        self.tables: dict[str, list[dict]] = {"projects": [], "deployments": []}
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.upload_calls: list[tuple[str, str]] = []

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _test(value, predicate: str) -> bool:
        op, _, expected = predicate.partition(".")

        if op == "in":
            members = {
                item.strip().strip('"')
                for item in expected.strip("()").split(",")
                if item.strip()
            }
            return value is not None and str(value) in members

        expected_value = None if expected == "null" else expected
        if op == "eq":
            if value is None:
                return expected_value is None
            return str(value) == str(expected_value)
        if op == "neq":
            if value is None:
                return expected_value is not None
            return str(value) != str(expected_value)
        raise AssertionError("unsupported operator: " + op)

    # -- PostgREST ---------------------------------------------------------

    async def select(self, table: str, params: dict) -> list[dict]:
        rows = list(self.tables[table])
        reserved = {"select", "order", "limit", "offset"}

        # Reproduce the real failure this fake once papered over: `projects` and
        # `deployments` are joined by two foreign keys, so an embed naming only
        # the table is ambiguous and PostgREST answers 300, not rows.
        if "!inner" in str(params.get("select", "")) or any(
            "." in key for key in params if key not in reserved
        ):
            raise SupabaseError(
                "Could not embed because more than one relationship was found",
                300,
            )

        for key, predicate in params.items():
            if key in reserved:
                continue
            rows = [row for row in rows if self._test(row.get(key), predicate)]

        order = params.get("order")
        if order:
            column, _, direction = order.partition(".")
            rows.sort(key=lambda row: row.get(column) or "", reverse=direction == "desc")

        limit = params.get("limit")
        if limit:
            rows = rows[: int(limit)]

        return [dict(row) for row in rows]

    async def insert(self, table: str, row: dict) -> dict:
        record = dict(row)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", _now())

        if table == "projects":
            if any(p["slug"] == record["slug"] for p in self.tables["projects"]):
                raise SupabaseError("duplicate key value violates unique constraint", 409)
            record.setdefault("live_deployment_id", None)
        if table == "deployments":
            record.setdefault("status", "pending")
            record.setdefault("size_bytes", 0)
            record.setdefault("file_count", 0)
            record.setdefault("error", None)
            record.setdefault("commit_sha", None)
            record.setdefault("file_paths", None)

        self.tables[table].append(record)
        return dict(record)

    async def update(self, table: str, params: dict, patch: dict) -> list[dict]:
        if not self.supports_manifest and "file_paths" in patch:
            raise SupabaseError("column deployments.file_paths does not exist", 400)

        updated = []
        for row in self.tables[table]:
            if all(
                self._test(row.get(key), predicate)
                for key, predicate in params.items()
                if key not in {"select", "order", "limit"}
            ):
                row.update(patch)
                updated.append(dict(row))
        return updated

    async def delete(self, table: str, params: dict) -> None:
        keep, removed = [], []
        for row in self.tables[table]:
            if all(
                self._test(row.get(key), predicate) for key, predicate in params.items()
            ):
                removed.append(row)
            else:
                keep.append(row)
        self.tables[table] = keep

        if table == "projects":  # emulate ON DELETE CASCADE
            gone = {row["id"] for row in removed}
            self.tables["deployments"] = [
                row for row in self.tables["deployments"] if row["project_id"] not in gone
            ]

    # -- Storage -----------------------------------------------------------

    def public_url(self, key: str) -> str:
        return "https://fake.supabase.co/storage/v1/object/public/%s/%s" % (
            self.bucket,
            key,
        )

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)
        self.upload_calls.append((key, content_type))

    async def list_prefix(self, prefix: str) -> list[str]:
        head = prefix.rstrip("/") + "/"
        return [key for key in self.objects if key.startswith(head)]

    async def remove(self, keys) -> None:
        for key in list(keys):
            self.objects.pop(key, None)

    async def remove_prefix(self, prefix: str) -> None:
        await self.remove(await self.list_prefix(prefix))

    async def object_exists(self, key: str) -> bool:
        return key in self.objects

    async def aclose(self) -> None:
        return None
