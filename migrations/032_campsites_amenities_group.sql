-- ============================================================
-- Devil's Lake Mapping Project, campsites: move Parking into the POI group and rename
-- that group to "Amenities". Applied via Supabase MCP; recorded for the log.
--
-- Uses the per-experience layer_group_override added in migration 031, so the
-- non-public 'default' editor map is unaffected. Resulting campsites groups:
--   Camping / Amenities / Paths & Routes / Climbing
-- (Built Environment is now empty here: buildings -> Camping in 031,
--  parking -> Amenities here.) sort_order kept contiguous per group.
-- ============================================================

update experience_layers el set
  layer_group_override = case
    when el.template_slug in ('parking', 'pois_restrooms', 'pois_water') then 'Amenities'
    else el.layer_group_override end,
  sort_order = case el.template_slug
                 when 'pois_camping'      then 0
                 when 'campsite_sites'    then 1
                 when 'buildings'         then 2
                 when 'pois_restrooms'    then 3
                 when 'pois_water'        then 4
                 when 'parking'           then 5
                 when 'roads'             then 6
                 when 'climbing_boulders' then 7
                 when 'climbing_areas'    then 8
                 when 'climbing_routes'   then 9
                 else el.sort_order end
where el.experience_id = (select id from experiences where slug = 'campsites');

-- Verify
select el.sort_order, coalesce(el.layer_group_override, lt.layer_group) as grp,
       coalesce(el.label_override, lt.label) as label, el.template_slug, el.visible_by_default
from experience_layers el
join layer_templates lt on lt.slug = el.template_slug
where el.experience_id = (select id from experiences where slug = 'campsites')
order by el.sort_order;
