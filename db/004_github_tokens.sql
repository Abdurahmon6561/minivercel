-- Phase 2: storage for the GitHub OAuth provider token.
--
-- SPEC.md Phase 2: "Store the provider token; you'll need it to read repos."
-- Phase 3 calls the GitHub API server-side on the user's behalf, so the token
-- has to reach the server and survive there.
--
-- This is the most sensitive row in the database. A `repo`-scoped token is
-- write access to every repository the user can see, so:
--
--   * RLS is enabled and NO policy is created. That is deliberate, not an
--     oversight: with no policy, every client-side role is denied outright.
--     service_role bypasses RLS, so the API can still read and write it, and
--     nothing holding an anon or user JWT can touch it even with the row's id.
--   * The value is encrypted before it is written (app/crypto.py), so a
--     database dump is not a pile of live GitHub credentials.
--   * No endpoint ever returns it. `GET /api/me` reports whether one exists.

create table if not exists github_tokens (
  user_id           uuid primary key references auth.users(id) on delete cascade,
  encrypted_token   text not null,
  scopes            text,
  github_login      text,
  updated_at        timestamptz not null default now()
);

alter table github_tokens enable row level security;

-- Intentionally no policies. See above.

comment on table github_tokens is
  'GitHub OAuth provider tokens, encrypted at rest. service_role access only - '
  'RLS is on with no policy, which denies every client role.';
