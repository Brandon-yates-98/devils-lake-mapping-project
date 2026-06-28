"""
Compute elevation gain/loss + a small elevation profile for Sauk County trails
near Devil's Lake, from USGS 3DEP 1m LiDAR, and store the results in each trail's
properties (so the front-end popup can show "420 ft gain" + a profile sparkline).

Why a separate enrichment step (not part of import_sauk_trails.py):
  Trail geometry is stable, so this is a one-time / on-demand LOCAL run. The
  monthly import cron stays stdlib-only and CI gains no heavy geo dependencies.

Whole-trail aggregation:
  The county splits each trail into many short segments (e.g. "East Bluff Trail"
  is 13 separate features). We group the near-lake segments by name, sum gain/loss
  across the group, aggregate distance + high/low, and stitch the segments into a
  single profile -- then stamp that whole-trail aggregate onto EVERY segment of
  the name, so clicking any piece shows the full trail. Unnamed segments are kept
  individual. Stitch order is a greedy nearest-endpoint chain, so the profile
  SHAPE is approximate for branching/looping trails; gain/loss totals are not
  affected by stitch order.

Scope: by default we only enrich trails whose geometry passes within
  --near-miles (default 2.0) of Devil's Lake -- that's where elevation actually
  matters and it keeps the data fetching tiny. Use --all to enrich every trail.

Elevation source: the USGS 3DEP Elevation ImageServer (The National Map),
  https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer
  -- a public, key-less, multi-resolution bare-earth mosaic that includes 1m
  LiDAR where available (Devil's Lake is covered). For each segment we exportImage
  a small GeoTIFF clipped to its bbox at ~1 m/px in UTM 16N, sample it with
  rasterio, then discard it (clips are cached on disk by bbox so re-runs and
  overlapping trails are cheap).

Method (all tunable via the constants below so you can "see what's up"):
  project to UTM 16N (meters) -> densify the line to DENSIFY_M spacing -> sample
  the DEM -> light smoothing -> hysteresis threshold (MIN_STEP_M) to sum gain /
  loss without micro-relief noise inflating the total -> downsample to
  PROFILE_POINTS for the sparkline. Output is in feet (length is shown in miles).

Round-trip: we read the full source via get_layer_geojson, add elev_* keys to the
  near-lake trails, and rewrite the WHOLE source via the replace_layer_geometries
  RPC (which truncates first) -- so far-away trails are rewritten unchanged rather
  than deleted. Sources with no near-lake trails are skipped (not touched).

Requirements (added to the venv for this script):
  pip install rasterio pyproj      # numpy + requests already present

Usage:
  # validate on a few trails first (no writes); --limit caps the number of trails:
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/compute_trail_elevation.py --source sauk_trail_hiking --limit 5 --dry-run
  # full near-Devil's-Lake run:
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/compute_trail_elevation.py

Required env (locally via 1Password `op`):
  SUPABASE_URL, SUPABASE_KEY (service_role -- read + the write RPC)
"""
import os, sys, math, hashlib

import numpy as np
import requests
import rasterio
from pyproj import Transformer
from shapely.geometry import LineString

# Reuse the source list + helpers from the importer (single source of truth for
# the per-type slugs, the Supabase creds, and the batched write RPC wrapper).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_sauk_trails import (  # noqa: E402
    ALL_SLUGS, SUPABASE_URL, SUPABASE_KEY, _request, write_source,
)

# ─── Scope ────────────────────────────────────────────────────────────────────
# Devil's Lake (state park lake center). Trails passing within NEAR_MILES of this
# point get elevation; everything else is left as-is.
DEVILS_LAKE = (-89.7350, 43.4283)   # (lon, lat)
NEAR_MILES = 2.0

# Trail names to skip (case-insensitive prefix match). Ice Age is a long, heavily
# branching thru-trail (34 near-lake segments) whose summed gain + stitched profile
# aren't meaningful as a single "trail" -- excluded for now.
EXCLUDE_NAME_PREFIXES = ('ice age',)

# ─── Tunables (adjust + re-run with --dry-run to dial in gain accuracy) ────────
DENSIFY_M = 10.0        # sample spacing along the trail (m). 10 m on a 1 m DEM
                        # avoids micro-relief noise inflating cumulative gain.
SMOOTH_WINDOW = 3       # rolling-mean window over the sampled series (1 = off).
MIN_STEP_M = 2.0        # hysteresis threshold (m): only commit gain/loss once the
                        # move from the last reference exceeds this.
PROFILE_POINTS = 40     # samples in the stored sparkline array.
PAD_M = 200.0           # bbox padding around a segment when clipping the DEM (m).
TARGET_RES_M = 1.0      # requested DEM resolution (m/px) -> true 1m where covered.
MAX_PX = 4000           # cap on clip width/height in px (ImageServer max ~4100);
                        # very long segments fall back to slightly coarser than 1m.

M_TO_FT = 3.280839895
MILE_M = 1609.344
UTM16N_EPSG = 32616     # meters, covers southern Wisconsin

EXPORT_API = ('https://elevation.nationalmap.gov/arcgis/rest/services/'
              '3DEPElevation/ImageServer/exportImage')
CACHE_DIR = os.path.join(os.environ.get('TEMP', '/tmp'), 'apex_trail_dem_cache')

# Keys get_layer_geojson injects into properties on read; strip before writing
# back so they don't get persisted into the JSONB (the RPC re-injects them).
STRIP_KEYS = {'id', 'photos', 'photo_meta', 'custom_data'}

_TF_WGS_UTM = Transformer.from_crs('EPSG:4326', f'EPSG:{UTM16N_EPSG}', always_xy=True)


def haversine_miles(lon1, lat1, lon2, lat2):
    r = 3958.7613  # earth radius, miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geom_parts(geom):
    """Return a list of coordinate rings ([[lon,lat],...]) for a (Multi)LineString."""
    t = (geom or {}).get('type')
    c = (geom or {}).get('coordinates') or []
    if t == 'LineString':
        return [c] if c else []
    if t == 'MultiLineString':
        return [p for p in c if p]
    return []


def near_devils_lake(parts, miles):
    dlon, dlat = DEVILS_LAKE
    for part in parts:
        for lon, lat, *_ in part:
            if haversine_miles(lon, lat, dlon, dlat) <= miles:
                return True
    return False


def to_utm_parts(parts):
    """Project (Multi)LineString parts to UTM 16N; drop degenerate parts."""
    out = []
    for part in parts:
        pts = [_TF_WGS_UTM.transform(lon, lat) for lon, lat, *_ in part]
        if len(pts) >= 2:
            out.append(pts)
    return out


def read_source(source):
    """Fetch the full FeatureCollection for a source via get_layer_geojson."""
    url = f'{SUPABASE_URL}/rest/v1/rpc/get_layer_geojson'
    headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}',
               'Content-Type': 'application/json'}
    data = _request(url, method='POST', headers=headers, body={'p_source': source})
    return (data or {}).get('features') or []


# ─── DEM fetch (USGS 3DEP ImageServer) + sampling ─────────────────────────────
def fetch_dem(utm_parts, res_m=TARGET_RES_M):
    """exportImage a 3DEP GeoTIFF (UTM 16N) clipped to the bbox at ~res_m/px.
    Returns a local path, or None if the service errored / returned no raster.
    res_m defaults to 1 m (trail segments); callers sampling large extents (whole
    loops) pass a coarser value to keep the download small."""
    xs = [p[0] for part in utm_parts for p in part]
    ys = [p[1] for part in utm_parts for p in part]
    w, e = min(xs) - PAD_M, max(xs) + PAD_M
    s, n = min(ys) - PAD_M, max(ys) + PAD_M
    cols = min(MAX_PX, max(2, round((e - w) / res_m)))
    rows = min(MAX_PX, max(2, round((n - s) / res_m)))

    key = hashlib.md5(f'{w:.1f}_{s:.1f}_{e:.1f}_{n:.1f}_{cols}_{rows}'.encode()).hexdigest()[:16]
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f'dem_{key}.tif')
    miss = path + '.miss'
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    if os.path.exists(miss):
        return None

    params = {
        'bbox': f'{w},{s},{e},{n}', 'bboxSR': UTM16N_EPSG, 'imageSR': UTM16N_EPSG,
        'size': f'{cols},{rows}', 'format': 'tiff', 'pixelType': 'F32',
        'interpolation': 'RSP_BilinearInterpolation', 'noData': '',
        'adjustAspectRatio': 'false', 'f': 'image',
    }
    # Retry transient failures (timeouts, 5xx); only a 4xx is a real "no coverage".
    for attempt in range(3):
        try:
            r = requests.get(EXPORT_API, params=params, timeout=120)
        except requests.RequestException as ex:
            sys.stderr.write(f'  DEM request error (try {attempt + 1}): {ex}\n')
            continue
        if r.status_code == 200 and r.content[:2] in (b'II', b'MM'):
            with open(path, 'wb') as fh:
                fh.write(r.content)
            return path
        if 400 <= r.status_code < 500:
            sys.stderr.write(f'  no DEM ({r.status_code}): {(r.text or "")[:200]}\n')
            open(miss, 'w').close()
            return None
        sys.stderr.write(f'  DEM {r.status_code} (try {attempt + 1}), retrying\n')
    return None  # transient: leave uncached so a re-run tries again


def sample_part(pts_utm, ds, tf):
    """Densify one UTM line part, sample the DEM. Returns (elevs_m, length_m) with
    nodata gaps interpolated over, or None if all nodata / degenerate."""
    line = LineString(pts_utm)
    if line.length <= 0:
        return None
    n = max(2, int(line.length // DENSIFY_M) + 1)
    dists = np.linspace(0.0, line.length, n)
    samp = [(p.x, p.y) for p in (line.interpolate(float(d)) for d in dists)]
    if tf is not None:
        samp = [tf.transform(x, y) for x, y in samp]
    vals = np.array([v[0] for v in ds.sample(samp)], dtype='float64')

    nodata = ds.nodata
    mask = ~np.isfinite(vals) | (vals <= -1000) | (vals >= 1e4)
    if nodata is not None:
        mask |= np.isclose(vals, nodata)
    if mask.all():
        return None
    if mask.any():  # linear-interpolate over small gaps so smoothing is clean
        idx = np.arange(len(vals))
        vals[mask] = np.interp(idx[mask], idx[~mask], vals[~mask])
    return vals, float(line.length)


def smooth(a):
    if SMOOTH_WINDOW <= 1 or len(a) < SMOOTH_WINDOW:
        return a
    # Edge-pad (not zero-pad) so the first/last samples aren't dragged toward 0,
    # which would otherwise create a fake dip-and-recover at every segment end and
    # massively inflate cumulative gain/loss.
    pad = SMOOTH_WINDOW // 2
    k = np.ones(SMOOTH_WINDOW) / SMOOTH_WINDOW
    return np.convolve(np.pad(a, pad, mode='edge'), k, mode='valid')


def gain_loss_m(elevs):
    """Cumulative gain/loss (m) via a hysteresis threshold from the last reference."""
    gain = loss = 0.0
    ref = elevs[0]
    for e in elevs[1:]:
        d = e - ref
        if d >= MIN_STEP_M:
            gain += d
            ref = e
        elif d <= -MIN_STEP_M:
            loss += -d
            ref = e
    return gain, loss


def compute_segment(geom, res_m=TARGET_RES_M):
    """Sample one geometry. Returns a dict with its smoothed elevation series,
    gain/loss/length/min/max, and UTM start/end endpoints, or None if no DEM.
    res_m sets the DEM resolution (1 m for trail segments; coarser for whole loops)."""
    utm_parts = to_utm_parts(geom_parts(geom))
    if not utm_parts:
        return None
    dem_path = fetch_dem(utm_parts, res_m)
    if not dem_path:
        return None

    series, length, gain, loss = [], 0.0, 0.0, 0.0
    with rasterio.open(dem_path) as ds:
        epsg = ds.crs.to_epsg() if ds.crs else None
        tf = None if epsg == UTM16N_EPSG else Transformer.from_crs(
            f'EPSG:{UTM16N_EPSG}', ds.crs, always_xy=True)
        for pts in utm_parts:
            res = sample_part(pts, ds, tf)
            if res is None:
                continue
            elevs, l = res
            elevs = smooth(elevs)
            g, ll = gain_loss_m(elevs)
            gain += g
            loss += ll
            length += l
            series.append(elevs)
    if not series:
        return None

    s = np.concatenate(series)
    return {'gain': gain, 'loss': loss, 'length': length,
            'min': float(s.min()), 'max': float(s.max()), 'series': s,
            'start': utm_parts[0][0], 'end': utm_parts[-1][-1]}


def _d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def stitch_profile(segs):
    """Concatenate segment series into one profile via a greedy nearest-endpoint
    chain, starting from the endpoint farthest from the group centroid (reduces
    starting mid-trail). Approximate for branching/looping trails."""
    pts = [p for s in segs for p in (s['start'], s['end'])]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)

    start_i, start_flip, best = 0, False, -1.0
    for i, s in enumerate(segs):
        for flip, pt in ((False, s['start']), (True, s['end'])):
            d = (pt[0] - cx) ** 2 + (pt[1] - cy) ** 2
            if d > best:
                best, start_i, start_flip = d, i, flip

    remaining = list(segs)
    cur = remaining.pop(start_i)
    # If the farthest point is this segment's 'end', traverse end->start (reverse).
    chain = [cur['series'][::-1] if start_flip else cur['series']]
    tail = cur['start'] if start_flip else cur['end']
    while remaining:
        bi, bflip, bd = 0, False, float('inf')
        for i, s in enumerate(remaining):
            ds, de = _d2(tail, s['start']), _d2(tail, s['end'])
            if ds < bd:
                bd, bi, bflip = ds, i, False
            if de < bd:
                bd, bi, bflip = de, i, True
        s = remaining.pop(bi)
        chain.append(s['series'][::-1] if bflip else s['series'])
        tail = s['start'] if bflip else s['end']

    allv = np.concatenate(chain)
    x = np.linspace(0, len(allv) - 1, min(PROFILE_POINTS, len(allv)))
    prof_ft = np.interp(x, np.arange(len(allv)), allv) * M_TO_FT
    return [int(round(v)) for v in prof_ft]


def aggregate(segs):
    """Whole-trail elev_* dict from a group of computed segments."""
    gain = sum(s['gain'] for s in segs)
    loss = sum(s['loss'] for s in segs)
    length = sum(s['length'] for s in segs)
    return {
        'elev_gain_ft': int(round(gain * M_TO_FT)),
        'elev_loss_ft': int(round(loss * M_TO_FT)),
        'elev_min_ft': int(round(min(s['min'] for s in segs) * M_TO_FT)),
        'elev_max_ft': int(round(max(s['max'] for s in segs) * M_TO_FT)),
        'elev_dist_mi': round(length / MILE_M, 2),
        'elev_profile': stitch_profile(segs),
        'elev_src': 'usgs_3dep_1m',
    }


def clean_props(props):
    return {k: v for k, v in props.items() if k not in STRIP_KEYS}


def parse_args(argv):
    a = {'dry_run': '--dry-run' in argv, 'all': '--all' in argv,
         'source': None, 'limit': None, 'near_miles': NEAR_MILES}
    for i, tok in enumerate(argv):
        if tok == '--source' and i + 1 < len(argv):
            a['source'] = argv[i + 1]
        elif tok == '--limit' and i + 1 < len(argv):
            a['limit'] = int(argv[i + 1])
        elif tok == '--near-miles' and i + 1 < len(argv):
            a['near_miles'] = float(argv[i + 1])
    return a


def group_key(feat):
    """Group near-lake segments by trail name; unnamed stay individual."""
    nm = (feat.get('properties', {}).get('name') or '').strip()
    return nm.lower() if nm else f'__seg_{id(feat)}'


def main():
    args = parse_args(sys.argv[1:])
    need = [n for n, v in (('SUPABASE_URL', SUPABASE_URL),
                           ('SUPABASE_KEY', SUPABASE_KEY)) if not v]
    if need:
        sys.exit(f'ERROR: missing env: {", ".join(need)}\n'
                 'Run via: op run --env-file=.env.tpl -- .venv/Scripts/python.exe '
                 'scripts/compute_trail_elevation.py')

    slugs = [args['source']] if args['source'] else ALL_SLUGS
    miles = None if args['all'] else args['near_miles']
    scope = 'ALL trails' if args['all'] else f"trails within {miles} mi of Devil's Lake"
    print(f"Enriching {scope}{'  [DRY RUN]' if args['dry_run'] else ''}\n"
          f"  densify={DENSIFY_M}m smooth={SMOOTH_WINDOW} min_step={MIN_STEP_M}m\n")

    grand_trails = grand_skipped = 0
    for slug in slugs:
        feats = read_source(slug)
        if not feats:
            print(f'  {slug}: (empty)')
            continue
        for f in feats:
            f['properties'] = clean_props(f.get('properties') or {})

        # Group the in-scope segments by trail name (skipping excluded names).
        groups = {}
        for f in feats:
            nm = (f.get('properties', {}).get('name') or '').strip().lower()
            if nm and any(nm.startswith(p) for p in EXCLUDE_NAME_PREFIXES):
                continue
            if miles is not None and not near_devils_lake(geom_parts(f.get('geometry')), miles):
                continue
            groups.setdefault(group_key(f), []).append(f)

        keys = list(groups)
        if args['limit'] is not None:
            keys = keys[:args['limit']]

        trails = skipped = 0
        for key in keys:
            segs = groups[key]
            seg_data = [d for d in (compute_segment(f.get('geometry')) for f in segs) if d]
            if not seg_data:
                skipped += 1
                continue
            agg = aggregate(seg_data)
            for f in segs:
                f['properties'].update(agg)
            trails += 1
            if args['dry_run']:
                nm = segs[0]['properties'].get('name') or '(unnamed)'
                print(f"    + {nm[:34]:<34} {len(segs):>2} seg  {agg['elev_gain_ft']:>5} ft gain  "
                      f"({agg['elev_min_ft']}-{agg['elev_max_ft']} ft, {agg['elev_dist_mi']} mi)")

        grand_trails += trails
        grand_skipped += skipped
        print(f'  {slug}: {trails} trails enriched, {skipped} no-coverage')

        if not args['dry_run'] and trails:
            write_source(slug, feats)
            print(f'    wrote {len(feats)} features back to {slug}')

    print(f'\nDone. {grand_trails} trails enriched, '
          f'{grand_skipped} skipped (no coverage)'
          f"{'  [DRY RUN — nothing written]' if args['dry_run'] else ''}.")


if __name__ == '__main__':
    main()
