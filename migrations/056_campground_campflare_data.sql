-- ============================================================
-- Devil's Lake Mapping Project — write Campflare campground-level data onto the
-- campgrounds layer (osm_geometries WHERE source='pois_camping').
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Companion to set_campsite_campflare (migration 054), but for the campground
-- feature rather than individual sites. Only the DNR campgrounds Campflare covers
-- (Quartzite, Northern Lights) get a blob; enrich_campsites_campflare.py matches
-- them by the GoingToCamp mapId in properties.reservation_url. The public popup
-- shows the Campflare section only when properties.campflare is present, so the
-- "DNR campgrounds only" rule is enforced by the data.
--
-- Stores properties.campflare = { status, status_description, amenities{...},
--   price_min, price_max, check_in, check_out, cell_service{...} } plus a
-- custom_data.campflare = { fetched_at } stamp.
--
-- Re-runnable (last write wins). service_role-only.
-- ============================================================

create or replace function public.set_campground_campflare(p_id bigint, p_data jsonb)
returns void language sql security definer set search_path = public as $fn$
  update osm_geometries
  set properties = coalesce(properties, '{}'::jsonb) || p_data,
      custom_data = jsonb_set(
        coalesce(custom_data, '{}'::jsonb),
        '{campflare}',
        jsonb_build_object('fetched_at', now()),
        true),
      updated_at = now()
  where id = p_id and source = 'pois_camping';
$fn$;

revoke execute on function public.set_campground_campflare(bigint, jsonb) from public, anon, authenticated;
grant  execute on function public.set_campground_campflare(bigint, jsonb) to service_role;
