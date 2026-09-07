"""Deleting a project completely.

Extracted from `routers/projects.py` so that deleting an account can delete
every project the same way. Doing it twice would have meant two orderings
drifting apart, and the ordering is the whole point.
"""

from __future__ import annotations

import logging

from .cache import project_cache
from .config import Settings
from .github import GitHubError, split_repo
from .gitops import GitOpsError, client_for_user, disable_builds
from .store import Store

log = logging.getLogger("minivercel.projectops")


async def delete_project_fully(
    store: Store, settings: Settings, user_id: str, project: dict
) -> None:
    """Remove the GitHub wiring, then every storage object, then the row.

    That order is deliberate. Storage is NOT covered by `ON DELETE CASCADE` -
    the database knows nothing about the bucket - so dropping the row first
    would orphan every object with no remaining record of which keys to remove,
    against a 1 GB quota. And a webhook left registered on a deleted project
    delivers pushes to a 401 for ever.

    Nothing GitHub does can stop the deletion. The user asked for their project
    to go; a revoked token or a repository they no longer admin must not make
    that impossible. Those failures are logged and stepped over.

    Environment variables need no step of their own: `project_env_vars` is
    `ON DELETE CASCADE` on `projects`, so the row deletion takes them.
    """
    slug = project["slug"]

    if project.get("repo_full_name"):
        try:
            client = await client_for_user(store, settings, user_id)
            owner, name = split_repo(project["repo_full_name"])
            try:
                if project.get("webhook_id"):
                    await client.delete_webhook(owner, name, int(project["webhook_id"]))
                if project.get("builds_enabled"):
                    # Otherwise a workflow keeps firing at a project that is gone.
                    await disable_builds(store, settings, project)
            finally:
                await client.aclose()
        except (GitOpsError, GitHubError) as exc:
            log.warning("could not clean up GitHub for %s: %s", slug, exc)

    deployments = await store.list_deployments(project["id"], limit=500)
    for deployment in deployments:
        try:
            await store.db.remove_prefix(deployment["id"])
        except Exception:  # pragma: no cover - keep deleting the rest
            log.exception("could not remove objects for deployment %s", deployment["id"])

    await store.delete_project(user_id, project["id"])
    project_cache.invalidate(slug)
