-- ============================================================
-- Devil's Lake Mapping Project — "Hiking Loops" template layer
-- Applied via Supabase MCP; recorded for the repo log.
--
-- scripts/compute_trail_loops.py writes the precomputed loops to osm_geometries
-- under source 'hiking_loops' (in addition to the structured trail_loops table),
-- so they render + toggle through the normal layer machinery (get_layer_geojson).
-- This migration registers the template + experience links and a popup that
-- reuses the existing .tr-pop styling (shared with the Sauk trail popup).
-- ============================================================

insert into layer_templates (slug, label, geom_type, default_style, layer_group, is_custom, sort_order, popup_template)
values (
  'hiking_loops', 'Hiking Loops', 'line',
  '{"color":"#1f7a3d","width":3}'::jsonb,
  'Paths & Routes', false, 101,
  $tpl$<div class="dl-popup-custom"><div class="tr-pop">
  <div class="tr-pop-head" style="border-bottom-color:#1f7a3d">
    <div class="tr-pop-title">{{ name }}</div>
    <span class="tr-pop-type" style="background:#1f7a3d"><i class="fa-solid fa-person-hiking"></i> Loop</span>
  </div>
  <div class="tr-pop-body">
    <div class="tr-pop-facts"><span><i class="fa-solid fa-ruler-horizontal"></i> {{ distance_mi }} mi</span></div>
    {{#if trails_label}}<div class="tr-pop-fn">{{ trails_label }}</div>{{/if}}
    <button class="popup-directions-btn"><i class="fa-solid fa-route"></i> Directions</button>
  </div>
</div></div>$tpl$
)
on conflict (slug) do update
  set label = excluded.label, geom_type = excluded.geom_type,
      default_style = excluded.default_style, layer_group = excluded.layer_group,
      popup_template = excluded.popup_template;

-- Add to both experiences (public Campsites map + private default/editor map),
-- off by default (opt-in overlay).
insert into experience_layers (experience_id, template_slug, visible_by_default, sort_order)
select e.id, 'hiking_loops', false, 101
from experiences e
where e.slug in ('campsites', 'default')
  and not exists (
    select 1 from experience_layers el
    where el.experience_id = e.id and el.template_slug = 'hiking_loops');
