-- ============================================================
-- Devil's Lake Mapping Project, point G3 at Devil's Lake Group Camp
-- Applied via Supabase MCP; recorded for the repo log.
--
-- G3 is a single group site within Devil's Lake's Group Camp. Migration 038
-- temporarily pointed it at the park overview map (loop unknown); now repoint it
-- to the Group Camp map (mapId -2147483629). res/tx stays Devil's Lake
-- (-2147483634). Both duplicate G3 rows (12924, 12954) are updated.
-- ============================================================

update osm_geometries
set properties = jsonb_set(properties, '{reservation_url}',
      to_jsonb('https://wisconsin.goingtocamp.com/create-booking/results?transactionLocationId=-2147483634&resourceLocationId=-2147483634&mapId=-2147483629'::text)),
    updated_at = now()
where source = 'pois_camping' and name = 'G3' and id in (12924, 12954);

-- Verify
select id, name, properties->>'reservation_url' as reservation_url
from osm_geometries
where source = 'pois_camping' and name = 'G3'
order by id;
