#!/usr/bin/env python
"""Find out where a wrong Content-Type is coming from.

    SUPABASE_URL=https://<ref>.supabase.co \
    SUPABASE_SERVICE_KEY=<service_role> \
    python scripts/diagnose_content_type.py [deployment-id]

There are three distinct places the type can be wrong, and they need different
fixes. Guessing between them is what makes this bug expensive, so this asks all
three:

  1. what we SEND      - a live upload to a scratch key, header captured locally
  2. what Storage KEEPS - the object row's metadata.mimetype
  3. what the CDN SERVES - a HEAD on the public URL

  1 wrong -> the bug is in app/supabase.py
  1 ok, 2 wrong -> Storage rejected or overrode the type. Check the bucket's
                   allowed_mime_types; a restricted bucket silently coerces.
  2 ok, 3 wrong -> a cached CDN response. Our objects are sent with
                   `max-age=31536000, immutable`, so a response cached once is
                   cached for a year. New deploys get new keys and dodge it;
                   the stale URL never recovers on its own.

Nothing here writes to a real deployment: the scratch object is uploaded under
`_diagnostics/` and deleted before exit.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import httpx

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BUCKET = os.environ.get("SUPABASE_BUCKET", "sites")

EXPECTED = "text/html; charset=utf-8"
GREEN, RED, YELLOW, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def verdict(ok: bool, text: str) -> str:
    return "%s%s%s" % (GREEN if ok else RED, text, OFF)


async def main() -> int:
    if not URL or not KEY:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_KEY.", file=sys.stderr)
        return 2

    headers = {"apikey": KEY, "Authorization": "Bearer " + KEY}
    scratch = "_diagnostics/%s/index.html" % uuid.uuid4().hex[:8]
    failures = 0

    async with httpx.AsyncClient(base_url=URL, timeout=30.0, headers=headers) as client:
        # 1. what we send ---------------------------------------------------
        print("1. uploading a scratch object with Content-Type: %s" % EXPECTED)
        response = await client.post(
            "/storage/v1/object/%s/%s" % (BUCKET, scratch),
            content=b"<!doctype html><h1>diagnostic</h1>",
            headers={
                "Content-Type": EXPECTED,
                "x-upsert": "true",
                "cache-control": "public, max-age=31536000, immutable",
            },
        )
        print("   upload -> %s" % response.status_code)
        if response.status_code >= 300:
            print("   %s" % verdict(False, response.text[:300]))
            return 1

        try:
            # 2. what Storage kept -------------------------------------------
            prefix, _, name = scratch.rpartition("/")
            listing = await client.post(
                "/storage/v1/object/list/" + BUCKET,
                json={"prefix": prefix, "limit": 100},
                headers={"Content-Type": "application/json"},
            )
            stored = None
            for item in listing.json() if listing.status_code == 200 else []:
                if item.get("name") == name:
                    stored = (item.get("metadata") or {}).get("mimetype")
            ok_stored = stored == EXPECTED
            print("\n2. Storage metadata.mimetype: %s" % verdict(ok_stored, str(stored)))
            if not ok_stored:
                failures += 1
                print(
                    "   %sStorage did not keep the type we sent. Check the bucket's\n"
                    "   allowed_mime_types - a restricted bucket coerces silently.%s"
                    % (YELLOW, OFF)
                )

            # 3. what the CDN serves -----------------------------------------
            public = await client.head(
                "/storage/v1/object/public/%s/%s" % (BUCKET, scratch)
            )
            served = public.headers.get("content-type")
            ok_served = (served or "").split(";")[0].strip() == "text/html"
            print("\n3. public URL Content-Type:   %s" % verdict(ok_served, str(served)))
            if not ok_served:
                failures += 1
        finally:
            await client.request(
                "DELETE",
                "/storage/v1/object/" + BUCKET,
                json={"prefixes": [scratch]},
                headers={"Content-Type": "application/json"},
            )

        # A real deployment, if one was named ---------------------------------
        if len(sys.argv) > 1:
            deployment_id = sys.argv[1]
            print("\n4. real deployment %s" % deployment_id)
            listing = await client.post(
                "/storage/v1/object/list/" + BUCKET,
                json={"prefix": deployment_id, "limit": 100},
                headers={"Content-Type": "application/json"},
            )
            rows = listing.json() if listing.status_code == 200 else []
            if not rows:
                print("   %sno objects under that prefix%s" % (YELLOW, OFF))
            for item in rows:
                if item.get("id") is None:
                    continue
                key = "%s/%s" % (deployment_id, item["name"])
                stored = (item.get("metadata") or {}).get("mimetype")
                head = await client.head(
                    "/storage/v1/object/public/%s/%s" % (BUCKET, key)
                )
                served = head.headers.get("content-type")
                agree = (stored or "").split(";")[0] == (served or "").split(";")[0]
                print(
                    "   %-40s stored=%-28s served=%s%s"
                    % (item["name"], stored, served, "" if agree else "  <-- differs")
                )
                if not agree:
                    failures += 1
                    print(
                        "   %sstored and served disagree: that is a cached CDN\n"
                        "   response, not an upload bug.%s" % (YELLOW, OFF)
                    )

    print()
    if failures:
        print(verdict(False, "%d problem(s) found - see the notes above." % failures))
    else:
        print(verdict(True, "Upload, storage and CDN all agree on text/html."))
        print(
            "%sIf a browser still shows plain text, the page being fetched is not\n"
            "this object - check the deployment id in the URL you are testing.%s"
            % (DIM, OFF)
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
