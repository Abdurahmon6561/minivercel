#!/usr/bin/env python
"""Re-point every imported project's webhook and workflow at PUBLIC_BASE_URL.

Run this once, right after changing PUBLIC_BASE_URL - which is exactly what
the getdropbin.xyz migration does (AUTODEPLOY.md section 1): PUBLIC_BASE_URL
moves from `https://minivercel.onrender.com` to `https://api.getdropbin.xyz`.

Site URLs themselves need no migration: app/urls.py reads PUBLIC_BASE_URL /
URL_MODE / SITE_DOMAIN fresh on every call, so `site_url()` already returns
the new form for every project the moment the environment variable changes.
What this script exists for is the two things that get BAKED IN at a point in
time and never read PUBLIC_BASE_URL again on their own:

  * the webhook GitHub calls on every push, registered with the OLD URL
    (app/gitops.py's `import_repo`, at import time)
  * the `.github/workflows/minivercel.yml` file committed to the user's own
    repository, whose `curl` calls hard-code the OLD URL as text
    (app/gitops.py's `render_workflow`, at the moment builds were enabled)

A project imported or built *after* the environment variable changes already
gets the new value - see app/gitops.py. This script is only for projects that
predate the change.

Usage:

    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... GITHUB_TOKEN_KEY=... \\
    PUBLIC_BASE_URL=https://api.getdropbin.xyz \\
    python scripts/reimport_all.py [--dry-run] [--limit N]

Set every environment variable the running server itself needs (see
.env.example) - this script loads app/config.py's Settings exactly the way
app/main.py does, and reads GitHub OAuth tokens the same way the API does
(decrypted with GITHUB_TOKEN_KEY, one per project owner).

Safe to re-run: every project is independent, a project with nothing to
change is skipped, and a project that fails (revoked GitHub token, deleted
repository, missing scope) is reported and does not stop the rest.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import deps  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.crypto import EncryptionUnavailable, decrypt  # noqa: E402
from app.github import GitHubError, split_repo  # noqa: E402
from app.gitops import (  # noqa: E402
    WORKFLOW_PATH,
    GitOpsError,
    client_for_user,
    render_workflow,
    validate_build_settings,
)
from app.store import PROJECT_COLUMNS, Store  # noqa: E402
from app.urls import api_base_url, webhook_url  # noqa: E402

GREEN, RED, YELLOW, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


async def _reimport_one(store: Store, settings, project: dict, *, dry_run: bool) -> tuple[str, str]:
    """(outcome, detail). outcome is one of updated / skipped / failed."""
    repo_full_name = project.get("repo_full_name")
    if not repo_full_name:
        return "skipped", "not linked to a GitHub repository"

    try:
        owner, name = split_repo(repo_full_name)
    except GitHubError as exc:
        return "failed", "bad repo_full_name %r: %s" % (repo_full_name, exc)

    needs_webhook = bool(project.get("webhook_id") and project.get("webhook_secret"))
    needs_workflow = bool(project.get("builds_enabled"))
    if not needs_webhook and not needs_workflow:
        return "skipped", "no webhook or workflow on file for this project"

    try:
        client = await client_for_user(store, settings, project["owner_id"])
    except GitOpsError as exc:
        return "failed", "GitHub not connected for the owner: %s" % exc

    changed: list[str] = []
    try:
        # -- webhook ---------------------------------------------------------
        if needs_webhook:
            try:
                secret = decrypt(project["webhook_secret"], settings)
            except EncryptionUnavailable:
                return (
                    "failed",
                    "webhook secret cannot be decrypted - has GITHUB_TOKEN_KEY "
                    "rotated since this project was imported?",
                )
            new_webhook_url = webhook_url(settings)
            try:
                if not dry_run:
                    await client.update_webhook_url(
                        owner, name, int(project["webhook_id"]), new_webhook_url, secret
                    )
                changed.append("webhook -> " + new_webhook_url)
            except GitHubError as exc:
                return "failed", "webhook update failed: %s" % exc

        # -- workflow file, only if builds are actually enabled --------------
        if needs_workflow:
            branch = project.get("repo_branch") or "main"
            build_command = project.get("build_command") or "npm run build"
            output_dir = project.get("output_dir") or "dist"
            try:
                validate_build_settings(build_command, output_dir)
            except GitOpsError as exc:
                return "failed", "stored build settings are no longer valid: %s" % exc

            new_api_base = api_base_url(settings)
            try:
                if not dry_run:
                    await client.put_file(
                        owner,
                        name,
                        WORKFLOW_PATH,
                        render_workflow(
                            branch=branch,
                            build_command=build_command,
                            output_dir=output_dir,
                            api_base_url=new_api_base,
                            slug=project["slug"],
                        ),
                        "Update MiniVercel deploy workflow (PUBLIC_BASE_URL changed)",
                        branch,
                    )
                changed.append("workflow -> " + new_api_base)
            except GitHubError as exc:
                return "failed", "workflow commit failed: %s" % exc
    finally:
        await client.aclose()

    return "updated", ", ".join(changed)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-point every imported project's webhook and workflow "
        "at the current PUBLIC_BASE_URL."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without calling GitHub or writing anything.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum number of projects to scan (default: 1000).",
    )
    args = parser.parse_args()

    settings = get_settings()
    try:
        settings.require_configured()
    except RuntimeError as exc:
        print("%s%s%s" % (RED, exc, OFF), file=sys.stderr)
        return 2

    print("PUBLIC_BASE_URL = %s" % settings.public_base_url)
    print("URL_MODE        = %s" % settings.url_mode)
    print("webhook_url()   = %s" % webhook_url(settings))
    print("api_base_url()  = %s" % api_base_url(settings))
    if args.dry_run:
        print("%s(dry run - nothing will be written to GitHub)%s" % (YELLOW, OFF))
    print()

    store = deps.get_store()
    try:
        # PROJECT_COLUMNS (app/store.py) is every column a project row can
        # carry, including the webhook and build fields store.all_projects()
        # deliberately narrows away for the GC sweep it was built for.
        projects = await store.db.select(
            "projects",
            {
                "select": PROJECT_COLUMNS,
                "repo_full_name": "not.is.null",
                "order": "created_at.asc",
                "limit": str(args.limit),
            },
        )

        if not projects:
            print("No GitHub-imported projects found. Nothing to do.")
            return 0

        counts = {"updated": 0, "skipped": 0, "failed": 0}
        for project in projects:
            outcome, detail = await _reimport_one(store, settings, project, dry_run=args.dry_run)
            counts[outcome] += 1
            color = {"updated": GREEN, "skipped": DIM, "failed": RED}[outcome]
            print(
                "%s%-8s%s %-30s %s"
                % (color, outcome, OFF, project["slug"], detail)
            )

        print()
        print(
            "%d updated, %d skipped, %d failed (out of %d GitHub-imported project(s))"
            % (counts["updated"], counts["skipped"], counts["failed"], len(projects))
        )
        if counts["failed"]:
            print(
                "%sSome projects need attention above - most often a revoked "
                "GitHub token or a missing scope. Re-running this script is "
                "safe once that is fixed.%s" % (YELLOW, OFF)
            )
        return 1 if counts["failed"] else 0
    finally:
        await deps.shutdown()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
