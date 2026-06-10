"""
Fetch all OSM data within the bounding polygon from map (2).geojson
and organize into GeoJSON files by type in ./osm_data_files/
"""

import json
import os
import urllib.request
import urllib.parse
import urllib.error

# Bounding box extracted from map (2).geojson polygon
SOUTH = 43.36943624189496
WEST  = -89.79109915402259
NORTH = 43.450313139429596
EAST  = -89.66480152493047

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "osm_data_files")

QUERY = f"""[out:json][timeout:180][bbox:{SOUTH},{WEST},{NORTH},{EAST}];
(
  way["highway"];
  way["natural"];
  way["waterway"];
  way["landuse"];
  way["building"];
  way["amenity"];
  way["leisure"];
  way["boundary"];
  way["barrier"];
  way["route"];
  node["amenity"];
  node["tourism"];
  node["shop"];
  node["historic"];
  node["information"];
  node["natural"~"peak|spring|cave_entrance|viewpoint|tree"];
  node["leisure"];
  node["sport"];
  node["emergency"];
  relation["natural"];
  relation["landuse"];
  relation["waterway"];
  relation["leisure"~"park|nature_reserve"];
  relation["boundary"];
  relation["route"~"hiking|foot|bicycle|mtb|canoe"];
);
out geom;"""


# ── Geometry helpers ─────────────────────────────────────────────────────────

def way_coords(geometry):
    return [[g["lon"], g["lat"]] for g in geometry]

def is_area(tags):
    if tags.get("area") == "yes":
        return True
    if tags.get("area") == "no":
        return False
    area_keys = {
        "natural": {"water", "wetland", "wood", "forest", "grassland", "heath",
                    "scrub", "rock", "bare_rock", "sand", "beach", "glacier", "fell"},
        "landuse": None,
        "building": None,
        "leisure":  {"park", "nature_reserve", "garden", "pitch", "camp_site",
                     "campsite", "common", "dog_park", "golf_course"},
        "amenity":  {"parking", "school", "university", "hospital",
                     "place_of_worship", "marketplace"},
        "boundary": None,
    }
    for key, vals in area_keys.items():
        if key in tags and (vals is None or tags[key] in vals):
            return True
    return False

def assemble_ring(segments):
    """Connect way-segment coord lists into one closed ring, best-effort."""
    segs = [list(s) for s in segments]
    ring  = segs.pop(0)
    for _ in range(len(segs) * 2 + 2):
        if not segs:
            break
        for i, seg in enumerate(segs):
            if seg[0] == ring[-1]:
                ring.extend(seg[1:]);  segs.pop(i);  break
            if seg[-1] == ring[-1]:
                ring.extend(reversed(seg[:-1]));  segs.pop(i);  break
        else:
            break
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring if len(ring) >= 4 else None


# ── Element → GeoJSON feature ────────────────────────────────────────────────

def node_feature(e):
    return {
        "type": "Feature",
        "id": f"node/{e['id']}",
        "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"]]},
        "properties": {**e.get("tags", {}), "_osm_type": "node", "_osm_id": e["id"]},
    }

def way_feature(e):
    tags = e.get("tags", {})
    pts  = e.get("geometry", [])
    if not pts:
        return None
    coords   = way_coords(pts)
    closed   = len(coords) >= 4 and coords[0] == coords[-1]
    geometry = ({"type": "Polygon",    "coordinates": [coords]}
                if closed and is_area(tags)
                else {"type": "LineString", "coordinates": coords})
    return {
        "type": "Feature",
        "id": f"way/{e['id']}",
        "geometry": geometry,
        "properties": {**tags, "_osm_type": "way", "_osm_id": e["id"]},
    }

def relation_feature(e):
    tags    = e.get("tags", {})
    members = e.get("members", [])

    outer_segs, inner_segs = [], []
    for m in members:
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        coords = [[g["lon"], g["lat"]] for g in m["geometry"]]
        (inner_segs if m.get("role") == "inner" else outer_segs).append(coords)

    if not outer_segs:
        return None

    # Separate pre-closed rings from open segments
    closed_outer = [s for s in outer_segs if s[0] == s[-1] and len(s) >= 4]
    open_outer   = [s for s in outer_segs if s not in closed_outer]

    if open_outer:
        assembled = assemble_ring(open_outer)
        if assembled:
            closed_outer.append(assembled)

    if not closed_outer:
        return None

    inner_rings = [s for s in inner_segs if s[0] == s[-1] and len(s) >= 4]

    if len(closed_outer) == 1:
        geometry = {"type": "Polygon", "coordinates": [closed_outer[0]] + inner_rings}
    else:
        geometry = {"type": "MultiPolygon",
                    "coordinates": [[ring] for ring in closed_outer]}

    return {
        "type": "Feature",
        "id": f"relation/{e['id']}",
        "geometry": geometry,
        "properties": {**tags, "_osm_type": "relation", "_osm_id": e["id"]},
    }


# ── Categorization ────────────────────────────────────────────────────────────

def categorize(tags):
    h       = tags.get("highway", "")
    amenity = tags.get("amenity", "")
    nat     = tags.get("natural", "")
    leis    = tags.get("leisure", "")
    ww      = tags.get("waterway", "")
    route   = tags.get("route", "")

    if route in ("hiking", "foot", "bicycle", "mtb", "canoe"):
        return "routes"
    if h in ("path", "footway", "track", "steps", "bridleway", "cycleway"):
        return "trails"
    if h in ("motorway", "motorway_link", "trunk", "trunk_link",
             "primary", "primary_link", "secondary", "secondary_link",
             "tertiary", "tertiary_link", "unclassified",
             "residential", "service", "living_street", "road"):
        return "roads"
    if h in ("crossing", "traffic_signals", "stop", "give_way"):
        return "roads"

    if nat in ("water", "wetland", "spring") or ww or tags.get("water"):
        return "water"

    if nat in ("wood", "forest", "grassland", "heath", "scrub",
               "rock", "bare_rock", "cliff", "peak", "saddle",
               "sand", "beach", "glacier", "fell", "scree",
               "shingle", "mud", "ridge", "valley", "sinkhole"):
        return "natural"
    if nat in ("tree", "tree_row", "hedge"):
        return "natural"
    if nat:  # catch any remaining natural=* values
        return "natural"

    if leis in ("park", "nature_reserve", "common", "dog_park"):
        return "parks"
    if tags.get("boundary"):  # any boundary=* value
        return "parks"

    lu = tags.get("landuse", "")
    if lu:
        return "landuse"

    if tags.get("building"):
        return "buildings"

    if amenity == "parking" or tags.get("parking"):
        return "parking"

    if leis:  # any remaining leisure=* value
        return "pois"
    if amenity or tags.get("tourism") or tags.get("shop") or tags.get("historic"):
        return "pois"
    if tags.get("information") or tags.get("emergency"):
        return "pois"
    if tags.get("sport"):
        return "pois"
    if tags.get("man_made") or tags.get("power") or tags.get("railway"):
        return "infrastructure"
    if tags.get("barrier"):
        return "barriers"

    return "other"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Querying Overpass API …")
    print(f"  bbox: S={SOUTH:.5f}  W={WEST:.5f}  N={NORTH:.5f}  E={EAST:.5f}\n")

    payload = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(
        OVERPASS_URL, data=payload,
        headers={"User-Agent": "ApexAdventureAlliance-TrailMap/1.0 (byates@deepwalkresearch.com)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=210) as resp:
            raw = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:400]}")
        return
    except Exception as e:
        print(f"Error: {e}")
        return

    elements = raw.get("elements", [])
    print(f"Received {len(elements):,} elements from Overpass\n")

    buckets = {k: [] for k in [
        "trails", "roads", "water", "natural", "parks",
        "landuse", "buildings", "parking", "pois", "routes",
        "barriers", "infrastructure", "other"
    ]}

    skipped = 0
    for elem in elements:
        tags = elem.get("tags", {})
        if not tags:
            skipped += 1
            continue

        etype = elem.get("type")
        if   etype == "node":     feat = node_feature(elem)
        elif etype == "way":      feat = way_feature(elem)
        elif etype == "relation": feat = relation_feature(elem)
        else:                     continue

        if feat is None:
            skipped += 1
            continue

        buckets[categorize(tags)].append(feat)

    print(f"{'Category':<14} {'Features':>8}   {'File size':>12}")
    print("-" * 40)
    written = 0
    for cat, features in buckets.items():
        if not features:
            continue
        path = os.path.join(OUTPUT_DIR, f"{cat}.geojson")
        fc   = {"type": "FeatureCollection", "features": features}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(fc, fh, separators=(",", ":"))
        size = os.path.getsize(path)
        print(f"  {cat:<12} {len(features):>8}   {size/1024:>9.1f} KB")
        written += 1

    print("-" * 40)
    print(f"  {'TOTAL':<12} {sum(len(v) for v in buckets.values()):>8}")
    print(f"\n{written} files written to: {OUTPUT_DIR}")
    if skipped:
        print(f"({skipped} elements skipped — no tags or empty geometry)")

if __name__ == "__main__":
    main()
