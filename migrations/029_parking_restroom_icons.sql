-- ============================================================
-- Devil's Lake Mapping Project, fix parking visibility + parking/restroom icons
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- Two problems, both fixed here:
--  1. The default experience showed an empty `pois_parking` point layer
--     (visible) while the populated dedicated `parking` layer (76 features,
--     polygons + points) was hidden, so parking never drew on either map.
--  2. Neither parking nor restrooms had a real marker glyph: `parking` had
--     no icon at all, and `pois_restrooms` pointed at the sprite-dependent
--     "toilets" name (renders as a blank circle when the basemap sprite
--     lacks it). Both now use offline-safe canvas glyphs (dl-parking /
--     dl-restroom) drawn client-side in drawMapGlyph().
-- ============================================================

-- 1. Show the dedicated parking layer; drop the empty pois_parking duplicate.
with exp as (select id from experiences where slug = 'default')
update experience_layers el
   set visible_by_default = true
  from exp
 where el.experience_id = exp.id
   and el.template_slug = 'parking';

with exp as (select id from experiences where slug = 'default')
delete from experience_layers el
 using exp
 where el.experience_id = exp.id
   and el.template_slug = 'pois_parking';

-- 2. Point both templates at their baked dl-* marker glyphs (preserve color).
update layer_templates
   set default_style = default_style || jsonb_build_object('icon', 'dl-parking')
 where slug = 'parking';

update layer_templates
   set default_style = jsonb_set(default_style, '{icon}', '"dl-restroom"')
 where slug = 'pois_restrooms';

-- Verify
select slug, default_style from layer_templates where slug in ('parking', 'pois_restrooms');
select el.template_slug, el.visible_by_default
  from experience_layers el
  join experiences e on e.id = el.experience_id
 where e.slug = 'default' and el.template_slug ilike '%parking%';
