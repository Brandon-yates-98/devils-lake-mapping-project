import json
import os
import sys
from pathlib import Path
from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    sys.exit("Set SUPABASE_URL and SUPABASE_KEY — use: op run --env-file=.env.tpl -- python import_geojson.py")

supabase = create_client(url, key)

# Trails already migrated via supabase_migration.sql
SKIP = {'trails'}

# Optional: pass layer names as args to run only specific layers
# e.g.: python import_geojson.py natural roads water
only_layers = set(sys.argv[1:]) if len(sys.argv) > 1 else None

osm_dir = Path("osm_data_files")
for geojson_file in sorted(osm_dir.glob("*.geojson")):
    layer = geojson_file.stem
    if layer in SKIP:
        print(f"Skipping {layer} (migrated via SQL)")
        continue
    if only_layers and layer not in only_layers:
        print(f"Skipping {layer} (not in target list)")
        continue

    with open(geojson_file, encoding="utf-8") as f:
        geojson = json.load(f)

    features = geojson["features"]
    if not features:
        print(f"Skipping {layer} (empty)")
        continue

    print(f"Importing {layer} ({len(features)} features)...")
    success, errors = 0, 0
    for i, feature in enumerate(features):
        try:
            supabase.rpc("import_feature", {"p_source": layer, "feature": feature}).execute()
            success += 1
            if success % 50 == 0:
                print(f"  {success}/{len(features)}...")
        except Exception as e:
            osm_id = feature["properties"].get("_osm_id", "?")
            print(f"  Error on feature {i} (osm_id={osm_id}): {e}")
            errors += 1

    print(f"  Done: {success} imported, {errors} errors\n")

print("All layers imported.")
