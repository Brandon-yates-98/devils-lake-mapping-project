-- ============================================================
-- Apex Web Maps — One-time cleanup: remove campsites from 'pois'
-- Run in Supabase: Dashboard → SQL Editor → New query
--
-- Campsites now live in the dedicated 'pois_camping' layer (all 68),
-- so they should no longer appear in the general 'pois' layer.
-- Direct DELETE is blocked for the API key (no delete RLS policy on
-- osm_geometries), so this runs from the SQL Editor.
--
-- Scope: every camp_site / caravan_site / leisure=camp_site in source
-- 'pois'. The matching rows already exist (verified) in 'pois_camping',
-- so nothing is lost. Re-importable via fetch_campsites.py if needed.
-- ============================================================

-- Preview what will be removed (run this first if you want to eyeball it):
-- select id, name, properties->>'tourism' as tourism, properties->>'leisure' as leisure
-- from osm_geometries
-- where source = 'pois'
--   and (properties->>'tourism' in ('camp_site','caravan_site')
--        or properties->>'leisure' = 'camp_site');

delete from osm_geometries
where source = 'pois'
  and (properties->>'tourism' in ('camp_site', 'caravan_site')
       or properties->>'leisure' = 'camp_site');

-- Verify: should report 0 campsites left in 'pois'
select count(*) as campsites_left_in_pois
from osm_geometries
where source = 'pois'
  and (properties->>'tourism' in ('camp_site', 'caravan_site')
       or properties->>'leisure' = 'camp_site');
