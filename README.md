# MiniVercel — Phase 1

Upload a zip of static files, get a public URL.

We never execute anything a user gives us. Not Node, not Python, not shell.
Uploads are inert files that get validated, stored, and redirected to. That
restriction is the entire security model — see [SPEC.md](SPEC.md)
"Non-negotiables" before changing anything in [app/](app/).

**Status: Phase 1 complete and tested; not yet deployed.** Deploying needs a
Supabase project and a Render account, which only you can create. The runbook
below is the remaining work, and it is about fifteen minutes. Phases 2–5 are
gated on it by the spec ("Do NOT start Phase 2 until Phase 1 is deployed and
working"), so nothing past Phase 1 has been started.

---

## How it fits together

```
  curl -F file=@site.zip                     browser
          |                                     |
          v                                     v
  POST /api/deployments                GET /s/{slug}/about
          |                                     |
   [ verify JWT ]                        [ rate limit 60/min ]
   [ stream to /tmp, abort at 50 MB ]    [ slug -> project (cached 15s) ]
   [ validate EVERY entry ]              [ resolve via file manifest ]
   [ extract, whitelist content-types ]          |
          |                              css/js/img/font   HTML
          v                                     |            |
  Supabase Storage (public bucket)              v            v
  Supabase Postgres (rows)              307 -> Supabase   streamed
                                          CDN directly    through us
                                        (bytes never      (Supabase
                                         touch us)         would send
                                                           text/plain)
```

Two rules explain most of the design:

- **Never proxy user bytes, except HTML.** Serving is a redirect to Supabase's
  public CDN. The one exception is HTML, which Supabase deliberately serves as
  `text/plain`, so a redirect cannot render a page — see "Known limitations".
- **Never trust the archive.** Every entry is checked *before* extraction, and
  the content-type comes from our own extension whitelist, never from the zip.

## Layout

| Path | What it is |
| --- | --- |
| [app/zipvalidate.py](app/zipvalidate.py) | Archive inspection and safe extraction. The security core. |
| [app/upload_stream.py](app/upload_stream.py) | Streaming multipart receiver that aborts mid-body at the cap. |
| [app/routers/deployments.py](app/routers/deployments.py) | The upload pipeline, one step per SPEC.md step. |
| [app/routers/serve.py](app/routers/serve.py) | Path resolution, clean URLs, 307 for assets, HTML proxy. |
| [app/auth.py](app/auth.py) | Supabase JWT verification (HS256 secret or JWKS). |
| [app/store.py](app/store.py) | Every database call in the app. |
| [app/supabase.py](app/supabase.py) | Thin async PostgREST + Storage client. |
| [db/](db/) | SQL to run in the Supabase editor, in order. |
| [scripts/smoke.sh](scripts/smoke.sh) | The Phase 1 curl deliverable, end to end. |
| [tests/](tests/) | 195 tests, no network required. |

---

## Deploy runbook

### 1. Supabase

Create a project (free plan), then in the SQL editor run, in order:

1. [db/001_init.sql](db/001_init.sql) — tables, RLS policies. Verbatim from the spec.
2. [db/002_file_manifest.sql](db/002_file_manifest.sql) — the file manifest. Not
   in the spec; the file explains why it earns its place. The app works without
   it, just with more storage round-trips per request.
3. [db/003_storage_bucket.sql](db/003_storage_bucket.sql) — the public `sites` bucket.

Then collect, from Project Settings → API:

- the project URL
- the **`service_role`** key — server-side only, forever
- the JWT secret, if your project still uses legacy HS256 signing. Newer
  projects use ES256/RS256 signing keys instead; leave `SUPABASE_JWT_SECRET`
  blank and the app verifies against your project's JWKS endpoint.

### 2. Render

Push this repo to GitHub, then Render → New → Blueprint, pointed at the repo.
[render.yaml](render.yaml) defines one free Docker web service with a health
check on `/health`. Fill in the four `sync: false` variables in the dashboard:

```
SUPABASE_URL          https://<ref>.supabase.co
SUPABASE_SERVICE_KEY  <service_role key>
SUPABASE_JWT_SECRET   <JWT secret, or blank for JWKS>
PUBLIC_BASE_URL       https://<service>.onrender.com
CORS_ORIGINS          https://<dashboard>.vercel.app     (Phase 2; blank for now)
```

Only one free service fits in a workspace: the free tier grants 750 instance
hours a month across the whole workspace and always-on burns about 720.

### 3. Keep-alive

Point a HetrixTools uptime monitor at `https://<service>.onrender.com/health`
every 10 minutes. This does two jobs: it stays ahead of Render's 15-minute
spin-down (a cold start is about a minute), and `/health` runs a throttled
Postgres query so Supabase never hits its 7-day inactivity pause. The throttle
means the ping costs one query every five minutes, not one per ping.

### 4. Verify

```bash
BASE=https://<service>.onrender.com TOKEN=<supabase user access token> ./scripts/smoke.sh
```

It deploys [scripts/sample-site/](scripts/sample-site/), checks clean URLs, the
404 fallback, the redirect target, both rejection paths, and deletes the project
again. `TOKEN` is a *user* access token from a Supabase sign-in — never the
service_role key.

To get a token before the Phase 2 dashboard exists:

```bash
curl -X POST "$SUPABASE_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $SUPABASE_ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"..."}' | jq -r .access_token
```

---

## Running locally

```bash
pip install -r requirements-dev.txt
cp .env.example .env          # fill it in
set -a; . ./.env; set +a
uvicorn app.main:app --reload
```

`/docs` gives you the interactive API. `/health` answers even with no Supabase
configured, so you can tell "misconfigured" apart from "down".

```bash
python -m pytest              # 195 tests, no network, no Supabase project
```

---

## What is enforced, and where

| Limit | Value | Enforced in |
| --- | --- | --- |
| Deployment size | 50 MB | [upload_stream.py](app/upload_stream.py) while streaming, then re-checked against the archive header and again during extraction |
| Files per deployment | 500 | [zipvalidate.py](app/zipvalidate.py), before extraction |
| Storage per user | 100 MB | [routers/deployments.py](app/routers/deployments.py), before any object is written |
| Proxied HTML page | 5 MB | [routers/serve.py](app/routers/serve.py), refused on Content-Length before a byte is streamed |
| Serving requests | 60/min per IP | [ratelimit.py](app/ratelimit.py) |
| Deployments | 20/hour per user | [ratelimit.py](app/ratelimit.py) |

Rejected archives, and what stops them:

| Attack | Check |
| --- | --- |
| Zip bomb | Uncompressed sizes summed from the header before extraction, then a live byte counter during extraction in case the header lied |
| Path traversal | `..`, absolute paths and drive letters rejected by name, then a `realpath` containment check |
| Symlink escape | Unix mode bits inspected; symlinks and all other non-regular files rejected |
| Null byte / backslash | Rejected outright |
| Content-type confusion | Extension whitelist only; unknown extensions become `application/octet-stream` |
| Decompression codecs | Only STORED and DEFLATED accepted |

Nothing in the upload path imports `subprocess`, calls `eval`, or shells out;
[a test asserts it](tests/test_zipvalidate.py).

---

## Known limitations

**User HTML executes on this origin.** Not merely "is linked from" — HTML is
proxied through the service (see below), so a deployed page runs as
`<your-service>.onrender.com`. That is exactly the risk Supabase declines to
take on `*.supabase.co`, and we have taken it deliberately because the platform
leaves no other way to serve HTML at all. **Nothing on this domain may ever set
a cookie or hold a session.** The Phase 2 dashboard belongs on Vercel, on a
separate origin, authenticating with a bearer token — that separation is now
load-bearing, not merely tidy. Real isolation needs a wildcard domain and a
proxy layer; the spec puts that out of scope.

**HTML is proxied; everything else redirects.** Supabase Storage serves
`text/html` as `text/plain` on public URLs by policy (supabase/storage#186,
discussions #2557 and #39110) — anti-phishing for their shared origin, not a bug,
and not defeatable from the upload side: our objects carry the correct
`metadata->>'mimetype'` and are downgraded on the way out anyway. So HTML and
XHTML are streamed through FastAPI with the whitelisted content-type, capped at
`MAX_PROXY_BYTES` (5 MB). css, js, images and fonts still redirect and never
touch the dyno. The cost is that HTML crosses the dyno twice, counting against
Render bandwidth and Supabase egress; HTML is the small half of a static site,
which is what makes that affordable. Do not let this exception widen — see
SPEC.md non-negotiable #2 for the standard of evidence required.

**Rate limits are per instance and per IP.** One free dyno means one process, so
an in-memory dict is exactly right today. It is also spoofable via
`X-Forwarded-For`; it protects CPU, not authorisation, and nothing
security-relevant keys off the client address.

**Old deployments are never collected.** Storage grows with every deploy until
the 100 MB per-user quota stops it. That is Phase 5's garbage collector, and
with 1 GB total it will be needed early.

---

## Not built yet

Phase 2 (dashboard), 3 (GitHub import), 4 (Actions-based builds) and 5 (GC,
rollback, build logs) are untouched, per the spec's gate on Phase 1 being
deployed first. Two pieces of Phase 1 already lean their way: the redundant-root
stripping in `zipvalidate.strip_redundant_root` is what Phase 3 needs for
GitHub's `owner-repo-sha1/` wrapper, and `deployments.commit_sha` is populated
from the `X-Commit-Sha` header that the Phase 4 workflow sends.
