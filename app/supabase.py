"""Thin async Supabase client: PostgREST for rows, Storage for objects.

Deliberately not the `supabase` SDK. We need four verbs and a public URL
builder; a hand-rolled httpx wrapper is smaller, async all the way down, and has
no sync-in-async footguns on a 0.1 CPU dyno.

NON-NEGOTIABLE #4: the service_role key is attached here and nowhere else. It is
never returned to a caller and never logged - `_redact` exists to make sure a
Supabase error body can never carry it back out.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable
from urllib.parse import quote

import httpx

from .config import Settings, get_settings

log = logging.getLogger("minivercel.supabase")

TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=60.0, pool=5.0)


class SupabaseError(RuntimeError):
    """A Supabase call failed. Message is redacted and safe to log."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _encode_key(key: str) -> str:
    """Percent-encode a storage key, preserving the `/` hierarchy."""
    return quote(key, safe="/")


class SupabaseClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.require_configured()
        self._client = httpx.AsyncClient(
            base_url=self.settings.supabase_url,
            timeout=TIMEOUT,
            headers={
                "apikey": self.settings.supabase_service_key,
                "Authorization": "Bearer " + self.settings.supabase_service_key,
            },
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- internals ---------------------------------------------------------

    def _redact(self, text: str) -> str:
        key = self.settings.supabase_service_key
        if key and key in text:
            text = text.replace(key, "[REDACTED]")
        return text[:500]

    def _check(self, response: httpx.Response, what: str) -> httpx.Response:
        """Accept 2xx and nothing else.

        `>= 400` is the tempting version and it is wrong. PostgREST answers an
        ambiguous embed with `300 Multiple Choices` and a body describing the
        candidate relationships - not a row list. Letting that through means the
        caller iterates a JSON object as if it were rows and dies somewhere far
        away with `'str' object has no attribute 'get'`. Any non-2xx is an error
        here, reported with the status and body that explain it.
        """
        if not 200 <= response.status_code < 300:
            detail = self._redact(response.text)
            log.error("%s failed: %s %s", what, response.status_code, detail)
            raise SupabaseError(
                "%s failed (%d): %s" % (what, response.status_code, detail),
                response.status_code,
            )
        return response

    # -- PostgREST ---------------------------------------------------------

    async def select(self, table: str, params: dict[str, Any]) -> list[dict]:
        response = await self._client.get("/rest/v1/" + table, params=params)
        self._check(response, "select " + table)
        return response.json()

    async def insert(self, table: str, row: dict[str, Any]) -> dict:
        response = await self._client.post(
            "/rest/v1/" + table,
            json=row,
            headers={"Prefer": "return=representation", "Content-Type": "application/json"},
        )
        self._check(response, "insert " + table)
        rows = response.json()
        if not rows:
            raise SupabaseError("insert %s returned no row" % table)
        return rows[0]

    async def upsert(
        self, table: str, row: dict[str, Any], *, on_conflict: str
    ) -> dict:
        """Insert, or replace the row that collides on `on_conflict`."""
        response = await self._client.post(
            "/rest/v1/" + table,
            params={"on_conflict": on_conflict},
            json=row,
            headers={
                "Prefer": "return=representation,resolution=merge-duplicates",
                "Content-Type": "application/json",
            },
        )
        self._check(response, "upsert " + table)
        rows = response.json()
        return rows[0] if rows else {}

    async def update(
        self, table: str, params: dict[str, Any], patch: dict[str, Any]
    ) -> list[dict]:
        response = await self._client.patch(
            "/rest/v1/" + table,
            params=params,
            json=patch,
            headers={"Prefer": "return=representation", "Content-Type": "application/json"},
        )
        self._check(response, "update " + table)
        return response.json()

    async def delete(self, table: str, params: dict[str, Any]) -> None:
        response = await self._client.delete("/rest/v1/" + table, params=params)
        self._check(response, "delete " + table)

    # -- Storage -----------------------------------------------------------

    @property
    def bucket(self) -> str:
        return self.settings.supabase_bucket

    def public_url(self, key: str) -> str:
        return "%s/storage/v1/object/public/%s/%s" % (
            self.settings.supabase_url,
            self.bucket,
            _encode_key(key),
        )

    async def upload(self, key: str, data: bytes, content_type: str) -> int:
        """Write one object as a raw binary body.

        Deliberately NOT multipart. With `files=`, httpx builds a
        multipart/form-data envelope and a top-level Content-Type header is
        ignored - Storage reads the per-part type instead, and an unset per-part
        type is how objects end up stored as text/plain. Sending the bytes as
        the body means the request's own Content-Type is the object's type, with
        nothing in between to lose it.

        Returns the response status so callers can log what actually happened.
        """
        response = await self._client.post(
            "/storage/v1/object/%s/%s" % (self.bucket, _encode_key(key)),
            content=data,
            headers={
                "Content-Type": content_type,
                "x-upsert": "true",
                "cache-control": "public, max-age=31536000, immutable",
            },
        )
        # One line per file, at INFO, so Render's log shows what was sent for
        # every object rather than only what failed.
        log.info(
            "upload %s content-type=%s bytes=%d -> %s",
            key,
            content_type,
            len(data),
            response.status_code,
        )
        self._check(response, "upload object")
        return response.status_code

    async def stored_content_type(self, key: str) -> str | None:
        """What Supabase actually serves for this key, via the public URL.

        Answers the question logs cannot: whether the type we sent survived.
        Returns None if the object cannot be reached.
        """
        try:
            response = await self._client.head(
                "/storage/v1/object/public/%s/%s" % (self.bucket, _encode_key(key))
            )
        except httpx.HTTPError as exc:
            log.warning("could not read back %s: %s", key, exc)
            return None
        if response.status_code != 200:
            return None
        return response.headers.get("content-type")

    async def remove_prefix(self, prefix: str) -> None:
        """Delete every object under `prefix/`.

        Storage has no recursive delete, so list then delete by exact key. Used
        to clean up after a failed deployment (SPEC.md step 6).
        """
        keys = await self.list_prefix(prefix)
        if keys:
            await self.remove(keys)

    async def remove(self, keys: Iterable[str]) -> None:
        payload = list(keys)
        if not payload:
            return
        for start in range(0, len(payload), 100):
            response = await self._client.request(
                "DELETE",
                "/storage/v1/object/" + self.bucket,
                json={"prefixes": payload[start : start + 100]},
                headers={"Content-Type": "application/json"},
            )
            self._check(response, "delete objects")

    async def list_prefix(self, prefix: str) -> list[str]:
        """Recursively list object keys under `prefix`.

        The storage list API is one directory level at a time, so this walks.
        Only ever called on cleanup and on the manifest fallback path, both of
        which are rare.
        """
        found: list[str] = []
        queue = [prefix.rstrip("/")]
        guard = 0
        while queue:
            guard += 1
            if guard > 600:  # 500-file cap plus directories; never legitimately hit
                log.warning("list_prefix walk exceeded its guard for %s", prefix)
                break
            current = queue.pop()
            offset = 0
            while True:
                response = await self._client.post(
                    "/storage/v1/object/list/" + self.bucket,
                    json={
                        "prefix": current,
                        "limit": 100,
                        "offset": offset,
                        "sortBy": {"column": "name", "order": "asc"},
                    },
                    headers={"Content-Type": "application/json"},
                )
                self._check(response, "list objects")
                items = response.json()
                if not items:
                    break
                for item in items:
                    name = item.get("name")
                    if not name:
                        continue
                    key = current + "/" + name if current else name
                    # Storage marks pseudo-directories with a null id.
                    if item.get("id") is None:
                        queue.append(key)
                    else:
                        found.append(key)
                if len(items) < 100:
                    break
                offset += len(items)
        return found

    async def open_object_stream(self, key: str) -> httpx.Response:
        """Open a streaming GET on a public object.

        The caller owns the response and MUST `aclose()` it - it holds a
        connection from the pool until then. Used only by the HTML proxy path in
        routers/serve.py; everything else is served by redirect.
        """
        request = self._client.build_request(
            "GET", "/storage/v1/object/public/%s/%s" % (self.bucket, _encode_key(key))
        )
        return await self._client.send(request, stream=True)

    async def object_exists(self, key: str) -> bool:
        response = await self._client.head(
            "/storage/v1/object/public/%s/%s" % (self.bucket, _encode_key(key))
        )
        return response.status_code == 200
