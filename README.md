# Devil's Lake Mapping Project

An installable, offline-capable web map for outdoor recreation around **Devil's Lake / Baraboo / Sauk County, Wisconsin** — trails, climbing, campsites, and points of interest. No app store, no native code: one HTML file, Mapbox GL JS, and Supabase.

This is an **independent community project, maintained by a single developer** and not run for profit — ownership and liability stay with the project itself (see [Independence](#independence)).

**Live map:** https://brandon-yates-98.github.io/devils-lake-mapping-project/

- 📱 Installable on iPhone/Android via *Add to Home Screen*
- 🛰️ Works offline at the trailhead — trails, climbs, POIs, photos, and filters all cached on-device
- 🧗 Climbing data (routes, boulders, areas) from OpenBeta; trails and POIs from OpenStreetMap
- 🧭 Directions hand off to the device's native maps app

## What this project is for

1. **Be a genuinely useful, free resource** — a high-quality, offline-ready map of the Devil's Lake / Sauk County outdoors that anyone can use at the trailhead without a paywall or an account.
2. **Support local businesses** — surface local outdoor businesses (campgrounds, shops, guides, outfitters) and send visitors their way.
3. **Collect community photos & local knowledge** — let the people who actually use these places contribute photos and on-the-ground detail back into the map.
4. **Contribute back to open source** — upstream verifiable facts (campsite locations, trail details) to OpenStreetMap and OpenBeta so the wider commons improves, not just this map.
5. **Give back to the area** — the map is free and stays free; it surfaces local outdoor orgs, and any business that gets value from a custom experience is encouraged (never required) to donate to one directly. The developer takes nothing.

### Not run for money

This project is maintained by a **single developer**, in his spare time, for the love of the area — it isn't a business:

- The map is **free** — no ads, paywall, or account.
- **Custom map experiences** for local businesses or organizations are built at the developer's **own discretion and motivation, free of charge**. Being featured is **not for sale** and **not an endorsement** — it's just one person choosing what to build.
- If a business gets value from one, it's **encouraged (never required)** to give back by donating to a **local outdoor org of its choice** — paid **directly to the org**. The **developer takes nothing**: no wages, fees, or donations, and nothing is routed through the project.

Full operator model and the gift/donation reasoning: [`licensing/PERMITTED-USES.md`](licensing/PERMITTED-USES.md).

### Independence

This is an independent project and is **not affiliated with, operated by, or the responsibility of** onX or the Wisconsin DNR. The map uses only OpenStreetMap, OpenBeta, and original survey data — **no onX data**.

## License — please read before reusing

This project is **source-available** and is **moving to a noncommercial license** (not OSI "open source").

**What's operative today:** the root [`LICENSE.md`](LICENSE.md) — **PolyForm Shield 1.0.0**, which is source-available and permits use *except* building a competing product. The intended end state is the **[PolyForm Noncommercial License 1.0.0](licensing/LICENSE.md)** plus the per-layer scaffold in [`licensing/`](licensing/) (code, data/content, trademarks, disclaimer, attribution, community-submission terms). **Those files are DRAFTS pending legal review and are not yet in force** (see [`licensing/README.md`](licensing/README.md)).

**Plain-English summary of the _intended_ noncommercial license** (the license text governs):

> ✅ Running an outdoors community somewhere else? Use it freely for **noncommercial** purposes — copy it, adapt it, build your own community's map from it. That's why it's published.
>
> ❌ Don't use it for **commercial** purposes — selling access, or operating it for profit or wages.

The project's own custom-experience and donation activities are deliberately structured to stay noncommercial (gifts + voluntary, decoupled donations) — they are **not** a commercial exception. See [`licensing/PERMITTED-USES.md`](licensing/PERMITTED-USES.md).

If you're unsure whether your use qualifies, open an issue or get in touch — permission for genuine noncommercial uses is the default answer.

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
editor.html              ← admin editor (auth-gated; deliberately NOT deployed)
migrations/              ← Supabase SQL migrations, in order
licensing/               ← draft noncommercial license + per-layer terms (pending review)
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

**Forking this for another area?** See [`REPLICATE.md`](REPLICATE.md) for the full step-by-step.

Independent, noncommercial community project. Climbing is dangerous — this map is informational and is no substitute for guidebooks, local knowledge, or judgment.
