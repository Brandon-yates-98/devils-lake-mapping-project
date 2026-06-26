#!/usr/bin/env python3
"""
compute_area_hulls.py
Boundary polygon for EVERY parent climbing area (the semantic-clustering
hulls behind the public map's zoom bands), using the same methodology as
the sector boundaries this supersedes (compute_sector_boundaries.py):

  concave hull (ratio 0.45) of the subtree's climbs, follows the bluff
  line instead of ballooning across the lake, computed in a
  latitude-corrected space so the ~55 m round buffer is metrically round,
  lightly simplified (~6 m). Convex fallback below 4 distinct points.

Unlike the sector script there is no top-level grouping: one hull per
parent area at every hierarchy depth (the zoom bands need all levels).
Linkups/Contrivances stays excluded (non-geographic; the map renders it
as a point badge via HULL_AS_POINT).

Writes:
  migrations/020_climbing_area_hulls_v2.sql, replaces the climbing_area_hulls
    rows AND retires the climbing_route_sectors / climbing_boulder_sectors
    layers. Run in Supabase SQL Editor; safe to re-run.
  _hulls_preview.geojson, local visual QA (not committed)

Run:  .venv/Scripts/python.exe compute_area_hulls.py
Reads are anon (RLS-allowed); the write happens via the SQL file you run.
"""
import json
import math
import sys
import urllib.request

from shapely import concave_hull, set_precision
from shapely.geometry import MultiPoint, mapping
from shapely.affinity import scale as shp_scale

SUPABASE_URL = "https://lcenhesezodgrjrymngg.supabase.co"
ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxj"
    "ZW5oZXNlem9kZ3JqcnltbmdnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk0Mjk2MDksImV4"
    "cCI6MjA5NTAwNTYwOX0.HD9iIKp267i3t2csvLA68TBZ4ASDBL14xznlSQumn30"
)

BUFFER_DEG = 55 / 111_000          # ~55 m in latitude degrees
SIMPLIFY_DEG = 6 / 111_000         # ~6 m, keeps vertices low, shape smooth
CONCAVE_RATIO = 0.45               # 0 = max concave, 1 = convex hull
EXCLUDE_NAMES = {
    "Linkups, Contrivances, Oddities and Triflings",  # not geographic
    "Devil's Lake Rock Climbing",  # park-wide root, too big to be a useful polygon
}
OUT_SQL = sys.argv[1] if len(sys.argv) > 1 else "migrations/020_climbing_area_hulls_v2.sql"
OUT_PREVIEW = "_hulls_preview.geojson"


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
    # ancestor in its area_path), so a hull covers all the walls beneath it.
    by_subtree = {}
    for feats in (routes, boulders):
        for f in feats:
            if f["geometry"]["type"] != "Point":
                continue
            for aid in set(f["properties"].get("area_path") or []):
                by_subtree.setdefault(aid, []).append(tuple(f["geometry"]["coordinates"]))

    parents = [aid for aid in area_by_id if children.get(aid)]
    lat0 = 43.43
    kx = math.cos(math.radians(lat0))   # lon degrees are shorter than lat degrees

    features = []
    for aid in sorted(parents, key=lambda a: area_by_id[a].get("name") or ""):
        meta = area_by_id[aid]
        if (meta.get("name") or "") in EXCLUDE_NAMES:
            continue
        coords = by_subtree.get(aid)
        if not coords:
            continue
        pts = MultiPoint(list(set(coords)))
        # locally-scaled space → metric-ish round buffer → back to degrees.
        scaled = shp_scale(pts, xfact=kx, yfact=1.0, origin=(0, 0))
        hull = concave_hull(scaled, ratio=CONCAVE_RATIO) if len(pts.geoms) >= 4 else scaled.convex_hull
        poly = hull.buffer(BUFFER_DEG, quad_segs=12).simplify(SIMPLIFY_DEG)
        poly = shp_scale(poly, xfact=1.0 / kx, yfact=1.0, origin=(0, 0))
        poly = set_precision(poly, 1e-6)  # ~10 cm, keeps the SQL compact
        features.append({
            "geometry": mapping(poly),
            "properties": {
                "area_id": aid,
                "parent_id": meta.get("parent_id") or "",
                "name": meta.get("name") or "(unnamed area)",
                "depth": meta.get("depth") or 0,
                "_hull": True,
            },
        })
        print(f"  d{meta.get('depth') or 0} {meta.get('name'):<55} climbs={len(coords):>4}")
    print(f"parent-area hulls: {len(features)}")

    with open(OUT_PREVIEW, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection",
                   "features": [{"type": "Feature", **x} for x in features]}, f)

    def sq(s):
        return str(s).replace("'", "''")

    rows = []
    for feat in features:
        props = feat["properties"]
        geom = json.dumps(feat["geometry"], separators=(",", ":"))
        rows.append(
            "('climbing_area_hulls', '%s', st_setsrid(st_geomfromgeojson('%s'), 4326), '%s'::jsonb)"
            % (sq(props["name"]), sq(geom), sq(json.dumps(props, separators=(",", ":"))))
        )

    values_sql = ",\n".join(rows)
    sql = f"""-- ============================================================
-- Devil's Lake Mapping Project, parent-area hulls v2 (generated)
-- Run in Supabase: Dashboard → SQL Editor → New query
-- Generated by compute_area_hulls.py, safe to re-run (replaces all).
--
-- Concave-hull methodology carried over from the sector boundaries
-- (which this supersedes and retires below): concave hull of the
-- subtree's climbs, 55 m round buffer, ~6 m simplify.
-- ============================================================

delete from osm_geometries where source = 'climbing_area_hulls';

insert into osm_geometries (source, name, geometry, properties) values
{values_sql};

-- Retire the sector boundary layers, the banded hulls replace them
delete from osm_geometries where source in ('climbing_route_sectors', 'climbing_boulder_sectors');
delete from experience_layers where template_slug in ('climbing_route_sectors', 'climbing_boulder_sectors');
delete from layer_templates where slug in ('climbing_route_sectors', 'climbing_boulder_sectors');
"""
    with open(OUT_SQL, "w", encoding="utf-8") as f:
        f.write(sql)
    print(f"wrote {OUT_SQL} ({len(sql) // 1024} KB) and {OUT_PREVIEW}")


if __name__ == "__main__":
    main()
