-- ============================================================
-- Devil's Lake Mapping Project, normalize campsite ref/site_type/campground
-- Applied via Supabase MCP; recorded for the repo log.
--
-- The map's campsite icon + label expressions read TOP-LEVEL properties
-- (['get','site_type'], ['get','ref']). Imported sites (migration 026) store
-- those there, but sites created in the editor stored them in custom_data, so
-- editor-made accessible sites (A1/A2/A3) rendered as plain tents with no label.
--
-- 1. Move ref / site_type / campground from custom_data up to top-level
--    properties (only the sites that have them nested; imports are untouched).
-- 2. Mark those three fields `base` in the layer template so the editor
--    reads/writes them at top level from now on (consistent with imports),
--    preventing the issue from recurring for new sites.
-- ============================================================

update osm_geometries
set properties = properties || jsonb_strip_nulls(jsonb_build_object(
      'ref',        coalesce(properties->>'ref',        custom_data->>'ref'),
      'site_type',  coalesce(properties->>'site_type',  custom_data->>'site_type'),
      'campground', coalesce(properties->>'campground', custom_data->>'campground'))),
    custom_data = (custom_data - 'ref' - 'site_type' - 'campground'),
    updated_at = now()
where source = 'campsite_sites'
  and custom_data ?| array['ref','site_type','campground'];

update layer_templates
set field_schema = (
  select jsonb_agg(case when e->>'name' in ('ref','campground','site_type')
                        then e || '{"base":true}'::jsonb else e end)
  from jsonb_array_elements(field_schema) e)
where slug = 'campsite_sites';

-- Verify the accessible sites now carry top-level site_type/ref
select id, name, properties->>'ref' ref, properties->>'site_type' st
from osm_geometries where source='campsite_sites' and properties->>'site_type'='handicapped'
order by id;
