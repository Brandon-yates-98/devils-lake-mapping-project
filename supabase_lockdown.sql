-- Pre-deployment lockdown — run in Supabase: Dashboard → SQL Editor.
-- Closes the public-write holes before the site/repo goes public.

-- 1. The import RPCs are SECURITY DEFINER and, by Postgres default, executable
--    by everyone — including `anon`, whose key ships in the public HTML.
--    Revoke execute from the web-facing roles; imports must then run with the
--    service_role key (op run --env-file=.env.tpl, with the 1Password item
--    pointed at the service key instead of the anon key).
revoke execute on function import_feature(text, json) from public, anon, authenticated;
revoke execute on function import_trail(json)         from public, anon, authenticated;

-- 2. Read RPCs stay public — they're what the map uses. (No change needed;
--    listed here for the record.)
--      get_layer_geojson(text), get_experience_config(text), get_trails_geojson()

-- 3. OPTIONAL but recommended: scope writes to your own account instead of any
--    authenticated user. The current policies pass for ANYONE who signs up.
--    Find your user id: select id, email from auth.users;
--    Then uncomment and fill in:
--
-- drop policy "Auth insert" on osm_geometries;
-- drop policy "Auth update" on osm_geometries;
-- create policy "Owner insert" on osm_geometries for insert
--   with check (auth.uid() = '<YOUR-USER-UUID>');
-- create policy "Owner update" on osm_geometries for update
--   using (auth.uid() = '<YOUR-USER-UUID>');
--    (repeat for the trails table and any other writable tables)

-- 4. NOT SQL — do these in the Dashboard:
--    a. Authentication → Sign In / Up → disable new email signups.
--       Without this, anyone can supabase.auth.signUp() with the anon key and
--       become `authenticated`, passing the write policies in (3).
--    b. Storage → policies: confirm photo-bucket writes require authenticated
--       (and ideally your uid), reads public.
--    c. Mapbox dashboard: URL-restrict the pk. token to your Pages domain,
--       custom domain, and localhost. Create a separate token for scripts
--       (compute_drive_times.py) — URL restrictions don't apply server-side.
