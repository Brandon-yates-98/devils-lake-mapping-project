"""
Build a routable graph of the Sauk County trail network from the noded
osm_geometries segments, report its topology, and demo a shortest path.

The trails layer is a properly noded network (segments split at junctions, shared
endpoints) -- see memory:sauk-trails-noded-network -- so we can turn it straight
into a graph: nodes = shared endpoints (lon/lat snapped to ~0.1 m), edges = trail
segments carrying length + type + name. We combine all sauk_trail_* sources so
cross-type junctions (a hiking segment meeting a bike route) connect via the
shared coordinate.

This is an OFFLINE analysis/experiment artifact (no DB writes, no schema change).
It's the foundation for either in-DB routing (enable pgRouting, persist node/edge
tables) or precomputed offline routes; today there is no in-app routing
(memory:routing-via-native-redirects).

Requirements: pip install networkx   (rasterio/pyproj/shapely already present)

Usage:
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/build_trail_graph.py
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/build_trail_graph.py --near 2 --export scratch
  # one trail type only:
  ! op run --env-file=.env.tpl -- .venv/Scripts/python.exe scripts/build_trail_graph.py --source sauk_trail_hiking

Required env (locally via 1Password `op`): SUPABASE_URL, SUPABASE_KEY
"""
import os, sys, json

import networkx as nx
from shapely.geometry import LineString

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_sauk_trails import ALL_SLUGS  # noqa: E402
from compute_trail_elevation import (  # noqa: E402
    read_source, geom_parts, near_devils_lake, _TF_WGS_UTM, M_TO_FT, MILE_M,
)

SNAP = 6  # decimal degrees for node identity (~0.11 m) -- matches the topology check


def node_key(coord):
    return (round(coord[0], SNAP), round(coord[1], SNAP))


def part_length_m(part):
    return LineString([_TF_WGS_UTM.transform(lon, lat) for lon, lat, *_ in part]).length


def parse_args(argv):
    a = {'source': None, 'near': None, 'export': None}
    for i, t in enumerate(argv):
        if t == '--source' and i + 1 < len(argv):
            a['source'] = argv[i + 1]
        elif t == '--near' and i + 1 < len(argv):
            a['near'] = float(argv[i + 1])
        elif t == '--export' and i + 1 < len(argv):
            a['export'] = argv[i + 1]
    return a


def build_graph(slugs, near_miles):
    """MultiGraph: parallel segments between the same two nodes are kept distinct."""
    G = nx.MultiGraph()
    for slug in slugs:
        for f in read_source(slug):
            geom = f.get('geometry')
            props = f.get('properties') or {}
            parts = geom_parts(geom)
            if near_miles is not None and not near_devils_lake(parts, near_miles):
                continue
            for part in parts:
                if len(part) < 2:
                    continue
                a, b = node_key(part[0]), node_key(part[-1])
                G.add_node(a, lon=a[0], lat=a[1])
                G.add_node(b, lon=b[0], lat=b[1])
                G.add_edge(a, b,
                           length_m=part_length_m(part),
                           name=(props.get('name') or '').strip() or None,
                           trail_type=props.get('trail_type'),
                           source=slug,
                           fid=props.get('id'))
    return G


def farthest_pair(H):
    """Approximate the most-distant node pair in a component via double sweep."""
    s = next(iter(H))
    d1 = nx.single_source_dijkstra_path_length(H, s, weight='length_m')
    u = max(d1, key=d1.get)
    d2 = nx.single_source_dijkstra_path_length(H, u, weight='length_m')
    v = max(d2, key=d2.get)
    return u, v, d2[v]


def named_route(H, path):
    """Collapse a node path into a human sequence of trail names with distances."""
    legs = []
    for x, y in zip(path, path[1:]):
        ed = min(H.get_edge_data(x, y).values(), key=lambda e: e['length_m'])
        nm = ed['name'] or f"({ed['trail_type'] or 'unnamed'})"
        if legs and legs[-1][0] == nm:
            legs[-1][1] += ed['length_m']
        else:
            legs.append([nm, ed['length_m']])
    return legs


def main():
    args = parse_args(sys.argv[1:])
    slugs = [args['source']] if args['source'] else ALL_SLUGS
    scope = f"within {args['near']} mi of Devil's Lake" if args['near'] else 'entire layer'
    print(f'Building trail graph ({scope})...\n')

    G = build_graph(slugs, args['near'])
    if G.number_of_edges() == 0:
        sys.exit('No segments in scope.')

    total_mi = sum(d['length_m'] for *_, d in G.edges(data=True)) / MILE_M
    degs = dict(G.degree())
    deadends = sum(1 for d in degs.values() if d == 1)
    junctions = sum(1 for d in degs.values() if d >= 3)
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    giant = G.subgraph(comps[0])
    giant_mi = sum(d['length_m'] for *_, d in giant.edges(data=True)) / MILE_M
    names = {d['name'] for *_, d in G.edges(data=True) if d['name']}

    print(f'  nodes:            {G.number_of_nodes()}')
    print(f'  edges (segments): {G.number_of_edges()}')
    print(f'  total length:     {total_mi:.1f} mi')
    print(f'  named trails:     {len(names)}')
    print(f'  dead-ends (deg1): {deadends}   junctions (deg>=3): {junctions}')
    print(f'  connected components: {len(comps)} '
          f'(largest: {giant.number_of_nodes()} nodes, '
          f'{giant.number_of_edges()} edges, {giant_mi:.1f} mi)')
    small = [len(c) for c in comps[1:]]
    if small:
        print(f'  other components: sizes {small[:12]}{" ..." if len(small) > 12 else ""}')

    # Demo: longest shortest-path across the largest component.
    u, v, dist_m = farthest_pair(giant)
    path = nx.dijkstra_path(giant, u, v, weight='length_m')
    print(f'\n  Demo route (farthest pair in largest component): {dist_m / MILE_M:.2f} mi')
    print(f'    from ({u[1]:.5f},{u[0]:.5f}) to ({v[1]:.5f},{v[0]:.5f}) via:')
    for nm, m in named_route(giant, path):
        print(f'      {m / MILE_M:5.2f} mi  {nm}')

    if args['export']:
        os.makedirs(args['export'], exist_ok=True)
        edges_fc = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature',
             'geometry': {'type': 'LineString', 'coordinates': [list(a), list(b)]},
             'properties': {k: v for k, v in d.items() if k != 'fid'}}
            for a, b, d in G.edges(data=True)]}
        nodes_fc = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature',
             'geometry': {'type': 'Point', 'coordinates': [n[0], n[1]]},
             'properties': {'degree': degs[n]}}
            for n in G.nodes()]}
        with open(os.path.join(args['export'], 'trail_graph_edges.geojson'), 'w') as fh:
            json.dump(edges_fc, fh)
        with open(os.path.join(args['export'], 'trail_graph_nodes.geojson'), 'w') as fh:
            json.dump(nodes_fc, fh)
        print(f"\n  exported edges + nodes GeoJSON to {args['export']}/")


if __name__ == '__main__':
    main()
