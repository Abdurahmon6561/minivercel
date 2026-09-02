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
VITE_GITHUB_SCOPES      repo,workflow
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

### Scopes — `public_repo` is not enough

This is the easiest thing to get wrong, because **GitHub reports a missing scope
as `404`**, so it reads as "repository not found" rather than "wrong scope".

| Operation | Scope |
| --- | --- |
| Read a public repo, download its zipball | `public_repo` |
| Read a **private** repo | `repo` |
| Register the push webhook (Phase 3) | `admin:repo_hook`, or `repo` |
| Commit `.github/workflows/minivercel.yml` (Phase 4) | `workflow` — **`repo` does not imply this** |
| Store the `MINIVERCEL_TOKEN` Actions secret | `repo` |

Per [GitHub's scope
documentation](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps),
`public_repo` covers "code, commit statuses, repository projects, collaborators,
and deployment statuses" — hooks are not in that list.

So the default is `repo,workflow`, which covers everything including private
repositories. Public-only deployments can narrow it to
`public_repo,admin:repo_hook,workflow`.

Changing `VITE_GITHUB_SCOPES` only affects **new** sign-ins. Existing users must
sign out and sign in again to re-authorise — their stored token keeps whatever
scopes it was granted. The API checks the granted scopes (from GitHub's
`X-OAuth-Scopes` header) before writing anything, so a too-narrow sign-in gets a
message naming the missing scope instead of a confusing 404.

Importing also needs **admin** on the repository, because that is what GitHub
requires to add a webhook.
