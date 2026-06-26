"""
Fetch all campsites within 25 miles of Devil's Lake State Park, WI from
OpenStreetMap and load them into the 'pois' layer.

  - tourism=camp_site / caravan_site / leisure=camp_site
  - nodes use their own coords; ways/relations use their centroid (Overpass
    `out center`) so polygon campsites render in the point-only POIs layer.
  - Always writes osm_data_files/campsites_25mi.geojson.
  - If SUPABASE_URL / SUPABASE_KEY are set, upserts into source='pois' via
    the upsert_osm_feature RPC (migration 008), safe to re-run, no dupes.

Usage:
  python fetch_campsites.py                         # fetch + write geojson only
  op run --env-file=.env.tpl -- python fetch_campsites.py   # fetch + import
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# Devil's Lake State Park center; 25 miles = 40234 m
LAT, LON, RADIUS_M = 43.4286, -89.7316, 40234
# Target layer source (osm_geometries.source). Override via 1st CLI arg.
# Defaults to the dedicated camping layer.
TARGET_SOURCE = sys.argv[1] if len(sys.argv) > 1 else "pois_camping"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OUTPUT_FILE = Path(__file__).parent / "osm_data_files" / "campsites_25mi.geojson"

QUERY = f"""[out:json][timeout:120];
(
  node["tourism"="camp_site"](around:{RADIUS_M},{LAT},{LON});
  way["tourism"="camp_site"](around:{RADIUS_M},{LAT},{LON});
  relation["tourism"="camp_site"](around:{RADIUS_M},{LAT},{LON});
  node["tourism"="caravan_site"](around:{RADIUS_M},{LAT},{LON});
  way["tourism"="caravan_site"](around:{RADIUS_M},{LAT},{LON});
  node["leisure"="camp_site"](around:{RADIUS_M},{LAT},{LON});
  way["leisure"="camp_site"](around:{RADIUS_M},{LAT},{LON});
);
out center tags;"""


def to_point_feature(e):
    """Build a Point GeoJSON feature (centroid for ways/relations)."""
    tags = e.get("tags", {})
    if e["type"] == "node":
        lon, lat = e.get("lon"), e.get("lat")
    else:
        c = e.get("center")
        if not c:
            return None
        lon, lat = c["lon"], c["lat"]
    if lon is None or lat is None:
        return None
    return {
        "type": "Feature",
        "id": f'{e["type"]}/{e["id"]}',
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {**tags, "_osm_type": e["type"], "_osm_id": e["id"]},
    }


def fetch():
    payload = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(
        OVERPASS_URL, data=payload,
        headers={"User-Agent": "DevilsLakeMappingProject/1.0 (byates@deepwalkresearch.com)"},
    )
    with urllib.request.urlopen(req, timeout=150) as resp:
        return json.loads(resp.read().decode()).get("elements", [])


def main():
    print(f"Querying Overpass for campsites within 25 mi of Devil's Lake "
          f"({LAT}, {LON}) …")
    try:
        elements = fetch()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:400]}")
        return
    except Exception as e:
        print(f"Error: {e}")
        return

    features, skipped = [], 0
    for e in elements:
        f = to_point_feature(e)
        if f:
            features.append(f)
        else:
            skipped += 1

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    fc = {"type": "FeatureCollection", "features": features}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, separators=(",", ":"))
    print(f"  {len(features)} campsites written to {OUTPUT_FILE}"
          + (f" ({skipped} skipped, no geometry)" if skipped else ""))

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not (url and key):
        print("\nSUPABASE_URL / SUPABASE_KEY not set, wrote GeoJSON only.")
        print("To import, run: op run --env-file=.env.tpl -- python fetch_campsites.py")
        return

    from supabase import create_client
    sb = create_client(url, key)
    print(f"\nUpserting into source='{TARGET_SOURCE}' via upsert_osm_feature …")
    inserted = updated = errors = 0
    for i, f in enumerate(features):
        try:
            res = sb.rpc("upsert_osm_feature",
                         {"p_source": TARGET_SOURCE, "p_feature": f}).execute()
            if res.data == "updated":
                updated += 1
            else:
                inserted += 1
        except Exception as ex:
            osm_id = f["properties"].get("_osm_id", "?")
            print(f"  Error on feature {i} (osm_id={osm_id}): {ex}")
            errors += 1
    print(f"  Done: {inserted} inserted, {updated} updated, {errors} errors")


if __name__ == "__main__":
    main()
