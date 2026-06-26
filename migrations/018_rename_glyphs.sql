-- ============================================================
-- Devil's Lake Mapping Project, rebrand marker glyph ids
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- drawMapGlyph() in both maps now answers to 'dl-*' names
-- ('apex-*' before the rebrand).
-- ============================================================

update layer_templates
set default_style = default_style || '{"icon": "dl-carabiner"}'::jsonb
where default_style->>'icon' = 'apex-carabiner';

update layer_templates
set default_style = default_style || '{"icon": "dl-boulder"}'::jsonb
where default_style->>'icon' = 'apex-boulder';

update layer_templates
set default_style = default_style || '{"icon": "dl-cliff"}'::jsonb
where default_style->>'icon' = 'apex-cliff';
