-- ============================================================
-- Devil's Lake Mapping Project, Sauk County Trails & Paths overlay
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Imports the county's public ArcGIS trails layer as an ordinary vector layer
-- (source='sauk_trails' in osm_geometries), so it renders + toggles through the
-- existing layer machinery with no front-end changes. scripts/import_sauk_trails.py
-- refreshes it on a schedule (ArcGIS layer 9 "All Trails", reprojected to WGS84).
--
-- 1. replace_layer_geometries(): full-refresh upsert for an imported source.
--    p_truncate clears the source first (sent on the first batch); later batches
--    append. service_role-only (bulk sync, not a user edit, no audit log).
-- 2. layer_templates row + experience_layers links (campsites + default), off by
--    default so it's an opt-in overlay.
-- ============================================================

create or replace function public.replace_layer_geometries(p_source text, p_features json, p_truncate boolean default false)
returns int language plpgsql security definer set search_path = public, extensions as $fn$
declare f json; n int := 0;
begin
  if p_truncate then delete from osm_geometries where source = p_source; end if;
  for f in select value from json_array_elements(p_features) loop
    insert into osm_geometries (source, name, geometry, properties)
    values (p_source,
            f->'properties'->>'name',
            st_geomfromgeojson(f->'geometry'),
            coalesce((f->'properties')::jsonb, '{}'::jsonb));
    n := n + 1;
  end loop;
  return n;
end;
$fn$;

revoke execute on function public.replace_layer_geometries(text, json, boolean) from public, anon, authenticated;
grant  execute on function public.replace_layer_geometries(text, json, boolean) to service_role;

-- Layer template (brown trail lines; grouped with paths/routes).
insert into layer_templates (slug, label, geom_type, default_style, layer_group, is_custom, sort_order)
values ('sauk_trails', 'Sauk County Trails', 'line', '{"color":"#b15928"}'::jsonb, 'Paths & Routes', false, 100)
on conflict (slug) do update
  set label = excluded.label, geom_type = excluded.geom_type,
      default_style = excluded.default_style, layer_group = excluded.layer_group;

-- Add to both experiences (public Campsites map + private default/editor map),
-- off by default (opt-in overlay).
insert into experience_layers (experience_id, template_slug, visible_by_default, sort_order)
select e.id, 'sauk_trails', false, 100
from experiences e
where e.slug in ('campsites', 'default')
  and not exists (
    select 1 from experience_layers el
    where el.experience_id = e.id and el.template_slug = 'sauk_trails');
