-- ============================================================
-- Devil's Lake Mapping Project, parent-area hull polygons
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- Semantic clustering: leaf walls render as point badges; every
-- parent area (one with child areas) renders as a convex hull of
-- the climbs beneath it, buffered 30m so two-wall parents (line
-- hulls) and stacked-children parents (point hulls) still produce
-- clean polygons. 70 hulls at depths 0-3.
--
-- Idempotent: safe to re-run after an importer refresh.
-- ============================================================

delete from osm_geometries where source = 'climbing_area_hulls';

insert into osm_geometries (source, name, geometry, properties)
select
  'climbing_area_hulls',
  p.name,
  st_buffer(st_convexhull(st_collect(c.geometry))::geography, 30)::geometry,
  jsonb_build_object(
    'area_id', p.aid,
    'parent_id', p.parent_id,
    'name', p.name,
    'depth', p.depth,
    '_hull', true
  )
from (
  select a.properties->>'area_id' as aid,
         a.properties->>'parent_id' as parent_id,
         a.properties->>'name' as name,
         (a.properties->>'depth')::int as depth
  from osm_geometries a
  where a.source = 'climbing_areas'
    and exists (
      select 1 from osm_geometries ch
      where ch.source = 'climbing_areas'
        and ch.properties->>'parent_id' = a.properties->>'area_id'
    )
) p
join (
  select jsonb_array_elements_text(properties->'area_path') as aid, geometry
  from osm_geometries
  where source in ('climbing_routes', 'climbing_boulders')
) c on c.aid = p.aid
group by p.aid, p.parent_id, p.name, p.depth;
