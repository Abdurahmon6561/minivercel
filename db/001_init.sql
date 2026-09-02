-- MiniVercel Phase 1 schema. Verbatim from SPEC.md.
-- Run in the Supabase SQL editor.

create table projects (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid references auth.users(id) on delete cascade,
  name        text not null,
  slug        text not null unique,
  created_at  timestamptz not null default now()
);
create index on projects (owner_id);

create table deployments (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references projects(id) on delete cascade,
  status       text not null default 'pending'
               check (status in ('pending','ready','failed')),
  size_bytes   bigint not null default 0,
  file_count   int    not null default 0,
  error        text,
  commit_sha   text,
  created_at   timestamptz not null default now()
);
create index on deployments (project_id, created_at desc);

-- One deployment per project is "live". Simplest correct approach:
alter table projects add column live_deployment_id uuid references deployments(id);

alter table projects    enable row level security;
alter table deployments enable row level security;

create policy "own projects" on projects
  for all using (auth.uid() = owner_id);
create policy "own deployments" on deployments
  for all using (
    exists (select 1 from projects p
            where p.id = deployments.project_id and p.owner_id = auth.uid())
  );
