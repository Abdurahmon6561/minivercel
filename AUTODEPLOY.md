# SPEC ADDENDUM — GitHub import, random URLs, auto-deploy

> Companion to SPEC.md. Implement after Phase 2 (auth + dashboard) works.

> **AMENDED after Phase 1 shipped.** Supabase Storage deliberately overrides
> `text/html` to `text/plain` on public URLs (supabase/storage#186,
> supabase discussions #2557 and #39110). It is platform policy, not a bug, and
> our uploads are correct — `storage.objects.metadata->>'mimetype'` reads
> `text/html; charset=utf-8`. Therefore SPEC.md non-negotiable #2 has an
> exception: **HTML is proxied through FastAPI with the correct Content-Type;
> every other asset type still gets the 307 redirect to Storage.** Wherever this
> file says "redirect", read it as "redirect, except HTML".

---

## 1. URL strategy

Start with **path-based**. Do not attempt subdomains until everything else works.

```
Phase A (now):    https://my-app.onrender.com/s/blue-forest-4821/
Phase B (later):  https://blue-forest-4821.yourdomain.com/
```

Phase B needs: a domain you own, Cloudflare in front (free Universal SSL covers
`*.yourdomain.com` at one level), and a wildcard CNAME pointing at Render.
Only the routing layer changes. The database, the storage keys, and the deploy
pipeline stay identical — so design the slug column now and swap the URL builder
later.

Put URL construction in ONE function. Never build URLs inline:

```python
# app/urls.py
import os

BASE = os.environ["PUBLIC_BASE_URL"]      # https://my-app.onrender.com
MODE = os.environ.get("URL_MODE", "path") # "path" or "subdomain"

def site_url(slug: str) -> str:
    if MODE == "subdomain":
        return f"https://{slug}.{os.environ['SITE_DOMAIN']}"
    return f"{BASE}/s/{slug}"
```

Switching to subdomains later = change two environment variables.

---

## 2. Random project names

**Status: not implemented yet.** Slugs are currently caller-supplied
(`smoke-1788339789`, `bbd-test-deploy`). Do this before the platform is public —
the RESERVED set below is a security control, not decoration.

Vercel style: readable words plus a short random suffix. Never expose database
IDs in URLs, and never let the user pick a raw slug (they will pick `admin`).

```python
# app/naming.py
import secrets

ADJECTIVES = ["blue", "swift", "quiet", "bold", "warm", "clever", "silent",
              "bright", "gentle", "rapid", "solid", "amber", "cosmic", "lucky"]
NOUNS = ["forest", "river", "harbor", "meadow", "canyon", "summit", "orbit",
         "ember", "lantern", "compass", "anchor", "prairie", "beacon", "vault"]

RESERVED = {"api", "www", "admin", "app", "dashboard", "docs", "status",
            "login", "auth", "static", "assets", "s", "health", "mail"}

def generate_slug() -> str:
    adj = secrets.choice(ADJECTIVES)
    noun = secrets.choice(NOUNS)
    num = secrets.randbelow(9000) + 1000
    return f"{adj}-{noun}-{num}"

def is_valid_slug(slug: str) -> bool:
    if slug in RESERVED:
        return False
    if not 3 <= len(slug) <= 63:
        return False
    return all(c.isalnum() or c == "-" for c in slug) and not slug.startswith("-")
```

Generate, then check uniqueness against the `projects` table. Retry up to 5
times on collision. With 14 x 14 x 9000 = 1.7M combinations, collisions are rare
but must still be handled — never assume.

The `RESERVED` set matters more than it looks. If a user gets the slug `api`,
`/s/api/...` collides with your own routes in path mode, and `api.yourdomain.com`
hijacks your API in subdomain mode.

---

## 3. Import a repo from GitHub

`POST /api/projects/import` body: `{"repo": "owner/name", "branch": "main"}`

Steps:
1. Read the user's GitHub OAuth token (stored at login by Supabase Auth).
2. `GET https://api.github.com/repos/{owner}/{repo}` — confirm it exists and the
   user can read it. If this 404s, the token lacks scope; say so plainly.
3. Insert a `projects` row with a generated slug.
4. Register the webhook (section 4).
5. Trigger the first deploy immediately (section 5) so the user sees a live URL
   without pushing anything.

---

## 4. Register the webhook

```python
import httpx

async def register_webhook(token: str, repo: str, project_id: str, secret: str):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.github.com/repos/{repo}/hooks",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "name": "web",
                "active": True,
                "events": ["push"],
                "config": {
                    "url": f"{PUBLIC_BASE_URL}/api/webhooks/github",
                    "content_type": "json",
                    "secret": secret,          # per-project, random, stored hashed
                    "insecure_ssl": "0",
                },
            },
        )
        r.raise_for_status()
        return r.json()["id"]   # store this so you can delete the hook later
```

Generate `secret` with `secrets.token_hex(32)`, one per project. Store it
encrypted or in a column that is never returned by any API response.

---

## 5. Receive the webhook — auto-deploy

Two rules that break this endpoint if ignored:

**Rule 1: verify the signature.** Without it, anyone who learns your webhook URL
can trigger deploys of arbitrary repos into your storage. This is not optional.

**Rule 2: respond within 10 seconds.** GitHub times out and marks the delivery
failed. A deploy takes 30-90 seconds. So you must return `202 Accepted`
immediately and do the work in the background.

```python
import hashlib
import hmac

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

router = APIRouter()


def verify_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    # compare_digest, never ==. A plain == returns as soon as two bytes differ,
    # so response time leaks how much of the signature was guessed correctly.
    # That is enough to forge a signature byte by byte over many requests.
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    # compare_digest, NOT ==. A plain == leaks timing information.
    return hmac.compare_digest(expected, signature)


@router.post("/api/webhooks/github", status_code=202)
async def github_webhook(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    body = await request.body()
    payload = await request.json()

    repo = payload.get("repository", {}).get("full_name")
    project = await find_project_by_repo(repo)
    if not project:
        raise HTTPException(404, "unknown repository")

    if not verify_signature(body, x_hub_signature_256, project["webhook_secret"]):
        raise HTTPException(401, "bad signature")

    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "push":
        return {"status": "ignored"}

    # Only deploy the tracked branch.
    ref = payload.get("ref", "")
    if ref != f"refs/heads/{project['branch']}":
        return {"status": "ignored", "reason": "other branch"}

    # Branch deletion arrives as a push with after == all zeros.
    if payload.get("after", "").strip("0") == "":
        return {"status": "ignored", "reason": "branch deleted"}

    deployment = await create_deployment(project["id"], commit_sha=payload["after"])
    background.add_task(run_deploy, deployment["id"], project["id"])
    return {"status": "queued", "deployment_id": deployment["id"]}
```

`run_deploy` downloads the zipball, runs the Phase 1 validation pipeline
unchanged, uploads to Supabase Storage, then sets `projects.live_deployment_id`.
**Only flip `live_deployment_id` on success.** If the deploy fails, the previous
version stays live — that is what makes deployments feel safe.

---

## 6. Background tasks on a free tier — the honest caveat

`BackgroundTasks` runs inside the same worker process. On Render's free plan
that means 0.1 CPU and 512 MB RAM, and the service spins down after 15 minutes
of no traffic. A background task can be killed mid-deploy.

Consequences to design for:
- A deployment stuck in `pending` for more than 10 minutes is dead. Add a query
  on startup that marks such rows `failed` with the reason "worker restarted".
- Keep the 50 MB cap. Do not raise it. Streaming 200 MB through 0.1 CPU will
  time out.
- The HetrixTools ping every 10 minutes keeps the service warm, which is what
  makes background deploys viable at all.

If deploys become unreliable, that is the signal to move builds to GitHub
Actions (SPEC.md Phase 4) — the runner does the work, your server only receives
the finished zip.

---

## 7. Deleting a project

Do all four, in this order:
1. Delete the GitHub webhook (`DELETE /repos/{repo}/hooks/{hook_id}`).
2. Delete every object under `{deployment_id}/` in Supabase Storage, for every
   deployment of the project.
3. Delete the `projects` row (deployments cascade).
4. Free the slug.

Skipping step 2 is the most common bug in projects like this. Storage is not
covered by `ON DELETE CASCADE` — Postgres has no idea those files exist. With
1 GB of free storage you will hit the ceiling within weeks.

---

## 8. What "auto-deploy" looks like to the user

```
push to main
   -> GitHub fires webhook            (instant)
   -> your API verifies + returns 202  (< 1s)
   -> background: download zipball     (5-20s)
   -> validate, upload to storage      (10-60s)
   -> flip live_deployment_id          (instant)
   -> new version live
```

The dashboard should poll `GET /api/deployments/{id}` every 2 seconds and show
`pending -> ready`. That status changing in front of the user is the moment the
project stops feeling like a school exercise and starts feeling like Vercel.
