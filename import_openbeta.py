#!/usr/bin/env python3
"""
import_openbeta.py
Fetches Devil's Lake climbing data from the OpenBeta GraphQL API and
upserts it into Supabase as three template layer sources:

  climbing_routes   — roped routes (trad, sport, TR, aid, alpine, mixed)
  climbing_boulders — bouldering problems
  climbing_areas    — named sectors/walls (overview markers)

License notice: OpenBeta data is licensed under the Open Database License
(ODbL). Any public display of this data must include the attribution:
  "© OpenBeta contributors (ODbL)"
See https://openbeta.io and https://opendatacommons.org/licenses/odbl/

Run after migrations/001, 002, and 003 have been applied:
  .venv/Scripts/python.exe import_openbeta.py
"""
import json, time, sys, os
import requests
from supabase import create_client

# ── Config ────────────────────────────────────────────────────────────────
SUPABASE_URL  = os.environ.get('SUPABASE_URL')
SUPABASE_KEY  = os.environ.get('SUPABASE_KEY')
if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit('Set SUPABASE_URL and SUPABASE_KEY — use: '
             'op run --env-file=.env.tpl -- python import_openbeta.py')
OPENBETA_URL  = 'https://api.openbeta.io'
DEVILS_LAKE_UUID = 'bf4481e8-d698-5b5f-a46d-81f807c26d7d'
BATCH_SIZE    = 40  # features per RPC call batch

db = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── GraphQL helper ────────────────────────────────────────────────────────
def gql(query, variables=None):
    r = requests.post(OPENBETA_URL,
                      json={'query': query, 'variables': variables or {}},
                      timeout=45,
                      headers={'Content-Type': 'application/json'})
    r.raise_for_status()
    d = r.json()
    if 'errors' in d:
        raise RuntimeError(d['errors'])
    return d['data']

# ── Queries ───────────────────────────────────────────────────────────────
# Fetch top-level children UUIDs to iterate over (avoids one giant query)
CHILDREN_Q = '''query($uuid: ID!) {
  area(uuid: $uuid) {
    area_name totalClimbs
    children { uuid area_name totalClimbs metadata { lat lng } }
  }
}'''

# Full area fetch: climbs at all 3 nesting levels
CLIMB_FRAG = '''
      uuid name fa length
      grades { yds vscale }
      type { trad sport bouldering tr aid alpine mixed }
      metadata { lat lng mp_id }
      content { description }'''

FULL_AREA_Q = '''query($uuid: ID!) {
  area(uuid: $uuid) {
    uuid area_name totalClimbs metadata { lat lng mp_id }
    climbs {''' + CLIMB_FRAG + '''}
    children {
      uuid area_name metadata { lat lng mp_id }
      climbs {''' + CLIMB_FRAG + '''}
      children {
        uuid area_name metadata { lat lng mp_id }
        climbs {''' + CLIMB_FRAG + '''}
        children {
          uuid area_name metadata { lat lng mp_id }
          climbs {''' + CLIMB_FRAG + '''}
          children {
            uuid area_name metadata { lat lng mp_id }
            climbs {''' + CLIMB_FRAG + '''}
          }
        }
      }
    }
  }
}'''

# ── Data collection ───────────────────────────────────────────────────────
def classify_type(t):
    """Return canonical climb type string from ClimbType object."""
    if not t:
        return 'unknown'
    if t.get('bouldering'):
        return 'boulder'
    types = [k for k in ('trad','sport','tr','aid','alpine','mixed') if t.get(k)]
    return '/'.join(types) if types else 'unknown'

def collect_from_area(area, parent_lat=None, parent_lng=None, ancestry=None, depth=0):
    """
    Walk the area tree, yielding (area_rows, route_rows, boulder_rows).
    Falls back to parent coords when a node has no coordinates of its own.

    `ancestry` is the list of ancestor uuids from root → immediate parent
    (excluding the current area). It lets us record the OpenBeta area
    association (parent_id + full path) on every area and climb, so the app
    can browse nested areas and filter a whole sub-tree at once.
    """
    ancestry = ancestry or []
    raw_lat = area['metadata']['lat']
    raw_lng = area['metadata']['lng']
    lat = raw_lat if raw_lat else parent_lat
    lng = raw_lng if raw_lng else parent_lng

    uuid = area.get('uuid', '')
    # Path of ancestor area uuids (root-first), and the path including this area.
    path        = list(ancestry)
    climb_path  = path + [uuid]            # area chain a climb here belongs to
    parent_id   = path[-1] if path else ''

    areas_out  = []
    routes_out = []
    boulders_out = []

    if lat and lng:
        areas_out.append({
            'uuid': uuid,
            'name': area['area_name'],
            'lat': lat, 'lng': lng,
            'parent_id': parent_id,
            'path': path,
            'depth': depth,
            'mp_id': (area.get('metadata') or {}).get('mp_id') or '',
        })

    for c in (area.get('climbs') or []):
        clat = c['metadata']['lat'] if c['metadata']['lat'] else lat
        clng = c['metadata']['lng'] if c['metadata']['lng'] else lng
        if not (clat and clng):
            continue  # skip if no coords at all

        ctype = classify_type(c.get('type'))
        g     = c.get('grades') or {}
        grade = g.get('yds') or g.get('vscale') or ''
        desc  = (c.get('content') or {}).get('description') or ''

        row = {
            'uuid':      c['uuid'],
            'name':      c['name'],
            'lat':       clat,
            'lng':       clng,
            'grade':     grade,
            'route_type': ctype,
            'fa':        c.get('fa') or '',
            'length_ft': round((c.get('length') or 0) * 3.281),  # m → ft
            'area_name': area['area_name'],
            'area_id':   uuid,             # immediate parent area
            'area_path': climb_path,       # full area chain (root → parent)
            'description': desc,
            'mp_id':     (c.get('metadata') or {}).get('mp_id') or '',
        }
        if ctype == 'boulder':
            boulders_out.append(row)
        else:
            routes_out.append(row)

    child_ancestry = path + [uuid]
    for child in (area.get('children') or []):
        a2, r2, b2 = collect_from_area(child, lat, lng, child_ancestry, depth+1)
        areas_out.extend(a2)
        routes_out.extend(r2)
        boulders_out.extend(b2)

    return areas_out, routes_out, boulders_out

# ── GeoJSON feature builder ───────────────────────────────────────────────
def make_route_feature(row):
    return {
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [row['lng'], row['lat']]},
        'properties': {
            '_draw_id':    'ob-' + row['uuid'],
            'name':        row['name'],
            'grade':       row['grade'],
            'route_type':  row['route_type'],
            'fa':          row['fa'],
            'length_ft':   str(row['length_ft']) if row['length_ft'] else '',
            'area_name':   row['area_name'],
            'area_id':     row['area_id'],          # immediate parent area uuid
            'area_path':   row['area_path'],        # root → parent uuid chain (jsonb array)
            # upsert_drawn_feature reads custom_data as props->>'custom_data' cast to jsonb
            # so it must be a JSON string embedded in the properties object
            'custom_data': json.dumps({k: v for k, v in {
                'description': row['description'],
                'openbeta_id': row['uuid'],
                'mp_id': row.get('mp_id'),
            }.items() if v}),
        }
    }

def make_area_feature(row):
    return {
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [row['lng'], row['lat']]},
        'properties': {
            '_draw_id':    'ob-area-' + row['uuid'],
            'name':        row['name'],
            'area_id':     row['uuid'],             # this area's own uuid
            'parent_id':   row.get('parent_id', ''),
            'area_path':   row.get('path', []),     # ancestor uuid chain (jsonb array)
            'depth':       row.get('depth', 0),
            'climb_count': row.get('climb_count', 0),
            'custom_data': json.dumps({k: v for k, v in {
                'openbeta_id': row['uuid'],
                'mp_id': row.get('mp_id'),
            }.items() if v}),
        }
    }

# ── Supabase upsert ───────────────────────────────────────────────────────
def upsert_batch(source, features):
    """Upsert a list of GeoJSON features via the existing RPC."""
    for i, feat in enumerate(features):
        try:
            db.rpc('upsert_drawn_feature', {
                'p_source':  source,
                'p_feature': feat,   # pass dict directly; supabase-py serialises it
            }).execute()
        except Exception as e:
            print(f"    [WARN] failed on feature {feat['properties'].get('name')}: {e}")
        if (i + 1) % BATCH_SIZE == 0:
            print(f"    {i+1}/{len(features)} …")
            time.sleep(0.3)  # brief pause every batch

# ── Main ──────────────────────────────────────────────────────────────────
# OpenBeta API quirk: climbs reached through nested children{} return
# metadata.mp_id as null, but querying each wall DIRECTLY populates it.
# Second pass: one query per wall, patch the rows.
MP_WALL_Q = '''query($uuid: ID!) {
  area(uuid: $uuid) { climbs { uuid metadata { mp_id } } }
}'''

def fetch_climb_mp_ids(rows):
    walls = sorted({r['area_id'] for r in rows if not r.get('mp_id')})
    print(f"\nFetching Mountain Project ids directly from {len(walls)} walls …")
    mp = {}
    failed = 0
    for i, wall in enumerate(walls):
        for attempt in (1, 2, 3):
            try:
                d = gql(MP_WALL_Q, {'uuid': wall})
                for c in ((d.get('area') or {}).get('climbs') or []):
                    mid = (c.get('metadata') or {}).get('mp_id')
                    if mid:
                        mp[c['uuid']] = mid
                break
            except Exception as e:
                if attempt == 3:
                    failed += 1
                    print(f"  [WARN] mp_id fetch failed for wall {wall}: {e}")
                else:
                    time.sleep(2.0 * attempt)   # back off and retry
        time.sleep(0.15)                        # be polite to the API
        if (i + 1) % 50 == 0:
            print(f"    {i + 1}/{len(walls)} walls …")
    n = 0
    for r in rows:
        if not r.get('mp_id') and r['uuid'] in mp:
            r['mp_id'] = mp[r['uuid']]
            n += 1
    print(f"  mp_id found for {n} climbs ({failed} walls failed)")

def main():
    print("Fetching Devil's Lake area children …")
    top = gql(CHILDREN_Q, {'uuid': DEVILS_LAKE_UUID})['area']
    children = top['children']
    print(f"  Found {len(children)} L1 areas  |  {top['totalClimbs']} total climbs")

    all_areas    = []
    all_routes   = []
    all_boulders = []

    # Also add the top-level area itself
    tlat = None; tlng = None
    for c in children:
        m = c['metadata']
        if m['lat'] and m['lng']:
            tlat = m['lat']; tlng = m['lng']
            break

    for i, child in enumerate(children, 1):
        print(f"\n[{i}/{len(children)}] Fetching '{child['area_name']}' ({child['totalClimbs']} climbs) …")
        try:
            full = gql(FULL_AREA_Q, {'uuid': child['uuid']})['area']
        except Exception as e:
            print(f"  ERROR: {e} — skipping")
            continue

        areas, routes, boulders = collect_from_area(full)
        print(f"  -> {len(areas)} areas, {len(routes)} routes, {len(boulders)} boulders")
        all_areas.extend(areas)
        all_routes.extend(routes)
        all_boulders.extend(boulders)
        time.sleep(0.5)  # be polite to the API

    # Deduplicate areas by uuid (same wall appears in multiple children)
    seen = set()
    unique_areas = []
    for a in all_areas:
        if a['uuid'] not in seen:
            seen.add(a['uuid'])
            unique_areas.append(a)

    # Climb count per area uuid, counting the whole sub-tree: a climb counts
    # for its immediate area and every ancestor in its area_path.
    climb_counts = {}
    for c in (all_routes + all_boulders):
        for aid in c.get('area_path', []):
            climb_counts[aid] = climb_counts.get(aid, 0) + 1
    for a in unique_areas:
        a['climb_count'] = climb_counts.get(a['uuid'], 0)

    fetch_climb_mp_ids(all_routes + all_boulders)

    print(f"\n--- Summary ---")
    print(f"  Areas:    {len(unique_areas)}")
    print(f"  Routes:   {len(all_routes)}")
    print(f"  Boulders: {len(all_boulders)}")
    print(f"  Total:    {len(all_routes) + len(all_boulders)}")

    # ── Insert into Supabase ───────────────────────────────────────────────
    sources = [
        ('climbing_routes',   [make_route_feature(r) for r in all_routes]),
        ('climbing_boulders', [make_route_feature(r) for r in all_boulders]),
        ('climbing_areas',    [make_area_feature(a)  for a in unique_areas]),
    ]

    for source, features in sources:
        print(f"\nUpserting {len(features)} features → source='{source}' …")
        upsert_batch(source, features)
        print(f"  Done.")

    print("\nImport complete.")
    print("  Run migrations/003_openbeta_templates.sql in Supabase SQL Editor")
    print("  to register the three new layer templates.")

if __name__ == '__main__':
    main()
