"""
Import Sauk County's public "Trails and Paths" ArcGIS layer into osm_geometries as
the `sauk_trails` vector layer, so it renders + toggles through the normal layer
machinery (layer_templates row + experience_layers links added in migration 057).

Source: https://gis.co.sauk.wi.us/arcgis/rest/services/Sauk/TrailsAndPaths/MapServer
We pull layer 9 ("All Trails", every trail with a TRAILTYPE), reprojected to WGS84
(outSR=4326) as GeoJSON, paginated (maxRecordCount 1000). Each run fully refreshes
the layer via the replace_layer_geometries RPC (first batch truncates, rest append),
so the county's edits flow through on the schedule.

Writes go through the replace_layer_geometries SECURITY DEFINER RPC (migration 057)
using the SERVICE key, the anon key is RLS-blocked for writes
(memory: supabase-write-constraints).

Usage:
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/import_sauk_trails.py --dry-run
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/import_sauk_trails.py

Required env (locally via 1Password `op`; in CI via GitHub Actions secrets):
  SUPABASE_URL   https://<project>.supabase.co
  SUPABASE_KEY   service_role key (bypasses RLS for the write RPC)
"""
import os, sys, json, urllib.parse, urllib.request, urllib.error

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

LAYER_URL = ('https://gis.co.sauk.wi.us/arcgis/rest/services/Sauk/TrailsAndPaths/'
             'MapServer/9/query')
SOURCE = 'sauk_trails'
PAGE = 1000          # service maxRecordCount
WRITE_BATCH = 300    # features per RPC call (keep the JSON payload modest)
OUT_FIELDS = 'NAME,TRAILTYPE,TRLFUNCTION,SKILLLEVEL,SURFTYPE,CONDITION,TOTALLENGTH'

DRY_RUN = '--dry-run' in sys.argv


def _request(url, *, method='GET', headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        sys.stderr.write(f'  HTTP {e.code} {method} {url.split("?")[0]}: {e.read().decode()[:300]}\n')
        return None


def fetch_trails():
    """Page through the ArcGIS layer as GeoJSON (WGS84). Returns mapped features."""
    out, offset = [], 0
    while True:
        qs = urllib.parse.urlencode({
            'where': '1=1', 'outFields': OUT_FIELDS, 'outSR': 4326,
            'returnGeometry': 'true', 'f': 'geojson',
            'resultRecordCount': PAGE, 'resultOffset': offset,
        })
        data = _request(f'{LAYER_URL}?{qs}')
        feats = (data or {}).get('features') or []
        for ft in feats:
            geom = ft.get('geometry')
            if not geom or not geom.get('coordinates'):
                continue
            p = ft.get('properties') or {}
            props = {
                'name': p.get('NAME'),
                'trail_type': p.get('TRAILTYPE'),
                'trail_function': p.get('TRLFUNCTION'),
                'skill_level': p.get('SKILLLEVEL'),
                'surface': p.get('SURFTYPE'),
                'condition': p.get('CONDITION'),
                'length_mi': p.get('TOTALLENGTH'),
                '_src': 'sauk_county_gis',
            }
            props = {k: v for k, v in props.items() if v not in (None, '')}
            out.append({'type': 'Feature', 'geometry': geom, 'properties': props})
        if len(feats) < PAGE:
            break
        offset += PAGE
    return out


def write_batches(features):
    url = f'{SUPABASE_URL}/rest/v1/rpc/replace_layer_geometries'
    headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}',
               'Content-Type': 'application/json'}
    total = 0
    for i in range(0, len(features), WRITE_BATCH):
        batch = features[i:i + WRITE_BATCH]
        n = _request(url, method='POST', headers=headers, body={
            'p_source': SOURCE, 'p_features': batch, 'p_truncate': i == 0,
        })
        total += n if isinstance(n, int) else 0
        print(f'  wrote {i + len(batch)}/{len(features)}')
    return total


def main():
    need = [n for n, v in (('SUPABASE_URL', SUPABASE_URL),) if not v]
    if not DRY_RUN:
        need += [n for n, v in (('SUPABASE_KEY', SUPABASE_KEY),) if not v]
    if need:
        sys.exit(f'ERROR: missing env: {", ".join(need)}\n'
                 'Run via: op run --env-file=.env.tpl -- .venv/Scripts/python.exe '
                 'scripts/import_sauk_trails.py')

    feats = fetch_trails()
    types = {}
    for f in feats:
        t = f['properties'].get('trail_type', '?')
        types[t] = types.get(t, 0) + 1
    print(f'Fetched {len(feats)} trail features{"  [DRY RUN]" if DRY_RUN else ""}')
    for t, c in sorted(types.items(), key=lambda kv: -kv[1]):
        print(f'  {c:>5}  {t}')
    if not feats:
        sys.exit('No features returned, aborting (refusing to truncate the layer).')

    if DRY_RUN:
        print('\n[dry run] would replace osm_geometries source=sauk_trails with the above.')
        return
    written = write_batches(feats)
    print(f'\nDone. replaced sauk_trails with {written} features.')


if __name__ == '__main__':
    main()
