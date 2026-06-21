-- ============================================================
-- Devil's Lake Mapping Project — write Street View coverage status onto campsites
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Used by scripts/precompute_streetview_coverage.py (a free metadata sweep) to mark
-- each campsite_sites row with properties.sv_status = 'ok' (Street View imagery
-- exists at the standing point) or 'none' (ZERO_RESULTS). The public map shows the
-- Street View photo hero only for 'ok' sites, and a branded placeholder otherwise.
-- service_role-only.
-- ============================================================

create or replace function public.set_campsite_sv_status(p_id bigint, p_status text)
returns void language sql security definer set search_path = public as $fn$
  update osm_geometries
  set properties = coalesce(properties,'{}'::jsonb) || jsonb_build_object('sv_status', p_status),
      updated_at = now()
  where id = p_id and source = 'campsite_sites';
$fn$;

revoke execute on function public.set_campsite_sv_status(bigint, text) from public, anon, authenticated;
grant  execute on function public.set_campsite_sv_status(bigint, text) to service_role;
