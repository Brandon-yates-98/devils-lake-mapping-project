# Restoring the Apex Adventure Alliance branding

In June 2026 the public map was rebranded to **"Devil's Lake Community Map"**
and all Apex references were removed from `docs/` (visible branding, logos,
PWA identity, and internal identifiers). This folder preserves everything
needed to put the Apex branding back.

The editor (`apex_editor.html`) was rebranded as well: its `<title>`
(`Map Editor — Apex Adventure Alliance`), login modal (rope-logo +
`APEX ADVENTURE ALLIANCE`), header (`#apex-header`, rope-logo,
`Apex Adventure Alliance` org line), loading logo, and sidebar footer logo
(`ApexPrimaryLogoFinal-271x300.png`) all match the public-map changes in the
tables below — the editor now points its logo slots at
`docs/icons/logo-mark.png` (relative path from the repo root).

## What changed (new → old)

### Visible branding — `docs/index.html`
| Where | Devil's Lake value | Apex value |
|---|---|---|
| `<title>` | `Devil's Lake Community Map` | `Apex Adventure Alliance — Trail Map` |
| `meta description` | "Interactive community map of Devil's Lake — trails, climbing, camping, and more. …" | "Interactive trail, climbing, and adventure maps by Apex Adventure Alliance. Works offline — save the map and take it to the crag." |
| `og:title` | `Devil's Lake Community Map` | `Apex Adventure Alliance — Trail Maps` |
| `og:image` | `icons/icon-512.png` | `https://apexadventurealliance.com/wp-content/uploads/2025/04/ApexPrimaryLogoFinal-271x300.png` |
| `apple-mobile-web-app-title` | `Devil's Lake Map` | `Apex Maps` |
| header logo `src` | `icons/logo-mark.png` | `https://apexadventurealliance.com/wp-content/uploads/2023/07/cropped-rope-logo-1.png` |
| header `.header-org` text | `Devil's Lake Community Map` | `Apex Adventure Alliance` |
| loading screen logo + `.loading-title` | `icons/logo-mark.png` / `Devil's Lake Community Map` | rope-logo URL above / `Apex Adventure Alliance` |
| sidebar `.panel-footer-logo` | `icons/logo-mark.png` | `https://apexadventurealliance.com/wp-content/uploads/2025/04/ApexPrimaryLogoFinal-271x300.png` |
| sidebar `.panel-footer-tagline` | `Devil's Lake Community Map` | `Wisconsin Climbing Guides` |
| `document.title` template | `` `${exp.title} — Devil's Lake Community Map` `` | `` `${exp.title} — Apex Adventure Alliance` `` |

### Visible branding — other files
- `docs/manifest.webmanifest`: name `Devil's Lake Community Map` (was
  `Apex Adventure Alliance — Trail Maps`), short_name `Devil's Lake Map`
  (was `Apex Maps`), description reworded.
- `docs/404.html` `<title>`: was `Apex Adventure Alliance — Page not found`.
- `docs/sw.js` header comment and the offline fallback page `<title>`
  (was `Offline — Apex Maps`).

### Icons / logos
- `docs/icons/icon-512.png`, `icon-192.png`, `icon-180.png` were replaced
  with a generated bluff-over-waves mark. **The original Apex icons are in
  [`icons/`](icons/) next to this README** — copy them back over
  `docs/icons/` to restore.
- `docs/icons/logo-mark.png` is new (transparent header/loading logo);
  the Apex layout hotlinked logos from `apexadventurealliance.com` instead
  (URLs in the table above). Delete `logo-mark.png` when restoring.

### Internal identifiers (renamed in `docs/index.html` AND `apex_editor.html`)
| New | Old |
|---|---|
| `#site-header` (public map CSS/markup id) | `#apex-header` |
| `.dl-popup-custom` (popup wrapper class, both files) | `.apex-popup-custom` |
| `.popup-custom-desc*` (popup description classes) | `.popup-apex-desc*` |
| `dl-offline` (IndexedDB database name) | `apex-offline` |
| `dl-shell-…`, `dl-cdn-…`, `dl-data-…`, `dl-media-…`, `dl-tiles-…` (sw.js cache names; `index.html` also opens `dl-shell-v2` directly) | `apex-shell-…` etc. |
| `dl-carabiner`, `dl-boulder`, `dl-cliff` (canvas glyph ids; `drawMapGlyph()` and the `baked = …indexOf('dl-')` checks in both files) | `apex-carabiner`, `apex-boulder`, `apex-cliff` |

The sw.js `activate` handler currently deletes caches starting with `dl-`
**or** `apex-` (the latter clears pre-rebrand caches). When restoring, swap
the prefixes back and keep the same trick in reverse so stale `dl-*` caches
get cleaned up. `CDN_HOSTS` in sw.js also dropped `apexadventurealliance.com`
(no more hotlinked logos) — re-add it if the logo URLs come back.

### Database (Supabase)
Migration `migrations/018_rename_apex_glyphs.sql` renamed the marker glyph
ids in `layer_templates.default_style`. To restore, run in the SQL Editor:

```sql
update layer_templates
set default_style = default_style || '{"icon": "apex-carabiner"}'::jsonb
where default_style->>'icon' = 'dl-carabiner';

update layer_templates
set default_style = default_style || '{"icon": "apex-boulder"}'::jsonb
where default_style->>'icon' = 'dl-boulder';

update layer_templates
set default_style = default_style || '{"icon": "apex-cliff"}'::jsonb
where default_style->>'icon' = 'dl-cliff';
```

(Only restore these together with the code rename — the glyph ids in the DB
must match the `drawMapGlyph()` branch names in both HTML files.)

## Deliberate exceptions (apex references that remain)
- `custom_data.apex_description` — a data field key present on thousands of
  `osm_geometries` rows; both the popup renderer and the editor's edit form
  read/write it. Renaming it is a data migration touching the importers
  (`import_openbeta.py` etc.), not a branding change.
- `apex_editor.html` — the file name itself (renaming it would break
  bookmarks/launch habits; its page branding IS rebranded).
- Historical migration files under `migrations/` mention apex glyph names in
  comments; they document history and were not rewritten.
- The git repo name/folder `Apex_Web_Maps`.
