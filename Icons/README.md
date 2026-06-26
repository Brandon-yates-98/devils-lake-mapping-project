# Map marker icons

This project draws every map marker as a **canvas-baked glyph** in `drawMapGlyph()`
(see `editor.html` / `docs/index.html`), not as a Mapbox sprite. This is
deliberate: baked glyphs render offline (PWA roadmap, and Mapbox's TOS forbids
caching their sprite/tiles), draw atomically with their marker disc, and size
consistently regardless of basemap.

So third-party icon sets are used here as **vector path sources**, not runtime
assets: we trace each `<path d="…">` into a `Path2D` inside `drawMapGlyph` (the
same technique `dl-boulder` already uses for `noun-rock-5301957.svg`).

## House standard

For outdoor-recreation markers we standardize on **Maki** (Mapbox) and
**Temaki**, both released under **CC0 1.0** (public domain, no attribution
required, commercial use OK). They share a 15×15 viewBox and a consistent
weight tuned for small map display, which is why they trace cleanly into the
64px glyph canvas. For recreation symbols those sets lack, the **U.S. National
Park Service Map Symbols** (public domain, U.S. federal work) are the fallback.

Climbing glyphs (`dl-carabiner`, `dl-cliff`) stay bespoke, no open set has a
good equivalent. `dl-boulder` traces `noun-rock-5301957.svg` (Noun Project).

## Vendored sources → baked glyph

| Glyph         | Source file                          | Set    | License |
|---------------|--------------------------------------|--------|---------|
| `dl-tent`     | `vendor/maki/campsite.svg`           | Maki   | CC0 1.0 |
| `dl-rv`       | `vendor/temaki/camper_trailer.svg`   | Temaki | CC0 1.0 |
| `dl-parking`  | `vendor/maki/parking.svg`            | Maki   | CC0 1.0 |
| `dl-restroom` | `vendor/maki/toilet.svg`             | Maki   | CC0 1.0 |
| `dl-water`    | `vendor/maki/drinking-water.svg`     | Maki   | CC0 1.0 |

To add or change a recreation glyph: drop the source SVG under `vendor/`, copy
its `d` attribute into a new `dl-*` branch in `drawMapGlyph`, and pick a
center (`cx,cy` in source units) + scale `s` so it sits inside the disc. The
`Icons/vendor/` SVGs are the source of truth, keep the baked path in sync.

## Licenses

- **Maki**, CC0 1.0 Universal. https://github.com/mapbox/maki
- **Temaki**, CC0 1.0 Universal. https://github.com/rapideditor/temaki
- **NPS Map Symbols** (fallback, not yet vendored), U.S. public domain.
  https://www.nps.gov/maps/tools/symbol-library/
- **The Noun Project** (`noun-rock-5301957.svg`), see file for attribution.

CC0 and U.S.-public-domain works require no attribution; this table is recorded
for provenance only.
