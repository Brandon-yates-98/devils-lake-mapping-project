-- ============================================================
-- Apex Web Maps — drinking water marker glyph
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- pois_water pointed at the sprite-dependent "drinking-water" name, which
-- renders on the non-baked path (separate circle + sprite) and at a
-- different size from the parking/restroom badges. Switch it to the
-- offline-safe baked dl-water teardrop (drawn client-side in
-- drawMapGlyph), which renders through the same baked-disc path and so
-- matches the parking/restroom marker size automatically.
-- ============================================================

update layer_templates
   set default_style = jsonb_set(default_style, '{icon}', '"dl-water"')
 where slug = 'pois_water';

-- Verify
select slug, default_style from layer_templates where slug = 'pois_water';
