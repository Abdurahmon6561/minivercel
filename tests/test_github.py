"""Phase 3 import and Phase 4 builds.

GitHub itself is stubbed at the HTTP layer with an httpx MockTransport, so these
exercise our real client code — URLs, headers, payload shapes, error mapping —
without a network or a repository.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from nacl import encoding, public

from app import deploytoken, gitops
from app.config import get_settings
from app.crypto import decrypt
from app.github import (
    HOOK_SCOPES,
    WORKFLOW_SCOPES,
    GitHubClient,
    GitHubError,
    has_scope,
    parse_scopes,
    seal_secret,
    split_repo,
)
from app.store import slugify
from app.zipvalidate import ZipEntry, select_site_root

from .conftest import auth_headers, make_zip

REPO = "octocat/hello-world"

# A throwaway keypair standing in for a repository's Actions public key.
_SECRET_KEY = public.PrivateKey.generate()
REPO_PUBLIC_KEY = _SECRET_KEY.public_key.encode(encoding.Base64Encoder()).decode()


# -- helpers ------------------------------------------------------------------


def repo_zipball(files: dict[str, str], *, wrapper="octocat-hello-world-abc1234") -> bytes:
    """A zipball shaped the way GitHub actually produces one."""
    return make_zip({"%s/%s" % (wrapper, path): body for path, body in files.items()})


class FakeGitHub:
    """Records calls and serves canned responses over httpx.MockTransport."""

    def __init__(self, *, zipball: bytes | None = None, can_admin=True, can_push=True):
        self.calls: list[tuple[str, str]] = []
        self.secrets: dict[str, str] = {}
        self.files: dict[str, str] = {}
        self.hooks: dict[int, dict] = {}
        self.deleted_hooks: list[int] = []
        self.zipball = zipball if zipball is not None else repo_zipball(
            {"index.html": "<h1>from github</h1>"}
        )
        self.can_admin = can_admin
        self.can_push = can_push
        self._next_hook_id = 4242
        #: What GitHub reports as granted, via X-OAuth-Scopes on every response.
        self.scopes = "repo,workflow"
        self.fail_hook_with_404 = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        response = self._route(request)
        # GitHub returns the granted scopes on every API response.
        response.headers["X-OAuth-Scopes"] = self.scopes
        return response

    def _route(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))

        if path == "/repos/octocat/hello-world" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "full_name": REPO,
                    "default_branch": "main",
                    "private": False,
                    "html_url": "https://github.com/" + REPO,
                    "permissions": {"admin": self.can_admin, "push": self.can_push},
                },
            )

        if path.endswith("/zipball/main") or "/zipball/" in path:
            return httpx.Response(200, content=self.zipball)

        if path.endswith("/hooks") and request.method == "POST":
            if self.fail_hook_with_404:
                # What GitHub actually does for a missing hook scope.
                return httpx.Response(404, json={"message": "Not Found"})
            hook_id = self._next_hook_id
            self._next_hook_id += 1
            self.hooks[hook_id] = json.loads(request.content)
            return httpx.Response(201, json={"id": hook_id})

        if "/hooks/" in path and request.method == "DELETE":
            self.deleted_hooks.append(int(path.rsplit("/", 1)[1]))
            return httpx.Response(204)

        if "/hooks/" in path and request.method == "PATCH":
            hook_id = int(path.rsplit("/", 1)[1])
            if hook_id not in self.hooks:
                return httpx.Response(404, json={"message": "Not Found"})
            self.hooks[hook_id]["config"] = json.loads(request.content)["config"]
            return httpx.Response(200, json={"id": hook_id})

        if path.endswith("/actions/secrets/public-key"):
            return httpx.Response(200, json={"key": REPO_PUBLIC_KEY, "key_id": "kid-1"})

        if "/actions/secrets/" in path:
            name = path.rsplit("/", 1)[1]
            if request.method == "PUT":
                self.secrets[name] = json.loads(request.content)["encrypted_value"]
                return httpx.Response(201)
            if request.method == "DELETE":
                self.secrets.pop(name, None)
                return httpx.Response(204)

        if "/contents/" in path:
            file_path = path.split("/contents/", 1)[1]
            if request.method == "GET":
                if file_path in self.files:
                    return httpx.Response(200, json={"sha": "filesha", "path": file_path})
                return httpx.Response(404, json={"message": "Not Found"})
            if request.method == "PUT":
                body = json.loads(request.content)
                self.files[file_path] = base64.b64decode(body["content"]).decode()
                return httpx.Response(201, json={"content": {"sha": "newsha"}})
            if request.method == "DELETE":
                self.files.pop(file_path, None)
                return httpx.Response(200, json={})

        if path == "/user/repos":
            return httpx.Response(
                200,
                json=[
                    {
                        "full_name": REPO,
                        "private": False,
                        "default_branch": "main",
                        "pushed_at": "2026-01-01T00:00:00Z",
                        "description": "hi",
                        "permissions": {"push": True},
                    },
                    {
                        "full_name": "someone/read-only",
                        "private": False,
                        "default_branch": "main",
                        "pushed_at": "2026-01-01T00:00:00Z",
                        "description": None,
                        "permissions": {"push": False},
                    },
                ],
            )

        return httpx.Response(404, json={"message": "Not Found"})

    def open_secret(self, name: str) -> str:
        """Decrypt what we sealed, the way GitHub would."""
        sealed = base64.b64decode(self.secrets[name])
        return public.SealedBox(_SECRET_KEY).decrypt(sealed).decode()


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    transport = httpx.MockTransport(fake.handler)

    original_init = GitHubClient.__init__

    def patched_init(self, token: str) -> None:
        original_init(self, token)
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com",
            transport=transport,
            headers={"Authorization": "Bearer " + token},
        )

    monkeypatch.setattr(GitHubClient, "__init__", patched_init)

    async def patched_download(self, owner, name, ref, dest):
        with open(dest, "wb") as handle:
            handle.write(fake.zipball)
        fake.calls.append(("GET", "/repos/%s/%s/zipball/%s" % (owner, name, ref)))
        return len(fake.zipball)

    monkeypatch.setattr(GitHubClient, "download_zipball", patched_download)
    return fake


async def connect_github(client, supabase):
    """Store an encrypted provider token, as the Phase 2 dashboard does."""
    response = await client.post(
        "/api/me/github-token",
        headers=auth_headers(),
        json={"provider_token": "gho_" + "x" * 36, "scopes": "public_repo"},
    )
    assert response.status_code == 204


# -- pure helpers -------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("octocat/hello-world", ("octocat", "hello-world")),
        ("https://github.com/octocat/hello-world", ("octocat", "hello-world")),
        ("https://github.com/octocat/hello-world.git", ("octocat", "hello-world")),
        ("  octocat/hello-world  ", ("octocat", "hello-world")),
    ],
)
def test_split_repo_accepts_the_usual_forms(value, expected):
    assert split_repo(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "octocat", "a/b/c", "octocat/", "/hello", "octo cat/repo", "../../etc/passwd"],
)
def test_split_repo_rejects_everything_else(value):
    with pytest.raises(GitHubError):
        split_repo(value)


def test_seal_secret_is_openable_only_with_the_private_key():
    sealed = seal_secret(REPO_PUBLIC_KEY, "mvd_secret_value")
    opened = public.SealedBox(_SECRET_KEY).decrypt(base64.b64decode(sealed))
    assert opened.decode() == "mvd_secret_value"
    assert "mvd_secret_value" not in sealed


# -- site root selection (SPEC.md Phase 3 step 4) -----------------------------


def entries(*paths: str) -> list[ZipEntry]:
    return [ZipEntry(name=p, path=p, size=10) for p in paths]


def test_root_index_html_wins():
    got, root = select_site_root(entries("index.html", "dist/index.html"))
    assert root is None
    assert len(got) == 2


@pytest.mark.parametrize("directory", ["dist", "build", "public", "_site"])
def test_each_build_output_directory_is_found(directory):
    got, root = select_site_root(
        entries("package.json", "src/main.js", "%s/index.html" % directory, "%s/a.css" % directory)
    )
    assert root == directory
    assert sorted(e.path for e in got) == ["a.css", "index.html"]


def test_the_first_matching_directory_wins():
    got, root = select_site_root(entries("build/index.html", "dist/index.html"))
    assert root == "dist", "dist is checked before build"
    assert [e.path for e in got] == ["index.html"]


def test_source_files_outside_the_output_directory_are_dropped():
    got, _ = select_site_root(
        entries("package.json", "node_modules/x/y.js", "dist/index.html")
    )
    assert [e.path for e in got] == ["index.html"]


def test_no_static_output_leaves_entries_alone():
    got, root = select_site_root(entries("package.json", "src/main.js"))
    assert root is None
    assert len(got) == 2


# -- import -------------------------------------------------------------------


async def test_import_creates_project_webhook_and_first_deployment(
    client, supabase, github
):
    await connect_github(client, supabase)

    response = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["repo_full_name"] == REPO
    assert body["repo_branch"] == "main"
    assert body["auto_deploy_enabled"] is True
    assert body["builds_enabled"] is False

    project = supabase.tables["projects"][0]
    assert project["webhook_id"] == 4242
    # The webhook secret is stored encrypted, never in the clear.
    assert project["webhook_secret"]
    assert len(decrypt(project["webhook_secret"], get_settings())) == 64

    # A first deploy ran without anyone pushing (SPEC.md Phase 3).
    assert len(supabase.tables["deployments"]) == 1
    assert supabase.tables["deployments"][0]["status"] == "ready"
    assert any(key.endswith("/index.html") for key in supabase.objects)


async def test_import_derives_the_slug_from_the_repository_name(
    client, supabase, github
):
    """The default: no slug sent, so the repository name is slugified."""
    await connect_github(client, supabase)

    response = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
    )
    assert response.status_code == 201, response.text
    assert supabase.tables["projects"][0]["slug"] == slugify(REPO.split("/")[1])


async def test_import_accepts_an_explicit_slug(client, supabase, github):
    """The import screen lets someone fix the derived name before creating it."""
    await connect_github(client, supabase)

    response = await client.post(
        "/api/projects/import",
        headers=auth_headers(),
        json={"repo": REPO, "slug": "my-chosen-name"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["slug"] == "my-chosen-name"
    assert supabase.tables["projects"][0]["slug"] == "my-chosen-name"


async def test_import_normalises_a_slug_before_using_it(client, supabase, github):
    await connect_github(client, supabase)

    response = await client.post(
        "/api/projects/import",
        headers=auth_headers(),
        json={"repo": REPO, "slug": "  MiXeD-Case  "},
    )
    assert response.status_code == 201, response.text
    assert response.json()["slug"] == "mixed-case"


async def test_import_blank_slug_falls_back_to_the_derived_one(client, supabase, github):
    """An empty field is "I did not choose", not "use an empty slug"."""
    await connect_github(client, supabase)

    response = await client.post(
        "/api/projects/import",
        headers=auth_headers(),
        json={"repo": REPO, "slug": "   "},
    )
    assert response.status_code == 201, response.text
    assert response.json()["slug"] == slugify(REPO.split("/")[1])


@pytest.mark.parametrize(
    "bad", ["ab", "Has Space", "under_score", "-leading", "trailing-", "x" * 64]
)
async def test_import_rejects_a_malformed_slug(client, supabase, github, bad):
    """422, not 409: this is a bad request, not a collision."""
    await connect_github(client, supabase)

    response = await client.post(
        "/api/projects/import",
        headers=auth_headers(),
        json={"repo": REPO, "slug": bad},
    )
    assert response.status_code == 422, response.text
    # Nothing was created on the way to rejecting it.
    assert supabase.tables["projects"] == []


async def test_import_reports_a_taken_slug_rather_than_moving_it(
    client, supabase, github
):
    """An explicit slug is a request, not a suggestion.

    The zip flow appends a suffix when a generated slug collides; an explicit
    one must not be silently relocated, or the URL someone was shown in the
    preview is not the URL they get.
    """
    await connect_github(client, supabase)
    first = await client.post(
        "/api/projects/import",
        headers=auth_headers(),
        json={"repo": REPO, "slug": "taken-name"},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/projects/import",
        headers=auth_headers(),
        json={"repo": REPO, "slug": "taken-name"},
    )
    assert second.status_code == 409
    assert "already taken" in second.json()["detail"]


async def test_import_strips_githubs_wrapper_directory(client, supabase, github):
    """GitHub wraps everything in {owner}-{repo}-{sha}/."""
    github.zipball = repo_zipball({"index.html": "hi", "assets/a.css": "body{}"})
    await connect_github(client, supabase)
    await client.post("/api/projects/import", headers=auth_headers(), json={"repo": REPO})

    deployment_id = supabase.tables["deployments"][0]["id"]
    assert set(supabase.objects) == {
        deployment_id + "/index.html",
        deployment_id + "/assets/a.css",
    }


async def test_import_finds_dist_when_there_is_no_root_index(client, supabase, github):
    github.zipball = repo_zipball(
        {"package.json": "{}", "src/main.js": "//", "dist/index.html": "built"}
    )
    await connect_github(client, supabase)
    await client.post("/api/projects/import", headers=auth_headers(), json={"repo": REPO})

    deployment = supabase.tables["deployments"][0]
    assert deployment["status"] == "ready"
    assert set(supabase.objects) == {deployment["id"] + "/index.html"}


async def test_import_with_no_static_output_fails_with_a_useful_message(
    client, supabase, github
):
    github.zipball = repo_zipball({"package.json": "{}", "src/main.js": "//"})
    await connect_github(client, supabase)
    response = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
    )
    assert response.status_code == 201  # the project exists; the deploy failed

    deployment = supabase.tables["deployments"][0]
    assert deployment["status"] == "failed"

    # Phase 5 "error messages": the failure has to name the directories that
    # were actually searched and point at the fix, not merely say no.
    error = deployment["error"]
    assert "No index.html found" in error
    for searched in ("dist/", "build/", "public/", "_site/"):
        assert searched in error, "the message must name every directory tried"
    assert "enable builds" in error.lower()
    assert supabase.objects == {}


async def test_import_without_a_connected_github_account_is_refused(client, supabase):
    response = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
    )
    assert response.status_code == 400
    assert "not connected" in response.json()["detail"].lower()
    assert supabase.tables["projects"] == []


async def test_import_requires_admin_access_for_the_webhook(client, supabase, github):
    github.can_admin = False
    await connect_github(client, supabase)
    response = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
    )
    assert response.status_code == 400
    assert "admin" in response.json()["detail"].lower()
    assert supabase.tables["projects"] == [], "no half-made project may survive"


async def test_import_requires_auth(client):
    assert (
        await client.post("/api/projects/import", json={"repo": REPO})
    ).status_code == 401


async def test_repo_picker_lists_only_pushable_repos(client, supabase, github):
    await connect_github(client, supabase)
    rows = (await client.get("/api/me/github/repos", headers=auth_headers())).json()
    assert [row["full_name"] for row in rows] == [REPO]


# -- webhook maintenance (scripts/reimport_all.py) -----------------------------


async def test_update_webhook_url_keeps_the_same_secret(github):
    """scripts/reimport_all.py's whole job after a PUBLIC_BASE_URL change.

    The secret is asserted, not just the URL: a webhook that silently lost its
    secret would look fine here and fail every signature check in
    app/routers/webhooks.py from the next push on.
    """
    client = GitHubClient("tok")
    hook_id = await client.create_push_webhook(
        "octocat", "hello-world", "https://minivercel.onrender.com/api/webhooks/github", "s3cr3t"
    )

    await client.update_webhook_url(
        "octocat", "hello-world", hook_id, "https://api.getdropbin.xyz/api/webhooks/github", "s3cr3t"
    )

    config = github.hooks[hook_id]["config"]
    assert config["url"] == "https://api.getdropbin.xyz/api/webhooks/github"
    assert config["secret"] == "s3cr3t"
    await client.aclose()


async def test_update_webhook_url_for_a_missing_hook_raises(github):
    client = GitHubClient("tok")
    with pytest.raises(GitHubError):
        await client.update_webhook_url(
            "octocat", "hello-world", 999999, "https://api.getdropbin.xyz/api/webhooks/github", "s"
        )
    await client.aclose()


# -- builds -------------------------------------------------------------------


async def imported(client, supabase, github):
    await connect_github(client, supabase)
    response = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
    )
    assert response.status_code == 201
    return response.json()["slug"]


async def test_enabling_builds_writes_the_secret_and_the_workflow(
    client, supabase, github
):
    slug = await imported(client, supabase, github)
    response = await client.post(
        "/api/projects/%s/builds" % slug, headers=auth_headers()
    )
    assert response.status_code == 200
    assert response.json()["builds_enabled"] is True
    assert response.json()["workflow_path"] == ".github/workflows/minivercel.yml"

    assert "MINIVERCEL_TOKEN" in github.secrets
    assert ".github/workflows/minivercel.yml" in github.files

    workflow = github.files[".github/workflows/minivercel.yml"]
    assert "npm run build" in workflow
    assert "secrets.MINIVERCEL_TOKEN" in workflow
    assert "/api/deployments" in workflow


async def test_only_the_hash_of_the_deploy_token_is_stored(client, supabase, github):
    slug = await imported(client, supabase, github)
    await client.post("/api/projects/%s/builds" % slug, headers=auth_headers())

    raw = github.open_secret("MINIVERCEL_TOKEN")
    assert raw.startswith("mvd_")

    project = supabase.tables["projects"][0]
    assert project["deploy_token_sha256"] == deploytoken.fingerprint(raw)
    assert raw not in json.dumps(project), "the raw token must not be in the row"


async def test_the_raw_deploy_token_appears_in_no_response_body(
    client, supabase, github
):
    """A named requirement."""
    slug = await imported(client, supabase, github)
    enable = await client.post("/api/projects/%s/builds" % slug, headers=auth_headers())
    raw = github.open_secret("MINIVERCEL_TOKEN")

    assert raw not in enable.text
    for path in ("/api/projects", "/api/projects/%s" % slug, "/api/me"):
        response = await client.get(path, headers=auth_headers())
        assert raw not in response.text, path
        assert "deploy_token" not in response.text.lower() or "sha256" not in response.text


async def test_the_raw_deploy_token_appears_in_no_log_line(
    client, supabase, github, caplog
):
    """A named requirement."""
    slug = await imported(client, supabase, github)
    with caplog.at_level("DEBUG"):
        await client.post("/api/projects/%s/builds" % slug, headers=auth_headers())

    raw = github.open_secret("MINIVERCEL_TOKEN")
    for record in caplog.records:
        assert raw not in record.getMessage()
    # It is still correlatable: the redacted form is logged.
    assert any("mvd_…" in record.getMessage() for record in caplog.records)


async def test_disabling_builds_revokes_the_token_and_removes_the_workflow(
    client, supabase, github
):
    slug = await imported(client, supabase, github)
    await client.post("/api/projects/%s/builds" % slug, headers=auth_headers())
    assert github.files

    response = await client.delete(
        "/api/projects/%s/builds" % slug, headers=auth_headers()
    )
    assert response.status_code == 200
    assert supabase.tables["projects"][0]["deploy_token_sha256"] is None
    assert supabase.tables["projects"][0]["builds_enabled"] is False
    assert "MINIVERCEL_TOKEN" not in github.secrets
    assert ".github/workflows/minivercel.yml" not in github.files


async def test_enabling_builds_needs_a_linked_repository(client, supabase):
    await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "Manual", "slug": "manual"}
    )
    response = await client.post("/api/projects/manual/builds", headers=auth_headers())
    assert response.status_code == 400
    assert "not linked" in response.json()["detail"].lower()


# -- deploy tokens as upload credentials --------------------------------------


async def test_a_deploy_token_can_upload_to_its_own_project(client, supabase, github):
    slug = await imported(client, supabase, github)
    await client.post("/api/projects/%s/builds" % slug, headers=auth_headers())
    token = github.open_secret("MINIVERCEL_TOKEN")

    response = await client.post(
        "/api/deployments",
        headers={"Authorization": "Bearer " + token, "X-Commit-Sha": "b" * 40},
        files={"file": ("site.zip", make_zip({"index.html": "built"}), "application/zip")},
    )
    assert response.status_code == 201
    assert response.json()["project"]["slug"] == slug
    assert response.json()["commit_sha"] == "b" * 40


async def test_a_deploy_token_cannot_target_another_project(client, supabase, github):
    slug = await imported(client, supabase, github)
    await client.post("/api/projects/%s/builds" % slug, headers=auth_headers())
    token = github.open_secret("MINIVERCEL_TOKEN")

    other = await client.post(
        "/api/projects", headers=auth_headers(), json={"name": "Other", "slug": "other"}
    )
    other_id = other.json()["id"]

    response = await client.post(
        "/api/deployments",
        headers={"Authorization": "Bearer " + token},
        # Ignored, not honoured: the token *is* the project.
        data={"project_id": other_id, "slug": "other"},
        files={"file": ("site.zip", make_zip({"index.html": "x"}), "application/zip")},
    )
    assert response.status_code == 201
    assert response.json()["project"]["slug"] == slug


@pytest.mark.parametrize(
    "token", ["mvd_totally-made-up", "mvd_", "mvd_" + "a" * 60]
)
async def test_an_unknown_deploy_token_is_rejected(client, token):
    response = await client.post(
        "/api/deployments",
        headers={"Authorization": "Bearer " + token},
        files={"file": ("site.zip", make_zip({"index.html": "x"}), "application/zip")},
    )
    assert response.status_code == 401


async def test_a_revoked_deploy_token_stops_working(client, supabase, github):
    slug = await imported(client, supabase, github)
    await client.post("/api/projects/%s/builds" % slug, headers=auth_headers())
    token = github.open_secret("MINIVERCEL_TOKEN")

    await client.delete("/api/projects/%s/builds" % slug, headers=auth_headers())

    response = await client.post(
        "/api/deployments",
        headers={"Authorization": "Bearer " + token},
        files={"file": ("site.zip", make_zip({"index.html": "x"}), "application/zip")},
    )
    assert response.status_code == 401


async def test_a_deploy_token_cannot_reach_any_other_endpoint(
    client, supabase, github
):
    slug = await imported(client, supabase, github)
    await client.post("/api/projects/%s/builds" % slug, headers=auth_headers())
    token = github.open_secret("MINIVERCEL_TOKEN")
    headers = {"Authorization": "Bearer " + token}

    assert (await client.get("/api/projects", headers=headers)).status_code == 401
    assert (await client.get("/api/me", headers=headers)).status_code == 401
    assert (
        await client.delete("/api/projects/%s" % slug, headers=headers)
    ).status_code == 401
    assert (
        await client.patch(
            "/api/projects/%s" % slug, headers=headers, json={"auto_deploy_enabled": False}
        )
    ).status_code == 401


async def test_a_deploy_token_upload_uses_the_zip_root_not_dist(
    client, supabase, github
):
    """Actions POSTs the *contents* of dist/, so the zip root is the site.

    A repo zipball gets the dist/ search; a deploy-token upload must not, or a
    site that happens to contain a dist/ folder would be deployed from it.
    """
    slug = await imported(client, supabase, github)
    await client.post("/api/projects/%s/builds" % slug, headers=auth_headers())
    token = github.open_secret("MINIVERCEL_TOKEN")

    response = await client.post(
        "/api/deployments",
        headers={"Authorization": "Bearer " + token},
        files={
            "file": (
                "site.zip",
                make_zip({"index.html": "root", "dist/index.html": "nested"}),
                "application/zip",
            )
        },
    )
    assert response.status_code == 201
    deployment_id = response.json()["id"]
    assert supabase.objects[deployment_id + "/index.html"][0] == b"root"


async def test_deploy_from_repo_adopts_a_pre_created_deployment(client, supabase, github):
    """The webhook creates the row before backgrounding the work, so the task
    must finish *that* row rather than opening a second one."""
    from app.config import get_settings as settings_of
    from app.deps import get_store
    from app.gitops import deploy_from_repo

    slug = await imported(client, supabase, github)
    supabase.tables["deployments"].clear()

    store = get_store()
    project = next(p for p in supabase.tables["projects"] if p["slug"] == slug)
    pre = await store.create_deployment(project["id"], "c" * 40)

    returned = await deploy_from_repo(
        store,
        settings_of(),
        project=project,
        commit_sha="c" * 40,
        deployment_id=pre["id"],
    )

    assert returned == pre["id"]
    assert len(supabase.tables["deployments"]) == 1
    assert supabase.tables["deployments"][0]["status"] == "ready"


# -- the workflow file --------------------------------------------------------


def test_rendered_workflow_is_valid_yaml_shape():
    workflow = gitops.render_workflow(
        branch="main",
        build_command="npm run build",
        output_dir="dist",
        api_base_url="https://minivercel.onrender.com",
        slug="demo",
    )
    assert "${{ secrets.MINIVERCEL_TOKEN }}" in workflow
    assert "${{ github.sha }}" in workflow
    assert "branches: [main]" in workflow
    assert "https://minivercel.onrender.com/api/deployments" in workflow
    # We never run npm on our server; the runner does.
    assert "runs-on: ubuntu-latest" in workflow


def test_rendered_workflow_honours_custom_build_settings():
    workflow = gitops.render_workflow(
        branch="release",
        build_command="npm run build:prod",
        output_dir="public",
        api_base_url="https://x.example",
        slug="s",
    )
    assert "branches: [release]" in workflow
    # The build command now pipes into the log file the Phase 5 log step ships,
    # so it is no longer the whole of the `run:` line.
    assert "npm run build:prod 2>&1 | tee -a" in workflow
    assert 'cd "public"' in workflow

    # Phase 5: the log is posted on every run, and a build that never reached
    # the upload step reports itself so the failure is visible in the dashboard.
    assert "if: always()" in workflow
    assert "https://x.example/api/deployments/$DEPLOYMENT_ID/logs" in workflow
    assert "https://x.example/api/deployments/build-failed" in workflow
    assert "tail -n 200" in workflow


def test_rendered_workflow_is_valid_yaml():
    """It is committed to a user's repository; a syntax error there is ours.

    The template is an f-string full of `${{ }}` expressions, backslashes and
    doubled braces, and every one of those is a way to emit YAML that GitHub
    silently refuses to run.
    """
    yaml = pytest.importorskip("yaml")
    parsed = yaml.safe_load(
        gitops.render_workflow(
            branch="main",
            build_command="npm run build",
            output_dir="dist",
            api_base_url="https://x.example",
            slug="blue-forest-4821",
        )
    )
    steps = parsed["jobs"]["build"]["steps"]
    assert [step for step in steps if step.get("if") == "always()"], (
        "the build log step must run even when the build failed"
    )
    upload = next(step for step in steps if step.get("id") == "upload")
    # The response embeds the project, which also has an "id". A greedy match
    # would take that one and post the log against the wrong row.
    assert "jq -r '.id // empty'" in upload["run"]


@pytest.mark.parametrize(
    "command",
    ["npm run build\nrm -rf /", "build && curl evil", "x" * 201, "build`whoami`"],
)
def test_hostile_build_commands_are_rejected(command):
    with pytest.raises(gitops.GitOpsError):
        gitops.validate_build_settings(command, None)


@pytest.mark.parametrize("directory", ["../etc", "/abs", "a/../../b", "di st", "x" * 120])
def test_hostile_output_dirs_are_rejected(directory):
    with pytest.raises(gitops.GitOpsError):
        gitops.validate_build_settings(None, directory)


# -- OAuth scopes -------------------------------------------------------------
#
# GitHub reports a missing scope as 404, not 403, so a too-narrow sign-in is
# indistinguishable from a deleted repository unless the scopes are checked
# directly. These cover that check and the message it produces.


def test_parse_scopes_reads_the_github_header():
    assert parse_scopes("repo, workflow, gist") == {"repo", "workflow", "gist"}
    assert parse_scopes("") == set()
    assert parse_scopes(None) == set()


def test_public_repo_does_not_grant_hooks():
    """The actual cause of "the token does not have access to it".

    Per GitHub's scope docs, public_repo covers code, commit statuses, projects,
    collaborators and deployment statuses - hooks are not in that list.
    """
    assert not has_scope({"public_repo"}, HOOK_SCOPES)
    assert has_scope({"admin:repo_hook"}, HOOK_SCOPES)
    assert has_scope({"repo"}, HOOK_SCOPES)


def test_repo_does_not_imply_workflow():
    """`repo` is not a superset: committing under .github/workflows/ needs
    `workflow` on its own."""
    assert not has_scope({"repo"}, WORKFLOW_SCOPES)
    assert has_scope({"repo", "workflow"}, WORKFLOW_SCOPES)


def test_unknown_scopes_do_not_block():
    """No header means we do not know; GitHub stays the authority."""
    assert has_scope(set(), HOOK_SCOPES)
    assert has_scope(None, WORKFLOW_SCOPES)


async def test_importing_with_public_repo_scope_names_the_missing_scope(
    client, supabase, github
):
    """The reported failure, end to end.

    Before: GitHub 404s the hook call and the user is told the repository may
    not exist. After: they are told which scope is missing.
    """
    github.scopes = "public_repo"
    await connect_github(client, supabase)

    response = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "admin:repo_hook" in detail
    assert "sign in again" in detail.lower()

    # And nothing was half-created.
    assert supabase.tables["projects"] == []
    assert github.hooks == {}


async def test_importing_with_a_hook_scope_succeeds(client, supabase, github):
    github.scopes = "public_repo,admin:repo_hook"
    await connect_github(client, supabase)
    response = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
    )
    assert response.status_code == 201


async def test_enabling_builds_without_workflow_scope_is_refused(
    client, supabase, github
):
    """`repo` is enough to import and still not enough to commit a workflow."""
    github.scopes = "repo"
    await connect_github(client, supabase)
    imported_slug = (
        await client.post(
            "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
        )
    ).json()["slug"]

    response = await client.post(
        "/api/projects/%s/builds" % imported_slug, headers=auth_headers()
    )
    assert response.status_code == 400
    assert "workflow" in response.json()["detail"]

    # Refused before anything was written - no live token for a workflow that
    # was never committed.
    project = supabase.tables["projects"][0]
    assert project["deploy_token_sha256"] is None
    assert project["builds_enabled"] is False
    assert github.files == {}
    assert github.secrets == {}


async def test_a_404_on_a_hook_call_blames_the_scope_not_the_repository(
    client, supabase, github
):
    """If the pre-check is somehow passed, the 404 message still says the right
    thing rather than 'the repository is private'."""
    from app.github import GitHubClient

    github.scopes = "repo,workflow"  # pre-check passes
    github.fail_hook_with_404 = True
    await connect_github(client, supabase)

    response = await client.post(
        "/api/projects/import", headers=auth_headers(), json={"repo": REPO}
    )
    # Phase 5 "error messages": a missing scope is a permission problem, so it
    # is reported as 403 even though GitHub expressed it as 404. Forwarding the
    # 404 told the user their repository was gone when it was sitting there.
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert "admin:repo_hook" in detail
    assert "private" not in detail.lower(), "the old, misleading advice"
    del GitHubClient
