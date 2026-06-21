-- ============================================================
-- Devil's Lake Mapping Project — campsite Street View camera (stand on road, face site)
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Precomputes, for every campsite_sites point, where a Street View camera should
-- stand and which way it should face so the first frame looks AT the campsite:
--   * sv_lng / sv_lat : the standing point on the road network.
--   * sv_heading       : bearing from that point toward the campsite (degrees,
--     0=N clockwise — same convention as the Maps Embed API `heading`).
--
-- Standing point is chosen in priority order:
--   1. The spur's road end (the spur/road intersection) when a _spur exists.
--   2. Else, for a campsite that is the dead-end tip of a short (<80 m) non-spur
--      access road, that road's FAR endpoint (its junction with the bigger road)
--      — so the camera stands at the junction and looks UP the access road at the
--      site. (Migration 045 snapped these campsites onto the road, erasing their
--      offset, so without this they'd get no heading and Street View would face
--      its arbitrary default "down the road".)
--   3. Else the closest point on the nearest road.
-- Heading is omitted only if the standing point ends up within 1 m of the site
-- (azimuth undefined). Heading is reset each run so it never goes stale.
--
-- Re-runnable: re-invoke after roads/spurs change. service_role-only.
-- ============================================================

create or replace function public.set_campsite_streetview_camera()
returns int language sql security definer set search_path = public, extensions as $fn$
  with spur as (
    select properties->>'campsite' as campsite, st_endpoint(geometry) as endpt
    from osm_geometries where source = 'roads' and (properties->>'_spur')::bool is true
  ),
  -- non-spur road whose endpoint coincides with the campsite (an access stub);
  -- far_end = the road's other end (its junction with the larger road)
  access as (
    select cs.id,
      first_value(case when st_dwithin(st_startpoint(r.geometry)::geography, cs.geometry::geography, 2)
                       then st_endpoint(r.geometry) else st_startpoint(r.geometry) end)
        over (partition by cs.id order by st_length(r.geometry::geography)) as far_end
    from osm_geometries cs
    join osm_geometries r
      on r.source = 'roads' and coalesce((r.properties->>'_spur')::bool, false) = false
     and st_length(r.geometry::geography) < 80
     and (st_dwithin(st_startpoint(r.geometry)::geography, cs.geometry::geography, 2)
          or st_dwithin(st_endpoint(r.geometry)::geography, cs.geometry::geography, 2))
    where cs.source = 'campsite_sites'
  ),
  cam as (
    select cs.id, cs.geometry as site,
      coalesce(
        (select sp.endpt from spur sp where sp.campsite = cs.name limit 1),  -- 1. spur/road intersection
        (select a.far_end from access a where a.id = cs.id limit 1),         -- 2. access-stub junction
        st_closestpoint(r.geom, cs.geometry)                                 -- 3. nearest road point
      ) as stand
    from osm_geometries cs
    cross join lateral (
      select r2.geometry as geom
      from osm_geometries r2
      where r2.source = 'roads'
        and coalesce((r2.properties->>'_spur')::bool, false) = false  -- aim at real roads, not spurs
        and r2.geometry is not null
      order by r2.geometry <-> cs.geometry   -- KNN nearest road
      limit 1
    ) r
    where cs.source = 'campsite_sites' and cs.geometry is not null
  ),
  upd as (
    update osm_geometries o
    set properties = (o.properties - 'sv_heading') || jsonb_strip_nulls(jsonb_build_object(
          'sv_lng', round(st_x(cam.stand)::numeric, 7),
          'sv_lat', round(st_y(cam.stand)::numeric, 7),
          'sv_heading', case when st_distance(cam.stand::geography, cam.site::geography) > 1
                             then round(degrees(st_azimuth(cam.stand::geography, cam.site::geography))::numeric, 1)
                             else null end))   -- omit heading only if standing on the site
    from cam
    where o.id = cam.id
    returning 1
  )
  select count(*)::int from upd;
$fn$;

revoke execute on function public.set_campsite_streetview_camera() from public, anon, authenticated;
grant  execute on function public.set_campsite_streetview_camera() to service_role;

select public.set_campsite_streetview_camera();
