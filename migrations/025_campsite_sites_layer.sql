-- ============================================================
-- Devil's Lake Mapping Project, campsite_sites layer template
-- Individual campsite spots digitized from the paper campground map.
-- Run in Supabase: Dashboard → SQL Editor → New query
-- ============================================================

insert into layer_templates
  (slug, label, geom_type, layer_group, is_custom, default_style, field_schema, sort_order)
values (
  'campsite_sites',
  'Campsite Sites',
  'point',
  'Camping',
  true,
  '{"color":"#27ae60"}'::jsonb,
  '[
    {"name":"ref",             "label":"Site #",       "type":"text"},
    {"name":"campground",      "label":"Campground",   "type":"select",
     "options":["quartzite","northern_lights"]},
    {"name":"site_type",       "label":"Type",         "type":"select",
     "options":["standard","electrical","handicapped","walk_in","group"]},
    {"name":"reservation_url", "label":"Reserve Link", "type":"text"}
  ]'::jsonb,
  31
)
on conflict (slug) do update set
  label         = excluded.label,
  geom_type     = excluded.geom_type,
  layer_group   = excluded.layer_group,
  default_style = excluded.default_style,
  field_schema  = excluded.field_schema,
  sort_order    = excluded.sort_order;

-- Add to the default experience (off by default, too dense at low zoom)
with exp as (select id from experiences where slug = 'default')
insert into experience_layers (experience_id, template_slug, visible_by_default, sort_order)
select exp.id, 'campsite_sites', false, 31 from exp
on conflict do nothing;

-- Verify
select slug, label, geom_type, layer_group from layer_templates where slug = 'campsite_sites';
