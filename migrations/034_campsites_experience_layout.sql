-- ============================================================
-- Devil's Lake Mapping Project, Campsites experience sidebar layout
-- Reorders the campsites experience's layers so each layer_group is
-- contiguous and camping-first, and declutters default visibility on the
-- satellite basemap. Climbing is kept but pushed to the bottom and off by
-- default (the sidebar then collapses the empty Climbing group).
--
-- Render order after this: Camping → Points of Interest → Paths & Routes
-- → Built Environment → Climbing.
--
-- RE-RUNNABLE: idempotent UPDATEs keyed by experience slug + template_slug.
-- ============================================================

update experience_layers el
set sort_order        = v.sort_order,
    visible_by_default = v.visible
from (values
  ('campsite_sites',    0, true),
  ('pois_camping',      1, true),
  ('pois_restrooms',    2, true),
  ('pois_water',        3, true),
  ('roads',             4, true),
  ('parking',           5, true),
  ('buildings',         6, false),
  ('climbing_boulders', 7, false),
  ('climbing_areas',    8, false),
  ('climbing_routes',   9, false)
) as v(template_slug, sort_order, visible)
where el.template_slug = v.template_slug
  and el.experience_id = (select id from experiences where slug = 'campsites');

select el.sort_order, el.template_slug, lt.layer_group, el.visible_by_default
from experience_layers el
join experiences e on e.id = el.experience_id
left join layer_templates lt on lt.slug = el.template_slug
where e.slug = 'campsites'
order by el.sort_order;
