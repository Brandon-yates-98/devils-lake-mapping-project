-- Run this in Supabase: Dashboard → SQL Editor → New query
-- Assumes osm_geometries table already exists with columns:
--   id uuid, source text, osm_id bigint, name text,
--   geometry geometry, properties jsonb, photos text[], custom_data jsonb, updated_at timestamptz

-- 1. Add missing columns to osm_geometries
alter table osm_geometries
  add column source      text,
  add column osm_id      bigint,
  add column name        text,
  add column geometry    geometry(Geometry, 4326),
  add column properties  jsonb    default '{}',
  add column photos      text[]   default '{}',
  add column custom_data jsonb    default '{}',
  add column updated_at  timestamptz default now();

-- 3. Indexes (skip if already created)
create index if not exists osm_geometries_geometry_idx on osm_geometries using gist(geometry);
create index if not exists osm_geometries_source_idx   on osm_geometries(source);
create index if not exists osm_geometries_osm_id_idx   on osm_geometries(osm_id);

-- 2. Auto-update updated_at (reuses function from supabase_setup.sql)
create trigger osm_geometries_updated_at
  before update on osm_geometries
  for each row execute function update_updated_at();

-- 3. RLS
alter table osm_geometries enable row level security;
create policy "Public read"  on osm_geometries for select using (true);
create policy "Auth insert"  on osm_geometries for insert with check (auth.role() = 'authenticated');
create policy "Auth update"  on osm_geometries for update using (auth.role() = 'authenticated');

-- 4. Import function (called by import_geojson.py for each feature)
create or replace function import_feature(p_source text, feature json)
returns void language plpgsql security definer as $$
declare
  props json;
begin
  props := feature->'properties';
  insert into osm_geometries (source, osm_id, name, geometry, properties)
  values (
    p_source,
    (props->>'_osm_id')::bigint,
    props->>'name',
    st_geomfromgeojson(feature->'geometry'),
    props::jsonb
  );
end;
$$;

-- 5. GeoJSON retrieval function (called per layer by index.html)
create or replace function get_layer_geojson(p_source text)
returns json language sql security definer as $$
  select json_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(json_agg(
      json_build_object(
        'type',     'Feature',
        'id',       id,
        'geometry', st_asgeojson(geometry)::json,
        'properties', properties || jsonb_build_object(
          'id',          id,
          'photos',      to_jsonb(photos),
          'custom_data', custom_data
        )
      )
    ), '[]'::json)
  )
  from osm_geometries
  where source = p_source;
$$;

-- 6. Migrate existing trails into osm_geometries
insert into osm_geometries (source, osm_id, name, geometry, properties, photos, custom_data, updated_at)
select
  'trails',
  osm_id,
  name,
  geometry,
  jsonb_strip_nulls(jsonb_build_object(
    'name',      name,
    'highway',   highway,
    'surface',   surface,
    'access',    access,
    'incline',   incline,
    '_osm_id',   osm_id,
    '_osm_type', 'way'
  )),
  photos,
  custom_data,
  updated_at
from trails;
