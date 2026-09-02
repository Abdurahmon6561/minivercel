# MiniVercel dashboard — Phases 2–4

React + Vite + Tailwind, deployed on Vercel. Talks to the Phase 1 API at
`https://minivercel.onrender.com` and to Supabase Auth directly.

```
/login      Continue with GitHub
/           project list — live URL, last deploy time, status dot
/new        drag-and-drop zip upload, or import from GitHub
/p/{slug}   deployment history, GitHub settings, upload, delete
```

On `/p/{slug}` a repo-backed project gets two independent switches — auto-deploy
on push, and build with GitHub Actions — plus the build command and output
directory (disabled while builds are off), and the outcome of the last webhook
delivery so a push can be told apart from a push that was ignored.

Plain Tailwind, no component library, per the spec. `src/components/Bits.tsx`
holds five primitives that exist because the same classes repeated five times —
that is deduplication, not an abstraction layer.

---

## Why the dashboard is on a different origin

Not a preference. Deployed sites are served from the API's origin, and since
Phase 1's HTML proxy they *execute* there (SPEC.md non-negotiable #2). Putting
the dashboard on the same domain would put user-controlled HTML in the same
origin as your session.

Hence: dashboard on Vercel, API on Render, **bearer tokens rather than cookies**.
The access token is held by supabase-js and attached per request in
`src/lib/api.ts`. Nothing here sets a cookie on the serving domain, and nothing
should.

## Setup

### 1. GitHub OAuth app

<https://github.com/settings/developers> → New OAuth App.

| Field | Value |
| --- | --- |
| Homepage URL | `https://<your-dashboard>.vercel.app` |
| Authorization callback URL | `https://<ref>.supabase.co/auth/v1/callback` |

The callback points at **Supabase**, not at the dashboard. Supabase completes
the OAuth exchange and then redirects to the dashboard. Getting this wrong is
the single most common way this fails, and the error ("redirect_uri mismatch")
names GitHub rather than Supabase, which sends you looking in the wrong place.

Copy the Client ID and generate a Client Secret.

### 2. Supabase

Dashboard → Authentication → Providers → GitHub: enable, paste the ID and
secret.

Authentication → URL Configuration:

- **Site URL**: `https://<your-dashboard>.vercel.app`
- **Redirect URLs**: add `http://localhost:5173` as well, or local development
  cannot complete a sign-in.

Then run [../db/004_github_tokens.sql](../db/004_github_tokens.sql) and
[../db/005_github_integration.sql](../db/005_github_integration.sql) in the SQL
editor — the provider-token table, and the repo/webhook/build columns.

### 3. API (Render)

Two environment variables:

```
CORS_ORIGINS      https://<your-dashboard>.vercel.app,http://localhost:5173
GITHUB_TOKEN_KEY  <a Fernet key>
```

Generate the key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Without it the API **refuses** to store GitHub tokens (503) rather than writing
them in plaintext. Everything else in the dashboard still works. Keep the key
stable: rotating it makes stored tokens undecryptable and every user has to
reconnect GitHub.

### 4. Vercel

Import this repo, set **Root Directory** to `web`. `vercel.json` handles the
rest, including the SPA rewrite that stops `/p/{slug}` 404ing on reload.

Environment variables:

```
VITE_SUPABASE_URL       https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY  <anon key>
VITE_API_BASE_URL       https://minivercel.onrender.com
VITE_GITHUB_SCOPES      public_repo
```

The **anon** key. It is public by design and RLS is what makes it safe. The
service_role key must never appear in a `VITE_*` variable — those are compiled
into the bundle and shipped to every visitor.

## Local development

```bash
cd web
npm install
cp .env.example .env      # fill in
npm run dev               # http://localhost:5173
```

`npm run build` typechecks and builds; `npm run typecheck` does the former
alone.

## Notes on two decisions

**The provider token is captured on the sign-in event, not on demand.** Supabase
returns `provider_token` exactly once and never refreshes it; miss it and the
only way to get another is to make the user authorise GitHub again. So
`AuthProvider` posts it to `/api/me/github-token` the moment it appears. It is
encrypted server-side and no endpoint ever returns it — `GET /api/me` reports
only that a connection exists.

**Uploads use XMLHttpRequest, not fetch.** `fetch` cannot report upload
progress, and the limit is 50 MB. On a home connection a progress bar is the
difference between "working" and "frozen".

## Scope

Phases 2, 3 and 4. Promoting an *older* deployment back to live is a one-line
change (`live_deployment_id`) but it is Phase 5's rollback feature, so it is not
here — "upload new version" and "push to the repo" both create a new deployment.

The `public_repo` scope is enough to import and deploy a public repository. A
**private** repository needs `repo`: set `VITE_GITHUB_SCOPES=repo` and have
users sign in again. Importing also needs **admin** on the repository, because
that is what GitHub requires to add a webhook.
