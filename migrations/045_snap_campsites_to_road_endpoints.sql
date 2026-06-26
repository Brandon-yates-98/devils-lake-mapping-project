-- ============================================================
-- Devil's Lake Mapping Project, snap campsite sites to road endpoints
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Each campsite point should sit on the end of its access spur (the spurs were
-- folded into the roads layer, migrations 028/033). This moves every POINT
-- campsite that is within 5 m of a road endpoint onto that exact endpoint, so
-- the site coincides with the road network. Sites that are already exactly on an
-- endpoint, and the 2 outliers > 5 m away (Site 150E = 16.37 m, truly
-- disconnected; Site 99e = 5.17 m), are left untouched for manual review.
-- Result: 218 / 220 point campsites now sit exactly on a road endpoint.
-- ============================================================

with road_ends as (
  select ST_StartPoint(g) pt from (select (ST_Dump(geometry)).geom g from osm_geometries where source='roads') d where GeometryType(g)='LINESTRING'
  union all
  select ST_EndPoint(g)   from (select (ST_Dump(geometry)).geom g from osm_geometries where source='roads') d where GeometryType(g)='LINESTRING'
),
sites as (select id, geometry pt from osm_geometries where source='campsite_sites' and GeometryType(geometry)='POINT'),
snap as (
  select s.id, ne.pt as new_geom
  from sites s
  cross join lateral (
    select re.pt, ST_Distance(s.pt::geography, re.pt::geography) dist_m
    from road_ends re order by s.pt <-> re.pt limit 1
  ) ne
  where ne.dist_m > 0 and ne.dist_m <= 5
)
update osm_geometries g
set geometry = ST_SetSRID(snap.new_geom, 4326), updated_at = now()
from snap
where g.id = snap.id and g.source = 'campsite_sites';
