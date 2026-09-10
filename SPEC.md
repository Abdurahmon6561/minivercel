# SPEC — "MiniVercel": a static site hosting platform

> Give this file to Claude Code in VS Code. Build phase by phase.
> Do NOT start Phase 2 until Phase 1 is deployed and working.

---

## 0. What this is and is not

**Is:** a platform where a user uploads (or imports from GitHub) a folder of
static files — HTML, CSS, JS, images — and gets a public URL that serves them.

**Is NOT:** a place that runs user code on our server. We never execute anything
a user gives us. Not Node, not Python, not shell. Uploads are inert files only.
This restriction is the entire security model. Do not weaken it.

**Stack**
| Layer | Choice | Why |
| --- | --- | --- |
| API + serving | FastAPI on Render (Docker runtime, free plan) | Free. NOT Hugging Face - Docker Spaces now require PRO ($9/mo) |
| Database | Supabase Postgres | Free 500 MB |
| File storage | Supabase Storage | Free 1 GB, has public CDN URLs |
| Auth | Supabase Auth | Free 50k MAU |
| Keep-alive | HetrixTools -> `GET /health` every 10 min | Beats Render 15-min spin-down + Supabase 7-day pause |
| Build runner (Phase 4) | GitHub Actions in the *user's* repo | Their compute, sandboxed by GitHub |

**Hard limits to design around**
- Supabase free: 1 GB storage, 5 GB egress/month, 500 MB database.
- Therefore: per-user quota of 250 MB, per-deployment cap of 50 MB, max 500 files.
  Enforce these in code from day one, not later.
  100 MB was the early-testing value; 250 MB is the current free-tier default
  (raised 2026-09-10 via `MAX_USER_BYTES` on Render). 250 MB × 4 users at full
  theoretical quota = the 1 GB Supabase Free ceiling, and real-world usage
  averages far below quota, so this fits 20+ users comfortably. Adjust upward
  when Supabase Pro comes into play.
- Render free tier: 750 instance hours/month across the WHOLE workspace.
  Always-on = ~720 hours. One free service fits. A second one does not.
- Render's filesystem is ephemeral and free services cannot attach a disk.
  Never write user data to local disk except `/tmp` during a single request,
  and delete it before returning.
- Render's own free Postgres expires after 30 days. Do not use it. Supabase only.
- Cold start after spin-down is ~1 minute. The 10-minute ping prevents this.

---

## Phase 1 — Upload a ZIP, serve it

### Goal
`POST /api/deployments` with a zip -> `GET /s/{slug}/` serves `index.html`.

### Database

```sql
create table projects (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid references auth.users(id) on delete cascade,
  name        text not null,
  slug        text not null unique,
  created_at  timestamptz not null default now()
);
create index on projects (owner_id);

create table deployments (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references projects(id) on delete cascade,
  status       text not null default 'pending'
               check (status in ('pending','ready','failed')),
  size_bytes   bigint not null default 0,
  file_count   int    not null default 0,
  error        text,
  commit_sha   text,
  created_at   timestamptz not null default now()
);
create index on deployments (project_id, created_at desc);

-- One deployment per project is "live". Simplest correct approach:
alter table projects add column live_deployment_id uuid references deployments(id);

alter table projects    enable row level security;
alter table deployments enable row level security;

create policy "own projects" on projects
  for all using (auth.uid() = owner_id);
create policy "own deployments" on deployments
  for all using (
    exists (select 1 from projects p
            where p.id = deployments.project_id and p.owner_id = auth.uid())
  );
```

Storage bucket: `sites`, **public read**. Object key format:
`{deployment_id}/{relative/path/inside/zip}`

Using a public bucket means the browser can fetch assets straight from Supabase's
CDN and our Space never touches the bytes. That is the difference between this
working and this melting.

### Upload flow

1. Authenticate the user. Reject anonymous.
2. Stream the upload to `/tmp/{uuid}.zip`. Reject at 50 MB **while streaming** —
   do not read the whole body into memory first.
3. Create a `deployments` row with `status='pending'`.
4. Open the zip and validate **before extracting anything**:
   - Reject if `len(zipfile.infolist()) > 500`.
   - Reject if `sum(i.file_size) > 50 MB` — this is the zip-bomb check, and it
     uses the *uncompressed* size from the header.
   - Reject any entry whose resolved path escapes the extraction root
     (`..`, absolute paths, symlinks). Do this with
     `os.path.realpath(os.path.join(root, name)).startswith(realpath(root))`.
   - Reject entries with a null byte or a backslash in the name.
5. Extract to `/tmp/{deployment_id}/`. Upload each file to Supabase Storage.
   Set `content-type` from the file extension via a **whitelist map**, never from
   anything in the zip. Unknown extension -> `application/octet-stream`.
6. On success: `status='ready'`, set `projects.live_deployment_id`.
   On any failure: `status='failed'`, write the reason to `error`, delete
   whatever was uploaded.
7. `finally:` delete `/tmp/{deployment_id}` and the zip. Always.

### Serving flow

`GET /s/{slug}/{path:path}`

1. Look up the project by slug, then its `live_deployment_id`. 404 if missing.
2. Resolve the path:
   - empty or ends with `/` -> append `index.html`
   - no file extension and the exact key doesn't exist -> try `{path}.html`,
     then `{path}/index.html` (this is what makes clean URLs work)
   - still nothing -> serve `404.html` if the deployment has one, else plain 404
3. **Redirect (307) to the Supabase public storage URL** for every type except
   HTML, which must be proxied — see non-negotiable #2 for why Supabase leaves
   no alternative. Do not proxy anything else: it burns CPU and doubles
   bandwidth for no benefit, because Supabase serves every other type correctly.
4. Rate limit: 600 requests/minute per IP. In-memory dict is fine at this scale.
   This was 60 while the serving path was being abuse-tested against a
   hand-written `index.html`. A real site breaks that immediately — one page
   load of a React app with fonts, chunked JS and images is easily 30+
   requests, so two refreshes returned 429 to ordinary visitors. The limit is a
   floor for abuse, not a budget for normal browsing.

### Response headers
Set on the deployment's `index.html` only, via a wrapper page if needed:
`X-Content-Type-Options: nosniff`. User sites are untrusted content served from
your origin — if you later add cookies or auth on the same domain, that becomes
an XSS hole. Note this as a known limitation now.

### Deliverable
Working upload + serve, no UI needed yet. Test with `curl`.

---

## Phase 2 — Auth and dashboard

Frontend: React + Vite + Tailwind, deployed on **Vercel itself** (free, and it
handles the wildcard-domain problem for your dashboard).

- Supabase Auth with GitHub OAuth. Not email/password — you'll need the GitHub
  token in Phase 3 anyway, so ask for it now with scope `repo` (or `public_repo`).
- Store the provider token; you'll need it to read repos.

Pages:
- `/login`
- `/` — project list with live URL, last deploy time, status badge
- `/new` — drag-and-drop zip upload
- `/projects/{slug}` — deployment history, redeploy, delete

Design: dark, monospace for URLs and hashes, generous whitespace, status dots
(green ready / amber pending / red failed). Do not build a component library;
use plain Tailwind.

---

## Phase 3 — GitHub import (static repos only)

`POST /api/projects/import` with `{repo: "owner/name", branch: "main"}`

1. Use the user's stored OAuth token.
2. `GET /repos/{owner}/{repo}/zipball/{branch}` — GitHub returns the whole repo
   as a zip. Feed it into the exact same validation pipeline as Phase 1.
3. Strip the top-level folder GitHub adds (`owner-repo-sha1/`).
4. If the repo has no `index.html` at root, look for `dist/`, `build/`, `public/`,
   `_site/` and use the first that contains `index.html`. If none, fail with a
   clear message: "No static output found. Add a build step (Phase 4)."
5. Webhook: register a `push` webhook so pushes redeploy automatically. Verify
   the `X-Hub-Signature-256` HMAC on every incoming webhook. Reject if it fails.

---

## Phase 4 — Builds, without build infrastructure

This is the important idea. **We never run `npm install`.** GitHub does.

Flow:
1. User clicks "Enable builds" in the dashboard.
2. We commit a workflow file to their repo via the GitHub API:

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci
      - run: npm run build
      - name: Upload to MiniVercel
        env:
          DEPLOY_TOKEN: ${{ secrets.MINIVERCEL_TOKEN }}
        run: |
          cd dist && zip -r ../site.zip .
          curl -f -X POST "https://YOUR-APP.onrender.com/api/deployments" \
            -H "Authorization: Bearer $DEPLOY_TOKEN" \
            -H "X-Commit-Sha: ${{ github.sha }}" \
            -F "file=@../site.zip"
```

3. We generate a per-project deploy token and store it as a repo secret named
   `MINIVERCEL_TOKEN` (GitHub API supports this — encrypt with the repo's public
   key using libsodium sealed box).
4. Deploy tokens are scoped to one project, are hashed in the database
   (store `sha256(token)`, never the token), and can be revoked.

Why this is the right design: the untrusted build runs on GitHub's isolated
runner, paid for by GitHub, with zero access to our database. We only ever
receive a zip of static output. Our security model from Phase 1 is unchanged.

---

## Phase 5 — Nice to have

- Deployment previews: keep old deployments and serve them at
  `/s/{slug}/_d/{deployment_id}/`. Roll back = change `live_deployment_id`.
- Garbage collection: cron that deletes non-live deployments older than 7 days.
  With 1 GB of storage you need this early, not late.
- Build logs: have the workflow POST its log output to `/api/deployments/{id}/logs`.
- Custom domains: **out of scope.** Requires a wildcard cert and a proxy layer.
  If you ever want it, put Cloudflare Workers in front — not HF Spaces.

---

## Non-negotiables — repeat these to Claude Code if it drifts

1. Never execute user-supplied code on the server. No `subprocess`, no `eval`,
   no `npm`, no image conversion libraries that shell out.
2. Never serve user files by proxying through FastAPI. Always redirect to the
   Supabase public URL — **with one exception, for HTML only.**

   Supabase Storage deliberately serves `text/html` as `text/plain` on public
   URLs (supabase/storage#186, discussions #2557 and #39110). It is anti-phishing
   policy for the shared `*.supabase.co` origin, not a bug, and no upload header
   defeats it: our objects carry the correct `metadata->>'mimetype'` and are
   downgraded on the way out regardless. A redirect therefore cannot render a
   page, which makes redirect-only serving incompatible with the product.

   So: **HTML (and XHTML) is streamed through FastAPI with the content-type from
   our whitelist. Everything else — css, js, images, fonts — still redirects,
   and always will.** The exception is scoped as narrowly as the platform allows
   and is capped by `MAX_PROXY_BYTES` (5 MB default), streamed, never buffered.

   Three consequences, all of which are now true and none of which may be
   forgotten:

   - User HTML executes on **our** origin instead of `supabase.co`. That is
     precisely the risk Supabase declined to take on a shared domain, and we
     have accepted it. Nothing on the serving domain may ever set a cookie or
     hold a session. The Phase 2 dashboard stays on a separate origin with
     bearer-token auth — this is now load-bearing, not merely tidy.
   - HTML crosses the dyno twice, counting against Render bandwidth and Supabase
     egress. HTML is the small half of a static site, which is what makes this
     affordable; do not let the exception widen.
   - Because we control the response, a deployment's `404.html` is now served
     with a real 404 status instead of the 200 a redirect forced.

   Widening this exception to any other type needs the same standard of
   evidence: a documented platform behaviour that makes redirecting impossible.
   "It would be convenient" is not that.
3. Validate zip entries before extraction, not after.
4. `SUPABASE_KEY` is `service_role` and lives only in Space secrets. It must
   never reach the frontend, never appear in a response body, never be logged.
5. Enforce quotas in code. The free tier will not warn you before it breaks.
6. Every file written to `/tmp` is deleted in a `finally` block.

---

## Order of work

- [x] Phase 1 backend, tested with curl
- [x] Deploy to Render, confirm `/health` works
- [x] HetrixTools monitor on `/health`
- [x] Phase 2 dashboard on Vercel
- [x] Phase 3 GitHub import + push auto-deploy
- [x] Phase 4 Actions-based builds
- [x] Phase 5 GC, rollback and build logs
