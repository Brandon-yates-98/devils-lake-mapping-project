"""
Compute hike-worthy LOOPS on the Devil's Lake trail network and store them in the
trail_loops table (migration 059).

"All possible loops" is not computable: the number of simple cycles in a graph is
exponential. Instead we enumerate simple cycles with a hard DISTANCE bound, keep
only ones that are actually hikeable, deduplicate to distinct routes, and store.

Network scope: hiking + hiking/biking + rescue-road trails, within NEAR_MILES of
Devil's Lake (hike_bike adds the lake's second cross-shore connector, which a
hiking+rescue-only network lacked, so around-the-lake / both-bluff loops exist).
The layer is a noded network (shared endpoints) -- memory:sauk-trails-noded-network.

Realism constraints (so we get routes a person would hike, not graph cycles):
  - Rescue roads that run ALONG a hiking trail are dropped (parallel duplicate ->
    out-and-back fake loops); rescue roads stay only where they add new path.
  - ANCHOR: a loop must pass within ANCHOR_M of a parking lot (source 'parking'),
    and we record the nearest lot as its start. No parking => not a real route.
  - ROAD FRACTION: drop loops that are > MAX_ROAD_FRAC rescue road (keep them hikes).
  - COMPACTNESS: drop "pinched" loops (tiny enclosed area for their length) -- they
    are technically cycles but hug themselves, not real loops.
  - No backtracking: these are strict SIMPLE cycles (no repeated node/edge).

Algorithm:
  build a MultiGraph (nodes = endpoints snapped to ~0.1 m, edges = segments) ->
  reduce to the loop-bearing core: prune degree-1 dead-ends, contract degree-2
  chains into super-edges (a whole segment-chain between two junctions). Enumerate
  simple cycles over the tiny junction graph with a distance bound, applying the
  anchor + road-fraction filters as cycles are found -> dedup near-duplicates
  (edge-set Jaccard >= DEDUP_J) -> compactness filter -> expand to full coordinates
  and write closed LineStrings + distance / names / start lot to trail_loops.

Guards: a wall-clock TIME_BUDGET_S and RAW_CAP bound the search.

Requirements: pip install networkx pyproj shapely   (all already present)

Usage:
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/compute_trail_loops.py --dry-run
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/compute_trail_loops.py

Required env (locally via 1Password `op`): SUPABASE_URL, SUPABASE_KEY (service).
"""
import os, sys, time, math, heapq
from collections import defaultdict

import numpy as np
from shapely.geometry import LineString, Polygon, shape
from shapely.ops import unary_union, transform as shp_transform

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compute_trail_elevation import (  # noqa: E402
    read_source, geom_parts, near_devils_lake, _TF_WGS_UTM, MILE_M,
    DEVILS_LAKE, haversine_miles, compute_segment, M_TO_FT, PROFILE_POINTS,
    SUPABASE_URL, SUPABASE_KEY, _request,
)
from import_sauk_trails import ALL_SLUGS  # noqa: E402  (all sauk_trail_* slugs)

# ─── Scope + tunables ──────────────────────────────────────────────────────────
SOURCES = ['sauk_trail_hiking', 'sauk_trail_hike_bike', 'sauk_trail_rescue_road']
PRIMARY = 'sauk_trail_hiking'          # added in full; the rest are overlap-filtered
RESCUE_SRC = 'sauk_trail_rescue_road'
PARKING_SRC = 'parking'
NEAR_MILES = 10.0
MIN_MI = 2.0
MAX_MI = 30.0
DEDUP_J = 0.7          # drop a loop sharing >= this fraction of edges with a kept one
NAMED_SET_DEDUP = False # collapse loops using the same SET of named trails to one
ALLOW_FIGURE8 = True    # compose longer routes from edge-disjoint base loops (below)
MAX_COMBINE = 10        # max base loops fused into one route (2 = figure-8s only)
BEAM_WIDTH = 300        # partial combos kept per growth step (the cost/coverage knob)
TARGET_MI = 13.0        # beam grows combos toward this length
COMPOSE_MIN_MI = 4.0    # only keep composed routes at least this long (else a base loop wins)
# Composition base = small "atomic" loops (minimal cycles / faces). Small loops
# overlap far less than the big display loops, so many more are edge-disjoint and
# fusable -- that's what yields more + longer multi-loop routes.
ATOM_MAX_MI = 4.0       # only enumerate small loops as composition atoms
ATOM_MAX_LEGS = 6       # ... with few legs (keeps them granular + the search cheap)
MAX_LOOPS = 500        # cap on stored loops
TIME_BUDGET_S = 240    # wall-clock guard on the cycle search
RAW_CAP = 300_000      # guard on number of accepted raw cycles
PER_START_CAP = 4000   # max cycles recorded per start node (spreads coverage so a
                       # deep leg cap doesn't drown the search in one corner)
SNAP = 6               # node identity precision in decimal degrees (~0.11 m)
DUP_TOL_M = 8.0        # two edges running within this (m) of each other over
DUP_FRAC = 0.85        # >= this fraction of length are the same physical tread
                       # (e.g. Ice Age co-digitized over a local trail) -> keep one,
                       # so routes can't walk the same ground twice (no backtracking)
MAX_RETRACE_FRAC = 0.05  # reject a composed route if > this share of it is retraced
LOOP_DEM_RES_M = 10.0    # DEM resolution for whole-loop elevation (coarse -> small
                         # downloads; gain is computed on a 10 m densification anyway)
# Link each loop to its nearest parking lot by NETWORK distance over any trail type
# or road (not straight line). The routing graph spans all of these:
ROUTING_SOURCES = list(ALL_SLUGS) + ['roads']
LINK_NEAR_MILES = 12.0   # routing graph radius (a touch wider than the loop scope)
LOT_SNAP_M = 300.0       # connect a parking lot to the network within this distance
NEARBY_PARKING_MI = 1.5  # list parking lots within this network distance of a loop
MAX_NEARBY_PARKING = 6   # cap on lots shown in the Nearby Parking dropdown
ANCHOR_AT_PARKING = False  # require loops to pass within ANCHOR_M of a parking lot
ANCHOR_M = 150.0       # a loop must pass within this of a parking lot (if anchoring)
START_NEAR_MI = 0.25   # label a loop's start with a parking lot only if within this
MAX_ROAD_FRAC = 0.40   # drop loops more than this fraction rescue road
LAYER_SOURCE = 'hiking_loops'  # osm_geometries source backing the map template layer
MIN_COMPACT = 0.03     # drop pinched loops (4*pi*area/perimeter^2 below this)
MAX_SUPEREDGES = 20    # cap junction-to-junction legs per loop (complexity + speed)
MAX_NAMED_TRAILS = 10  # cap distinct named trails per loop (keep routes simple)


def node_key(c):
    return (round(c[0], SNAP), round(c[1], SNAP))


def _to_utm(geom):
    return shp_transform(_TF_WGS_UTM.transform, geom)


def _parts_in_scope(src, near_miles):
    """Yield (part, props, utm_line) for in-scope parts of a source."""
    for f in read_source(src):
        props = f.get('properties') or {}
        parts = geom_parts(f.get('geometry'))
        if near_miles is not None and not near_devils_lake(parts, near_miles):
            continue
        for part in parts:
            if len(part) < 2:
                continue
            line = LineString([_TF_WGS_UTM.transform(lon, lat) for lon, lat, *_ in part])
            if line.length > 0:
                yield part, props, line


def load_parking(near_miles):
    """Parking lots within scope: a buffered UTM union (for the anchor test) plus
    representative lon/lat points + names (for assigning each loop a start lot)."""
    geoms, pts = [], []
    for f in read_source(PARKING_SRC):
        g = f.get('geometry')
        if not g:
            continue
        try:
            sh = shape(g)
        except Exception:
            continue
        c = sh.centroid
        if near_miles is not None and haversine_miles(c.x, c.y, *DEVILS_LAKE) > near_miles:
            continue
        props = f.get('properties') or {}
        kind = ('polygon' if sh.geom_type in ('Polygon', 'MultiPolygon')
                else 'point' if sh.geom_type in ('Point', 'MultiPoint') else 'line')
        geoms.append(_to_utm(sh))
        pts.append({'lon': c.x, 'lat': c.y, 'name': props.get('name'),
                    'osm_id': props.get('_osm_id'), 'kind': kind})
    buf = unary_union(geoms).buffer(ANCHOR_M) if geoms else None
    return buf, pts


def build_graph(near_miles, parking_buf):
    """adj: node -> [(neighbor, eid)]; edges[eid] = {a,b,len,name,type,src,coords,
    near_parking}. PRIMARY (hiking) added in full; rescue roads added only where
    they are not running along a hiking trail."""
    adj, edges, eid, dropped = defaultdict(list), {}, 0, 0

    def add(part, props, line, src):
        nonlocal eid
        a, b = node_key(part[0]), node_key(part[-1])
        if a == b:
            return
        edges[eid] = {'a': a, 'b': b, 'len': line.length, 'src': src,
                      'name': (props.get('name') or '').strip() or None,
                      'type': props.get('trail_type'),
                      'near_parking': bool(parking_buf is not None and line.intersects(parking_buf)),
                      'coords': [[c[0], c[1]] for c in part]}  # oriented a -> b
        adj[a].append((b, eid))
        adj[b].append((a, eid))
        eid += 1

    # Gather candidates across sources, ranked: primary (hiking) first, and the
    # long through-routes (Ice Age / Riverwalk) LAST so that where they're
    # co-digitized over a local named trail, the local trail's edge is the one kept.
    cands = []
    for src in SOURCES:
        for part, props, line in _parts_in_scope(src, near_miles):
            nm = (props.get('name') or '').lower()
            through = 1 if ('ice age' in nm or 'riverwalk' in nm) else 0
            cands.append(((0 if src == PRIMARY else 1, through), part, props, line, src))
    cands.sort(key=lambda c: c[0])

    # Drop collinear duplicate treads: skip a candidate that runs within DUP_TOL_M
    # of already-kept edges for >= DUP_FRAC of its length. Keeps each physical path
    # exactly once, so no route can traverse the same ground twice (no backtrack),
    # while genuinely distinct connectors (e.g. the hike_bike south shore) survive.
    kept_lines = []
    for _, part, props, line, src in cands:
        near = [k for k in kept_lines if line.distance(k) < DUP_TOL_M]
        if near:
            cov = line.intersection(unary_union([k.buffer(DUP_TOL_M) for k in near])).length
            if cov / line.length >= DUP_FRAC:
                dropped += 1
                continue
        add(part, props, line, src)
        kept_lines.append(line)
    return adj, edges, dropped


def reduce_to_core(adj, edges):
    """Prune degree-1 dead-ends, then contract degree-2 chains into super-edges.
    Returns (cadj, cedges, rings). Each cedge carries 'chain' = ordered
    [(orig_eid, forward)] from its node 'a' to 'b'."""
    inc = defaultdict(set)
    for eid, e in edges.items():
        inc[e['a']].add(eid)
        inc[e['b']].add(eid)

    alive = set(edges)
    leaves = [n for n in inc if len(inc[n]) == 1]
    while leaves:
        n = leaves.pop()
        if len(inc[n]) != 1:
            continue
        e = next(iter(inc[n]))
        alive.discard(e)
        a, b = edges[e]['a'], edges[e]['b']
        inc[a].discard(e)
        inc[b].discard(e)
        other = b if n == a else a
        if len(inc[other]) == 1:
            leaves.append(other)

    inc2 = defaultdict(list)
    for e in alive:
        inc2[edges[e]['a']].append(e)
        inc2[edges[e]['b']].append(e)
    junctions = {n for n in inc2 if len(inc2[n]) != 2}

    cadj, cedges, rings = defaultdict(list), {}, []
    used = set()
    cid = 0

    def walk_chain(j, e0):
        chain, total, cur, e = [], 0.0, j, e0
        while True:
            used.add(e)
            ed = edges[e]
            chain.append((e, ed['a'] == cur))
            total += ed['len']
            cur = ed['b'] if ed['a'] == cur else ed['a']
            if cur in junctions or cur == j:
                break
            nxt = [x for x in inc2[cur] if x != e]
            if not nxt:
                break
            e = nxt[0]
        return cur, total, chain

    for j in junctions:
        for e0 in list(inc2[j]):
            if e0 in used:
                continue
            end, total, chain = walk_chain(j, e0)
            if end == j:
                rings.append((total, chain))
            else:
                cedges[cid] = {'a': j, 'b': end, 'len': total, 'chain': chain}
                cadj[j].append((end, cid))
                cadj[end].append((j, cid))
                cid += 1

    for e in alive:
        if e in used:
            continue
        cur, total, chain = walk_chain(edges[e]['a'], e)
        rings.append((total, chain))

    return cadj, cedges, rings


def enumerate_loops(cadj, cedges, rings, edges, has_parking, *,
                    min_mi=MIN_MI, max_mi=MAX_MI, max_legs=MAX_SUPEREDGES,
                    anchor=None, road_cap=MAX_ROAD_FRAC, named_cap=MAX_NAMED_TRAILS):
    """Simple cycles over the contracted junction graph, length in [min,max].
    Parameterized so it serves both the display loops (default caps + anchor/road
    filters) and a granular atom set for composition (small caps, no filters)."""
    if anchor is None:
        anchor = ANCHOR_AT_PARKING
    nodes = sorted(cadj)
    idx = {n: i for i, n in enumerate(nodes)}
    max_m, min_m = max_mi * MILE_M, min_mi * MILE_M
    seen, found = set(), []
    t0 = time.time()
    st = {'stop': False, 'skip': False, 'cur': 0}

    def record(chains, dist):
        steps = [s for ch in chains for s in ch]
        es = frozenset(e for e, _ in steps)
        if es in seen:
            return
        if anchor and has_parking and not any(edges[e]['near_parking'] for e, _ in steps):
            return
        if len({edges[e]['name'] for e, _ in steps if edges[e]['name']}) > named_cap:
            return
        road = sum(edges[e]['len'] for e, _ in steps if edges[e]['src'] == RESCUE_SRC)
        if dist > 0 and road / dist > road_cap:
            return
        seen.add(es)
        found.append({'edges': es, 'steps': steps, 'dist': dist})
        st['cur'] += 1
        if st['cur'] >= PER_START_CAP:
            st['skip'] = True
        if len(found) >= RAW_CAP or time.time() - t0 > TIME_BUDGET_S:
            st['stop'] = True

    def chain_dir(cid, frm):
        ed = cedges[cid]
        if frm == ed['a']:
            return ed['chain']
        return [(e, not fwd) for e, fwd in reversed(ed['chain'])]

    def dfs(start, cur, cpath, npath, dist, visited):
        if st['stop'] or st['skip']:
            return
        for nb, ce in cadj[cur]:
            if ce in cpath:
                continue
            nd = dist + cedges[ce]['len']
            if nb == start:
                if len(cpath) >= 1 and min_m <= nd <= max_m:
                    record([chain_dir(c, npath[i]) for i, c in enumerate(cpath + [ce])], nd)
                    if st['stop'] or st['skip']:
                        return
                continue
            if (idx[nb] <= idx[start] or nb in visited or nd > max_m
                    or len(cpath) >= max_legs):
                continue
            visited.add(nb)
            cpath.append(ce)
            npath.append(nb)
            dfs(start, nb, cpath, npath, nd, visited)
            npath.pop()
            cpath.pop()
            visited.discard(nb)
            if st['stop'] or st['skip']:
                return

    for s in nodes:
        if st['stop']:
            break
        st['cur'], st['skip'] = 0, False
        dfs(s, s, [], [s], 0.0, {s})

    for total, chain in rings:
        if min_m <= total <= max_m:
            record([chain], total)

    return found, st['stop'], time.time() - t0


def jaccard(a, b):
    return len(a & b) / len(a | b)


def dedup_distinct(found, edges):
    """Distinct routes. Optionally (NAMED_SET_DEDUP) first collapse loops that use
    the same SET of named trails to the shortest representative, then always drop
    remaining near-duplicates by edge-set Jaccard."""
    if NAMED_SET_DEDUP:
        by_names = {}
        for c in found:
            names = frozenset(edges[e]['name'] for e, _ in c['steps'] if edges[e]['name'])
            key = names or c['edges']        # all-unnamed loops stay individual
            if key not in by_names or c['dist'] < by_names[key]['dist']:
                by_names[key] = c
        pool = list(by_names.values())
    else:
        pool = found

    kept = []
    for c in sorted(pool, key=lambda c: c['dist']):
        if all(jaccard(c['edges'], k['edges']) < DEDUP_J for k in kept):
            kept.append(c)
            if len(kept) >= MAX_LOOPS:
                break
    return kept


def loop_coords(c, edges):
    coords = []
    for e, fwd in c['steps']:
        cs = edges[e]['coords'] if fwd else edges[e]['coords'][::-1]
        coords.extend(cs[1:] if coords and coords[-1] == cs[0] else cs)
    return coords


def materialize_loop(c, edges):
    """Turn an enumerated cycle into a route struct (coords + node set + stats)."""
    nodes = set()
    for e, _ in c['steps']:
        nodes.add(edges[e]['a'])
        nodes.add(edges[e]['b'])
    return {
        'edges': c['edges'], 'dist': c['dist'], 'coords': loop_coords(c, edges),
        'nodes': nodes,
        'names': sorted({edges[e]['name'] for e, _ in c['steps'] if edges[e]['name']}),
        'road': sum(edges[e]['len'] for e, _ in c['steps'] if edges[e]['src'] == RESCUE_SRC),
        'nseg': len(c['steps']), 'type': 'loop'}


def compactness(coords):
    pts = [_TF_WGS_UTM.transform(lon, lat) for lon, lat in coords]
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    peri = LineString(pts).length
    return (4 * math.pi * poly.area / (peri * peri)) if peri > 0 else 0.0


def loop_name(names):
    """Human label from the trail set, e.g. 'East Bluff + Tumbled Rocks Loop'."""
    if not names:
        return 'Unnamed loop'
    label = ' + '.join(n.replace(' Trail', '') for n in names[:3])
    return label if 'loop' in label.lower() else f'{label} Loop'


def nearest_parking(coords, pts):
    step = max(1, len(coords) // 25)
    best, bd = None, 1e9
    for p in pts:
        for lon, lat in coords[::step]:
            d = haversine_miles(lon, lat, p['lon'], p['lat'])
            if d < bd:
                bd, best = d, p
    return best, bd


def eulerian_route(edge_ids, edges):
    """A union of edge-disjoint cycles has all-even degrees, so it has an Eulerian
    circuit: one closed walk over every edge exactly once (no backtracking).
    Hierholzer's algorithm; returns ordered coords, or None if not one connected
    circuit."""
    adj = defaultdict(list)
    for e in edge_ids:
        adj[edges[e]['a']].append((e, edges[e]['b']))
        adj[edges[e]['b']].append((e, edges[e]['a']))
    if not adj:
        return None
    start = edges[next(iter(edge_ids))]['a']
    used, stack, order = set(), [(start, None)], []
    while stack:
        v = stack[-1][0]
        nxt = None
        while adj[v]:
            e, w = adj[v].pop()
            if e not in used:
                nxt = (e, w)
                break
        if nxt:
            used.add(nxt[0])
            stack.append((nxt[1], nxt[0]))
        else:
            _, incoming = stack.pop()
            if incoming is not None:
                order.append(incoming)
    order.reverse()
    if len(order) != len(edge_ids):       # disconnected -> not a single circuit
        return None
    cur, coords = edges[order[0]]['a'], []
    for e in order:
        a, b = edges[e]['a'], edges[e]['b']
        if cur == a:
            cs, cur = edges[e]['coords'], b
        elif cur == b:
            cs, cur = edges[e]['coords'][::-1], a
        else:
            return None
        coords.extend(cs[1:] if coords and coords[-1] == cs[0] else cs)
    return coords


def build_compositions(loops, edges):
    """Compose longer routes by fusing edge-disjoint base loops that touch at a
    shared junction. Beam search grows connected loop-sets toward TARGET_MI; each
    union is Eulerian so it draws as one backtrack-free closed route. Cost is
    BEAM_WIDTH x base-loops x MAX_COMBINE -- polynomial, so it can't explode."""
    n = len(loops)
    adj = [set() for _ in range(n)]                    # loop graph: disjoint + touching
    for i in range(n):
        for j in range(i + 1, n):
            if not (loops[i]['edges'] & loops[j]['edges']) and (loops[i]['nodes'] & loops[j]['nodes']):
                adj[i].add(j)
                adj[j].add(i)

    max_m, target_m, min_res = MAX_MI * MILE_M, TARGET_MI * MILE_M, COMPOSE_MIN_MI * MILE_M

    def mk(i):
        L = loops[i]
        return {'loops': frozenset([i]), 'edges': set(L['edges']), 'nodes': set(L['nodes']),
                'dist': L['dist'], 'road': L['road'], 'names': set(L['names']), 'nseg': L['nseg']}

    frontier, seen, results = [mk(i) for i in range(n)], set(), []
    for _ in range(2, MAX_COMBINE + 1):
        nxt = []
        for combo in frontier:
            if combo['dist'] >= max_m:
                continue
            cands = set().union(*(adj[i] for i in combo['loops'])) - combo['loops']
            for j in cands:
                Lj = loops[j]
                if combo['edges'] & Lj['edges']:
                    continue
                d = combo['dist'] + Lj['dist']
                if d > max_m:
                    continue
                key = combo['loops'] | {j}
                if key in seen:
                    continue
                seen.add(key)
                nc = {'loops': frozenset(key), 'edges': combo['edges'] | Lj['edges'],
                      'nodes': combo['nodes'] | Lj['nodes'], 'dist': d,
                      'road': combo['road'] + Lj['road'],
                      'names': combo['names'] | set(Lj['names']),
                      'nseg': combo['nseg'] + Lj['nseg']}
                nxt.append(nc)
                if d >= min_res and (d <= 0 or nc['road'] / d <= MAX_ROAD_FRAC):
                    results.append(nc)
        nxt.sort(key=lambda c: abs(c['dist'] - target_m))
        frontier = nxt[:BEAM_WIDTH]
        if not frontier:
            break

    out = []
    for c in results:
        coords = eulerian_route(c['edges'], edges)
        if not coords:
            continue
        # Safety net: reject if the route still retraces ground (collinear overlap),
        # in case any near-duplicate edges slipped past the graph-level dedup.
        pts = [_TF_WGS_UTM.transform(lon, lat) for lon, lat in coords]
        ln = LineString(pts)
        if ln.length - unary_union(ln).length > MAX_RETRACE_FRAC * c['dist']:
            continue
        out.append({'edges': frozenset(c['edges']), 'dist': c['dist'], 'coords': coords,
                    'nodes': c['nodes'], 'road': c['road'], 'names': sorted(c['names']),
                    'nseg': c['nseg'],
                    'type': 'figure8' if len(c['loops']) == 2 else 'composite',
                    'compactness': None})
    return out


def make_feature(r, parking_pts):
    coords = r['coords']
    par, par_mi = nearest_parking(coords, parking_pts)
    at_lot = par is not None and par_mi <= START_NEAR_MI
    suffix = {'figure8': ' (figure-8)', 'composite': ' (loop circuit)'}.get(r['type'], '')
    return {'type': 'Feature',
            'geometry': {'type': 'LineString', 'coordinates': coords},
            'properties': {
                'name': loop_name(r['names']) + suffix,
                'route_type': r['type'],
                'distance_mi': round(r['dist'] / MILE_M, 2),
                'num_segments': r['nseg'], 'trail_names': r['names'],
                'trails_label': ', '.join(r['names']),
                'start_lon': par['lon'] if at_lot else coords[0][0],
                'start_lat': par['lat'] if at_lot else coords[0][1],
                'start_parking': par['name'] if at_lot else None,
                'road_frac': round(r['road'] / r['dist'], 2) if r['dist'] else 0,
                'compactness': r.get('compactness')}}


def _rpc(name, body):
    url = f'{SUPABASE_URL}/rest/v1/rpc/{name}'
    headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}',
               'Content-Type': 'application/json'}
    return _request(url, method='POST', headers=headers, body=body)


def build_routing_graph(near_miles):
    """Weighted graph over ALL trail types + roads (for linking loops to parking).
    adj: node -> [(neighbor, length_m, eid)]; node_utm: node -> (x, y);
    edges_geom: eid -> {a, b, coords} (lon/lat, for rebuilding spur paths)."""
    adj, node_utm, edges_geom = defaultdict(list), {}, {}
    eid = 0
    for src in ROUTING_SOURCES:
        for part, props, line in _parts_in_scope(src, near_miles):
            a, b = node_key(part[0]), node_key(part[-1])
            if a == b:
                continue
            node_utm[a] = line.coords[0]
            node_utm[b] = line.coords[-1]
            edges_geom[eid] = {'a': a, 'b': b, 'coords': [[c[0], c[1]] for c in part]}
            adj[a].append((b, line.length, eid))
            adj[b].append((a, line.length, eid))
            eid += 1
    return adj, node_utm, edges_geom


def _dijkstra_from(adj, source, init, cap):
    """Single-source Dijkstra (capped at `cap` m). Returns (dist, prev) where
    prev[node] = (predecessor_node, edge_id) for spur-path reconstruction."""
    INF = float('inf')
    dm, prev = {source: init}, {source: None}
    pq = [(init, source)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dm.get(u, INF) or d > cap:
            continue
        for v, w, eid in adj[u]:
            nd = d + w
            if nd < dm.get(v, INF):
                dm[v], prev[v] = nd, (u, eid)
                heapq.heappush(pq, (nd, v))
    return dm, prev


def _spur_coords(prev, edges_geom, target, lot):
    """Rebuild the on-network path (lon/lat) from a lot to a loop node `target`."""
    chain, cur = [], target
    while prev.get(cur) is not None:
        p, eid = prev[cur]
        chain.append((eid, p))
        cur = p
    chain.reverse()
    coords = [[lot['lon'], lot['lat']]]            # start at the lot itself
    for eid, p in chain:
        eg = edges_geom[eid]
        cs = eg['coords'] if eg['a'] == p else eg['coords'][::-1]
        coords.extend(cs[1:] if coords and coords[-1] == cs[0] else cs)
    return coords


def link_loops(routes, feats, parking_pts):
    """Link each loop to nearby parking by NETWORK distance over any trail type or
    road, ranking polygon lots ahead of point lots. Stores the primary (start) lot
    plus a `nearby_parking` list (each entry references a lot by OSM id) for the
    popup dropdown. One Dijkstra per lot (capped), each loop reads the min over its
    own nodes."""
    adj, node_utm, edges_geom = build_routing_graph(LINK_NEAR_MILES)
    if not node_utm:
        return 0
    items = list(node_utm.items())
    INF = float('inf')
    cap = LINK_NEAR_MILES * MILE_M
    nearby_m = NEARBY_PARKING_MI * MILE_M

    # Snap each lot to the nearest network node, then Dijkstra out from it.
    lot_data = []  # (lot, dist_by_node, prev_by_node)
    for lot in parking_pts:
        lx, ly = _TF_WGS_UTM.transform(lot['lon'], lot['lat'])
        best, bsq = None, LOT_SNAP_M ** 2
        for nk, (x, y) in items:
            dd = (x - lx) ** 2 + (y - ly) ** 2
            if dd < bsq:
                bsq, best = dd, nk
        if best is not None:
            dm, prev = _dijkstra_from(adj, best, bsq ** 0.5, cap)
            lot_data.append((lot, dm, prev))

    def lot_entry(lot, d):
        return {'osm_id': lot.get('osm_id'), 'name': lot.get('name'),
                'kind': lot.get('kind'), 'lon': lot['lon'], 'lat': lot['lat'],
                'dist_mi': round(d / MILE_M, 2)}

    linked = 0
    for r, f in zip(routes, feats):
        nodes = r['nodes']
        cand = []  # (lot, dist_m, nearest_loop_node, prev) for every reachable lot
        for lot, dm, prev in lot_data:
            best, bnk = INF, None
            for nk in nodes:
                dv = dm.get(nk, INF)
                if dv < best:
                    best, bnk = dv, nk
            if best < INF:
                cand.append((lot, best, bnk, prev))
        if not cand:
            f['properties']['nearby_parking'] = []
            f['properties']['approach_mi'] = None
            continue
        # Nearby lots, polygons first then by distance; fall back to overall nearest.
        nearby = sorted((c for c in cand if c[1] <= nearby_m),
                        key=lambda c: (0 if c[0]['kind'] == 'polygon' else 1, c[1]))
        chosen = nearby[:MAX_NEARBY_PARKING] if nearby else sorted(cand, key=lambda c: c[1])[:1]
        entries = [lot_entry(lot, d) for lot, d, nk, prev in chosen]
        # Spur (on-network path) only for the NEAREST lot, to keep the payload small.
        plot, pd, pnk, pprev = chosen[0]
        entries[0]['spur'] = _spur_coords(pprev, edges_geom, pnk, plot)
        f['properties']['nearby_parking'] = entries
        f['properties']['start_lon'] = plot['lon']
        f['properties']['start_lat'] = plot['lat']
        f['properties']['start_parking'] = plot.get('name')
        f['properties']['approach_mi'] = round(pd / MILE_M, 2)
        linked += 1
    return linked


def loop_elevation(geom):
    """Sample USGS 3DEP along a whole route -> elev_* props (gain/loss/min/max +
    downsampled profile, in feet). Coarse DEM res keeps composite downloads small."""
    seg = compute_segment(geom, res_m=LOOP_DEM_RES_M)
    if not seg:
        return None
    s = seg['series']
    x = np.linspace(0, len(s) - 1, min(PROFILE_POINTS, len(s)))
    prof = [int(round(v * M_TO_FT)) for v in np.interp(x, np.arange(len(s)), s)]
    return {
        'elev_gain_ft': int(round(seg['gain'] * M_TO_FT)),
        'elev_loss_ft': int(round(seg['loss'] * M_TO_FT)),
        'elev_min_ft': int(round(seg['min'] * M_TO_FT)),
        'elev_max_ft': int(round(seg['max'] * M_TO_FT)),
        'elev_dist_mi': round(seg['length'] / MILE_M, 2),
        'elev_profile': prof,
        'elev_src': 'usgs_3dep_10m',
    }


def write_loops(features):
    # Structured store (trail_loops) + the osm_geometries source that backs the
    # 'Hiking Loops' map template layer (migration 060), kept in sync.
    n = _rpc('replace_trail_loops', {'p_features': features, 'p_truncate': True})
    _rpc('replace_layer_geometries',
         {'p_source': LAYER_SOURCE, 'p_features': features, 'p_truncate': True})
    return n


def main():
    dry = '--dry-run' in sys.argv
    print(f"Loops on {' + '.join(SOURCES)} within {NEAR_MILES} mi of Devil's Lake\n"
          f"  band {MIN_MI}-{MAX_MI} mi, {'anchor<= %.0fm parking, ' % ANCHOR_M if ANCHOR_AT_PARKING else 'no parking anchor, '}road<= {MAX_ROAD_FRAC:.0%}, "
          f'<= {MAX_NAMED_TRAILS} named, <= {MAX_SUPEREDGES} legs, compact>= {MIN_COMPACT}, '
          f"dedup {'named-set + ' if NAMED_SET_DEDUP else ''}J>={DEDUP_J}"
          f"{', +compose<= %d loops (beam %d)' % (MAX_COMBINE, BEAM_WIDTH) if ALLOW_FIGURE8 else ''}"
          f"{'  [DRY RUN]' if dry else ''}\n")

    parking_buf, parking_pts = load_parking(NEAR_MILES)
    print(f'  parking lots in scope: {len(parking_pts)}')

    adj, edges, dropped = build_graph(NEAR_MILES, parking_buf)
    print(f'  graph: {len(adj)} nodes, {len(edges)} edges '
          f'({dropped} duplicate/coincident treads dropped)')

    cadj, cedges, rings = reduce_to_core(adj, edges)
    print(f'  contracted core: {len(cadj)} junctions, {len(cedges)} super-edges, '
          f'{len(rings)} rings')

    found, stopped, secs = enumerate_loops(cadj, cedges, rings, edges, parking_buf is not None)
    print(f'  anchored+hikeable cycles in band: {len(found)}  ({secs:.1f}s'
          f'{", HIT GUARD — partial" if stopped else ""})')

    kept = dedup_distinct(found, edges)

    # Display loops: the deduped distinct cycles, minus pinched ones.
    simple, pinched = [], 0
    for c in kept:
        m = materialize_loop(c, edges)
        comp = compactness(m['coords'])
        if comp < MIN_COMPACT:
            pinched += 1
            continue
        m['compactness'] = round(comp, 3)
        simple.append(m)

    routes = list(simple)
    if ALLOW_FIGURE8:
        # Composition base = granular minimal cycles (faces): enumerate small loops
        # (no min/anchor/road filters), then keep only those not containing a
        # smaller one's edges. These overlap little, so many are edge-disjoint.
        atoms_found, _, _ = enumerate_loops(
            cadj, cedges, rings, edges, False, min_mi=0.0, max_mi=ATOM_MAX_MI,
            max_legs=ATOM_MAX_LEGS, anchor=False, road_cap=1.0, named_cap=10 ** 9)
        atoms = sorted((materialize_loop(c, edges) for c in atoms_found),
                       key=lambda a: len(a['edges']))
        minimal = []
        for a in atoms:
            if not any(m['edges'] <= a['edges'] for m in minimal):
                minimal.append(a)
        print(f'  composition atoms: {len(minimal)} minimal cycles '
              f'(from {len(atoms_found)} small loops)')

        # Keep all display loops; dedup composed routes only against each other
        # (a composite contains base loops, so it always looks "similar").
        comp = []
        for r in sorted(build_compositions(minimal, edges), key=lambda r: r['dist']):
            if all(jaccard(r['edges'], k['edges']) < DEDUP_J for k in comp):
                comp.append(r)
                if len(comp) >= MAX_LOOPS:
                    break
        routes = simple + comp

    feats = [make_feature(r, parking_pts) for r in routes]
    feats.sort(key=lambda f: f['properties']['distance_mi'])
    n_loop = sum(1 for r in routes if r['type'] == 'loop')
    n_fig8 = sum(1 for r in routes if r['type'] == 'figure8')
    n_comp = sum(1 for r in routes if r['type'] == 'composite')
    print(f'  routes: {len(routes)} ({n_loop} loops + {n_fig8} figure-8s + '
          f'{n_comp} multi-loop, {pinched} pinched dropped)')
    if feats:
        ds = [f['properties']['distance_mi'] for f in feats]
        print(f'  distance: {min(ds):.1f}-{max(ds):.1f} mi (median {ds[len(ds) // 2]:.1f})\n')

    print('  longest 20:')
    for f in feats[::-1][:20]:
        p = f['properties']
        tag = {'figure8': '8', 'composite': 'C'}.get(p['route_type'], 'o')
        nm = ', '.join(p['trail_names'][:4]) or '(unnamed)'
        print(f"    {tag} {p['distance_mi']:5.2f} mi  @ {str(p['start_parking'])[:20]:<20} {nm[:48]}")

    if dry:
        print('\n[dry run] nothing written (elevation sampling skipped).')
        return

    # Sample USGS 3DEP elevation along each route so popups can show gain + profile
    # (same method as scripts/compute_trail_elevation.py). DEM clips are cached, so
    # overlapping routes reuse them.
    print(f'  sampling USGS 3DEP elevation for {len(feats)} routes...')
    got = 0
    for f in feats:
        elev = loop_elevation(f['geometry'])
        if elev:
            f['properties'].update(elev)
            got += 1
    print(f'  elevation: {got}/{len(feats)} routes')

    # Link each loop to its nearest parking lot over any trail/road (network distance).
    print('  linking loops to nearest parking via trail/road network...')
    linked = link_loops(routes, feats, parking_pts)
    print(f'  linked: {linked}/{len(feats)} routes to a parking lot')

    n = write_loops(feats)
    print(f'\nWrote {n} loops to trail_loops.')


if __name__ == '__main__':
    main()
