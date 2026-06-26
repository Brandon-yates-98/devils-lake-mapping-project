-- ============================================================
-- Devil's Lake Mapping Project, rename custom_data.apex_description
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Part of the Apex → Devil's Lake Mapping Project rebrand. The legacy custom
-- field key `apex_description` (the popup "Description" fallback, edited via the
-- editor's custom-description textarea) is renamed to `custom_description`.
-- The viewer and editor now read/write `custom_description`; this moves any
-- existing values so they keep rendering. Applies to all sources/layers.
-- ============================================================

update osm_geometries
set custom_data = (custom_data - 'apex_description')
      || jsonb_build_object('custom_description', custom_data->'apex_description'),
    updated_at = now()
where custom_data ? 'apex_description';

-- Verify (old_left should be 0)
select count(*) filter (where custom_data ? 'apex_description')  as old_left,
       count(*) filter (where custom_data ? 'custom_description') as new_count
from osm_geometries;
