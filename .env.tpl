# 1Password references — run: op run --env-file=.env.tpl -- python import_trails.py
# To find your vault name: op vault list
# NOTE: after supabase_lockdown.sql, import scripts need the service_role key
# (anon can no longer execute the import RPCs) — point this item at it.
SUPABASE_URL=op://Employee/Supabase apex/username
SUPABASE_KEY=op://Employee/Supabase apex/password
# Campflare v2 API key (Authorization header, raw value — no "Bearer").
# Used by scripts/enrich_campsites_campflare.py; the campflare-availability edge
# function reads its own copy from Supabase secrets, not this file.
CAMPFLARE_API_KEY=op://Employee/Campflare api key/password
# Server-side Mapbox token for scripts (the web token is URL-restricted).
# Uncomment when the 1Password item exists (only compute_drive_times.py needs it):
# MAPBOX_SCRIPT_TOKEN=op://Private/dl_mapbox_script/credential
