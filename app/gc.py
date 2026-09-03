"""Garbage collection for deployments, and the stuck-`pending` reaper.

With 1 GB of free Storage this is not optional (SPEC.md Phase 5). Every deploy
writes a fresh copy of the whole site and nothing has ever removed one, so a
project pushed to daily fills the bucket in weeks and then every user's deploy
fails at once.

The retention rules, applied per project:

  1. the live deployment is kept for ever, whatever its age;
  2. the 5 most recent **ready** non-live deployments are kept, whatever their
     age;
  3. any other ready deployment is deleted once it is older than 7 days;
  4. a failed deployment loses its storage objects immediately and its row after
     7 days;
  5. a `pending` deployment is never touched.

Rule 2 counts *ready* deployments and not merely non-live ones, and that
distinction is the whole point of the rule. A failed deployment can never be
promoted, so a project with five failures from this morning and one working
version from last week would - under a plain "five most recent non-live" -
spend all five slots on rows nobody can roll back to and then collect the only
version that still works. Failures must not hold rollback slots.

Rule 4 is the other half. A failed deployment is never served, so any objects a
partial upload left behind are pure waste against the 1 GB. `deployer.fail`
already removes them on the normal path; what it cannot cover is a worker killed
mid-upload, which leaves objects with nothing to clean them and a row the reaper
later marks failed. So the sweep removes a failed deployment's objects on sight,
whatever its age, and keeps the row itself for seven days because that row is
the error message the user is reading.

Rule 5 exists because a `pending` deployment may be uploading *right now*.
Deleting its objects would corrupt a deploy in flight. A dead one becomes
`failed` within ten minutes (`reap_stuck` below) and is then covered by rule 4.

**Storage objects are deleted first, then the row.** That order is the whole
reason this module exists rather than a `delete from deployments`. Postgres has
no idea the bucket exists, so `ON DELETE CASCADE` does not reach it
(AUTODEPLOY.md section 7); a row removed first is a set of object keys nobody
can ever enumerate again, and those bytes are then unreclaimable short of
listing the entire bucket by hand.

Render's free plan has no cron, so this runs in two places, both cheap:

  * opportunistically at the end of every successful deploy, scoped to the one
    project that just deployed - which is also the only project whose deployment
    list just changed;
  * as a full sweep from `POST /api/admin/gc`, guarded by ADMIN_TOKEN.

Nothing here ever raises into a caller. A failed collection is a log line and a
slightly fuller bucket; it must never turn a successful deploy into a failed one.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .cache import manifest_cache
from .store import Store

log = logging.getLogger("minivercel.gc")

#: Ready, non-live deployments kept per project regardless of age. These are the
#: rollback targets, which is why the count is on READY deployments rather than
#: on non-live ones - see rule 2 in the module docstring.
KEEP_RECENT_READY = 5
#: Grace period. A ready deployment past its keep slot, and a failed
#: deployment's row, are removed once older than this.
MAX_AGE_DAYS = 7
#: Ceiling on one project's scan. The 5-keep rule means a project can only grow
#: this list between sweeps, never permanently.
SCAN_LIMIT = 500

#: A stuck-pending reap is a single filtered UPDATE, but it is triggered from
#: read paths the dashboard polls every two seconds. Throttle it process-wide.
REAP_MIN_INTERVAL_SECONDS = 60.0
_last_reap = 0.0


@dataclass
class GCResult:
    """What one collection actually did. Reported by the admin endpoint."""

    deployments_deleted: int = 0
    bytes_reclaimed: int = 0
    #: Storage keys actually removed. Larger than the byte figure implies,
    #: because a failed deployment's `size_bytes` is 0 - it never reached
    #: `mark_deployment_ready` - so objects a partial upload left behind are
    #: counted here and cannot be counted there.
    objects_removed: int = 0
    projects_scanned: int = 0
    errors: list[str] = field(default_factory=list)

    def merge(self, other: "GCResult") -> "GCResult":
        self.deployments_deleted += other.deployments_deleted
        self.bytes_reclaimed += other.bytes_reclaimed
        self.objects_removed += other.objects_removed
        self.projects_scanned += other.projects_scanned
        self.errors.extend(other.errors)
        return self

    def as_dict(self) -> dict:
        return {
            "deployments_deleted": self.deployments_deleted,
            "bytes_reclaimed": self.bytes_reclaimed,
            "objects_removed": self.objects_removed,
            "projects_scanned": self.projects_scanned,
            "errors": self.errors[:20],
        }


@dataclass(frozen=True)
class Action:
    """What to do with one deployment.

    Two independent decisions, because they come apart: a failed deployment
    inside the grace period loses its objects and keeps its row, and no
    deployment ever loses its row while its objects survive.
    """

    deployment: dict
    remove_objects: bool
    remove_row: bool
    reason: str


def parse_timestamp(value: object) -> datetime | None:
    """Postgres timestamptz -> aware datetime, tolerantly.

    PostgREST renders `timestamptz` as ISO 8601, but the offset can arrive as
    `+00:00` or as a bare `Z`, and fractional seconds may carry more digits than
    `fromisoformat` accepted before 3.11. A timestamp we cannot read must not
    make a deployment immortal *or* delete it early, so an unparseable value
    returns None and the caller treats the row as too young to touch.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def plan_collection(
    deployments: list[dict], live_deployment_id: str | None, now: datetime
) -> list[Action]:
    """Apply the retention rules. Pure: it decides, it does not delete.

    `deployments` must be newest first, as `store.list_deployments` returns
    them. Returns one Action per deployment that needs something done to it, and
    nothing for the ones being kept intact.
    """
    cutoff = now - timedelta(days=MAX_AGE_DAYS)
    actions: list[Action] = []
    kept_ready = 0

    for deployment in deployments:
        status = deployment.get("status")

        # Rule 1. Whatever its age, whatever else is true.
        if live_deployment_id and deployment.get("id") == live_deployment_id:
            continue

        # Rule 5. It may be uploading right now; `reap_stuck` deals with a dead
        # one, and it arrives back here as `failed`.
        if status == "pending":
            continue

        created_at = parse_timestamp(deployment.get("created_at"))
        # A timestamp we cannot read fails towards keeping the row. The
        # alternative - treating it as infinitely old - deletes data on a
        # formatting change.
        expired = created_at is not None and created_at <= cutoff

        # Rule 4. Objects now (never served, so pure waste), row after 7 days
        # (it is the error message the user is reading).
        if status == "failed":
            actions.append(Action(deployment, True, expired, "failed"))
            continue

        # Rule 2: the five most recent working versions are the rollback
        # targets, and only a `ready` deployment can be one.
        if kept_ready < KEEP_RECENT_READY:
            kept_ready += 1
            continue

        # Rule 3.
        if expired:
            actions.append(Action(deployment, True, True, "expired"))

    return actions


async def remove_objects(store: Store, deployment_id: str) -> int:
    """Delete every object under this deployment's prefix. Returns how many.

    The same two calls `SupabaseClient.remove_prefix` makes, written out here
    only so the count is available: "3 orphaned objects swept" is the line that
    tells you a worker died mid-upload, and `remove_prefix` returns nothing.
    """
    keys = await store.db.list_prefix(deployment_id)
    if keys:
        await store.db.remove(keys)
    return len(keys)


async def collect_project(store: Store, project: dict, *, now: datetime | None = None) -> GCResult:
    """Collect one project. Never raises."""
    result = GCResult(projects_scanned=1)
    project_id = project.get("id")
    if not project_id:
        return result

    now = now or datetime.now(timezone.utc)
    try:
        deployments = await store.list_deployments(project_id, limit=SCAN_LIMIT)
    except Exception as exc:
        log.warning("gc: could not list deployments for %s: %s", project_id, exc)
        result.errors.append("list failed for project %s" % project_id)
        return result

    for action in plan_collection(deployments, project.get("live_deployment_id"), now):
        deployment_id = action.deployment["id"]

        # Objects first, always. See the module docstring: a row deleted while
        # its objects survive is a set of keys nobody can enumerate again.
        if action.remove_objects:
            try:
                removed = await remove_objects(store, deployment_id)
            except Exception as exc:
                # Leave the row alone: it is the only remaining record of which
                # keys to remove, so the next sweep can try again.
                log.warning(
                    "gc: could not remove objects for %s: %s", deployment_id, exc
                )
                result.errors.append("storage delete failed for %s" % deployment_id)
                continue

            result.objects_removed += removed
            # Only a `ready` deployment has a size; a failed one never reached
            # `mark_deployment_ready`, so its partial objects show up in
            # `objects_removed` and add nothing here.
            result.bytes_reclaimed += int(action.deployment.get("size_bytes") or 0)

            if removed and action.reason == "failed":
                log.info(
                    "gc: swept %d orphaned object(s) from failed deployment %s",
                    removed,
                    deployment_id,
                )

        if action.remove_row:
            try:
                await store.delete_deployment(deployment_id)
            except Exception as exc:
                # The objects are gone but the row survives, so the quota still
                # counts bytes that no longer exist. The next sweep deletes the
                # row - removing objects from an empty prefix is a no-op - and
                # the figure corrects itself.
                log.warning(
                    "gc: removed objects but not the row for %s: %s", deployment_id, exc
                )
                result.errors.append("row delete failed for %s" % deployment_id)
                continue

            manifest_cache.invalidate(deployment_id)
            result.deployments_deleted += 1

    if result.deployments_deleted or result.objects_removed:
        log.info(
            "gc: project %s reclaimed %d bytes, removed %d object(s) and "
            "%d deployment row(s)",
            project.get("slug") or project_id,
            result.bytes_reclaimed,
            result.objects_removed,
            result.deployments_deleted,
        )
    return result


async def collect_all(store: Store) -> GCResult:
    """Sweep every project. Never raises."""
    total = GCResult()
    now = datetime.now(timezone.utc)
    try:
        projects = await store.all_projects()
    except Exception as exc:
        log.warning("gc: could not list projects: %s", exc)
        total.errors.append("project list failed")
        return total

    for project in projects:
        total.merge(await collect_project(store, project, now=now))

    log.info(
        "gc sweep: %d project(s), %d deployment(s) deleted, %d object(s) "
        "removed, %d bytes reclaimed",
        total.projects_scanned,
        total.deployments_deleted,
        total.objects_removed,
        total.bytes_reclaimed,
    )
    return total


async def collect_after_deploy(store: Store, project: dict) -> None:
    """Opportunistic GC, run at the end of a successful deploy.

    Render's free plan has no cron (SPEC.md Phase 5), and this is the moment
    that matters anyway: the project that just deployed is the only one whose
    deployment list changed, and the deploy that pushed it over the keep-5
    threshold is the one that just landed.

    Swallows everything. A deploy that succeeded must not be reported as failed
    because housekeeping afterwards did not.
    """
    try:
        await collect_project(store, project)
    except Exception:  # pragma: no cover - defensive; collect_project catches
        log.exception("gc after deploy failed for %s", project.get("slug"))


# -- stuck pending deployments ------------------------------------------------


async def reap_stuck(store: Store, *, older_than_minutes: int = 10) -> int:
    """Mark long-`pending` deployments failed. Never raises.

    AUTODEPLOY.md section 6: a BackgroundTask runs inside the same worker, and
    Render restarts that worker on deploy, on spin-down and on OOM. A deploy
    interrupted between "insert pending" and "mark ready" leaves a row that will
    never resolve, and the dashboard polls it for ever showing "Building".
    Nothing is retried - the deployment never went live, so the previous one is
    still serving.
    """
    try:
        return await store.reap_stuck_pending(older_than_minutes)
    except Exception as exc:
        log.warning("could not reap stuck deployments: %s", exc)
        return 0


async def maybe_reap(store: Store) -> int:
    """Throttled `reap_stuck`, safe to call from a polled read path.

    The dashboard polls the project detail every two seconds while anything is
    pending, which is exactly when a dead row would be shown - so the reaper has
    to run from there and not only at startup. Once a minute per process is
    enough: the thing it is looking for is at least ten minutes old.
    """
    global _last_reap
    now = time.monotonic()
    if now - _last_reap < REAP_MIN_INTERVAL_SECONDS:
        return 0
    _last_reap = now
    reaped = await reap_stuck(store)
    if reaped:
        log.warning("marked %d stuck pending deployment(s) failed", reaped)
    return reaped


def reset_reap_throttle() -> None:
    """Test seam. Production never calls this."""
    global _last_reap
    _last_reap = 0.0
