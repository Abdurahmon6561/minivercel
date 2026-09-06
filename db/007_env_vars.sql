-- Build-time environment variables for a project.
--
-- Numbered 007, not 005: 005_github_integration.sql and 006_phase5.sql already
-- exist. The 005 in the plan was written before those landed.
--
-- These are secrets. A user will put an API token in here, so the row is
-- treated the same way `github_tokens` is (004):
--
--   * The value is encrypted before it is written, with the same Fernet key
--     and the same helper (app/crypto.py). A database dump is ciphertext.
--   * RLS is enabled with NO policy. That is deliberate: with no policy every
--     client-side role is denied outright, and service_role - which the API
--     uses - bypasses RLS. Nothing holding an anon or user JWT can read these
--     rows even knowing the id. Ownership is enforced in the API, which
--     resolves the project by (slug, owner_id) before it touches this table.
--   * No endpoint ever returns the plaintext. `GET .../env` masks every value
--     to its first two characters. The decrypted value leaves the server only
--     into the build runner, over the build-token endpoint added later.
--
-- The key format (^[A-Z_][A-Z0-9_]*$) is enforced in the API rather than by a
-- CHECK constraint, so that a rejected key produces a 422 naming the rule
-- instead of a constraint-violation 500. The length cap is here because a
-- column type is the honest place for it.

create table if not exists project_env_vars (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid not null references projects(id) on delete cascade,
  key               text not null check (char_length(key) between 1 and 64),
  value_encrypted   text not null,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

-- One value per name per project. This is what makes POST able to answer 409
-- rather than silently creating a second KEY that shadows the first.
create unique index if not exists project_env_vars_project_key_idx
  on project_env_vars (project_id, key);

-- Every read is "all variables for this project", so the unique index above
-- already covers the lookup. No second index.

alter table project_env_vars enable row level security;

-- Intentionally no policies. See above.

comment on table project_env_vars is
  'Per-project build environment variables, values encrypted at rest with '
  'GITHUB_TOKEN_KEY. service_role access only - RLS is on with no policy, '
  'which denies every client role. Ownership is enforced in the API.';
