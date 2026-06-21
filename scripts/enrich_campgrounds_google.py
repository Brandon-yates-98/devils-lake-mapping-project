"""
Enrich the campgrounds layer (osm_geometries WHERE source='pois_camping') with
Google Places (New) data: rating, description, hours, phone, accessibility/dog/
restroom/family flags, top-3 reviews, and photos.

Cost-shaped design (see the chat plan + migration 048 header):
  * One Place Details (New) call per campground bills a SINGLE SKU
    (Enterprise + Atmosphere, the ceiling set by reviews/editorialSummary/
    allowsDogs). ~57 campgrounds/month vs the ~1,000/mo free cap = ~6%.
  * place_id is resolved once via Text Search, then cached forever in
    custom_data.google.place_id (the only ToS-cacheable field). Refreshes skip
    resolution.
  * Photos are fetched per-image (Place Photo SKU) and their URIs are
    time-limited, so the whole payload is on a 30-day delete-and-refetch cycle.

GUARDRAILS: aborts if it would exceed MAX_CALLS_PER_RUN, and the DB function
only returns rows whose cache is missing or older than REFRESH_DAYS, so reruns
are idempotent and cheap. Use --dry-run to see the plan without spending calls.

Writes go through two SECURITY DEFINER RPCs (migration 048) using the SERVICE
key — the anon key is RLS-blocked for writes (memory: supabase-write-constraints).

Usage:
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/enrich_campgrounds_google.py --dry-run
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/enrich_campgrounds_google.py

Required env (locally via 1Password `op`; in CI via GitHub Actions secrets):
  SUPABASE_URL            https://<project>.supabase.co
  SUPABASE_KEY            service_role key (bypasses RLS for the write RPC)
  GOOGLE_PLACES_API_KEY   server key, restricted to the Places API (New)
"""
import os, sys, json, time, re, urllib.request, urllib.error

# ── Config / guardrails ──────────────────────────────────────────────────────
SUPABASE_URL  = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY  = os.environ.get('SUPABASE_KEY', '')   # must be the service_role key
GOOGLE_KEY    = os.environ.get('GOOGLE_PLACES_API_KEY', '')

REFRESH_DAYS       = 30      # match the ToS 30-day cache cycle
PHOTOS_PER_SITE    = 3       # Place Photo calls per campground
MAX_REVIEWS        = 3       # top-N reviews flattened into properties
PHOTO_MAX_WIDTH    = 1200
MAX_CALLS_PER_RUN  = 600     # backstop vs runaway loop; first run is ~5 calls/site
                             # (resolve + details + 3 photos) = ~285 for 57 sites
SEARCH_RADIUS_M    = 500     # location bias when resolving place_id by name

DRY_RUN = '--dry-run' in sys.argv

PLACES_BASE = 'https://places.googleapis.com/v1'
# Place Details field mask — every field we actually surface. Atmosphere fields
# (reviews/editorialSummary/allowsDogs/restroom/goodForChildren) set the SKU.
DETAILS_FIELDS = ','.join([
    'id', 'displayName', 'googleMapsUri',
    'rating', 'userRatingCount',
    'nationalPhoneNumber',
    'currentOpeningHours',
    'accessibilityOptions',
    'allowsDogs', 'restroom', 'goodForChildren',
    'editorialSummary',
    'reviews',
    'photos',
])

_calls = 0

def _budget(kind):
    global _calls
    _calls += 1
    if _calls > MAX_CALLS_PER_RUN:
        sys.exit(f'ABORT: exceeded MAX_CALLS_PER_RUN={MAX_CALLS_PER_RUN} (last: {kind}).')


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


# ── Supabase RPCs (migration 048) ────────────────────────────────────────────
def _sb_headers():
    return {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json'}

def fetch_targets():
    url = f'{SUPABASE_URL}/rest/v1/rpc/campgrounds_needing_google_enrichment'
    return _request(url, method='POST', headers=_sb_headers(),
                    body={'refresh_days': REFRESH_DAYS}) or []

def apply_enrichment(row_id, props, photo_meta, place_id):
    if DRY_RUN:
        n = len(photo_meta) if photo_meta else 0
        print(f'    [dry-run] would write {len(props)} props, append {n} Google photo(s)')
        return
    url = f'{SUPABASE_URL}/rest/v1/rpc/apply_campground_google_enrichment'
    # photos are append-only server-side; photo_meta=None leaves the gallery as-is.
    _request(url, method='POST', headers=_sb_headers(), body={
        'p_id': row_id, 'p_props': props,
        'p_photo_meta': photo_meta, 'p_place_id': place_id,
    })


# ── Google Places (New) ──────────────────────────────────────────────────────
# Generic camp words carry no identity — strip them before comparing names so
# "Snuffy's Family Campground" vs "Skillet Creek Campground" share nothing and the
# mismatch is caught (Text Search by name+location can return the wrong place).
_GENERIC_WORDS = {'campground', 'campsite', 'camp', 'camping', 'resort', 'rv',
                  'park', 'the', 'and', 'of', 'a', 'dca', 'llc', 'inc', 'co',
                  'state', 'county'}

def _name_tokens(s):
    s = (s or '').lower().replace('&', ' and ').replace("'", '')
    return {t for t in re.findall(r'[a-z0-9]+', s)
            if len(t) >= 3 and t not in _GENERIC_WORDS}

def _name_matches(want, got):
    """True if the Google name shares a distinctive token with the campground name."""
    wt = _name_tokens(want)
    if not wt:
        return True               # nothing distinctive to verify — accept
    return bool(wt & _name_tokens(got))

def resolve_place_id(name, lat, lng):
    """Text Search (New) — minimal field mask keeps this on the cheap SKU.
    Returns the first candidate whose name matches; skips (None) if none do."""
    _budget('text_search')
    url = f'{PLACES_BASE}/places:searchText'
    headers = {'Content-Type': 'application/json', 'X-Goog-Api-Key': GOOGLE_KEY,
               'X-Goog-FieldMask': 'places.id,places.displayName,places.location'}
    body = {'textQuery': name,
            'locationBias': {'circle': {'center': {'latitude': lat, 'longitude': lng},
                                        'radius': SEARCH_RADIUS_M}}}
    data = _request(url, method='POST', headers=headers, body=body)
    places = (data or {}).get('places') or []
    for p in places[:5]:
        got = (p.get('displayName') or {}).get('text', '')
        if _name_matches(name, got):
            return p['id']
    if places:
        top = (places[0].get('displayName') or {}).get('text', '?')
        sys.stderr.write(f'  name mismatch for "{name}": top result "{top}" — skipping '
                         '(set custom_data.google.place_id manually to override)\n')
    return None

def place_details(place_id):
    _budget('place_details')
    url = f'{PLACES_BASE}/places/{place_id}'
    headers = {'X-Goog-Api-Key': GOOGLE_KEY, 'X-Goog-FieldMask': DETAILS_FIELDS}
    return _request(url, headers=headers)

def place_photo_uri(photo_name):
    """skipHttpRedirect returns the display URI as JSON instead of the bytes."""
    _budget('place_photo')
    url = (f'{PLACES_BASE}/{photo_name}/media'
           f'?maxWidthPx={PHOTO_MAX_WIDTH}&skipHttpRedirect=true&key={GOOGLE_KEY}')
    data = _request(url)
    return (data or {}).get('photoUri')


# ── Shape the Google payload into flat properties the popup template reads ─────
def build_props(d):
    props = {}
    if d.get('rating'):            props['google_rating'] = d['rating']
    if d.get('userRatingCount'):   props['google_rating_count'] = d['userRatingCount']
    if d.get('googleMapsUri'):     props['google_maps_uri'] = d['googleMapsUri']
    if d.get('nationalPhoneNumber'): props['google_phone'] = d['nationalPhoneNumber']
    summ = (d.get('editorialSummary') or {}).get('text')
    if summ:                       props['google_description'] = summ

    hours = d.get('currentOpeningHours') or {}
    weekday = hours.get('weekdayDescriptions') or []
    if weekday:                    props['google_hours_today'] = '; '.join(weekday[:1])

    acc = d.get('accessibilityOptions') or {}
    if acc.get('wheelchairAccessibleEntrance'): props['google_wheelchair'] = 'Yes'
    if d.get('allowsDogs'):        props['google_allows_dogs'] = 'Yes'
    if d.get('restroom'):          props['google_restroom'] = 'Yes'
    if d.get('goodForChildren'):   props['google_good_for_children'] = 'Yes'

    for i, rv in enumerate((d.get('reviews') or [])[:MAX_REVIEWS], start=1):
        text = (rv.get('text') or {}).get('text') or (rv.get('originalText') or {}).get('text')
        if not text:
            continue
        props[f'google_review_{i}_author'] = (rv.get('authorAttribution') or {}).get('displayName', 'Google user')
        props[f'google_review_{i}_rating'] = rv.get('rating', '')
        props[f'google_review_{i}_text']   = text[:280]
    return props

def build_photo_meta(d):
    """Google photos as [{url, caption, source:'google'}]. The source tag lets the
    DB function refresh only Google's own entries and never touch community photos."""
    meta = []
    for ph in (d.get('photos') or [])[:PHOTOS_PER_SITE]:
        uri = place_photo_uri(ph['name'])
        if not uri:
            continue
        authors = [a.get('displayName', '') for a in (ph.get('authorAttributions') or [])]
        caption = f"Photo: {', '.join(a for a in authors if a)} · via Google" if authors else 'via Google'
        meta.append({'url': uri, 'caption': caption, 'source': 'google'})
    return meta


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    missing = [n for n, v in (('SUPABASE_URL', SUPABASE_URL),
                              ('SUPABASE_KEY', SUPABASE_KEY),
                              ('GOOGLE_PLACES_API_KEY', GOOGLE_KEY)) if not v]
    if missing:
        sys.exit(f'ERROR: missing env: {", ".join(missing)}\n'
                 'Run via: op run --env-file=.env.tpl -- .venv/Scripts/python.exe '
                 'scripts/enrich_campgrounds_google.py')

    targets = fetch_targets()
    print(f'{len(targets)} campground(s) need enrichment (refresh cycle: {REFRESH_DAYS}d)'
          f'{"  [DRY RUN]" if DRY_RUN else ""}')

    ok = skipped = 0
    for t in targets:
        name, place_id = t['name'], t.get('place_id')
        if place_id is None:
            place_id = resolve_place_id(name, t['lat'], t['lng'])
            if not place_id:
                print(f'  - {name}: no Google match, skipping'); skipped += 1; continue
            print(f'  + {name}: resolved place_id {place_id}')

        d = place_details(place_id)
        if not d:
            print(f'  - {name}: details fetch failed, skipping'); skipped += 1; continue

        props = build_props(d)
        meta = build_photo_meta(d)
        # Pass None (not []) when Google has no photos so the gallery is left as-is.
        apply_enrichment(t['id'], props, meta or None, place_id)
        print(f'  OK {name}: rating={props.get("google_rating", "-")}, '
              f'{len(meta)} photo(s), {sum(1 for k in props if k.endswith("_text"))} review(s)')
        ok += 1
        time.sleep(0.1)  # be gentle on the API

    print(f'\nDone. enriched={ok} skipped={skipped} google_api_calls={_calls}'
          f'{" (none — dry run)" if DRY_RUN else ""}')


if __name__ == '__main__':
    main()
