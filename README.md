# MiniVercel

Upload a zip of static files, get a public URL.

We never execute anything a user gives us. Not Node, not Python, not shell.
Uploads are inert files that get validated, stored, and redirected to. That
restriction is the entire security model — see [SPEC.md](SPEC.md)
"Non-negotiables" before changing anything in [app/](app/).

**Status: Phases 1–4 complete. Phase 1 and 2 deployed at
<https://minivercel.onrender.com>.** Phases 3 and 4 add GitHub import,
auto-deploy on push, and builds that run on GitHub Actions rather than here.
Phase 5 (garbage collection, rollback, build logs) has not been started.

Deploying 3 and 4 needs one new migration and one new environment variable —
see "Deploy runbook" below.

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
| [app/deployer.py](app/deployer.py) | The one deployment pipeline. Every source of a zip goes through it. |
| [app/urls.py](app/urls.py) | The one URL builder. `URL_MODE=subdomain` moves every site without touching a handler. |
| [app/naming.py](app/naming.py) | Slug generation and the RESERVED set that keeps a project off `api` or `www`. |
| [app/gitops.py](app/gitops.py) | Import, push deploys, and Actions build enablement. |
| [app/github.py](app/github.py) | GitHub REST: repos, zipballs, webhooks, workflow files, secrets. |
| [app/deploytoken.py](app/deploytoken.py) | Per-project deploy tokens. Stored as sha256, never in the clear. |
| [app/routers/webhooks.py](app/routers/webhooks.py) | `POST /api/webhooks/github`: verify, then 202 and deploy in the background. |
| [app/routers/me.py](app/routers/me.py) | `/api/me`: identity, quota, and the encrypted GitHub token. |
| [app/gc.py](app/gc.py) | Retention rules, the storage-before-row deletion order, and the stuck-`pending` reaper. |
| [app/routers/admin.py](app/routers/admin.py) | `POST /api/admin/gc`, behind `ADMIN_TOKEN`. |
| [app/routers/_errors.py](app/routers/_errors.py) | The one GitHub-error-to-HTTP-status mapping. |
| [app/crypto.py](app/crypto.py) | Fernet wrapper for the one secret we must store and read back. |
| [web/](web/) | Phase 2 dashboard: React + Vite + Tailwind, deployed on Vercel. |
| [scripts/smoke.sh](scripts/smoke.sh) | The Phase 1 curl deliverable, end to end. |
| [tests/](tests/) | 387 tests, no network required. |

---

## Deploy runbook

### 1. Supabase

Create a project (free plan), then in the SQL editor run, in order:

1. [db/001_init.sql](db/001_init.sql) — tables, RLS policies. Verbatim from the spec.
2. [db/002_file_manifest.sql](db/002_file_manifest.sql) — the file manifest. Not
   in the spec; the file explains why it earns its place. The app works without
   it, just with more storage round-trips per request.
3. [db/003_storage_bucket.sql](db/003_storage_bucket.sql) — the public `sites` bucket.
4. [db/004_github_tokens.sql](db/004_github_tokens.sql) — Phase 2: the encrypted
   GitHub provider token. RLS on, no policy, service_role only.
5. [db/005_github_integration.sql](db/005_github_integration.sql) — Phases 3 and
   4: repo linkage, webhook secret, the two switches, and the deploy-token hash.

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
CORS_ORIGINS          https://<dashboard>.vercel.app
GITHUB_TOKEN_KEY      <Fernet key>
ADMIN_TOKEN           <random secret, or blank to disable /api/admin/gc>
```

`ADMIN_TOKEN` is new in Phase 5 and is the only variable that has to be added to
an existing deployment. `render.yaml` generates one; if you set it by hand, use
`python -c "import secrets; print(secrets.token_urlsafe(32))"`. Leaving it blank
is safe — `POST /api/admin/gc` then answers 503 and garbage collection still
runs after every successful deploy.

`PUBLIC_BASE_URL` is load-bearing from Phase 3 on: it is the URL registered as
the GitHub webhook and baked into the committed workflow file. Changing it means
re-importing projects and re-enabling builds.

`GITHUB_TOKEN_KEY` encrypts both the GitHub provider token and each project's
webhook secret. Generate it with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Rotating it invalidates every stored token and webhook secret: users reconnect
GitHub, and projects must be re-imported.

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
python -m pytest              # 315 tests, no network, no Supabase project
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

## GitHub integration (Phases 3 and 4)

```
  push to main
       |
       v
  POST /api/webhooks/github
       |
  [ verify X-Hub-Signature-256 against this project's secret ]
       |
       +-- auto_deploy_enabled = false --> 202 ignored, recorded, nothing deploys
       +-- builds_enabled = true --------> 202 ignored; Actions will POST instead
       |
       v
  202 accepted (within 10s), deploy runs in a BackgroundTask
       |
  download zipball -> strip owner-repo-sha/ -> find dist|build|public|_site
       |
       v
  the Phase 1 validation pipeline, unchanged
```

**Two independent switches per project**, both on `/p/{slug}`:

| Switch | Off means |
| --- | --- |
| `auto_deploy_enabled` | Pushes are received and recorded, nothing deploys. The webhook stays registered — deleting it would need the OAuth token to re-create later, and that can fail silently. |
| `builds_enabled` | The repository is deployed as-is. On, GitHub Actions builds it and POSTs the output; the webhook then defers, or every push would produce two deployments, the second one wrong. |

**Builds never run here.** Enabling them commits
`.github/workflows/minivercel.yml` to the user's repo and stores a per-project
deploy token as the `MINIVERCEL_TOKEN` Actions secret (libsodium sealed box). We
keep `sha256(token)` and nothing else. `npm install` runs on GitHub's runner,
paid for by GitHub, with no access to our database — Render Free is 0.1 CPU and
512 MB, and the Phase 1 security model is unchanged because all we ever receive
is a zip of static output.

A failed deploy never changes `live_deployment_id`: a broken push leaves the
previous version serving.

## Rollback, garbage collection and build logs (Phase 5)

### Every deployment is kept, and any of them can be made live again

A deploy no longer replaces what came before it. Each deployment keeps its own
key prefix in Storage, so a past one can be looked at without disturbing the
site:

```
https://<service>.onrender.com/s/<slug>/_d/<deployment-id>/
```

That URL is public, like the site itself, and carries `X-Robots-Tag: noindex`.
It resolves clean URLs, serves `404.html` and redirects assets exactly as the
live route does — it is the same code with a different deployment id — so a
preview cannot render differently from the site it is a preview of. It refuses
a deployment belonging to another project, and refuses one that is not `ready`.

Promotion is a pointer move:

```
POST /api/projects/{slug}/deployments/{id}/promote
```

It sets `projects.live_deployment_id` and touches no storage at all, which is
what makes it instant and free. It is refused if the deployment is not `ready`
(promoting a half-uploaded deployment would replace a working site with a broken
one) or belongs to another project (answered 404, not 403, so the route cannot be
used to discover deployment ids). Promoting what is already live is a no-op, not
an error. In the dashboard each row gets **Preview** and **Promote to live**,
with a confirmation step; the live row shows the LIVE badge instead.

### Garbage collection

Retention, applied per project:

1. the live deployment is kept for ever, whatever its age;
2. the **5 most recent *ready* non-live** deployments are kept, whatever their
   age — this is what leaves something to roll back *to*;
3. any other ready deployment is deleted once it is more than **7 days** old;
4. a **failed** deployment loses its storage objects immediately and its row
   after 7 days;
5. a **pending** deployment is never touched.

Rule 2 counts *ready* deployments deliberately. A failed deployment can never be
promoted, so if failures held rollback slots, a project with five failures from
this morning and one working version from last week would spend every slot on
rows nobody can roll back to and then collect the only version that still works.

Rule 4 is the other half of that. A failed deployment is never served, so any
objects a partial upload left behind are pure waste against the 1 GB.
`deployer.fail` already removes them on the normal path; what it cannot cover is
a worker killed mid-upload, which leaves objects with nothing to clean them and a
row the reaper only later marks failed. So the sweep removes a failed
deployment's objects on sight and keeps the row for seven days, because that row
is the error message the user is reading.

Rule 5 exists because a `pending` deployment may be uploading *right now*, and
deleting its objects would truncate a deploy in flight. A dead one becomes
`failed` within ten minutes and is then covered by rule 4.

**Storage objects are deleted first, then the row.** That order is the whole
point. Postgres knows nothing about the bucket, so `ON DELETE CASCADE` does not
reach it (AUTODEPLOY.md section 7); a row deleted first leaves a set of object
keys nobody can enumerate again, and those bytes are unreclaimable short of
listing the entire bucket by hand. If the storage delete fails, the row is
deliberately left in place so the next sweep can retry.

Render's free plan has no cron, so collection runs in two places:

* **after every successful deploy**, scoped to the project that just deployed —
  which is also the only project whose deployment list just changed. It cannot
  fail a deploy: every error is swallowed and logged.
* **`POST /api/admin/gc`**, a full sweep, guarded by `ADMIN_TOKEN` and compared
  with `hmac.compare_digest`. Useful for projects that stopped deploying, which
  nothing else will ever collect. Any external scheduler can call it — a
  HetrixTools monitor or a GitHub Actions cron reaches it as easily as `/health`.

Bytes reclaimed and objects removed are logged on every run and returned by the
admin endpoint. The two are reported separately because a failed deployment's
`size_bytes` is 0 — it never reached `mark_deployment_ready` — so objects swept
from a partial upload show up as a count and cannot show up as bytes.
`GET /api/me` reports live `usage.bytes_used`, recomputed per call, so the quota
bar falls as soon as a sweep frees space.

### Build logs

The committed workflow tees every step into one file and, in a final
`if: always()` step, ships its last 200 lines:

```
POST /api/deployments/{id}/logs          # attach to a deployment
POST /api/deployments/build-failed       # the build never produced a zip
GET  /api/deployments/{id}/logs          # owner only, read it back
```

It authenticates with the same per-project deploy token the upload uses — no new
credential and no new scope. The second endpoint exists because a build that
dies during `npm run build` never reaches the upload step, so before Phase 5 it
produced no deployment row at all and the dashboard went on showing the previous
successful deploy. It accepts a deploy token only; a browser has no business
inventing a failed deployment.

Logs are truncated to the last 200 lines and 64 KB — a build fails at the end —
stored as text, and never interpreted. The dashboard shows the panel collapsed
and fetches the text only when it is opened, so listing fifty deployments does
not drag fifty logs across the wire.

### Stuck deployments

A deployment `pending` for more than ten minutes is a worker that died
mid-deploy, not a slow one (AUTODEPLOY.md section 6). It is marked `failed` with
the reason `worker restarted`, at startup, on the admin sweep, and — throttled to
once a minute per process — from the project list and detail routes, which is
where the dashboard is actually polling it.

---

## Not built yet

Custom domains and subdomain serving. Both need a domain, a wildcard
certificate and a proxy layer in front (SPEC.md Phase 5, AUTODEPLOY.md section
1); `URL_MODE` and `app/urls.py` are already shaped for the switch, and nothing
else changes.
