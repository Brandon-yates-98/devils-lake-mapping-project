-- ============================================================
-- Devil's Lake Mapping Project, Add custom popup template + CSS to layer_templates
-- Lets each layer carry its own popup HTML template and CSS.
-- Updates get_experience_config to return popup_template / popup_css.
-- Safe to re-run (IF NOT EXISTS / CREATE OR REPLACE).
-- ⚠ Run this in the Supabase SQL Editor, the anon API key cannot
--   ALTER TABLE or CREATE OR REPLACE FUNCTION.
-- ============================================================

-- ── 1. Add popup columns ─────────────────────────────────────
alter table layer_templates
  add column if not exists popup_template text;

alter table layer_templates
  add column if not exists popup_css text;

-- ── 2. Update get_experience_config to include popup fields ──
-- NOTE: the deployed experience_layers has no instance_type/static_source
-- columns, so source_key is simply the template_slug. Mirror the live
-- function shape and just add popup_template / popup_css.
create or replace function get_experience_config(p_slug text)
returns json language sql security definer as $$
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
          'label',              lt.label,
          'geom_type',          lt.geom_type,
          'layer_group',        lt.layer_group,
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
$$;

-- ── 3. Verify ────────────────────────────────────────────────
select slug, label,
       (popup_template is not null) as has_popup_template,
       (popup_css is not null)      as has_popup_css
from layer_templates
order by sort_order;
