"""
Apply campsite enrichment (price / website / reservation) to the pois_camping
layer. Reads a JSON map of { "<_osm_id>": {min_price, max_price, website,
reservation_url, price_source} } and merges each into the matching feature's
base properties via the security-definer upsert_osm_feature RPC.

  - Only keys present in the JSON entry are written (null/missing left alone).
  - price_date_extracted is stamped on every entry (records when checked).
  - Existing properties/geometry are preserved (read-merge-write).

Usage:
  op run --env-file=.env.tpl -- python enrich_campsites.py [enrichment.json]
"""

import os
import sys
import json
from supabase import create_client

SOURCE = "pois_camping"
DATE = "2026-05-29"  # price_date_extracted stamp
FIELDS = ("min_price", "max_price", "website", "reservation_url", "price_source")
infile = sys.argv[1] if len(sys.argv) > 1 else "osm_data_files/campsite_enrichment.json"

url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
if not (url and key):
    sys.exit("Set SUPABASE_URL / SUPABASE_KEY (use: op run --env-file=.env.tpl -- python enrich_campsites.py)")

sb = create_client(url, key)
enrich = json.load(open(infile, encoding="utf-8"))

fs = sb.rpc("get_layer_geojson", {"p_source": SOURCE}).execute().data["features"]
by_osm = {str(f["properties"]["_osm_id"]): f for f in fs if f["properties"].get("_osm_id")}

priced = nolink = missing = 0
for osm_id, vals in enrich.items():
    f = by_osm.get(osm_id)
    if not f:
        print(f"  MISSING in {SOURCE}: osm {osm_id}")
        missing += 1
        continue
    props = {k: v for k, v in f["properties"].items() if k not in ("id", "photos", "custom_data")}
    for k in FIELDS:
        if vals.get(k) is not None:
            props[k] = vals[k]
    props["price_date_extracted"] = DATE
    feature = {"type": "Feature", "geometry": f["geometry"], "properties": props}
    sb.rpc("upsert_osm_feature", {"p_source": SOURCE, "p_feature": feature}).execute()
    if vals.get("min_price") is not None:
        priced += 1
    else:
        nolink += 1

print(f"Done: {priced} priced, {nolink} checked-no-price, {missing} not found "
      f"(of {len(enrich)} entries)")
