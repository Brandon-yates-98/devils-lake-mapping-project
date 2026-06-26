-- ============================================================
-- Devil's Lake Mapping Project, Custom marker icons for climbing layers
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- 'apex-cliff' and 'apex-boulder' are drawn in-app by drawMapGlyph()
-- (no sprite dependency, they work on any basemap and offline).
-- ============================================================

update layer_templates
set default_style = coalesce(default_style, '{}'::jsonb) || '{"icon": "apex-cliff"}'::jsonb
where slug = 'climbing_routes';

update layer_templates
set default_style = coalesce(default_style, '{}'::jsonb) || '{"icon": "apex-boulder"}'::jsonb
where slug = 'climbing_boulders';
