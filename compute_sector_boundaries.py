#!/usr/bin/env python3
"""
compute_sector_boundaries.py
Compute a boundary polygon for each top-level climbing SECTOR GROUP and emit
a SQL migration that loads them as the `climbing_sectors` layer.

Grouping (matches the OpenBeta hierarchy at Devil's Lake):
  - the top-level areas (East Bluff 01-08, West Bluff 01-07, ...) one each,
  - EXCEPT umbrella areas whose climbs span a huge extent (Devil's Lake
    Bouldering: 7.4 km) — those descend one level to their children,
  - and non-geographic areas (Linkups/Contrivances: full-park link-ups)
    are excluded entirely.
  → ~28 clean polygons instead of one per leaf wall.

Shape: concave hull of the group's climbs (follows the bluff line instead of
ballooning across the lake), buffered ~55 m with round joins, computed in a
latitude-corrected space so curves are metrically round, lightly simplified.

Each polygon carries the same OpenBeta association properties as the area
markers (area_id / parent_id / area_path), so the public map's climb lists,
sub-tree filtering, and popups work on sectors out of the box.

Writes:
  migrations/015_climbing_sectors.sql   — run in Supabase SQL Editor
  _sectors_preview.geojson              — local visual QA (not committed)

Run:  .venv/Scripts/python.exe compute_sector_boundaries.py
Reads are anon (RLS-allowed); the write happens via the SQL file you run.
"""
import json
import math
import urllib.request

from shapely import concave_hull
from shapely.geometry import MultiPoint, mapping
from shapely.affinity import scale as shp_scale

SUPABASE_URL = "https://lcenhesezodgrjrymngg.supabase.co"
ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxj"
    "ZW5oZXNlem9kZ3JqcnltbmdnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk0Mjk2MDksImV4"
    "cCI6MjA5NTAwNTYwOX0.HD9iIKp267i3t2csvLA68TBZ4ASDBL14xznlSQumn30"
)

BUFFER_DEG = 55 / 111_000          # ~55 m in latitude degrees
SIMPLIFY_DEG = 6 / 111_000         # ~6 m — keeps vertices low, shape smooth
CONCAVE_RATIO = 0.45               # 0 = max concave, 1 = convex hull
SPLIT_EXTENT_KM = 1.8              # umbrella areas wider than this descend a level
EXCLUDE_NAMES = {"Linkups, Contrivances, Oddities and Triflings"}  # not geographic
OUT_SQL = "migrations/015_climbing_sectors.sql"
OUT_PREVIEW = "_sectors_preview.geojson"


def rpc(fn, args):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/{fn}",
        data=json.dumps(args).encode(),
        headers={"Content-Type": "application/json", "apikey": ANON_KEY},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main():
    routes = rpc("get_layer_geojson", {"p_source": "climbing_routes"})["features"]
    boulders = rpc("get_layer_geojson", {"p_source": "climbing_boulders"})["features"]
    areas = rpc("get_layer_geojson", {"p_source": "climbing_areas"})["features"]
    print(f"routes={len(routes)} boulders={len(boulders)} areas={len(areas)}")

    area_by_id = {}
    children = {}
    for f in areas:
        p = f["properties"]
        aid = p.get("area_id")
        if not aid:
            continue
        area_by_id[aid] = p
        par = p.get("parent_id") or ""
        children.setdefault(par, []).append(aid)

    # Climb coordinates per area SUB-TREE (a climb counts toward every
    # ancestor in its area_path), so a group polygon covers all its walls.
    # Track route vs boulder counts to classify each sector group.
    by_subtree = {}
    route_n = {}
    boulder_n = {}
    for kind, feats in (("r", routes), ("b", boulders)):
        for f in feats:
            p = f["properties"]
            if f["geometry"]["type"] != "Point":
                continue
            for aid in set(p.get("area_path") or []):
                by_subtree.setdefault(aid, []).append(tuple(f["geometry"]["coordinates"]))
                tally = route_n if kind == "r" else boulder_n
                tally[aid] = tally.get(aid, 0) + 1

    def extent_km(coords):
        if len(coords) < 2:
            return 0.0
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        return max((max(xs) - min(xs)) * 81, (max(ys) - min(ys)) * 111)

    # Group selection: top-level areas; oversized umbrellas descend one level.
    roots = [aid for aid in area_by_id if (area_by_id[aid].get("parent_id") or "") not in area_by_id]
    groups = []
    for aid in roots:
        if area_by_id[aid].get("name") in EXCLUDE_NAMES:
            continue
        coords = by_subtree.get(aid, [])
        if not coords:
            continue
        if extent_km(coords) > SPLIT_EXTENT_KM and children.get(aid):
            groups.extend(c for c in children[aid] if by_subtree.get(c))
        else:
            groups.append(aid)

    lat0 = 43.43
    kx = math.cos(math.radians(lat0))   # lon degrees are shorter than lat degrees

    features = []
    for aid in sorted(groups, key=lambda a: area_by_id[a].get("name") or ""):
        meta = area_by_id[aid]
        coords = by_subtree[aid]
        pts = MultiPoint(list(set(coords)))
        # locally-scaled space → metric-ish round buffer → back to degrees.
        # Concave hull follows the bluff line; convex fallback for tiny sets.
        scaled = shp_scale(pts, xfact=kx, yfact=1.0, origin=(0, 0))
        hull = concave_hull(scaled, ratio=CONCAVE_RATIO) if len(pts.geoms) >= 4 else scaled.convex_hull
        poly = hull.buffer(BUFFER_DEG, quad_segs=12).simplify(SIMPLIFY_DEG)
        poly = shp_scale(poly, xfact=1.0 / kx, yfact=1.0, origin=(0, 0))
        # Majority climb type decides the layer: roped sectors carry a few
        # stray boulders (and vice versa), but the group identity is clear.
        nr, nb = route_n.get(aid, 0), boulder_n.get(aid, 0)
        source = "climbing_boulder_sectors" if nb >= nr else "climbing_route_sectors"
        features.append({
            "type": "Feature",
            "source": source,
            "geometry": mapping(poly),
            "properties": {
                "_draw_id": "ob-sector-" + aid,
                "name": meta.get("name") or "(unnamed sector)",
                "area_id": aid,
                "parent_id": meta.get("parent_id") or "",
                "area_path": meta.get("area_path") or [],
                "depth": meta.get("depth") or 0,
                "climb_count": len(coords),
            },
            "custom_data": {"openbeta_id": aid},
        })
        print(f"  [{source.split('_')[1]:<7}] {meta.get('name'):<50} routes={nr:>4} boulders={nb:>4}")
    print(f"sector groups with boundaries: {len(features)}")

    with open(OUT_PREVIEW, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection",
                   "features": [{"type": "Feature", "geometry": x["geometry"],
                                 "properties": {**x["properties"], "kind": x["source"]}}
                                for x in features]}, f)

    def sq(s):  # SQL single-quote escape
        return str(s).replace("'", "''")

    rows = []
    for feat in features:
        props = dict(feat["properties"])
        geom = json.dumps(feat["geometry"], separators=(",", ":"))
        rows.append(
            "('%s', '%s', st_setsrid(st_geomfromgeojson('%s'), 4326), "
            "'%s'::jsonb, '%s'::jsonb)" % (
                feat["source"], sq(props["name"]), sq(geom),
                sq(json.dumps(props, separators=(",", ":"))),
                sq(json.dumps(feat["custom_data"], separators=(",", ":"))),
            )
        )

    values_sql = ",\n".join(rows)
    sql = f"""-- ============================================================
-- Apex Web Maps — Climbing sector boundaries (generated)
-- Run in Supabase: Dashboard → SQL Editor → New query
-- Generated by compute_sector_boundaries.py — safe to re-run (replaces all).
-- Two layers: route sectors (roped) and boulder sectors, classified by
-- each group's majority climb type.
-- ============================================================

insert into layer_templates (slug, label, geom_type, layer_group, default_style, is_custom)
values
  ('climbing_route_sectors', 'Route Sectors', 'polygon', 'Climbing',
   '{{"color":"#e67e22","fill_opacity":0.12}}'::jsonb, false),
  ('climbing_boulder_sectors', 'Boulder Sectors', 'polygon', 'Climbing',
   '{{"color":"#8e6fc1","fill_opacity":0.12}}'::jsonb, false)
on conflict (slug) do update
  set label = excluded.label, geom_type = excluded.geom_type,
      default_style = excluded.default_style;

-- Retire the old combined layer (replaced by the two above)
delete from osm_geometries where source = 'climbing_sectors';
delete from experience_layers where template_slug = 'climbing_sectors';
delete from layer_templates where slug = 'climbing_sectors';

delete from osm_geometries where source in ('climbing_route_sectors', 'climbing_boulder_sectors');

insert into osm_geometries (source, name, geometry, properties, custom_data) values
{values_sql};
"""
    with open(OUT_SQL, "w", encoding="utf-8") as f:
        f.write(sql)
    print(f"wrote {OUT_SQL} ({len(sql) // 1024} KB) and {OUT_PREVIEW}")


if __name__ == "__main__":
    main()
