-- ============================================================
-- Devil's Lake Mapping Project, fold campsite spurs into the roads layer
-- Spurs were stored as a separate source ('campsite_spurs', migration 028)
-- and rendered as a campsite companion. They are now first-class roads:
-- re-tagged source='roads' with highway='service' so they toggle, style,
-- and load with every other road. The _spur / campsite / len_m properties
-- are retained for provenance and so migration 028 can find + refresh them.
--
-- RE-RUNNABLE: no-op once the rows already live in 'roads'.
-- ============================================================

update osm_geometries
set source     = 'roads',
    properties = properties || '{"highway":"service"}'::jsonb
where source = 'campsite_spurs';

select count(*) as spurs_now_roads
from osm_geometries
where source = 'roads' and coalesce(properties->>'_spur', '') = 'true';
