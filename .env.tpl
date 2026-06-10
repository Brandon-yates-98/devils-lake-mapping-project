# 1Password references — run: op run --env-file=.env.tpl -- python import_trails.py
# To find your vault name: op vault list
# NOTE: after supabase_lockdown.sql, import scripts need the service_role key
# (anon can no longer execute the import RPCs) — point this item at it.
SUPABASE_URL=op://Private/apex_supabase/username
SUPABASE_KEY=op://Private/apex_supabase/password
# Server-side Mapbox token for scripts (the web token is URL-restricted)
MAPBOX_SCRIPT_TOKEN=op://Private/apex_mapbox_script/credential
