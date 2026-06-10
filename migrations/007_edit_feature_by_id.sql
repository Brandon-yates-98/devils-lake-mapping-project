-- ============================================================
-- Apex Web Maps — Edit any feature in place (drawn or imported)
-- Run in Supabase: Dashboard → SQL Editor → New query
-- REQUIRES 006_audit_log.sql (audit_log table + audit_actor()).
--
-- Enables the editor's popup "Edit feature" button to save edits to
-- *imported* OSM features without creating duplicates: every feature
-- from get_layer_geojson carries its DB row id in properties.id, so we
-- match on that first. Imported features get a _draw_id stamped on
-- first edit ("adopted") so they stay editable. New drawn features
-- (no DB id) fall back to the existing _draw_id matching.
-- Safe to re-run (CREATE OR REPLACE).
-- ============================================================

create or replace function upsert_drawn_feature(p_source text, p_feature json)
returns void language plpgsql security definer as $$
declare
  props    jsonb;
  geom     geometry;
  db_id    uuid;
  draw_id  text;
  v_action text;
  v_entity text;
begin
  props   := (p_feature->'properties')::jsonb;
  geom    := st_geomfromgeojson(p_feature->'geometry');
  db_id   := nullif(props->>'id', '')::uuid;     -- DB row id (present on existing features)
  draw_id := nullif(props->>'_draw_id', '');

  -- ── 1. Match by DB id (covers imported + previously-saved features) ──
  if db_id is not null then
    -- Canonical identity is the row id; keep _draw_id in sync so the
    -- feature remains matchable/deletable by _draw_id afterwards.
    props := jsonb_set(props, '{_draw_id}', to_jsonb(db_id::text));

    update osm_geometries
    set
      geometry    = geom,
      properties  = props,
      name        = props->>'name',
      custom_data = coalesce((props->>'custom_data')::jsonb, custom_data),
      updated_at  = now()
    where id = db_id and source = p_source;

    if found then
      v_action := 'update';
      v_entity := db_id::text;
    end if;
  end if;

  -- ── 2. Fall back to _draw_id matching, else insert ──
  if v_action is null then
    if draw_id is null then
      draw_id := gen_random_uuid()::text;
      props   := jsonb_set(props, '{_draw_id}', to_jsonb(draw_id));
    end if;

    update osm_geometries
    set
      geometry    = geom,
      properties  = props,
      name        = props->>'name',
      custom_data = coalesce((props->>'custom_data')::jsonb, custom_data),
      updated_at  = now()
    where source = p_source and properties->>'_draw_id' = draw_id;

    if found then
      v_action := 'update';
    else
      insert into osm_geometries (source, name, geometry, properties, custom_data)
      values (
        p_source, props->>'name', geom, props,
        coalesce((props->>'custom_data')::jsonb, '{}')
      );
      v_action := 'create';
    end if;
    v_entity := draw_id;
  end if;

  insert into audit_log (actor_email, entity_type, action, source, entity_id, detail)
  values (
    audit_actor(), 'feature', v_action, p_source, v_entity,
    jsonb_build_object('name', props->>'name', 'custom_data', props->>'custom_data')
  );
end;
$$;
