-- Additive migration. Not in SPEC.md; here is why it exists.
--
-- The serving flow has to answer "does key X exist in this deployment?" in order
-- to implement clean URLs (`/about` -> `about.html` -> `about/index.html`) and
-- the `404.html` fallback. Without a manifest that means up to three HEAD
-- round-trips to Supabase Storage on every single request, which burns the one
-- resource the free tier actually rations: request latency on a 0.1 CPU dyno.
--
-- A deployment is immutable once `ready`, so its file list is immutable too:
-- store it once at deploy time, cache it in memory forever, and serve with zero
-- storage calls. 500 paths is the hard cap, so the column stays tiny.
--
-- The server degrades gracefully if this migration is not applied: it falls back
-- to HEAD probing. Applying it is strongly recommended.

alter table deployments add column if not exists file_paths text[];

-- Phase 5 garbage collection will want this.
create index if not exists deployments_status_created_at_idx
  on deployments (status, created_at desc);
