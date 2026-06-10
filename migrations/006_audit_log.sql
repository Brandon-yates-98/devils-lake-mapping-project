-- ============================================================
-- Apex Web Maps — Edit tracking (audit_log)
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- Captures two kinds of edits, fully server-side (no client change):
--   1. Feature data edits  — via upsert_drawn_feature / delete_drawn_feature
--   2. Field schema edits   — via a trigger on layer_templates.field_schema
--
-- No in-editor UI yet; query audit_log directly in Supabase.
-- Safe to re-run (IF NOT EXISTS / CREATE OR REPLACE).
-- ============================================================

-- ── 1. audit_log table ──────────────────────────────────────
create table if not exists audit_log (
  id           uuid        primary key default gen_random_uuid(),
  occurred_at  timestamptz not null default now(),
  actor_email  text        not null default 'system',
  entity_type  text        not null,            -- 'feature' | 'field_schema'
  action       text        not null,            -- 'create' | 'update' | 'delete'
  source       text,                            -- layer slug / osm_geometries.source
  entity_id    text,                            -- feature _draw_id (features only)
  detail       jsonb       not null default '{}'::jsonb
);

create index if not exists audit_log_occurred_at_idx on audit_log(occurred_at desc);
create index if not exists audit_log_source_idx       on audit_log(source);
create index if not exists audit_log_entity_type_idx  on audit_log(entity_type);

alter table audit_log enable row level security;

-- Authenticated users can read the log; writes happen only through the
-- security-definer functions/trigger below (which bypass RLS as owner).
drop policy if exists "Auth read" on audit_log;
create policy "Auth read" on audit_log for select using (auth.role() = 'authenticated');

-- ── 2. actor helper ─────────────────────────────────────────
-- Resolves the current user's email from the request JWT, falling back
-- to 'system' for non-authenticated / server contexts.
create or replace function audit_actor()
returns text language sql stable as $$
  select coalesce(nullif(auth.jwt() ->> 'email', ''), 'system');
$$;

-- ── 3. Feature edits: re-define the draw RPCs with logging ──
create or replace function upsert_drawn_feature(p_source text, p_feature json)
returns void language plpgsql security definer as $$
declare
  props    json;
  draw_id  text;
  geom     geometry;
  v_action text;
begin
  props   := p_feature->'properties';
  draw_id := props->>'_draw_id';
  geom    := st_geomfromgeojson(p_feature->'geometry');

  if draw_id is not null then
    update osm_geometries
    set
      geometry    = geom,
      properties  = props::jsonb,
      name        = props->>'name',
      custom_data = coalesce((props->>'custom_data')::jsonb, custom_data),
      updated_at  = now()
    where source = p_source and properties->>'_draw_id' = draw_id;

    if found then
      v_action := 'update';
    else
      insert into osm_geometries (source, name, geometry, properties, custom_data)
      values (
        p_source, props->>'name', geom, props::jsonb,
        coalesce((props->>'custom_data')::jsonb, '{}')
      );
      v_action := 'create';
    end if;
  else
    insert into osm_geometries (source, name, geometry, properties)
    values (p_source, props->>'name', geom, props::jsonb);
    v_action := 'create';
  end if;

  insert into audit_log (actor_email, entity_type, action, source, entity_id, detail)
  values (
    audit_actor(), 'feature', v_action, p_source, draw_id,
    jsonb_build_object('name', props->>'name', 'custom_data', props->>'custom_data')
  );
end;
$$;

create or replace function delete_drawn_feature(p_source text, p_draw_id text)
returns void language plpgsql security definer as $$
declare
  v_name text;
begin
  select name into v_name
  from osm_geometries
  where source = p_source and properties->>'_draw_id' = p_draw_id
  limit 1;

  delete from osm_geometries
  where source = p_source and properties->>'_draw_id' = p_draw_id;

  insert into audit_log (actor_email, entity_type, action, source, entity_id, detail)
  values (
    audit_actor(), 'feature', 'delete', p_source, p_draw_id,
    jsonb_build_object('name', v_name)
  );
end;
$$;

-- ── 4. Field schema edits: trigger on layer_templates ───────
-- Fires only when field_schema actually changes (not on other column
-- updates, inserts, or duplicates). Records the before/after schema.
create or replace function log_field_schema_change()
returns trigger language plpgsql security definer as $$
begin
  if new.field_schema is distinct from old.field_schema then
    insert into audit_log (actor_email, entity_type, action, source, detail)
    values (
      audit_actor(), 'field_schema', 'update', new.slug,
      jsonb_build_object('before', old.field_schema, 'after', new.field_schema)
    );
  end if;
  return new;
end;
$$;

drop trigger if exists layer_templates_field_schema_audit on layer_templates;
create trigger layer_templates_field_schema_audit
  after update on layer_templates
  for each row execute function log_field_schema_change();

-- ── 5. Verify ────────────────────────────────────────────────
select id, occurred_at, actor_email, entity_type, action, source
from audit_log order by occurred_at desc limit 20;
