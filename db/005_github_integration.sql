-- Phase 3 + Phase 4: GitHub import, push auto-deploy, and Actions-based builds.
--
-- All additive. Nothing here changes the Phase 1 schema, and every column has a
-- default so existing rows keep working untouched.

alter table projects
  -- Phase 3: where this project came from, and how pushes reach us.
  add column if not exists repo_full_name        text,      -- "owner/name"
  add column if not exists repo_branch           text,
  add column if not exists webhook_id            bigint,
  add column if not exists webhook_secret        text,      -- Fernet-encrypted
  add column if not exists auto_deploy_enabled   boolean not null default true,

  -- Phase 4: builds run on GitHub's runners, never here.
  add column if not exists builds_enabled        boolean not null default false,
  add column if not exists build_command         text not null default 'npm run build',
  add column if not exists output_dir            text not null default 'dist',
  -- sha256(token) only. The raw deploy token is written straight into the
  -- repo's Actions secrets and never persisted here (SPEC.md Phase 4 point 4).
  add column if not exists deploy_token_sha256   text,

  -- So the dashboard can answer "did my push arrive?".
  add column if not exists last_webhook_at       timestamptz,
  add column if not exists last_webhook_status   text,
  add column if not exists last_webhook_detail   text,
  add column if not exists last_webhook_sha      text;

-- A deploy token authenticates by hash lookup on every Actions upload, so this
-- index is on the hot path for Phase 4.
create unique index if not exists projects_deploy_token_sha256_idx
  on projects (deploy_token_sha256)
  where deploy_token_sha256 is not null;

-- The webhook handler finds candidate projects by repository name before it
-- verifies any signature.
create index if not exists projects_repo_full_name_idx
  on projects (repo_full_name)
  where repo_full_name is not null;

-- Phase 3 section 6: a deployment left `pending` is a dead worker, not a slow
-- one. The startup reaper scans for these.
create index if not exists deployments_pending_idx
  on deployments (status, created_at)
  where status = 'pending';

comment on column projects.deploy_token_sha256 is
  'sha256 hex of the per-project deploy token. The token itself is never stored.';
comment on column projects.webhook_secret is
  'Fernet-encrypted HMAC secret for X-Hub-Signature-256 verification.';
comment on column projects.auto_deploy_enabled is
  'When false the webhook stays registered but pushes are recorded and ignored. '
  'Deleting the webhook instead would need the OAuth token to re-register later.';
