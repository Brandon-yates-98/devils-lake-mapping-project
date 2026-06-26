"""
Enrich campsites (osm_geometries WHERE source='campsite_sites') with Campflare's
static per-site data: site kind, firepit/hookups/ADA, capacity, nightly price,
check-in/out times, reservation URL, and photos. The public popup reads these from
properties.campflare; the Campflare campsite id is also stored (properties.campflare_id)
as documentation of the join.

This is the SLOW-MOVING metadata only. Live availability is fetched separately by the
campflare-availability edge function (it changes constantly and must not be cached in
the GeoJSON).

Campflare keys everything by its own campsite id; the /campsites `name` field is the
site number, which equals our properties.ref. We match Campflare site -> our row by
(campground, normalized site number) and log anything that doesn't match so the
normalization can be tightened.

Modes:
  --discover   Search Campflare for the Devil's Lake campgrounds and print their ids
               (run this first, then paste the ids into CAMPFLARE_CAMPGROUNDS in
               docs/index.html and, optionally, KNOWN_IDS below).
  --dry-run    Resolve + match but write nothing; print the plan.
  --emit-sql   Print one UPDATE…FROM VALUES to stdout instead of calling the write
               RPC, so it can run with a read key and be applied via Supabase MCP.

Writes go through the set_campsite_campflare SECURITY DEFINER RPC (migration 054)
using the SERVICE key — the anon key is RLS-blocked for writes
(memory: supabase-write-constraints).

Usage:
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/enrich_campsites_campflare.py --discover
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/enrich_campsites_campflare.py --dry-run
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/enrich_campsites_campflare.py

Required env (locally via 1Password `op`; in CI via GitHub Actions secrets):
  SUPABASE_URL         https://<project>.supabase.co
  SUPABASE_KEY         service_role key (bypasses RLS for the write RPC; a read key
                       is fine with --emit-sql / --discover / --dry-run)
  CAMPFLARE_API_KEY    Campflare v2 API key (Authorization header, raw — no "Bearer")
"""
import os, sys, json, re, time, urllib.parse, urllib.request, urllib.error

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
CF_KEY       = os.environ.get('CAMPFLARE_API_KEY', '')

CF_BASE  = 'https://api.campflare.com/v2'
PHOTOS_PER_SITE = 5

DISCOVER = '--discover' in sys.argv
DRY_RUN  = '--dry-run' in sys.argv
EMIT_SQL = '--emit-sql' in sys.argv

# Our campground slugs -> the text query used to find them on Campflare. Fill
# KNOWN_IDS after a --discover run to skip the search step (and to pin the exact
# campground when a search is ambiguous).
CAMPGROUNDS = {
    'quartzite':       'Devils Lake Quartzite Wisconsin',
    'northern_lights': 'Devils Lake Northern Lights Wisconsin',
}
KNOWN_IDS: dict[str, str] = {
    'quartzite':       'devils-lake-quartzite-wisc',
    'northern_lights': 'northern-lights-wisc',
}
# The campgrounds layer (pois_camping) has no slug, so each DNR campground feature
# is matched by the GoingToCamp mapId embedded in its reservation_url. Mirrors
# CAMPSITE_RESERVATION in docs/index.html.
CAMPGROUND_GTC_MAPID = {
    'quartzite':       '-2147483636',
    'northern_lights': '-2147483635',
}
# Devil's Lake bbox to bias/sanity-check campground search hits.
DL_BBOX = {'min_lat': 43.37, 'max_lat': 43.47, 'min_lng': -89.78, 'max_lng': -89.68}


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _request(url, *, method='GET', headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        sys.stderr.write(f'  HTTP {e.code} {method} {url.split("?")[0]}: {e.read().decode()[:300]}\n')
        return None


def _cf_headers():
    return {'Authorization': CF_KEY, 'Accept': 'application/json'}

def _sb_headers():
    return {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json'}


# ── Campflare ────────────────────────────────────────────────────────────────
def cf_search(query):
    data = _request(f'{CF_BASE}/campgrounds/search', method='POST', headers=_cf_headers(),
                    body={'query': query, 'limit': 10})
    return (data or {}).get('campgrounds', []) if isinstance(data, dict) else (data or [])

def _within_dl(loc):
    try:
        lat, lng = float(loc.get('latitude')), float(loc.get('longitude'))
    except (TypeError, ValueError):
        return False
    return (DL_BBOX['min_lat'] <= lat <= DL_BBOX['max_lat']
            and DL_BBOX['min_lng'] <= lng <= DL_BBOX['max_lng'])

def resolve_campground_id(slug, query):
    if KNOWN_IDS.get(slug):
        return KNOWN_IDS[slug]
    hits = cf_search(query)
    # Prefer a hit inside the Devil's Lake bbox; else the first result.
    near = [h for h in hits if _within_dl(h.get('location') or {})]
    chosen = (near or hits or [None])[0]
    if chosen:
        sys.stderr.write(f'  resolved {slug} -> {chosen.get("id")} ("{chosen.get("name")}")\n')
        return chosen.get('id')
    sys.stderr.write(f'  no Campflare campground found for {slug} (query "{query}")\n')
    return None

def cf_campsites(campground_id):
    data = _request(f'{CF_BASE}/campground/{urllib.parse.quote(str(campground_id))}/campsites',
                    headers=_cf_headers())
    if isinstance(data, dict):
        return data.get('campsites', [])
    return data or []

def cf_campground(campground_id):
    return _request(f'{CF_BASE}/campground/{urllib.parse.quote(str(campground_id))}',
                    headers=_cf_headers()) or {}


# ── Supabase ─────────────────────────────────────────────────────────────────
def fetch_our_sites(slug):
    q = (f'{SUPABASE_URL}/rest/v1/osm_geometries?source=eq.campsite_sites'
         f'&properties->>campground=eq.{urllib.parse.quote(slug)}&select=id,name,properties')
    return _request(q, headers=_sb_headers()) or []

def fetch_our_campgrounds():
    q = (f'{SUPABASE_URL}/rest/v1/osm_geometries?source=eq.pois_camping'
         '&select=id,name,properties')
    return _request(q, headers=_sb_headers()) or []

def write_campflare(row_id, data):
    url = f'{SUPABASE_URL}/rest/v1/rpc/set_campsite_campflare'
    _request(url, method='POST', headers=_sb_headers(), body={'p_id': row_id, 'p_data': data})

def write_campground_campflare(row_id, data):
    url = f'{SUPABASE_URL}/rest/v1/rpc/set_campground_campflare'
    _request(url, method='POST', headers=_sb_headers(), body={'p_id': row_id, 'p_data': data})

def match_our_campground(our_campgrounds, map_id):
    """The DNR campground feature carries the GoingToCamp mapId in its reservation_url."""
    needle = f'mapId={map_id}'
    for row in our_campgrounds:
        if needle in ((row.get('properties') or {}).get('reservation_url') or ''):
            return row
    return None


# ── Matching ─────────────────────────────────────────────────────────────────
def _key(s):
    """Match key = (leading letters, digits), ignoring a trailing letter and a
    'Site ' prefix. So 'Site 60E' -> ('', '60') matches our '60', while accessible
    'A2' -> ('A', '2') stays distinct from numeric '2' -> ('', '2')."""
    s = re.sub(r'[^A-Za-z0-9]+', '', str(s or '').upper())
    s = re.sub(r'^SITE', '', s)
    m = re.match(r'^([A-Z]*)(\d+)[A-Z]*$', s)
    return (m.group(1), m.group(2)) if m else (s, '')

def build_index(campsites):
    """Index Campflare sites by match key (first wins on a collision)."""
    idx = {}
    for c in campsites:
        idx.setdefault(_key(c.get('name')), c)
    return idx

def match_site(ref, idx):
    return idx.get(_key(ref))


# ── Shape the Campflare payload into the stored blob ───────────────────────────
def build_data(c):
    photos = []
    for ph in (c.get('photos') or [])[:PHOTOS_PER_SITE]:
        url = ph.get('medium_url') or ph.get('large_url') or ph.get('original_url')
        if url:
            photos.append({'url': url, 'caption': ph.get('attribution') or ''})
    price = (c.get('price') or {}).get('per_night')
    sched = c.get('schedule') or {}
    blob = {
        'kind': c.get('kind'),
        'firepit': c.get('firepit'),
        'picnic_table': c.get('picnic_table'),
        'electric_hookups': c.get('electric_hookups'),
        'water_hookups': c.get('water_hookups'),
        'sewer_hookups': c.get('sewer_hookups'),
        'ada_accessible': c.get('ada_accessible'),
        'max_people': c.get('max_people'),
        'max_rv_length': c.get('max_rv_length'),
        'price_per_night': price,
        'check_in': sched.get('check_in_time'),
        'check_out': sched.get('check_out_time'),
        'reservation_url': c.get('reservation_url'),
        'photos': photos,
    }
    # Drop null/empty so the stored blob stays compact.
    blob = {k: v for k, v in blob.items() if v not in (None, '', [], {})}
    return {'campflare_id': str(c.get('id')), 'campflare': blob}


def build_campground_data(c):
    """Campground-level blob for the campground popup (DNR campgrounds only)."""
    am = c.get('amenities') or {}
    amenities = {k: v for k, v in {
        'showers': am.get('showers'),
        'toilets': am.get('toilets'),
        'toilet_kind': am.get('toilet_kind'),
        'dump_station': am.get('dump_station'),
        'water': am.get('water'),
        'camp_store': am.get('camp_store'),
        'wifi': am.get('wifi'),
        'pets_allowed': am.get('pets_allowed'),
        'fires_allowed': am.get('fires_allowed'),
        'electric_hookups': am.get('electric_hookups'),
        'trash': am.get('trash'),
    }.items() if v not in (None, False, '')}
    sched = c.get('default_campsite_schedule') or {}
    cell = {k: v for k, v in (c.get('cell_service') or {}).items() if v is not None}
    blob = {
        'status': c.get('status'),
        'status_description': c.get('status_description'),
        'amenities': amenities,
        'check_in': sched.get('check_in_time'),
        'check_out': sched.get('check_out_time'),
        'cell_service': cell or None,
    }
    blob = {k: v for k, v in blob.items() if v not in (None, '', [], {})}
    return {'campflare_id': str(c.get('id')), 'campflare': blob}


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    need = [n for n, v in (('SUPABASE_URL', SUPABASE_URL), ('CAMPFLARE_API_KEY', CF_KEY)) if not v]
    if not (DISCOVER or DRY_RUN or EMIT_SQL):
        need += [n for n, v in (('SUPABASE_KEY', SUPABASE_KEY),) if not v]
    if need:
        sys.exit(f'ERROR: missing env: {", ".join(need)}\n'
                 'Run via: op run --env-file=.env.tpl -- .venv/Scripts/python.exe '
                 'scripts/enrich_campsites_campflare.py')

    if DISCOVER:
        for slug, query in CAMPGROUNDS.items():
            print(f'\n# {slug}  (query: {query})')
            for h in cf_search(query):
                loc = h.get('location') or {}
                flag = ' *DL*' if _within_dl(loc) else ''
                print(f'  id={h.get("id")}  name="{h.get("name")}"  '
                      f'loc=({loc.get("latitude")},{loc.get("longitude")}){flag}')
        print('\nPaste the *DL* ids into CAMPFLARE_CAMPGROUNDS (docs/index.html) and KNOWN_IDS.')
        return

    sql_rows = []        # campsite_sites updates
    cg_sql_rows = []     # pois_camping (campground) updates
    our_campgrounds = fetch_our_campgrounds()
    total_ok = total_unmatched = 0
    for slug, query in CAMPGROUNDS.items():
        cg_id = resolve_campground_id(slug, query)
        if not cg_id:
            continue
        cf_sites = cf_campsites(cg_id)
        our_sites = fetch_our_sites(slug)
        idx = build_index(cf_sites)
        print(f'\n{slug}: {len(our_sites)} mapped sites, {len(cf_sites)} Campflare sites'
              f'{"  [DRY RUN]" if DRY_RUN else ""}')

        matched_refs = set()
        for row in our_sites:
            ref = (row.get('properties') or {}).get('ref')
            c = match_site(ref, idx)
            if not c:
                total_unmatched += 1
                print(f'  ? no Campflare match for ref={ref!r} (name={row.get("name")!r})')
                continue
            matched_refs.add(_key(c.get('name')))
            data = build_data(c)
            if EMIT_SQL:
                sql_rows.append((row['id'], json.dumps(data)))
            elif DRY_RUN:
                print(f'  + ref={ref}: would write campflare_id={data["campflare_id"]}, '
                      f'{len(data["campflare"].get("photos", []))} photo(s)')
            else:
                write_campflare(row['id'], data)
            total_ok += 1
        # Campflare sites we never matched to one of ours (extra loops, name drift).
        leftover = [c.get('name') for c in cf_sites if _key(c.get('name')) not in matched_refs]
        if leftover:
            print(f'  (unmatched Campflare sites: {", ".join(map(str, leftover[:20]))}'
                  f'{" …" if len(leftover) > 20 else ""})')

        # Campground-level enrichment for the DNR campground popup. Match our
        # pois_camping feature by the GoingToCamp mapId in its reservation_url.
        cg_row = match_our_campground(our_campgrounds, CAMPGROUND_GTC_MAPID.get(slug, ''))
        if cg_row:
            cg_data = build_campground_data(cf_campground(cg_id))
            ams = list((cg_data['campflare'].get('amenities') or {}).keys())
            if EMIT_SQL:
                cg_sql_rows.append((cg_row['id'], json.dumps(cg_data)))
            elif DRY_RUN:
                print(f'  campground "{cg_row.get("name")}": would write {len(ams)} amenities {ams}')
            else:
                write_campground_campflare(cg_row['id'], cg_data)
                print(f'  campground "{cg_row.get("name")}": wrote {len(ams)} amenities')
        else:
            print(f'  (no pois_camping feature matched mapId {CAMPGROUND_GTC_MAPID.get(slug)})')
        time.sleep(0.1)

    def _emit(rows, source):
        values = ',\n  '.join(f"({rid}, '{j.replace(chr(39), chr(39)*2)}'::jsonb)" for rid, j in rows)
        print('update osm_geometries o\n'
              "set properties = coalesce(o.properties,'{}'::jsonb) || v.data\n"
              f'from (values\n  {values}\n) as v(id, data)\n'
              f"where o.id = v.id and o.source = '{source}';")
    if EMIT_SQL and sql_rows:
        _emit(sql_rows, 'campsite_sites')
    if EMIT_SQL and cg_sql_rows:
        _emit(cg_sql_rows, 'pois_camping')

    print(f'\nDone. matched={total_ok} unmatched={total_unmatched}'
          f'{" (emit-sql)" if EMIT_SQL else " (dry run)" if DRY_RUN else ""}', file=sys.stderr)


if __name__ == '__main__':
    main()
