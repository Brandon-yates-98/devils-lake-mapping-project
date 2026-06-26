"""
Precompute Street View coverage for campsites and store it as properties.sv_status
('ok' = imagery exists, 'none' = ZERO_RESULTS) so the public map can show the
Street View hero only where it'll actually render, and a branded placeholder
otherwise (never a gray "no imagery" tile).

Uses the Street View **metadata** endpoint, which is FREE (no per-request charge),
so a full sweep of all campsites costs nothing. Run after set_campsite_streetview_camera()
(it reads the sv_lat/sv_lng that function writes); re-run when coverage may have changed.

Two modes:
  * default     , write sv_status via the set_campsite_sv_status RPC (needs the
                   service_role key). Use this on a schedule / locally with secrets.
  * --emit-sql  , print one UPDATE…FROM VALUES to stdout instead of writing, so it
                   can run with only a read key (apply the SQL via Supabase MCP).

Usage:
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/precompute_streetview_coverage.py
  ! ... scripts/precompute_streetview_coverage.py --emit-sql > coverage.sql

Env:
  SUPABASE_URL              https://<project>.supabase.co
  SUPABASE_KEY              service_role key (write mode) or a read key (--emit-sql)
  GOOGLE_STREETVIEW_KEY     the Street View key (same one the map uses)
  GOOGLE_STREETVIEW_REFERER an allowed HTTP referer for that key (it's referrer-restricted)
"""
import os, sys, json, time, urllib.request, urllib.error

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
SV_KEY       = os.environ.get('GOOGLE_STREETVIEW_KEY', '')
SV_REFERER   = os.environ.get('GOOGLE_STREETVIEW_REFERER', '')
EMIT_SQL     = '--emit-sql' in sys.argv

META_URL = 'https://maps.googleapis.com/maps/api/streetview/metadata'


def _get(url, headers):
    req = urllib.request.Request(url, headers=headers, method='GET')
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def fetch_campsites():
    url = (f'{SUPABASE_URL}/rest/v1/osm_geometries'
           '?source=eq.campsite_sites&select=id,name,properties')
    return _get(url, {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'})


def coverage(lat, lng):
    """Return 'ok' if Street View imagery exists near (lat,lng), 'none' if not,
    or None to skip (auth/quota error, don't overwrite)."""
    url = f'{META_URL}?location={lat},{lng}&key={SV_KEY}'
    headers = {}
    if SV_REFERER:
        headers['Referer'] = SV_REFERER
    try:
        data = _get(url, headers)
    except urllib.error.HTTPError as e:
        sys.stderr.write(f'  metadata HTTP {e.code}: {e.read().decode()[:120]}\n')
        return None
    status = data.get('status')
    if status == 'OK':
        return 'ok'
    if status in ('ZERO_RESULTS', 'NOT_FOUND'):
        return 'none'
    sys.stderr.write(f'  metadata status {status} at {lat},{lng}, skipping\n')
    return None


def refresh_camera():
    """Recompute sv_lat/lng/heading from current geometry (set_campsite_streetview_camera)
    so coverage is checked at up-to-date standing points. Write mode only."""
    url = f'{SUPABASE_URL}/rest/v1/rpc/set_campsite_streetview_camera'
    req = urllib.request.Request(url, data=b'{}', method='POST', headers={
        'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req).read()
        sys.stderr.write('Refreshed campsite Street View camera (sv_lat/lng/heading).\n')
    except urllib.error.HTTPError as e:
        sys.stderr.write(f'  camera refresh HTTP {e.code}: {e.read().decode()[:160]}\n')


def write_status(row_id, status):
    url = f'{SUPABASE_URL}/rest/v1/rpc/set_campsite_sv_status'
    body = json.dumps({'p_id': row_id, 'p_status': status}).encode()
    req = urllib.request.Request(url, data=body, method='POST', headers={
        'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json'})
    urllib.request.urlopen(req).read()


def main():
    missing = [n for n, v in (('SUPABASE_URL', SUPABASE_URL), ('SUPABASE_KEY', SUPABASE_KEY),
                              ('GOOGLE_STREETVIEW_KEY', SV_KEY)) if not v]
    if missing:
        sys.exit(f'ERROR: missing env: {", ".join(missing)}')

    if not EMIT_SQL:
        refresh_camera()

    rows = fetch_campsites()
    results = []  # (id, status)
    ok = none = skip = 0
    for r in rows:
        p = r.get('properties') or {}
        lat, lng = p.get('sv_lat'), p.get('sv_lng')
        if lat is None or lng is None:
            continue
        status = coverage(lat, lng)
        if status is None:
            skip += 1
            continue
        results.append((r['id'], status))
        ok += (status == 'ok'); none += (status == 'none')
        if not EMIT_SQL:
            write_status(r['id'], status)
        time.sleep(0.05)  # gentle; metadata is free but be polite

    sys.stderr.write(f'\nCoverage: ok={ok} none={none} skipped={skip} (of {len(rows)} campsites)\n')

    if EMIT_SQL and results:
        values = ',\n  '.join(f"({rid}, '{st}')" for rid, st in results)
        print("update osm_geometries o\n"
              "set properties = coalesce(o.properties,'{}'::jsonb) || jsonb_build_object('sv_status', v.status)\n"
              f"from (values\n  {values}\n) as v(id, status)\n"
              "where o.id = v.id and o.source = 'campsite_sites';")


if __name__ == '__main__':
    main()
