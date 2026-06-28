-- ============================================================
-- Name street-side parking after its adjacent road
-- Applied via Supabase MCP; recorded for the repo log.
--
-- name_street_parking() renames every parking=street_side feature to
-- "<adjacent road> Street Parking", using the nearest NAMED road within
-- max_dist_m (default 30 m) so lots on unnamed local roads are left alone.
-- Idempotent; import_geojson.py calls it after each OSM import so the names
-- survive a re-import of the parking/roads layers.
-- ============================================================

create or replace function public.name_street_parking(max_dist_m numeric default 30)
returns int language plpgsql security definer set search_path = public, extensions as $fn$
declare n int;
begin
  with sp as (
    select p.id, r.rname, r.rm
    from osm_geometries p
    cross join lateral (
      select rr.properties->>'name' as rname,
             st_distance(p.geometry::geography, rr.geometry::geography) as rm
      from osm_geometries rr
      where rr.source = 'roads' and rr.properties->>'name' is not null
      order by p.geometry <-> rr.geometry
      limit 1
    ) r
    where p.source = 'parking' and p.properties->>'parking' = 'street_side'
  )
  update osm_geometries g
  set name = sp.rname || ' Street Parking',
      properties = jsonb_set(coalesce(g.properties, '{}'::jsonb), '{name}',
                             to_jsonb(sp.rname || ' Street Parking'))
  from sp
  where g.id = sp.id and sp.rm <= max_dist_m;
  get diagnostics n = row_count;
  return n;
end;
$fn$;
revoke execute on function public.name_street_parking(numeric) from public, anon, authenticated;
grant  execute on function public.name_street_parking(numeric) to service_role;
