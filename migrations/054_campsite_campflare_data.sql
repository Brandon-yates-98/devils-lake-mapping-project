-- ============================================================
-- Devil's Lake Mapping Project — write Campflare per-site data onto campsites
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Used by scripts/enrich_campsites_campflare.py to stamp each campsite_sites row
-- with the static Campflare attributes used to enrich the public popup:
--   properties.campflare_id   — the Campflare campsite id (join key for availability)
--   properties.campflare      — { kind, firepit, water/electric/sewer_hookups,
--                                 ada_accessible, max_people, price_per_night,
--                                 check_in, check_out, photos[], reservation_url }
-- and a custom_data.campflare = { fetched_at } stamp so refreshes are auditable.
--
-- Availability is NOT stored here — it changes constantly and is fetched live by
-- the campflare-availability edge function. This is the slow-moving site metadata.
--
-- Re-runnable (last write wins). service_role-only, mirroring set_campsite_sv_status
-- (migration 053) and apply_campground_google_enrichment (migration 048).
-- ============================================================

create or replace function public.set_campsite_campflare(p_id bigint, p_data jsonb)
returns void language sql security definer set search_path = public as $fn$
  update osm_geometries
  set properties = coalesce(properties, '{}'::jsonb) || p_data,
      custom_data = jsonb_set(
        coalesce(custom_data, '{}'::jsonb),
        '{campflare}',
        jsonb_build_object('fetched_at', now()),
        true),
      updated_at = now()
  where id = p_id and source = 'campsite_sites';
$fn$;

revoke execute on function public.set_campsite_campflare(bigint, jsonb) from public, anon, authenticated;
grant  execute on function public.set_campsite_campflare(bigint, jsonb) to service_role;
