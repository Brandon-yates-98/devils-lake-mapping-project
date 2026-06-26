-- ============================================================
-- Devil's Lake Mapping Project, Saved filter presets per experience
-- Stores admin-defined filter queries (price / field-presence) that
-- surface as buttons in the public viewer.
-- ⚠ Run this in the Supabase SQL Editor (anon key cannot ALTER TABLE).
--
-- No RPC change needed: get_experience_config returns row_to_json(e.*),
-- so this column flows to the public config automatically.
-- ============================================================

-- Each entry in the array looks like:
--   {
--     "id":      "uuid",
--     "label":   "Under $50 / night",
--     "icon":    "fa-dollar-sign",          -- optional Font Awesome class
--     "target":  "pois_camping",            -- layer source_key the filter applies to
--     "match":   "all",                     -- "all" (AND) | "any" (OR) across conditions
--     "conditions": [
--       { "field": "min_price", "op": "<", "value": 50 },
--       { "field": "website",   "op": "exists" }
--     ]
--   }
alter table experiences
  add column if not exists saved_filters jsonb not null default '[]'::jsonb;

-- ── Verify ────────────────────────────────────────────────
select slug, title, jsonb_array_length(saved_filters) as filter_count
from experiences
order by created_at;
