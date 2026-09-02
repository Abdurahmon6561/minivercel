"""POST /api/webhooks/github - push events.

Three properties this endpoint has to have, in order:

  1. **Verify before trusting anything.** The body is attacker-controlled until
     `X-Hub-Signature-256` checks out against a per-project secret, using
     `hmac.compare_digest`. Nothing is written and no work is scheduled before
     that.
  2. **Answer fast.** GitHub gives a webhook 10 seconds. A deploy takes far
     longer, so we return 202 immediately and do the work in a BackgroundTask.
     A slow answer here shows up as a red delivery in the user's repo settings.
  3. **Ignore loudly, not silently.** Every outcome - deployed, ignored, failed
     - is recorded on the project so the dashboard can answer "did my push
     arrive?". A push that does nothing because auto-deploy is off must be
     distinguishable from a push that never got here.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, Response, status

from ..config import Settings, get_settings
from ..crypto import EncryptionUnavailable, decrypt
from ..deps import get_store
from ..gitops import deploy_from_repo
from ..store import Store

log = logging.getLogger("minivercel.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# GitHub caps payloads at 25 MB. We never need more than the metadata, and
# refusing early keeps an oversized body off a 512 MB dyno.
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024

DELETED_BRANCH_SHA = "0" * 40


def signature_matches(secret: str, body: bytes, header: str | None) -> bool:
    """Constant-time comparison of X-Hub-Signature-256.

    `compare_digest` rather than `==`: a byte-by-byte comparison leaks, through
    timing, how much of a guessed signature was correct, which turns forging one
    into a tractable search.
    """
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


async def _match_project(
    store: Store, settings: Settings, repo_full_name: str, body: bytes, signature: str | None
) -> dict | None:
    """The project whose secret verifies this delivery.

    Two users may import the same public repository, so the repo name alone does
    not identify a project. The signature does: each project has its own secret,
    and exactly one can verify a given delivery.
    """
    for project in await store.projects_for_repo(repo_full_name):
        stored = project.get("webhook_secret")
        if not stored:
            continue
        try:
            secret = decrypt(stored, settings)
        except EncryptionUnavailable:
            log.error(
                "webhook secret for %s cannot be decrypted; GITHUB_TOKEN_KEY may "
                "have been rotated",
                project["slug"],
            )
            continue
        if signature_matches(secret, body, signature):
            return project
    return None


def _accepted(status_name: str, reason: str) -> dict:
    return {"status": status_name, "reason": reason}


@router.post("/github")
async def github_push(
    request: Request,
    response: Response,
    background: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
):
    body = await request.body()
    if len(body) > MAX_PAYLOAD_BYTES:
        response.status_code = status.HTTP_413_CONTENT_TOO_LARGE
        return {"status": "rejected", "reason": "payload too large"}

    # `ping` is what GitHub sends when the hook is created. It carries a valid
    # signature but no push to act on.
    if x_github_event == "ping":
        return {"status": "pong"}

    if x_github_event != "push":
        response.status_code = status.HTTP_202_ACCEPTED
        return _accepted("ignored", "event %r is not a push" % (x_github_event or ""))

    try:
        payload = await request.json()
    except Exception:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"status": "rejected", "reason": "body is not JSON"}

    repo_full_name = ((payload.get("repository") or {}).get("full_name") or "").strip()
    if not repo_full_name:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"status": "rejected", "reason": "no repository in payload"}

    store = get_store()
    project = await _match_project(
        store, settings, repo_full_name, body, x_hub_signature_256
    )
    if project is None:
        # Same answer whether the repo is unknown or the signature is wrong: a
        # 401 that distinguishes them is an oracle for which repos we host.
        log.warning("rejected webhook for %s: no matching signature", repo_full_name)
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"status": "rejected", "reason": "signature verification failed"}

    ref = payload.get("ref") or ""
    after = payload.get("after") or ""
    branch = project.get("repo_branch") or "main"
    expected_ref = "refs/heads/" + branch

    async def record(status_name: str, reason: str) -> None:
        await store.record_webhook_delivery(
            project["id"], status=status_name, detail=reason, sha=after or None
        )

    if ref != expected_ref:
        await record("ignored", "push to %s, watching %s" % (ref or "?", expected_ref))
        response.status_code = status.HTTP_202_ACCEPTED
        return _accepted("ignored", "not the deploy branch")

    # A branch deletion arrives as a push whose `after` is all zeros. Deploying
    # a deleted ref would fail; treating it as a no-op is correct.
    if after == DELETED_BRANCH_SHA or payload.get("deleted"):
        await record("ignored", "branch deleted")
        response.status_code = status.HTTP_202_ACCEPTED
        return _accepted("ignored", "branch deleted")

    if not project.get("auto_deploy_enabled", True):
        # The hook stays registered on purpose: re-registering it later needs
        # the OAuth token and can fail silently.
        await record("ignored", "auto-deploy disabled")
        response.status_code = status.HTTP_202_ACCEPTED
        return _accepted("ignored", "auto-deploy disabled")

    if project.get("builds_enabled"):
        # GitHub Actions will build and POST the output. Deploying the raw
        # source here as well would produce two deployments per push, the
        # second of them wrong.
        await record("ignored", "builds enabled; GitHub Actions will deploy")
        response.status_code = status.HTTP_202_ACCEPTED
        return _accepted("ignored", "GitHub Actions will deploy this push")

    # The row is created here, not in the background task, so the 202 can carry
    # its id: AUTODEPLOY.md section 8 has the dashboard polling
    # GET /api/deployments/{id} to watch pending -> ready. Created in the task
    # instead, there would be nothing to poll until the deploy had already
    # started, and a task killed before its first write would leave no trace.
    deployment = await store.create_deployment(project["id"], after or None)
    await record("deploying", "push %s accepted" % (after[:7] or "?"))
    log.info(
        "webhook accepted for %s at %s -> deployment %s",
        project["slug"],
        after[:7],
        deployment["id"],
    )

    background.add_task(
        _deploy_in_background, settings, project, after or None, deployment["id"]
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return {
        "status": "queued",
        "deployment_id": deployment["id"],
        "commit": after[:7] or None,
    }


async def _deploy_in_background(
    settings: Settings,
    project: dict,
    commit_sha: str | None,
    deployment_id: str,
) -> None:
    """Runs after the 202. Never raises - the task runner has nowhere to report."""
    store = get_store()
    try:
        deployment_id = await deploy_from_repo(
            store,
            settings,
            project=project,
            commit_sha=commit_sha,
            deployment_id=deployment_id,
        )
        deployment = (
            await store.get_deployment(deployment_id) if deployment_id else None
        )
        if deployment and deployment.get("status") == "ready":
            await store.record_webhook_delivery(
                project["id"],
                status="deployed",
                detail="deployed %s" % deployment_id,
                sha=commit_sha,
            )
        else:
            await store.record_webhook_delivery(
                project["id"],
                status="failed",
                detail=(deployment or {}).get("error") or "deploy failed",
                sha=commit_sha,
            )
    except Exception:  # pragma: no cover - defensive
        log.exception("background deploy failed for %s", project.get("slug"))
        try:
            await store.record_webhook_delivery(
                project["id"], status="failed", detail="internal error", sha=commit_sha
            )
        except Exception:
            log.exception("could not record webhook failure")
