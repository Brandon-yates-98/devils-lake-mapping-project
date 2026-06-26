-- ============================================================
-- Devil's Lake Mapping Project, rename Wheeler's Campground to Skillet Creek Campground
-- Applied via Supabase MCP; recorded for the repo log.
--
-- The campground (id 13056, Campspot slug skillet-creek-campground) is now
-- called Skillet Creek Campground. Update both the name column and
-- properties.name (the latter drives the popup title, search, and list).
-- ============================================================

update osm_geometries
set name = 'Skillet Creek Campground',
    properties = jsonb_set(properties, '{name}', to_jsonb('Skillet Creek Campground'::text)),
    updated_at = now()
where source = 'pois_camping' and id = 13056;

-- Verify
select id, name, properties->>'name' as prop_name
from osm_geometries
where source = 'pois_camping' and id = 13056;
