-- ============================================================
-- Apex Web Maps — Add campsite price/booking fields to the camping layer
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- The enrichment VALUES are written by fetch via upsert_osm_feature (into
-- each feature's base properties). This migration registers the FIELD
-- DEFINITIONS on the pois_camping layer so they show in the popup + editor.
-- Direct field_schema writes via the API key are RLS-blocked, so this runs
-- from the SQL Editor. Idempotent (guarded by @> check).
-- ============================================================

update layer_templates
set field_schema = field_schema || '[
  {"name":"min_price","type":"number","label":"Min Price (USD/night)","base":true},
  {"name":"max_price","type":"number","label":"Max Price (USD/night)","base":true},
  {"name":"reservation_url","type":"text","label":"Reservation Link","base":true},
  {"name":"price_date_extracted","type":"text","label":"Price Date Extracted","base":true},
  {"name":"price_source","type":"text","label":"Price Source","base":true,"hidden":true}
]'::jsonb
where slug = 'pois_camping'
  and not (field_schema @> '[{"name":"min_price"}]');

-- Verify
select jsonb_pretty(field_schema) from layer_templates where slug = 'pois_camping';
