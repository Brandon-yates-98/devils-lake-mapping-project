-- ============================================================
-- Apex Web Maps — campsite_spurs
-- A short connector ("driveway") line from each campsite to the
-- closest point on the nearest road (source='roads', NOT campground
-- hulls). Campsites already within 5 m of a road are skipped — they
-- effectively sit on the road and need no spur.
--
-- RE-RUNNABLE: delete-then-insert. Re-apply after editing campsites
-- or roads to refresh the connectors.
-- ============================================================

delete from osm_geometries where source = 'campsite_spurs';

insert into osm_geometries (source, name, geometry, properties)
select
  'campsite_spurs',
  cs.name,
  ST_ShortestLine(cs.geometry::geometry, r.geom) as geometry,
  jsonb_build_object(
    '_spur',    true,
    'campsite', cs.name,
    'len_m',    round(ST_Distance(cs.geometry::geography, r.geom::geography)::numeric, 1)
  ) as properties
from (select id, name, geometry from osm_geometries where source = 'campsite_sites') cs
cross join lateral (
  -- nearest road geometry to this campsite (KNN <-> ordering)
  select geometry::geometry as geom
  from osm_geometries
  where source = 'roads'
  order by cs.geometry::geometry <-> geometry::geometry
  limit 1
) r
where ST_Distance(cs.geometry::geography, r.geom::geography) > 5;  -- skip sites already on a road

select count(*) as spurs,
  round(min((properties->>'len_m')::numeric),1) as min_m,
  round(max((properties->>'len_m')::numeric),1) as max_m
from osm_geometries where source = 'campsite_spurs';
