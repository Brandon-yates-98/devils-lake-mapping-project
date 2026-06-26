-- ============================================================
-- Devil's Lake Mapping Project, campsite spurs (folded into the roads layer)
-- A short connector ("driveway") line from each campsite to the
-- closest point on the nearest road. Campsites already within 5 m of
-- a road are skipped, they effectively sit on the road and need no spur.
--
-- Spurs are stored as ordinary roads (source='roads', highway='service')
-- so they toggle, style, and load with the rest of the road network. The
-- _spur flag marks them as generated so this migration can refresh them
-- (and so the nearest-road search below never snaps a spur to a spur).
--
-- RE-RUNNABLE: delete-then-insert. Re-apply after editing campsites
-- or roads to refresh the connectors.
-- ============================================================

-- Clear generated spurs (new home + any legacy separate-source rows).
delete from osm_geometries
where source = 'roads' and coalesce(properties->>'_spur', '') = 'true';
delete from osm_geometries where source = 'campsite_spurs';

insert into osm_geometries (source, name, geometry, properties)
select
  'roads',
  cs.name,
  ST_ShortestLine(cs.geometry::geometry, r.geom) as geometry,
  jsonb_build_object(
    '_spur',    true,
    'highway',  'service',
    'campsite', cs.name,
    'len_m',    round(ST_Distance(cs.geometry::geography, r.geom::geography)::numeric, 1)
  ) as properties
from (select id, name, geometry from osm_geometries where source = 'campsite_sites') cs
cross join lateral (
  -- nearest real road geometry to this campsite (KNN <-> ordering);
  -- exclude generated spurs so they never snap to each other
  select geometry::geometry as geom
  from osm_geometries
  where source = 'roads'
    and coalesce(properties->>'_spur', '') <> 'true'
  order by cs.geometry::geometry <-> geometry::geometry
  limit 1
) r
where ST_Distance(cs.geometry::geography, r.geom::geography) > 5;  -- skip sites already on a road

select count(*) as spurs,
  round(min((properties->>'len_m')::numeric),1) as min_m,
  round(max((properties->>'len_m')::numeric),1) as max_m
from osm_geometries
where source = 'roads' and coalesce(properties->>'_spur', '') = 'true';
