-- ============================================================
-- Devil's Lake Mapping Project, per-experience label / layer_group overrides
-- Applied via Supabase MCP (apply_migration). Recorded here for the repo log.
--
-- label and layer_group live on layer_templates (global). To curate one
-- experience's sidebar without disturbing others (e.g. the non-public
-- 'default' editor map), add nullable per-experience overrides and have
-- get_experience_config coalesce them over the template values. The editor
-- (editor.html) coalesces the same two columns in its layer normalizer.
--
-- Then reorganize the public 'campsites' experience Camping group to:
--   Campgrounds (pois_camping, renamed) -> Campsites (campsite_sites) -> Buildings
-- and default Buildings on.
-- ============================================================

alter table experience_layers
  add column if not exists label_override       text,
  add column if not exists layer_group_override text;

create or replace function public.get_experience_config(p_slug text)
  returns json
  language sql
  security definer
as $function$
  select json_build_object(
    'experience', row_to_json(e.*),
    'layers', (
      select coalesce(json_agg(
        json_build_object(
          'id',                 el.id,
          'template_slug',      el.template_slug,
          'source_key',         el.template_slug,
          'style_overrides',    el.style_overrides,
          'filter_expr',        el.filter_expr,
          'visible_by_default', el.visible_by_default,
          'label',              coalesce(el.label_override, lt.label),
          'geom_type',          lt.geom_type,
          'layer_group',        coalesce(el.layer_group_override, lt.layer_group),
          'default_style',      lt.default_style,
          'field_schema',       lt.field_schema,
          'popup_template',     lt.popup_template,
          'popup_css',          lt.popup_css,
          'sort_order',         el.sort_order
        ) order by el.sort_order
      ), '[]'::json)
      from experience_layers el
      join layer_templates lt on lt.slug = el.template_slug
      where el.experience_id = e.id
    )
  )
  from experiences e
  where e.slug = p_slug and e.is_public = true;
$function$;

update experience_layers el set
  label_override = case when el.template_slug = 'pois_camping' then 'Campgrounds'
                        else el.label_override end,
  layer_group_override = case when el.template_slug in ('pois_camping', 'buildings') then 'Camping'
                              else el.layer_group_override end,
  visible_by_default = case when el.template_slug = 'buildings' then true
                            else el.visible_by_default end,
  sort_order = case el.template_slug
                 when 'pois_camping'      then 0
                 when 'campsite_sites'    then 1
                 when 'buildings'         then 2
                 when 'pois_restrooms'    then 3
                 when 'pois_water'        then 4
                 when 'roads'             then 5
                 when 'parking'           then 6
                 when 'climbing_boulders' then 7
                 when 'climbing_areas'    then 8
                 when 'climbing_routes'   then 9
                 else el.sort_order end
where el.experience_id = (select id from experiences where slug = 'campsites');

-- Verify
select el.sort_order, coalesce(el.layer_group_override, lt.layer_group) as grp,
       coalesce(el.label_override, lt.label) as label, el.template_slug, el.visible_by_default
from experience_layers el
join layer_templates lt on lt.slug = el.template_slug
where el.experience_id = (select id from experiences where slug = 'campsites')
order by el.sort_order;
