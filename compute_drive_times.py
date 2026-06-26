#!/usr/bin/env python3
"""
compute_drive_times.py
Compute driving times from every campsite (pois_camping) to Devil's Lake's
North Shore and South Shore, then emit a SQL migration that:

  1. Writes drive_min_north_shore / drive_min_south_shore (minutes) into each
     osm_geometries row's properties jsonb.
  2. Adds those two fields to the pois_camping layer_templates.field_schema.
  3. Rewrites the pois_camping popup_template (.cp card) to show the drive times.

Routing: Mapbox Directions API (driving profile), one call per
campsite/shore. This is a one-time offline precompute, the public map no
longer does any live routing (it deep-links to the device maps app).

Run:  .venv/Scripts/python.exe compute_drive_times.py
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# ── Config ──────────────────────────────────────────────────────────────────
# The web map's pk. token is URL-restricted, so scripts need their own
# server-side token (MAPBOX_SCRIPT_TOKEN in 1Password).
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON = os.environ.get("SUPABASE_KEY")
MAPBOX_TOKEN = os.environ.get("MAPBOX_SCRIPT_TOKEN")
if not SUPABASE_URL or not SUPABASE_ANON or not MAPBOX_TOKEN:
    sys.exit("Set SUPABASE_URL, SUPABASE_KEY, MAPBOX_SCRIPT_TOKEN, use: "
             "op run --env-file=.env.tpl -- python compute_drive_times.py")

# Devil's Lake shore routing destinations [lng, lat].
NORTH_SHORE = [-89.7295, 43.4288]   # North Shore day-use / beach
SOUTH_SHORE = [-89.7350, 43.4185]   # South Shore beach / park HQ

SOURCE_KEY = "pois_camping"
OUT_SQL = "migrations/004_campsite_drive_times.sql"


# ── Supabase read (anon, RLS-allowed) ───────────────────────────────────────
def fetch_campsites():
    url = f"{SUPABASE_URL}/rest/v1/rpc/get_layer_geojson"
    body = json.dumps({"p_source": SOURCE_KEY}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "apikey": SUPABASE_ANON,
            "Authorization": f"Bearer {SUPABASE_ANON}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


# ── Mapbox Directions (driving) ─────────────────────────────────────────────
def drive_minutes(src_lng, src_lat, dst):
    """Return driving minutes (int) from src to dst, or None if no route."""
    coords = f"{src_lng},{src_lat};{dst[0]},{dst[1]}"
    url = (
        f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords}"
        f"?overview=false&access_token={urllib.parse.quote(MAPBOX_TOKEN)}"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"    ! request failed: {e}", file=sys.stderr)
        return None
    routes = data.get("routes") or []
    if not routes:
        return None
    return round(routes[0]["duration"] / 60.0)


# ── SQL emit ────────────────────────────────────────────────────────────────
# New popup card: the original .cp template plus two drive-time rows. {{#if}}
# guards mean campsites without a computed time simply omit the row.
POPUP_TEMPLATE = """  <div class="cp">
    <div class="cp-head">
      <div class="cp-title">{{ name }}</div>
      <div class="cp-tag"><i class="fa-solid fa-tent"></i> Campground</div>
    </div>
    <div class="cp-body">
      <div class="cp-price">
        <span class="cp-price-amt">${{ min_price }}{{#if max_price}} – ${{ max_price }}{{/if}}</span>
        <span class="cp-price-unit">/ night</span>
      </div>
      {{#if price_date_extracted}}<div class="cp-meta"><i class="fa-solid fa-clock"></i> Prices checked {{ price_date_extracted }}</div>{{/if}}
      {{#if drive_min_north_shore}}<div class="cp-meta"><i class="fa-solid fa-car-side"></i> {{ drive_min_north_shore }} min to North Shore</div>{{/if}}
      {{#if drive_min_south_shore}}<div class="cp-meta"><i class="fa-solid fa-car-side"></i> {{ drive_min_south_shore }} min to South Shore</div>{{/if}}
      <div class="cp-actions">
        {{#if reservation_url}}<a class="cp-btn cp-btn-primary" href="{{ reservation_url }}" target="_blank" rel="noopener"><i class="fa-solid fa-calendar-check"></i> Reserve</a>{{/if}}
        {{#if website}}<a class="cp-btn cp-btn-ghost" href="{{ website }}" target="_blank" rel="noopener"><i class="fa-solid fa-circle-info"></i> Details</a>{{/if}}
      </div>
      <button class="popup-directions-btn"><i class="fa-solid fa-route"></i> Directions</button>
    </div>
  </div>"""

FIELD_SCHEMA_ADD = [
    {"name": "drive_min_north_shore", "type": "number", "label": "Drive to North Shore (min)"},
    {"name": "drive_min_south_shore", "type": "number", "label": "Drive to South Shore (min)"},
]


def sql_str(s):
    """Single-quote a string literal for SQL (double embedded quotes)."""
    return "'" + s.replace("'", "''") + "'"


def build_sql(rows):
    lines = []
    lines.append("-- ============================================================")
    lines.append("-- 004_campsite_drive_times.sql  (generated by compute_drive_times.py)")
    lines.append("-- Driving minutes from each campsite to Devil's Lake N & S shores.")
    lines.append(f"-- North shore dest: {NORTH_SHORE}   South shore dest: {SOUTH_SHORE}")
    lines.append("-- Run in Supabase: Dashboard -> SQL Editor -> New query.")
    lines.append("-- ============================================================")
    lines.append("")
    lines.append("begin;")
    lines.append("")
    lines.append("-- 1. Per-campsite drive times (minutes) -> properties jsonb")
    for r in rows:
        patch = {}
        if r["north"] is not None:
            patch["drive_min_north_shore"] = r["north"]
        if r["south"] is not None:
            patch["drive_min_south_shore"] = r["south"]
        if not patch:
            lines.append(f"  -- id {r['id']} ({r['name']}): no route found, skipped")
            continue
        patch_json = json.dumps(patch, separators=(",", ":"))
        lines.append(
            f"  update osm_geometries set properties = properties || "
            f"{sql_str(patch_json)}::jsonb where id = {r['id']};"
            f"  -- {r['name']}"
        )
    lines.append("")
    lines.append("-- 2. Expose the two fields on the pois_camping template "
                 "(idempotent: strip any prior copies first)")
    add_json = json.dumps(FIELD_SCHEMA_ADD, separators=(",", ":"))
    lines.append("  update layer_templates set field_schema = (")
    lines.append("      select coalesce(jsonb_agg(e), '[]'::jsonb)")
    lines.append("      from jsonb_array_elements(field_schema) e")
    lines.append("      where e->>'name' not in "
                 "('drive_min_north_shore','drive_min_south_shore')")
    lines.append(f"    ) || {sql_str(add_json)}::jsonb")
    lines.append("  where slug = 'pois_camping';")
    lines.append("")
    lines.append("-- 3. Show drive times in the campsite popup card")
    lines.append("  update layer_templates set popup_template = "
                 f"{sql_str(POPUP_TEMPLATE)}")
    lines.append("  where slug = 'pois_camping';")
    lines.append("")
    lines.append("commit;")
    lines.append("")
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print(f"Fetching campsites from {SOURCE_KEY} ...")
    fc = fetch_campsites()
    feats = [f for f in fc.get("features", []) if f.get("geometry")]
    print(f"  {len(feats)} campsites\n")

    rows = []
    for i, f in enumerate(feats, 1):
        props = f["properties"]
        cid = props["id"]
        name = props.get("name") or f"(unnamed #{cid})"
        lng, lat = f["geometry"]["coordinates"][:2]
        north = drive_minutes(lng, lat, NORTH_SHORE)
        south = drive_minutes(lng, lat, SOUTH_SHORE)
        rows.append({"id": cid, "name": name, "north": north, "south": south})
        print(f"  [{i:>2}/{len(feats)}] {name[:38]:<38}  N={north}  S={south}")
        time.sleep(0.12)  # gentle pacing for the Directions API

    sql = build_sql(rows)
    with open(OUT_SQL, "w", encoding="utf-8") as fh:
        fh.write(sql)

    n_ok = sum(1 for r in rows if r["north"] is not None or r["south"] is not None)
    print(f"\nWrote {OUT_SQL}  ({n_ok}/{len(rows)} campsites with at least one route)")
    print("Next: run the migration in the Supabase SQL Editor.")


if __name__ == "__main__":
    main()
