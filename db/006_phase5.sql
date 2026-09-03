-- Phase 5: rollback, garbage collection and build logs.
--
-- All additive. Nothing here changes an existing column, and the server keeps
-- working (with the feature degraded, never broken) if this file has not been
-- applied yet - see app/store.py `_supports_build_log`.

alter table deployments
  -- The tail of the GitHub Actions build output, POSTed by the workflow to
  -- /api/deployments/{id}/logs with the project's deploy token. Truncated to
  -- the last 200 lines before it is written, because that is where the error
  -- is and because a 500 MB database will not survive whole build logs.
  add column if not exists build_log      text,
  -- Non-null means "a log exists". The deployment list selects this column and
  -- not `build_log`, so listing 50 deployments does not drag 50 logs across the
  -- wire for a panel that is collapsed by default.
  add column if not exists build_log_at   timestamptz;

-- Garbage collection walks deployments per project, newest first: it keeps the
-- live one plus the five most recent *ready* ones, deletes older ready ones
-- after seven days, and removes a failed deployment's objects on sight while
-- keeping its row for seven days (SPEC.md Phase 5, app/gc.py). The Phase 1 index
-- on (project_id, created_at desc) already covers that walk; this one is for the
-- admin sweep, which filters on age across every project.
create index if not exists deployments_created_at_idx
  on deployments (created_at);

comment on column deployments.build_log is
  'Last 200 lines of the GitHub Actions build output. Written only by the '
  'per-project deploy token or the project owner; never executed, only shown.';
comment on column deployments.build_log_at is
  'When the build log was received. Null means no log was ever posted.';
