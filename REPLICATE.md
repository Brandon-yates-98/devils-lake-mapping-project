# Fork this for your area

The Devil's Lake Mapping Project is an independent, noncommercial community map. If you run
an outdoors community somewhere else, you're welcome to stand up your own copy (see the
license summary in [`README.md`](README.md), noncommercial use is the default *yes*).

This is the **honest, current** process. Today the area- and brand-specific values are
**scattered across several files** rather than a single config; this guide lists every spot
to change. The [Friction & next steps](#friction--next-steps) section at the end proposes how
to make this a one-file edit later.

---

## 1. Prerequisites
- A [Supabase](https://supabase.com) project (free tier is fine).
- A [Mapbox](https://mapbox.com) account + a public token (`pk.…`).
- Python 3.11+ for the data pipeline. Optional: [1Password CLI](https://developer.1password.com/docs/cli/) (`op`) for secrets.

## 2. Secrets

**Client (the deployed site)**, paste your own keys into the two HTML files:
- `docs/index.html`, `mapboxgl.accessToken = '…'` and the Supabase `createClient('<url>', '<anon key>')` (near the top of the `<script>`, ~line 1296–1300).
- `editor.html`, the same Mapbox token + Supabase URL/anon key.

The Supabase **anon** key is safe to ship (Row-Level Security + `supabase_lockdown.sql` protect writes). URL-restrict the Mapbox token to your domain.

**Scripts (the importers)**, read `SUPABASE_URL`, `SUPABASE_KEY` (use the **service_role** key, after lockdown), and `MAPBOX_SCRIPT_TOKEN` from the environment. Copy `.env.tpl` and fill it in, or run via 1Password: `op run --env-file=.env.tpl -- python import_trails.py`.

> ⚠️ `compute_area_hulls.py` currently **hardcodes** the Supabase URL/key inline, swap them (or switch it to env vars) before reuse.

## 3. Area parameters to change

| File | What to change |
|------|----------------|
| `fetch_osm.py` | The bounding box (`SOUTH`/`NORTH`/`EAST`/`WEST`) for trail/POI fetch. |
| `fetch_campsites.py` | `LAT`, `LON`, `RADIUS_M` (campground search center + radius). |
| `import_openbeta.py` | The OpenBeta climbing **area UUID** for your region (find it on openbeta.io / the GraphQL API). |
| `compute_drive_times.py` | `NORTH_SHORE` / `SOUTH_SHORE` anchor coords, your two "drive time to" landmarks (or skip drive times entirely). |
| `migrations/001_template_system.sql` | The seeded `default` experience: `title`, `description`, `initial_center` `[lng,lat]`, `initial_zoom`. |

## 4. Database setup
1. Run `supabase_setup.sql` (base schema).
2. Run the **schema** migrations in order, then `supabase_lockdown.sql` (RLS hardening, run before going live).
3. **Skip / replace the Devil's-Lake data seeds**, these are specific to this area, not reusable schema:
   - `004` campsite drive times, `019`–`023` climbing-area hulls/hierarchy,
   - `026` campsite-site coordinates, `037`–`042` reservation IDs + campground renames,
   - `043` (field rename, keep; it's schema-neutral).
   Everything else (template system, field schema, popup templates, audit log, photo storage, icons) is reusable.

## 5. Import data
Run the pipeline (each needs the script's env/keys):
1. `fetch_osm.py` → `import_trails.py` (trails + POIs from OpenStreetMap).
2. `import_openbeta.py` (climbing routes/boulders/areas from OpenBeta).
3. `fetch_campsites.py` → `enrich_campsites.py` (campgrounds).
4. `compute_*` (drive times, area hulls) as needed.

> The individual **campsite-site** layer (numbered sites within a campground) is the one big manual blocker, it was hand-digitized via `scripts/ocr_*` / `digitize_campground.py` from campground maps. Most areas can skip this and ship campground outlines only.

## 6. Branding
- Replace `docs/icons/_logo_src.png` with your logo, then run `python make_icons.py` to regenerate all sizes.
- Update the visible name (currently "Devil's Lake Mapping Project") in: `docs/index.html` (`<title>`, meta/og, header, loading screen, page-title suffix), `editor.html`, `docs/manifest.webmanifest` (`name`/`description`), `docs/sw.js` (comment + offline page), `docs/404.html`, and the header location pill ("Sauk County, WI").

## 7. Deploy
- GitHub Pages: Settings → Pages → branch `main`, folder `/docs`.
- Confirm the Mapbox token is URL-restricted to your Pages domain.

## Friction & next steps

To make replication a near one-file job (recommended future work, **not** done yet):
- **`docs/config.js`**, a single, git-ignored config (`config.example.js` checked in) holding the brand strings, Mapbox token, Supabase URL/anon key, and map defaults; `index.html` + `editor.html` read from `window.DLMAP_CONFIG` instead of hardcoding. Removes secrets from the HTML and gives one file to edit per deployment.
- **A shared `region` config** for the Python importers (bbox, center, radius, OpenBeta UUID, drive-time anchors) so the importers stop hardcoding area params across five files; fix `compute_area_hulls.py` to use env vars.
- **Separate** the reusable schema migrations from the Devil's-Lake data seeds (e.g. a `seed/devils-lake/` folder) so a fork runs schema + its own seeds cleanly.
