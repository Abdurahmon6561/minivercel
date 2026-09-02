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
        if expected == "null":
            expected_value = None
        else:
            expected_value = expected
        if op == "eq":
            return str(value) == str(expected_value) if value is not None else expected_value is None
        if op == "neq":
            return not (str(value) == str(expected_value) if value is not None else expected_value is None)
        raise AssertionError("unsupported operator: " + op)

    def _parent(self, row: dict) -> dict | None:
        return next(
            (p for p in self.tables["projects"] if p["id"] == row.get("project_id")), None
        )

    # -- PostgREST ---------------------------------------------------------

    async def select(self, table: str, params: dict) -> list[dict]:
        rows = list(self.tables[table])
        reserved = {"select", "order", "limit", "offset"}

        for key, predicate in params.items():
            if key in reserved:
                continue
            if "." in key:  # embedded filter, e.g. projects.owner_id
                _, _, column = key.partition(".")
                rows = [
                    row
                    for row in rows
                    if (self._parent(row) or {}) and self._test((self._parent(row) or {}).get(column), predicate)
                ]
            else:
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
