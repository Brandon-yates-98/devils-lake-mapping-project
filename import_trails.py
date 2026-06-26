import json
import os
import sys
from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    sys.exit("Set SUPABASE_URL and SUPABASE_KEY, use: op run --env-file=.env.tpl -- python import_trails.py")

supabase = create_client(url, key)

with open("osm_data_files/trails.geojson", encoding="utf-8") as f:
    geojson = json.load(f)

features = geojson["features"]
print(f"Importing {len(features)} trails...")

success, errors = 0, 0
for i, feature in enumerate(features):
    try:
        supabase.rpc("import_trail", {"feature": feature}).execute()
        success += 1
        if success % 50 == 0:
            print(f"  {success}/{len(features)}...")
    except Exception as e:
        osm_id = feature["properties"].get("_osm_id", "?")
        print(f"  Error on feature {i} (osm_id={osm_id}): {e}")
        errors += 1

print(f"\nDone: {success} imported, {errors} errors")
