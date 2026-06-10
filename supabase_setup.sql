-- Run this in Supabase: Dashboard → SQL Editor → New query

-- 1. Enable PostGIS
create extension if not exists postgis;

-- 2. Trails table
create table trails (
  id          uuid primary key default gen_random_uuid(),
  osm_id      bigint,
  name        text,
  highway     text,
  surface     text,
  access      text,
  incline     text,
  geometry    geometry(LineString, 4326) not null,
  photos      text[]   default '{}',
  custom_data jsonb    default '{}',
  updated_at  timestamptz default now()
);

-- 3. Indexes
create index trails_geometry_idx on trails using gist(geometry);
create index trails_osm_id_idx   on trails(osm_id);

-- 4. Auto-update updated_at on every save
create or replace function update_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger trails_updated_at
  before update on trails
  for each row execute function update_updated_at();

-- 5. Row Level Security
alter table trails enable row level security;

create policy "Public read"  on trails for select using (true);
create policy "Auth insert"  on trails for insert with check (auth.role() = 'authenticated');
create policy "Auth update"  on trails for update using (auth.role() = 'authenticated');

-- 6. Import function (used by import_trails.py — accepts a GeoJSON feature, inserts one row)
create or replace function import_trail(feature json)
returns uuid language plpgsql security definer as $$
declare
  props  json;
  new_id uuid;
begin
  props := feature->'properties';
  insert into trails (osm_id, name, highway, surface, access, incline, geometry)
  values (
    (props->>'_osm_id')::bigint,
    props->>'name',
    props->>'highway',
    props->>'surface',
    props->>'access',
    props->>'incline',
    st_geomfromgeojson(feature->'geometry')
  )
  returning id into new_id;
  return new_id;
end;
$$;

-- 7. GeoJSON function (used by Mapbox GL JS to load all trails)
create or replace function get_trails_geojson()
returns json language sql security definer as $$
  select json_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(json_agg(
      json_build_object(
        'type',     'Feature',
        'id',       id,
        'geometry', st_asgeojson(geometry)::json,
        'properties', json_build_object(
          'id',          id,
          'osm_id',      osm_id,
          'name',        name,
          'highway',     highway,
          'surface',     surface,
          'access',      access,
          'incline',     incline,
          'photos',      photos,
          'custom_data', custom_data
        )
      )
    ), '[]'::json)
  )
  from trails;
$$;
