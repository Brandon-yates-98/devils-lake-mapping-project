-- ============================================================
-- Devil's Lake Mapping Project, fix Fox Hill's Campspot reservation link
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Campspot reserve links are gated on the campspot.com/book/{slug} host+path:
-- the viewer parses the slug and opens a date + site-type picker that builds the
-- /search/{start}/{end}/guests0,1,0/list?campsiteCategory=... deep link (see
-- parseCampspot / campspotUrl / CAMPSPOT_CATEGORIES in docs/index.html).
--
-- Fox Hill was stored as a /park/ landing page (not bookable). Its real booking
-- slug is foxhillrvpark. The other four campspot campgrounds (Green Valley,
-- Lake Wisconsin, Smoky Hollow, Skillet Creek/Wheeler's) already use /book/{slug}.
-- ============================================================

update osm_geometries
set properties = jsonb_set(properties, '{reservation_url}',
      to_jsonb('https://www.campspot.com/book/foxhillrvpark'::text)),
    updated_at = now()
where id = 13032 and source = 'pois_camping'
  and name = 'Fox Hill RV Park & Campground';

-- Verify
select id, name, properties->>'reservation_url' as reservation_url
from osm_geometries
where source = 'pois_camping' and properties->>'reservation_url' ilike '%campspot.com%'
order by name;
