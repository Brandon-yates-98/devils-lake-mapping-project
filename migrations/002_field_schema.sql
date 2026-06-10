-- ============================================================
-- Apex Web Maps — Add field_schema to layer_templates
-- Adds structured field definitions for custom/climbing layers.
-- Updates get_experience_config to return field_schema.
-- Safe to re-run (IF NOT EXISTS / CREATE OR REPLACE).
-- ============================================================

-- ── 1. Add field_schema column ───────────────────────────────
alter table layer_templates
  add column if not exists field_schema jsonb not null default '[]'::jsonb;

-- ── 2. Update get_experience_config to include field_schema ──
create or replace function get_experience_config(p_slug text)
returns json language sql security definer as $$
  select json_build_object(
    'experience', row_to_json(e.*),
    'layers', (
      select coalesce(json_agg(
        json_build_object(
          'id',                 el.id,
          'template_slug',      el.template_slug,
          'instance_type',      el.instance_type,
          'source_key',         case
                                  when el.instance_type = 'static' then el.static_source
                                  else el.template_slug
                                end,
          'style_overrides',    el.style_overrides,
          'filter_expr',        el.filter_expr,
          'visible_by_default', el.visible_by_default,
          'label',              lt.label,
          'geom_type',          lt.geom_type,
          'layer_group',        lt.layer_group,
          'default_style',      lt.default_style,
          'field_schema',       lt.field_schema,
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
select slug, label, jsonb_array_length(field_schema) as field_count
from layer_templates
order by sort_order;
