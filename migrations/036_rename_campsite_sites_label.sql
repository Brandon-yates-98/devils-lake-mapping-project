-- ============================================================
-- Apex Web Maps — campsites: show "Campsite Sites" as just "Campsites"
-- Applied via Supabase MCP; recorded for the repo log.
-- Per-experience label_override (migration 031); global template unchanged.
-- ============================================================

update experience_layers el
   set label_override = 'Campsites'
  from experiences e
 where e.id = el.experience_id
   and e.slug = 'campsites'
   and el.template_slug = 'campsite_sites';

-- Verify
select coalesce(el.label_override, lt.label) as shown, el.template_slug
from experience_layers el
join layer_templates lt on lt.slug = el.template_slug
where el.experience_id = (select id from experiences where slug = 'campsites')
  and el.template_slug = 'campsite_sites';
