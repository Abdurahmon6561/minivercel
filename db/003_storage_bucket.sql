-- Storage bucket for deployed sites: PUBLIC READ.
--
-- Public read is deliberate and load-bearing (SPEC.md): the browser fetches
-- assets straight from Supabase's CDN and our FastAPI service never touches the
-- bytes. Writes are service_role only - no client-side policy grants insert,
-- update or delete, so the only path to writing an object is through the
-- validated upload pipeline in app/routers/deployments.py.

insert into storage.buckets (id, name, public)
values ('sites', 'sites', true)
on conflict (id) do update set public = true;

-- Anonymous read of deployed site files.
drop policy if exists "public read sites" on storage.objects;
create policy "public read sites" on storage.objects
  for select using (bucket_id = 'sites');

-- Deliberately: no insert/update/delete policy. service_role bypasses RLS.
grep env .gitignore