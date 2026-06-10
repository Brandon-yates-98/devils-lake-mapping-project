-- ============================================================
-- Apex Web Maps — Idempotent OSM re-import (upsert by _osm_id)
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- import_feature() always INSERTs, so re-running an OSM pull creates
-- duplicates. upsert_osm_feature() matches on properties->>'_osm_id'
-- within a source: updates the existing row if present, else inserts.
-- Used by fetch_campsites.py to top up the 'pois' layer safely.
-- Not audit-logged on purpose — this is bulk data sync, not a user edit.
-- Safe to re-run (CREATE OR REPLACE).
-- ============================================================

create or replace function upsert_osm_feature(p_source text, p_feature json)
returns text language plpgsql security definer as $$
declare
  props   jsonb;
  osm_txt text;
  osm_num bigint;
  geom    geometry;
begin
  props   := (p_feature->'properties')::jsonb;
  osm_txt := props->>'_osm_id';
  osm_num := nullif(osm_txt, '')::bigint;
  geom    := st_geomfromgeojson(p_feature->'geometry');

  if osm_txt is not null and osm_txt <> '' then
    update osm_geometries
    set geometry   = geom,
        properties = props,
        name       = props->>'name',
        updated_at = now()
    where source = p_source and properties->>'_osm_id' = osm_txt;

    if found then
      return 'updated';
    end if;
  end if;

  insert into osm_geometries (source, osm_id, name, geometry, properties)
  values (p_source, osm_num, props->>'name', geom, props);
  return 'inserted';
end;
$$;
