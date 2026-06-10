# Apex Web Maps

Interactive trail, climbing, and adventure maps by [Apex Adventure Alliance](https://apexadventurealliance.com) — built as an installable, offline-capable web app (PWA). No app store, no native code: one HTML file, Mapbox GL JS, and Supabase.

**Live map:** https://brandon-yates-98.github.io/apex_web_maps/

- 📱 Installable on iPhone/Android via *Add to Home Screen*
- 🛰️ Works offline at the trailhead — trails, climbs, POIs, photos, and filters all cached on-device
- 🧗 Climbing data (routes, boulders, areas) from OpenBeta; trails and POIs from OpenStreetMap
- 🧭 Directions hand off to the device's native maps app

## License — please read before reusing

This project is **source-available** under the [PolyForm Shield License 1.0.0](LICENSE.md).

**Plain-English summary** (the license text governs):

> ✅ You're a climbing or outdoors community somewhere else in the world? Use this freely — copy it, adapt it, build your own community's map from it. That's why it's published.
>
> ❌ You may **not** use it to build or operate a map or guide product that competes with Apex Adventure Alliance's offering — in particular, another map of the **Devil's Lake / Baraboo, Wisconsin area**.

If you're unsure whether your use qualifies, open an issue or get in touch — permission for non-competing uses is the default answer.

### Data attribution (your obligations, not ours to waive)

The map *software* is ours; the *data* is not:

- Climbing data © [OpenBeta](https://openbeta.io) contributors, licensed [ODbL](https://opendatacommons.org/licenses/odbl/)
- Trail/POI data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, licensed ODbL

If you build on this, you must keep equivalent attribution and comply with ODbL yourself. The license above cannot and does not restrict the underlying open data.

## Repository layout

```
docs/                    ← the deployed site (GitHub Pages serves this folder)
  index.html             ← the public map: app, styles, and logic in one file
  sw.js                  ← service worker: offline caching (never caches Mapbox tiles — TOS)
  manifest.webmanifest   ← PWA manifest
  icons/                 ← app icons (regenerate with make_icons.py)
apex_editor.html         ← admin editor (auth-gated; deliberately NOT deployed)
migrations/              ← Supabase SQL migrations, in order
supabase_setup.sql       ← initial schema
supabase_lockdown.sql    ← pre-deployment security hardening — run before going live
fetch_*.py, import_*.py  ← data pipeline (OSM, OpenBeta, campsites)
compute_drive_times.py   ← one-time drive-time precompute (Mapbox Directions API)
```

## Running your own

1. Create a [Supabase](https://supabase.com) project; run `supabase_setup.sql`, the `migrations/` in order, then `supabase_lockdown.sql`.
2. Get a [Mapbox](https://mapbox.com) token; URL-restrict it to your domain. Put both keys in `docs/index.html`.
3. Import data: `op run --env-file=.env.tpl -- python import_openbeta.py` (and the other importers). Imports need the `service_role` key; the web app uses only the `anon` key.
4. Serve `docs/` over HTTPS (GitHub Pages: Settings → Pages → branch `main`, folder `/docs`).

© Apex Adventure Alliance. Climbing is dangerous — this map is informational and is no substitute for guidebooks, local knowledge, or judgment.
