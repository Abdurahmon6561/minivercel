"""GitHub REST client: repo metadata, zipballs, webhooks, workflow files, secrets.

Every call here is made with a *user's* OAuth token, on that user's behalf. The
token arrives decrypted from `github_tokens` (app/crypto.py) and lives only for
the duration of a request. It is never logged: `GitHubError` messages carry
GitHub's own text, which never contains the credential.

NON-NEGOTIABLE #1 is unaffected by anything in this file. We download an archive
and read it; we never execute it. Phase 4 exists precisely so that `npm install`
runs on GitHub's runners rather than ours.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from nacl import encoding, public

log = logging.getLogger("minivercel.github")

API = "https://api.github.com"
ACCEPT = "application/vnd.github+json"
API_VERSION = "2022-11-28"

# OAuth scopes, verified against GitHub's own documentation:
#   https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps
#
# The trap: `public_repo` grants "read/write access to code, commit statuses,
# repository projects, collaborators, and deployment statuses" - and NOT hooks.
# Registering a webhook needs a hook scope, and GitHub answers a scope-less hook
# call with 404, not 403, so it is indistinguishable from "no such repository"
# unless you check the scopes yourself. That is what this section is for.
#
# Any ONE of the alternatives in each tuple is sufficient.
HOOK_SCOPES = ("admin:repo_hook", "write:repo_hook", "repo")
#: Committing under .github/workflows/ needs `workflow`, which `repo` does NOT
#: imply. (GitHub waives it only when an identical file already exists on
#: another branch, which is never true for a file we are creating.)
WORKFLOW_SCOPES = ("workflow",)
#: Actions secrets are repository administration.
SECRET_SCOPES = ("repo",)
#: Reading a private repository at all.
PRIVATE_REPO_SCOPES = ("repo",)

#: Which scope a given call needs, for the 404 message. Keyed on the label
#: passed to `_check`.
SCOPE_FOR_CALL = {
    "create webhook": "admin:repo_hook (or repo)",
    "delete webhook": "admin:repo_hook (or repo)",
    "commit file": "workflow",
    "delete file": "workflow",
    "get repo public key": "repo",
    "put actions secret": "repo",
    "delete actions secret": "repo",
}


def parse_scopes(header: str | None) -> set[str]:
    """The X-OAuth-Scopes header GitHub returns on every API response."""
    if not header:
        return set()
    return {scope.strip() for scope in header.split(",") if scope.strip()}


def has_scope(granted: set[str] | None, alternatives: tuple[str, ...]) -> bool:
    """Whether any of `alternatives` was granted.

    Unknown scopes (we have not made a call yet, or GitHub sent no header) count
    as satisfied: GitHub is the authority, and guessing "no" here would block a
    request that would actually have worked.
    """
    if not granted:
        return True
    return any(alternative in granted for alternative in alternatives)


def missing_scope_message(alternatives: tuple[str, ...], what: str) -> str:
    return (
        "Your GitHub sign-in is missing the `%s` scope, which is required to %s. "
        "Sign out and sign in again to re-authorise with the wider scope. (If you "
        "run this dashboard yourself, set VITE_GITHUB_SCOPES to "
        "`repo,workflow` and redeploy it.)" % (alternatives[0], what)
    )

# Zipballs redirect to codeload; the download must follow that.
DOWNLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)

CHUNK = 64 * 1024


class GitHubError(RuntimeError):
    """A GitHub call failed. The message is safe to show the user."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        scope_hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        #: The OAuth scope this call needed, when the failure looks like a
        #: missing one. Set here so `routers/_errors.py` can answer 403 - the
        #: honest status - instead of forwarding GitHub's misleading 404 or a
        #: blanket 502. None means the failure was not about permissions.
        self.scope_hint = scope_hint


@dataclass(frozen=True)
class Repo:
    full_name: str
    default_branch: str
    private: bool
    can_admin: bool  # needed to create a webhook
    can_push: bool   # needed to commit a workflow file
    html_url: str


def split_repo(full_name: str) -> tuple[str, str]:
    """"owner/name" -> ("owner", "name"), rejecting anything else."""
    cleaned = (full_name or "").strip().strip("/")
    if cleaned.startswith("https://github.com/"):
        cleaned = cleaned[len("https://github.com/") :]
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]

    parts = cleaned.split("/")
    if len(parts) != 2 or not all(parts):
        raise GitHubError("Repository must be in the form owner/name.")
    owner, name = parts
    for part in (owner, name):
        if not all(char.isalnum() or char in "-._" for char in part):
            raise GitHubError("Repository must be in the form owner/name.")
    return owner, name


def seal_secret(public_key_base64: str, value: str) -> str:
    """libsodium sealed box, as GitHub's Actions secrets API requires.

    The repo's public key encrypts the value; only GitHub can open it. This is
    how a deploy token gets into a repository without us ever storing it.
    """
    key = public.PublicKey(public_key_base64.encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(key).encrypt(value.encode())
    return base64.b64encode(sealed).decode()


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._token = token
        #: Populated from X-OAuth-Scopes on the first response. This is what
        #: GitHub actually granted, which is not necessarily what we asked for.
        self.granted_scopes: set[str] = set()
        self._client = httpx.AsyncClient(
            base_url=API,
            timeout=TIMEOUT,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": ACCEPT,
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "minivercel",
            },
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- internals ---------------------------------------------------------

    def _note_scopes(self, response: httpx.Response) -> None:
        scopes = parse_scopes(response.headers.get("x-oauth-scopes"))
        if scopes:
            self.granted_scopes = scopes

    def _check(self, response: httpx.Response, what: str) -> httpx.Response:
        self._note_scopes(response)
        if 200 <= response.status_code < 300:
            return response

        try:
            message = response.json().get("message") or response.text[:200]
        except ValueError:
            message = response.text[:200]

        needed = SCOPE_FOR_CALL.get(what)
        scope_hint = None

        if response.status_code == 401:
            message = "GitHub rejected the stored token. Reconnect GitHub and try again."
        elif response.status_code == 403 and "rate limit" in message.lower():
            message = "GitHub API rate limit reached. Try again shortly."
        elif response.status_code == 403:
            # A real 403: the resource exists and this token may not touch it.
            # If we know which scope the call needs, that is almost always why.
            if needed:
                scope_hint = needed
                message = (
                    "GitHub refused this call. The sign-in is missing the `%s` "
                    "scope, which is required to %s. Sign out and sign in again "
                    "to re-authorise with the wider scope. (If you run this "
                    "dashboard yourself, set VITE_GITHUB_SCOPES to "
                    "`repo,workflow` and redeploy it.)" % (needed, what)
                )
            else:
                message = (
                    "GitHub refused this call: %s. You may not have admin access "
                    "to this repository." % message
                )
        elif response.status_code == 404:
            # GitHub returns 404 rather than 403 when a token lacks a scope, so
            # this one status covers both "does not exist" and "not allowed".
            # Naming the scope the *specific* call needs beats a blanket guess:
            # telling someone to add `repo` when the real problem is `workflow`
            # sends them round the loop a second time.
            if needed:
                scope_hint = needed
                message = (
                    "GitHub returned 404 for this call. That almost always means "
                    "the sign-in is missing the `%s` scope rather than that the "
                    "repository is gone - GitHub reports a missing scope as 404. "
                    "Sign out and sign in again to re-authorise with the wider "
                    "scope. (If you run this dashboard yourself, set "
                    "VITE_GITHUB_SCOPES to `repo,workflow` and redeploy it.)"
                    % needed
                )
            else:
                message = (
                    "Not found on GitHub, or the token cannot see it. A private "
                    "repository needs the `repo` scope; sign out and sign in "
                    "again to re-authorise."
                )

        log.warning("%s failed: %s %s", what, response.status_code, message)
        raise GitHubError(message, response.status_code, scope_hint=scope_hint)

    # -- repositories ------------------------------------------------------

    async def get_repo(self, owner: str, name: str) -> Repo:
        response = self._check(
            await self._client.get("/repos/%s/%s" % (owner, name)), "get repo"
        )
        body = response.json()
        permissions = body.get("permissions") or {}
        return Repo(
            full_name=body["full_name"],
            default_branch=body.get("default_branch") or "main",
            private=bool(body.get("private")),
            can_admin=bool(permissions.get("admin")),
            can_push=bool(permissions.get("push")),
            html_url=body.get("html_url", ""),
        )

    async def list_repos(self, limit: int = 100) -> list[dict]:
        """Repos the user can push to, most recently pushed first."""
        response = self._check(
            await self._client.get(
                "/user/repos",
                params={
                    "sort": "pushed",
                    "direction": "desc",
                    "per_page": min(limit, 100),
                    "affiliation": "owner,collaborator,organization_member",
                },
            ),
            "list repos",
        )
        return [
            {
                "full_name": row["full_name"],
                "private": bool(row.get("private")),
                "default_branch": row.get("default_branch") or "main",
                "pushed_at": row.get("pushed_at"),
                "description": row.get("description"),
            }
            for row in response.json()
            if (row.get("permissions") or {}).get("push")
        ]

    async def download_zipball(self, owner: str, name: str, ref: str, dest: str) -> int:
        """Stream `GET /repos/{owner}/{name}/zipball/{ref}` to a file.

        Streamed, and capped by the caller deleting the file if validation later
        rejects it: a repository can be far larger than our 50 MB deployment cap
        and must never be held in memory on a 512 MB dyno.
        """
        url = "%s/repos/%s/%s/zipball/%s" % (API, owner, name, ref)
        written = 0
        async with httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT,
            follow_redirects=True,  # zipballs redirect to codeload.github.com
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": ACCEPT,
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "minivercel",
            },
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code >= 300:
                    await response.aread()
                    self._check(response, "download zipball")
                with open(dest, "wb") as sink:
                    async for chunk in response.aiter_bytes(CHUNK):
                        written += len(chunk)
                        sink.write(chunk)
        return written

    # -- webhooks ----------------------------------------------------------

    async def create_push_webhook(
        self, owner: str, name: str, url: str, secret: str
    ) -> int:
        response = self._check(
            await self._client.post(
                "/repos/%s/%s/hooks" % (owner, name),
                json={
                    "name": "web",
                    "active": True,
                    "events": ["push"],
                    "config": {
                        "url": url,
                        "content_type": "json",
                        "secret": secret,
                        "insecure_ssl": "0",
                    },
                },
            ),
            "create webhook",
        )
        return int(response.json()["id"])

    async def delete_webhook(self, owner: str, name: str, hook_id: int) -> None:
        response = await self._client.delete(
            "/repos/%s/%s/hooks/%s" % (owner, name, hook_id)
        )
        if response.status_code == 404:
            return  # already gone; deleting is idempotent
        self._check(response, "delete webhook")

    # -- contents (workflow file) ------------------------------------------

    async def get_file_sha(self, owner: str, name: str, path: str, ref: str) -> str | None:
        response = await self._client.get(
            "/repos/%s/%s/contents/%s" % (owner, name, path), params={"ref": ref}
        )
        if response.status_code == 404:
            return None
        self._check(response, "get file")
        body = response.json()
        return body.get("sha") if isinstance(body, dict) else None

    async def put_file(
        self,
        owner: str,
        name: str,
        path: str,
        content: str,
        message: str,
        branch: str,
    ) -> None:
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        existing = await self.get_file_sha(owner, name, path, branch)
        if existing:
            payload["sha"] = existing  # required to update rather than create
        self._check(
            await self._client.put(
                "/repos/%s/%s/contents/%s" % (owner, name, path), json=payload
            ),
            "commit file",
        )

    async def delete_file(
        self, owner: str, name: str, path: str, message: str, branch: str
    ) -> None:
        sha = await self.get_file_sha(owner, name, path, branch)
        if sha is None:
            return
        self._check(
            await self._client.request(
                "DELETE",
                "/repos/%s/%s/contents/%s" % (owner, name, path),
                json={"message": message, "sha": sha, "branch": branch},
            ),
            "delete file",
        )

    # -- Actions secrets ---------------------------------------------------

    async def put_actions_secret(
        self, owner: str, name: str, secret_name: str, value: str
    ) -> None:
        key = self._check(
            await self._client.get("/repos/%s/%s/actions/secrets/public-key" % (owner, name)),
            "get repo public key",
        ).json()

        self._check(
            await self._client.put(
                "/repos/%s/%s/actions/secrets/%s" % (owner, name, secret_name),
                json={
                    "encrypted_value": seal_secret(key["key"], value),
                    "key_id": key["key_id"],
                },
            ),
            "put actions secret",
        )

    async def delete_actions_secret(self, owner: str, name: str, secret_name: str) -> None:
        response = await self._client.delete(
            "/repos/%s/%s/actions/secrets/%s" % (owner, name, secret_name)
        )
        if response.status_code == 404:
            return
        self._check(response, "delete actions secret")
