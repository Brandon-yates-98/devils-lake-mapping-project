-- ============================================================
-- Devil's Lake Mapping Project, restore Skillet Creek's reservation link + price
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Skillet Creek Campground (id 13056, formerly Wheeler's; see migration 042) was
-- the only Campspot campground missing both reservation_url and pricing, so its
-- popup showed no Reserve workflow and no price. The Campspot booking slug
-- (skillet-creek-campground) is the one already wired in CAMPSPOT_CATEGORIES in
-- docs/index.html and referenced by migrations 039/042; verified it resolves
-- (campspot.com/book/skillet-creek-campground -> HTTP 200). The popup turns any
-- http-valued property into a link (fmtVal in docs/index.html), and the reserve
-- handler keys off the campspot.com/book/ href, so restoring reservation_url is
-- enough to bring the booking flow back.
--
-- Price: the campground only publishes "starting" rates (tent from $40, RV from
-- $50), so we store min_price=40 and leave max_price unset, the same min-only
-- shape ~10 other records already use. Source is their own rates page.
-- ============================================================

update osm_geometries
set properties = properties || jsonb_build_object(
      'reservation_url',      'https://www.campspot.com/book/skillet-creek-campground',
      'min_price',            40,
      'price_source',         'https://www.skilletcreekcampground.com/tent-camping/',
      'price_date_extracted', '2026-06-23'),
    updated_at = now()
where id = 13056 and source = 'pois_camping';

-- Verify
select id, name,
       properties->>'reservation_url' as reservation_url,
       properties->'min_price'        as min_price,
       properties->>'price_source'    as price_source
from osm_geometries
where id = 13056 and source = 'pois_camping';
