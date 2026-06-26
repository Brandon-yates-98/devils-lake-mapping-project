-- ============================================================
-- Devil's Lake Mapping Project, Carabiner marker icon for climbing routes
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- 'apex-carabiner' is drawn in-app by drawMapGlyph(): a simplified
-- pear-shaped ring with a gate slit, legible at 16px marker size.
-- Replaces the 'apex-cliff' glyph set in 016 for routes;
-- boulders keep 'apex-boulder'.
-- ============================================================

update layer_templates
set default_style = coalesce(default_style, '{}'::jsonb) || '{"icon": "apex-carabiner"}'::jsonb
where slug = 'climbing_routes';
