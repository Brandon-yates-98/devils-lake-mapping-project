-- ============================================================
-- Devil's Lake Mapping Project, campground_hulls
-- One convex-hull polygon per campground, computed from its
-- campsite_sites points and padded ~25 m so edge sites sit inside.
-- Rendered as a low-zoom "footprint" that hands off to individual
-- tent/RV site icons as you zoom in (mirrors climbing_area_hulls).
--
-- RE-RUNNABLE: delete-then-insert. Re-apply after editing campsites
-- to refresh the footprints (the hull is precomputed, not live).
-- ============================================================

delete from osm_geometries where source = 'campground_hulls';

insert into osm_geometries (source, name, geometry, properties)
select
  'campground_hulls',
  initcap(replace(properties->>'campground', '_', ' ')) || ' Campground' as name,
  -- convex hull of the site points, buffered 25 m via a geography cast
  -- (so the padding is metric), back to a 4326 geometry for storage.
  ST_Buffer(
    ST_ConvexHull(ST_Collect(geometry::geometry))::geography,
    25
  )::geometry as geometry,
  jsonb_build_object(
    'campground',  properties->>'campground',
    '_hull',       true,
    '_sites',      count(*),
    '_standard',   count(*) filter (where properties->>'site_type' = 'standard'),
    '_electrical', count(*) filter (where properties->>'site_type' = 'electrical')
  ) as properties
from osm_geometries
where source = 'campsite_sites'
  and coalesce(properties->>'campground', '') <> ''
group by properties->>'campground';

-- Verify
select name, ST_GeometryType(geometry) as geom_type,
  properties->>'_sites' as sites,
  properties->>'_standard' as standard,
  properties->>'_electrical' as electrical
from osm_geometries where source = 'campground_hulls' order by name;
