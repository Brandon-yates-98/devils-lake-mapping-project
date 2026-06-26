-- ============================================================
-- Devil's Lake Mapping Project, seed GoingToCamp deep links for the remaining
-- Wisconsin State Parks campgrounds. Applied via Supabase MCP; recorded here.
--
-- IDs harvested from wisconsin.goingtocamp.com's own API
-- (/api/resourceLocation + /api/maps?resourceLocationId=...). Within a park the
-- campgrounds share the park's resourceLocationId/transactionLocationId and
-- differ only by mapId (the campground/loop sub-map). The viewer parses these
-- three IDs and rebuilds the full URL with the user's chosen dates + equipment
-- type + a fresh searchTime (see goingToCampUrl / parseGoingToCamp).
--
--   Park          res = tx          campground            mapId
--   Devil's Lake  -2147483634       Ice Age (Upper)       -2147483632  (migration 037)
--                                   Northern Lights       -2147483635
--                                   Quartzite             -2147483636
--                                   Group Campground      -2147483629
--                                   G3 (-> park overview) -2147483637  (loop unverified)
--   Mirror Lake   -2147483610       Bluewater Bay         -2147483574
--                                   Cliffwood             -2147483575
--                                   Sandstone Ridge       -2147483575  (shared loop map)
--   Rocky Arbor   -2147483595       Rocky Arbor           -2147483473
--   Tower Hill    -2147483593       Tower Hill            -2147483401
-- ============================================================

update osm_geometries g
set properties = jsonb_set(
      g.properties, '{reservation_url}',
      to_jsonb('https://wisconsin.goingtocamp.com/create-booking/results?transactionLocationId='
        || v.tx::text || '&resourceLocationId=' || v.res::text || '&mapId=' || v.map::text)),
    updated_at = now()
from (values
  (13017, -2147483610, -2147483610, -2147483574),  -- Bluewater Bay (Mirror Lake)
  (13019, -2147483610, -2147483610, -2147483575),  -- Cliffwood (Mirror Lake)
  (13018, -2147483610, -2147483610, -2147483575),  -- Sandstone Ridge (Mirror Lake)
  (13036, -2147483634, -2147483634, -2147483635),  -- Northern Lights (Devil's Lake)
  (13070, -2147483634, -2147483634, -2147483636),  -- Quartzite (Devil's Lake)
  (13037, -2147483634, -2147483634, -2147483629),  -- Group Campground (Devil's Lake)
  (13063, -2147483593, -2147483593, -2147483401),  -- Tower Hill
  (13071, -2147483595, -2147483595, -2147483473),  -- Rocky Arbor
  (12954, -2147483634, -2147483634, -2147483637),  -- G3 (Devil's Lake overview)
  (12924, -2147483634, -2147483634, -2147483637)   -- G3 (Devil's Lake overview)
) as v(id, res, tx, map)
where g.id = v.id and g.source = 'pois_camping';

-- Verify
select id, name, properties->>'reservation_url' as reservation_url
from osm_geometries
where source = 'pois_camping'
  and id in (13017,13019,13018,13036,13070,13037,13063,13071,12954,12924)
order by name;
