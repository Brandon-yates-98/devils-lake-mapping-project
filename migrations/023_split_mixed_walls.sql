-- ============================================================
-- Devil's Lake Mapping Project, split mixed walls by climb type
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- 16 walls carry both routes and boulders. The majority type keeps
-- the original area (ties → routes); the minority type's climbs move
-- to a duplicate area with the same name, parent, path and depth -
-- every leaf area becomes single-type while parent hulls, subtree
-- counts, and the dropdown tree are unchanged by construction
-- (ancestor chains are preserved).
--
-- The split pair would stack at identical coordinates, so the
-- BOULDER side (area marker + its boulder climbs, keeping the
-- climbs-on-marker invariant) is shifted 10 m north:
--   · route-majority wall → the boulder duplicate shifts
--   · boulder-majority wall → the original (boulder) area shifts,
--     flagged _split_shifted for the unwind
--
-- Duplicate ids derive deterministically (md5(id || ':split') as a
-- uuid) and carry split_of/split_type + empty custom_data (no
-- openbeta_id, the client aliases ids through it and would collapse
-- the duplicate into the original). Safe to re-run: prior splits are
-- unwound, shifts reversed. Re-run after importer refreshes (with 021).
-- ============================================================

do $$
declare
  rec record;
  dup_id text;
  minority_src text;
  minority_n int;
  dy constant float := 0.00009;   -- ~10 m of latitude
begin
  -- ── unwind any prior split ──
  for rec in
    select properties->>'area_id' as dup, properties->>'split_of' as orig,
           properties->>'split_type' as stype,
           (select p.properties->>'name' from osm_geometries p
            where p.source = 'climbing_areas'
              and p.properties->>'area_id' = properties->>'split_of') as orig_name
    from osm_geometries
    where source = 'climbing_areas' and properties ? 'split_of'
  loop
    update osm_geometries
      set properties = properties || jsonb_build_object(
            'area_id', rec.orig,
            'area_name', rec.orig_name,
            'area_path',
              ((properties->'area_path') - (jsonb_array_length(properties->'area_path') - 1))
              || to_jsonb(rec.orig)),
          geometry = case when rec.stype = 'boulders'
                          then st_translate(geometry, 0, -dy) else geometry end
      where source in ('climbing_routes', 'climbing_boulders')
        and properties->>'area_id' = rec.dup;
  end loop;
  delete from osm_geometries
    where source = 'climbing_areas' and properties ? 'split_of';
  -- shifted boulder-majority originals move back
  for rec in
    select properties->>'area_id' as aid
    from osm_geometries
    where source = 'climbing_areas' and properties ? '_split_shifted'
  loop
    update osm_geometries
      set geometry = st_translate(geometry, 0, -dy),
          properties = properties - '_split_shifted'
      where source = 'climbing_areas' and properties->>'area_id' = rec.aid;
    update osm_geometries
      set geometry = st_translate(geometry, 0, -dy)
      where source = 'climbing_boulders' and properties->>'area_id' = rec.aid;
  end loop;

  -- ── split every mixed wall ──
  for rec in
    select a.id as row_id, a.properties as p, a.geometry as g, a.name as nm,
           c.routes, c.boulders
    from (
      select properties->>'area_id' as aid,
             count(*) filter (where source = 'climbing_routes') as routes,
             count(*) filter (where source = 'climbing_boulders') as boulders
      from osm_geometries
      where source in ('climbing_routes', 'climbing_boulders')
      group by 1
      having count(*) filter (where source = 'climbing_routes') > 0
         and count(*) filter (where source = 'climbing_boulders') > 0
    ) c
    join osm_geometries a
      on a.source = 'climbing_areas' and a.properties->>'area_id' = c.aid
  loop
    -- majority keeps the original; ties go to routes
    if rec.routes >= rec.boulders then
      minority_src := 'climbing_boulders';
      minority_n := rec.boulders;
    else
      minority_src := 'climbing_routes';
      minority_n := rec.routes;
    end if;
    dup_id := md5((rec.p->>'area_id') || ':split')::uuid::text;

    insert into osm_geometries (source, name, geometry, properties)
    values ('climbing_areas', rec.nm,
      case when minority_src = 'climbing_boulders'
           then st_translate(rec.g, 0, dy) else rec.g end,
      rec.p || jsonb_build_object(
        'area_id', dup_id,
        'climb_count', minority_n,
        'split_of', rec.p->>'area_id',
        'split_type', case when minority_src = 'climbing_boulders'
                           then 'boulders' else 'routes' end,
        '_draw_id', 'split-' || (rec.p->>'area_id'),
        'custom_data', '{}'::jsonb));

    update osm_geometries
      set properties = properties || jsonb_build_object(
            'area_id', dup_id,
            'area_path',
              ((properties->'area_path') - (jsonb_array_length(properties->'area_path') - 1))
              || to_jsonb(dup_id)),
          geometry = case when minority_src = 'climbing_boulders'
                          then st_translate(geometry, 0, dy) else geometry end
      where source = minority_src
        and properties->>'area_id' = rec.p->>'area_id';

    if minority_src = 'climbing_routes' then
      -- boulder-majority wall: the original (boulder) side shifts instead
      update osm_geometries
        set geometry = st_translate(geometry, 0, dy),
            properties = properties || jsonb_build_object('_split_shifted', true)
        where id = rec.row_id;
      update osm_geometries
        set geometry = st_translate(geometry, 0, dy)
        where source = 'climbing_boulders'
          and properties->>'area_id' = rec.p->>'area_id';
    end if;

    -- the original's rollup count drops to its majority share
    update osm_geometries
      set properties = properties || jsonb_build_object(
        'climb_count', greatest(rec.routes, rec.boulders))
      where id = rec.row_id;
  end loop;
end $$;
