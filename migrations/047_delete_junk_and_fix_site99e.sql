-- ============================================================
-- Devil's Lake Mapping Project, remove junk campsite/road rows; connect Site 99e
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Cleanup from the campsite/road audit:
--  - 9 "campsite_sites" rows that were attribute-less 2-point LINESTRING
--    fragments (wrong geometry; 4 sat exactly on real named sites = duplicates).
--  - 1 "roads" row that was a bare POINT (a road can't be a point).
--  - Site 99e (id 14459) was 5.17 m from the nearest road endpoint; snap it on.
--
-- (Site 150E, the 16.37 m fully-disconnected outlier, was deleted manually.)
-- After this: all 219 campsite sites are points sitting exactly on a road endpoint.
-- ============================================================

delete from osm_geometries
where id in (14648,14649,14653,14655,14658,14659,14660,14661,14662,14666);

with road_ends as (
  select ST_StartPoint(g) pt from (select (ST_Dump(geometry)).geom g from osm_geometries where source='roads') d where GeometryType(g)='LINESTRING'
  union all
  select ST_EndPoint(g)   from (select (ST_Dump(geometry)).geom g from osm_geometries where source='roads') d where GeometryType(g)='LINESTRING'
),
nearest as (
  select re.pt from road_ends re, osm_geometries t
  where t.id = 14459 order by t.geometry <-> re.pt limit 1
)
update osm_geometries g
set geometry = ST_SetSRID((select pt from nearest), 4326), updated_at = now()
where g.id = 14459;
