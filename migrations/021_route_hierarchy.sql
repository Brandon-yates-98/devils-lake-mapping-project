-- ============================================================
-- Devil's Lake Community Map — synthetic route hierarchy
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- The bouldering tree has one root (Devil's Lake Bouldering) the
-- semantic-clustering bands hang off; the roped crags were 17 flat
-- depth-0 roots. This adds:
--   Devil's Lake Rock Climbing            (new depth-0 root)
--   ├── East Bluff   ← East Bluff 01–08   (new depth-1 group)
--   ├── West Bluff   ← West Bluff 01–07   (new depth-1 group)
--   ├── South Bluff Towers                (re-parented, +1 depth)
--   └── Linkups, Contrivances, …          (re-parented, +1 depth)
-- Every descendant area and climb gets its area_path prepended and
-- depth shifted to match (depth == area_path length throughout the
-- dataset). Safe to re-run: synthetic ids are stripped back out of
-- every path first, then the structure is rebuilt.
-- Hulls are regenerated separately (compute_area_hulls.py → 022).
-- ============================================================

do $$
declare
  v_root text := '7c1e9a52-3d84-4b6f-9e21-d5a8c4f0b311';
  v_east text := '4f8b2c71-9a35-4d18-b6e4-2c9f7d1a8e22';
  v_west text := 'b3d61f94-5e27-4c83-a1f8-6b4e9c2d7533';
  eb text[]; wb text[]; other text[];
begin
  -- ── idempotency: remove prior synthetic rows + their path prepends ──
  delete from osm_geometries
    where source = 'climbing_areas'
      and properties->>'area_id' in (v_root, v_east, v_west);
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'area_path', (
        select coalesce(jsonb_agg(to_jsonb(t.e) order by t.ord), '[]'::jsonb)
        from jsonb_array_elements_text(properties->'area_path')
             with ordinality as t(e, ord)
        where t.e not in (v_root, v_east, v_west)
      ))
    where source in ('climbing_areas', 'climbing_routes', 'climbing_boulders')
      and properties->'area_path' @> to_jsonb(v_root);
  -- depth == path length everywhere in this dataset; recompute after strip
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'depth', jsonb_array_length(properties->'area_path'))
    where source = 'climbing_areas'
      and (properties->>'depth')::int != jsonb_array_length(properties->'area_path');

  select array_agg(properties->>'area_id') into eb
    from osm_geometries
    where source = 'climbing_areas'
      and name like 'East Bluff 0%' and jsonb_array_length(properties->'area_path') = 0;
  select array_agg(properties->>'area_id') into wb
    from osm_geometries
    where source = 'climbing_areas'
      and name like 'West Bluff 0%' and jsonb_array_length(properties->'area_path') = 0;
  select array_agg(properties->>'area_id') into other
    from osm_geometries
    where source = 'climbing_areas'
      and (name = 'South Bluff Towers' or name like 'Linkups%')
      and jsonb_array_length(properties->'area_path') = 0;

  -- ── new area markers (counts/centroids from the original roots) ──
  insert into osm_geometries (source, name, geometry, properties)
  select 'climbing_areas', 'Devil''s Lake Rock Climbing',
         st_centroid(st_collect(geometry)),
         jsonb_build_object('area_id', v_root, 'parent_id', '',
           'area_path', '[]'::jsonb, 'depth', 0,
           'name', 'Devil''s Lake Rock Climbing', 'climb_count', count(*),
           '_draw_id', 'synthetic-' || v_root, 'custom_data', '{}'::jsonb)
  from osm_geometries
  where source in ('climbing_routes', 'climbing_boulders')
    and properties->'area_path'->>0 = any(eb || wb || other);

  insert into osm_geometries (source, name, geometry, properties)
  select 'climbing_areas', 'East Bluff',
         st_centroid(st_collect(geometry)),
         jsonb_build_object('area_id', v_east, 'parent_id', v_root,
           'area_path', jsonb_build_array(v_root), 'depth', 1,
           'name', 'East Bluff', 'climb_count', count(*),
           '_draw_id', 'synthetic-' || v_east, 'custom_data', '{}'::jsonb)
  from osm_geometries
  where source in ('climbing_routes', 'climbing_boulders')
    and properties->'area_path'->>0 = any(eb);

  insert into osm_geometries (source, name, geometry, properties)
  select 'climbing_areas', 'West Bluff',
         st_centroid(st_collect(geometry)),
         jsonb_build_object('area_id', v_west, 'parent_id', v_root,
           'area_path', jsonb_build_array(v_root), 'depth', 1,
           'name', 'West Bluff', 'climb_count', count(*),
           '_draw_id', 'synthetic-' || v_west, 'custom_data', '{}'::jsonb)
  from osm_geometries
  where source in ('climbing_routes', 'climbing_boulders')
    and properties->'area_path'->>0 = any(wb);

  -- ── shift descendants of the old roots (before touching the roots
  --    themselves, whose paths are the membership test) ──
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'area_path', jsonb_build_array(v_root, v_east) || (properties->'area_path'),
      'depth', (properties->>'depth')::int + 2)
    where source = 'climbing_areas' and properties->'area_path'->>0 = any(eb);
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'area_path', jsonb_build_array(v_root, v_west) || (properties->'area_path'),
      'depth', (properties->>'depth')::int + 2)
    where source = 'climbing_areas' and properties->'area_path'->>0 = any(wb);
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'area_path', jsonb_build_array(v_root) || (properties->'area_path'),
      'depth', (properties->>'depth')::int + 1)
    where source = 'climbing_areas' and properties->'area_path'->>0 = any(other);

  -- ── climbs' chains (both sources — mixed walls carry a few climbs of
  --    the other family) ──
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'area_path', jsonb_build_array(v_root, v_east) || (properties->'area_path'))
    where source in ('climbing_routes', 'climbing_boulders')
      and properties->'area_path'->>0 = any(eb);
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'area_path', jsonb_build_array(v_root, v_west) || (properties->'area_path'))
    where source in ('climbing_routes', 'climbing_boulders')
      and properties->'area_path'->>0 = any(wb);
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'area_path', jsonb_build_array(v_root) || (properties->'area_path'))
    where source in ('climbing_routes', 'climbing_boulders')
      and properties->'area_path'->>0 = any(other);

  -- ── finally the old roots themselves ──
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'parent_id', v_east,
      'area_path', jsonb_build_array(v_root, v_east), 'depth', 2)
    where source = 'climbing_areas' and properties->>'area_id' = any(eb);
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'parent_id', v_west,
      'area_path', jsonb_build_array(v_root, v_west), 'depth', 2)
    where source = 'climbing_areas' and properties->>'area_id' = any(wb);
  update osm_geometries
    set properties = properties || jsonb_build_object(
      'parent_id', v_root,
      'area_path', jsonb_build_array(v_root), 'depth', 1)
    where source = 'climbing_areas' and properties->>'area_id' = any(other);
end $$;
