-- ============================================================
-- Devil's Lake Mapping Project — precomputed trail loops
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Stores hike-worthy circuits computed offline by
-- scripts/compute_trail_loops.py (bounded, deduplicated simple cycles over the
-- noded trail network — see memory:sauk-trails-noded-network). Each loop is a
-- closed LineString plus distance / segment count / the trail names it uses.
--
-- 1. trail_loops table (public-read RLS, GiST index on geometry).
-- 2. replace_trail_loops(): full-refresh writer, service_role-only (mirrors
--    replace_layer_geometries from migration 057).
-- 3. get_loops_geojson(): FeatureCollection for the front-end (mirrors
--    get_layer_geojson).
-- ============================================================

create table if not exists public.trail_loops (
  id            uuid primary key default gen_random_uuid(),
  geometry      geometry(LineString, 4326) not null,
  distance_mi   numeric(5,2) not null,
  num_segments  int not null,
  trail_names   text[] not null default '{}',
  start_lon     double precision,
  start_lat     double precision,
  properties    jsonb not null default '{}'::jsonb,
  created_at    timestamptz default now()
);

alter table public.trail_loops enable row level security;
drop policy if exists "public read trail_loops" on public.trail_loops;
create policy "public read trail_loops" on public.trail_loops for select using (true);
create index if not exists trail_loops_geom_idx on public.trail_loops using gist (geometry);

create or replace function public.replace_trail_loops(p_features json, p_truncate boolean default true)
returns int language plpgsql security definer set search_path = public, extensions as $fn$
declare f json; n int := 0;
begin
  if p_truncate then delete from trail_loops where true; end if;  -- WHERE: safe-updates guard
  for f in select value from json_array_elements(p_features) loop
    insert into trail_loops (geometry, distance_mi, num_segments, trail_names,
                             start_lon, start_lat, properties)
    values (
      st_geomfromgeojson(f->'geometry'),
      (f->'properties'->>'distance_mi')::numeric,
      (f->'properties'->>'num_segments')::int,
      coalesce((select array_agg(value) from json_array_elements_text(f->'properties'->'trail_names') as value), '{}'),
      (f->'properties'->>'start_lon')::double precision,
      (f->'properties'->>'start_lat')::double precision,
      coalesce((f->'properties')::jsonb, '{}'::jsonb)
    );
    n := n + 1;
  end loop;
  return n;
end;
$fn$;
revoke execute on function public.replace_trail_loops(json, boolean) from public, anon, authenticated;
grant  execute on function public.replace_trail_loops(json, boolean) to service_role;

create or replace function public.get_loops_geojson()
returns json language sql security definer set search_path = public, extensions as $fn$
  select json_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(json_agg(json_build_object(
      'type', 'Feature',
      'id', id,
      'geometry', st_asgeojson(geometry)::json,
      'properties', properties || jsonb_build_object(
        'id', id, 'distance_mi', distance_mi, 'num_segments', num_segments,
        'trail_names', to_jsonb(trail_names))
    )), '[]'::json)
  ) from trail_loops;
$fn$;
grant execute on function public.get_loops_geojson() to anon, authenticated, service_role;