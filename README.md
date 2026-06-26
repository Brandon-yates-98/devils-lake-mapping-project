# Devil's Lake Mapping Project

An installable, offline-capable web map for outdoor recreation around **Devil's Lake / Baraboo / Sauk County, Wisconsin**, trails, climbing, campsites, and points of interest. No app store, no native code: one HTML file, Mapbox GL JS, and Supabase.

This is an **independent community project, maintained by a single developer** and not run for profit, ownership and liability stay with the project itself (see [Independence](#independence)).

**Live map:** https://brandon-yates-98.github.io/devils-lake-mapping-project/

- 📱 Installable on iPhone/Android via *Add to Home Screen*
- 🛰️ Works offline at the trailhead, trails, climbs, POIs, photos, and filters all cached on-device
- 🧗 Climbing from OpenBeta; trails & POIs from OpenStreetMap; county trails from Sauk County GIS; campsite info & live availability from Campflare
- 🧭 Directions hand off to the device's native maps app

## What this project is for

1. **Be a genuinely useful, free resource**, a high-quality, offline-ready map of the Devil's Lake / Sauk County outdoors that anyone can use at the trailhead without a paywall or an account.
2. **Support local businesses**, surface local outdoor businesses (campgrounds, shops, guides, outfitters) and send visitors their way.
3. **Collect community photos & local knowledge**, let the people who actually use these places contribute photos and on-the-ground detail back into the map.
4. **Contribute back to open source**, upstream verifiable facts (campsite locations, trail details) to OpenStreetMap and OpenBeta so the wider commons improves, not just this map.
5. **Keep the public map free**, the public map stays free for everyone, and free to use and adapt for any noncommercial purpose (governments, nonprofits, community, personal). Commercial rights are reserved, leaving room to offer paid custom experiences for businesses in the future.

### Free map; commercial use reserved

The public map is **free**, no ads, paywall, or account, and free to use, adapt, and self-host for any **noncommercial** purpose (governments, nonprofits, community, personal).

**Commercial use is not granted by the license; the project reserves it.** That keeps the door open to offer, **in the future**, hosted **custom branded map experiences** for businesses on a subscription (a private, branded view, chosen layers, custom basemap, embeddable). **No paid offering is active today.** If one launches, governments, nonprofits, and community organizations could still get a custom experience free, at the operator's discretion.

Being featured on the **free public map** is **not for sale** and **not an endorsement**, that's editorial.

Operator model and what counts as noncommercial: [`licensing/PERMITTED-USES.md`](licensing/PERMITTED-USES.md). A draft template for a possible future business subscription: [`licensing/COMMERCIAL-SUBSCRIPTION.md`](licensing/COMMERCIAL-SUBSCRIPTION.md).

### Independence

This is an independent project and is **not affiliated with, operated by, or the responsibility of** onX or the Wisconsin DNR. Its data comes from OpenStreetMap, OpenBeta, Sauk County GIS, Campflare, Google (Street View & place info), and the project's own survey work, and contains **no onX data**.

## License, please read before reusing

This project is **source-available** under a **noncommercial license** (not OSI "open source").

The root [`LICENSE.md`](LICENSE.md) is the **[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)**, alongside the per-layer scaffold in [`licensing/`](licensing/) (code, data/content, trademarks, disclaimer, attribution, community-submission terms). **The copyright holder must be set and the promotion + business terms reviewed by counsel before this is published or relied upon** (see [`licensing/README.md`](licensing/README.md)).

**Plain-English summary** (the license text governs):

> ✅ Running an outdoors community somewhere else? Use it freely for **noncommercial** purposes, copy it, adapt it, build your own community's map from it. Governments, nonprofits, schools, and community groups all qualify. That's why it's published.
>
> 💼 Want it for a **business / commercial** purpose? The license doesn't grant that, the owner reserves commercial rights. A commercial license or a hosted business subscription may be offered in the future ([draft terms](licensing/COMMERCIAL-SUBSCRIPTION.md)); contact the owner.

If you're unsure whether your use qualifies as noncommercial, open an issue or get in touch.

### Data attribution (your obligations, not ours to waive)

The map *software* is ours; the *data* is not. Full list and terms: [`licensing/ATTRIBUTION.md`](licensing/ATTRIBUTION.md).

**Open data (attribute + comply if you reuse):**
- Climbing data © [OpenBeta](https://openbeta.io) contributors, licensed [ODbL](https://opendatacommons.org/licenses/odbl/)
- Trail/POI data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, licensed ODbL
- Sauk County trails © [Sauk County GIS](https://www.co.sauk.wi.us)
- Offline basemap tiles © [OpenTopoMap](https://opentopomap.org) (CC-BY-SA) + OpenStreetMap contributors

**Third-party services (shown under their own terms, not redistributable from here; you'd need your own access):**
- Campsite amenities & live availability via [Campflare](https://campflare.com)
- Street View imagery & place info (ratings/photos) via Google

If you build on this, keep equivalent attribution and comply with each source's license yourself. The license above cannot and does not restrict the underlying open data.

## Repository layout

```
docs/                    ← the deployed site (GitHub Pages serves this folder)
  index.html             ← the public map: app, styles, and logic in one file
  sw.js                  ← service worker: offline caching (never caches Mapbox tiles, TOS)
  manifest.webmanifest   ← PWA manifest
  icons/                 ← app icons (regenerate with make_icons.py)
editor.html              ← admin editor (auth-gated; deliberately NOT deployed)
migrations/              ← Supabase SQL migrations, in order
supabase/functions/      ← edge functions (e.g. campflare-availability, live availability)
licensing/               ← PolyForm Noncommercial license + per-layer terms (counsel-gated)
supabase_setup.sql       ← initial schema
supabase_lockdown.sql    ← pre-deployment security hardening, run before going live
fetch_*.py, import_*.py  ← root data pipeline (OSM, OpenBeta, campsites)
scripts/                 ← scheduled import/enrichment jobs (Sauk County trails, Campflare, Google Places, Street View)
compute_drive_times.py   ← one-time drive-time precompute (Mapbox Directions API)
```

## Running your own

1. Create a [Supabase](https://supabase.com) project; run `supabase_setup.sql`, the `migrations/` in order, then `supabase_lockdown.sql`.
2. Get a [Mapbox](https://mapbox.com) token; URL-restrict it to your domain. Put both keys in `docs/index.html`.
3. Import data: `op run --env-file=.env.tpl -- python import_openbeta.py` (and the other importers). Imports need the `service_role` key; the web app uses only the `anon` key.
4. Serve `docs/` over HTTPS (GitHub Pages: Settings → Pages → branch `main`, folder `/docs`).

**Forking this for another area?** See [`REPLICATE.md`](REPLICATE.md) for the full step-by-step.

Independent, noncommercial community project. Climbing is dangerous, this map is informational and is no substitute for guidebooks, local knowledge, or judgment.
