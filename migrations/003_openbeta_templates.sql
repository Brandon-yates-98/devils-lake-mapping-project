-- ============================================================
-- Apex Web Maps — OpenBeta Climbing Layer Templates
-- Run AFTER import_openbeta.py has populated osm_geometries.
-- License: OpenBeta data is ODbL — attribution required in UI.
-- ============================================================

-- ── 0. Remove null-property orphans from failed import runs ──
-- Previous runs with a serialization bug inserted rows with null
-- geometry/properties that the upsert could not find to overwrite.
delete from osm_geometries
where source in ('climbing_routes', 'climbing_boulders', 'climbing_areas')
  and properties is null;

-- ── 1. Insert climbing layer templates ──────────────────────
insert into layer_templates (slug, label, geom_type, layer_group, is_custom, default_style, field_schema, sort_order)
values
  ('climbing_routes',
   'Climbing Routes',
   'point',
   'Climbing',
   true,
   '{"color":"#e74c3c"}',
   '[
     {"name":"grade",      "label":"Grade (YDS)",  "type":"text"},
     {"name":"route_type", "label":"Type",          "type":"select",
      "options":["trad","sport","tr","aid","alpine","mixed","trad/sport","unknown"]},
     {"name":"length_ft",  "label":"Length (ft)",   "type":"number"},
     {"name":"fa",         "label":"First Ascent",  "type":"text"},
     {"name":"area_name",  "label":"Wall / Sector", "type":"text"}
   ]'::jsonb,
   20),

  ('climbing_boulders',
   'Bouldering',
   'point',
   'Climbing',
   true,
   '{"color":"#e67e22"}',
   '[
     {"name":"grade",     "label":"Grade (V-Scale)", "type":"text"},
     {"name":"fa",        "label":"First Ascent",    "type":"text"},
     {"name":"area_name", "label":"Boulder / Sector","type":"text"}
   ]'::jsonb,
   21),

  ('climbing_areas',
   'Climbing Areas',
   'point',
   'Climbing',
   true,
   '{"color":"#8e44ad"}',
   '[]'::jsonb,
   22)
on conflict (slug) do update set
  label        = excluded.label,
  geom_type    = excluded.geom_type,
  layer_group  = excluded.layer_group,
  is_custom    = excluded.is_custom,
  default_style = excluded.default_style,
  field_schema = excluded.field_schema,
  sort_order   = excluded.sort_order;

-- ── 2. Add climbing layers to the default experience ────────
with exp as (select id from experiences where slug = 'default')
insert into experience_layers (experience_id, template_slug, visible_by_default, sort_order)
select exp.id, t.slug, false, t.sort_order
from exp, layer_templates t
where t.slug in ('climbing_routes','climbing_boulders','climbing_areas')
on conflict do nothing;

-- ── 3. Verify ────────────────────────────────────────────────
select slug, label, layer_group,
       jsonb_array_length(field_schema) as field_count,
       (select count(*) from osm_geometries og where og.source = lt.slug) as feature_count
from layer_templates lt
where layer_group = 'Climbing'
order by sort_order;
