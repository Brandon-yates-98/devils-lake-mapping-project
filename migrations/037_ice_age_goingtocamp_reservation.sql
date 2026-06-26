-- ============================================================
-- Devil's Lake Mapping Project, seed Ice Age Campground's GoingToCamp deep link
-- Applied via Supabase MCP; recorded for the repo log.
--
-- The pois_camping reserve button is gated on the goingtocamp.com host: a
-- campground becomes a live deep link only when its reservation_url carries the
-- location IDs (transactionLocationId / resourceLocationId / mapId). The viewer
-- parses those IDs and rebuilds the full URL with fresh dates + searchTime each
-- time the user picks dates (see goingToCampUrl / parseGoingToCamp in
-- docs/index.html). Other Wisconsin DNR parks remain seeded with the bare
-- https://wisconsin.goingtocamp.com URL until their IDs are captured, and keep
-- their plain link until then.
-- ============================================================

update osm_geometries
set properties = jsonb_set(
      properties,
      '{reservation_url}',
      to_jsonb('https://wisconsin.goingtocamp.com/create-booking/results?transactionLocationId=-2147483634&resourceLocationId=-2147483634&mapId=-2147483632'::text)),
    updated_at = now()
where id = 13069
  and source = 'pois_camping'
  and name = 'Ice Age Campground';

-- Verify
select id, name, properties->>'reservation_url' as reservation_url
from osm_geometries
where id = 13069 and source = 'pois_camping';
