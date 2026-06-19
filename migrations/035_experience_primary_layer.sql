-- ============================================================
-- Apex Web Maps — experiences.primary_layer
-- Applied via Supabase MCP; recorded here for the repo log.
--
-- The "primary layer" is the layer whose features the top-of-map experience
-- bar (search / filters / list) operates on. Nullable: experiences without it
-- simply don't render the bar. No get_experience_config change is needed —
-- it returns row_to_json(e.*), so the new column flows through automatically.
-- ============================================================

alter table experiences add column if not exists primary_layer text;

update experiences set primary_layer = 'pois_camping' where slug = 'campsites';

-- Verify
select slug, primary_layer from experiences order by slug;
