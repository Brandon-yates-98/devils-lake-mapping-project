# Attribution & Third-Party Notices (DRAFT)

> ⚠️ **DRAFT, pending review.** Verify each source's current license before
> relying on this list.

This project builds on third-party data and assets. Required credits (also
surfaced in-app):

## Map data
- **OpenStreetMap**, © OpenStreetMap contributors, licensed under **ODbL 1.0**.
  <https://www.openstreetmap.org/copyright>
- **OpenTopoMap** (offline basemap tiles), **CC-BY-SA**.
  <https://opentopomap.org>
- **OpenBeta** (climbing data), © OpenBeta contributors. **Confirm the exact
  data license (CC0 vs. CC-BY-SA / ODbL) before redistribution.**
  <https://openbeta.io>
  - *Provenance:* **all** climbing data, including the Mountain Project
    cross-reference IDs (`mp_id`) used to build the "Mountain Project" popup
    links, came in through the **OpenBeta import**, not from any direct
    Mountain Project scrape. (Mountain Project is owned by onX; the popup link
    is an outbound reference only and reproduces none of its content.)
- **Sauk County GIS**, "Trails and Paths" service (`gis.co.sauk.wi.us`), imported
  as the `sauk_trails` layer. Public county GIS data; credited in-app as
  "Trails © Sauk County GIS". Confirm the county's open-data / redistribution terms,
  especially for the commercial offering.

## Live data services (provider terms apply)
- **Mapbox**, basemap styles, tiles, and Mapbox GL JS. Proprietary; billed per use.
  Attribution shown via the map's attribution control.
- **Google**, Street View (Static/Embed) and Places (ratings/photos) in campsite &
  campground popups. Google Maps Platform terms apply; imagery/content is **display-only**
  (not redistributed or cached beyond terms) and credited in-app ("Street View imagery
  © Google"; "Ratings, reviews & photos by Google").
- **Campflare**, campsite amenities and live availability. **Free only for
  individuals/nonprofits; commercial use requires a paid Campflare license.** Credited
  in-app ("by Campflare").

## Commercial use of this project
Commercial use is reserved for a possible **future** offering
([`COMMERCIAL-SUBSCRIPTION.md`](./COMMERCIAL-SUBSCRIPTION.md)); none is active today.
Before any such offering launches, the operator must hold the necessary **commercial**
licenses for the providers above, in particular a **commercial Campflare license**,
plus Mapbox and Google commercial billing. ODbL data (OpenStreetMap, OpenBeta) and
public county/agency GIS generally permit commercial use of the **produced map** with
attribution; confirm the Wisconsin DNR and Sauk County terms before commercial redistribution.

## Icons
- **Maki** (Mapbox) and **Temaki**, **CC0 1.0** (public domain). Vendored under
  `Icons/vendor/` with details in `Icons/README.md`.
- **Carabiner icon** by narak0rn, Flaticon.
- **Rock icon** by Brad, The Noun Project.

## Source material (not redistributed)
- **Wisconsin DNR** campground map (Quartzite & Northern Lights), used as a
  source to extract **facts** (site numbers/positions) only. The original map
  image is **not** redistributed and is not covered by this project's licenses.
  See the copyright notes; obtain DNR permission before hosting the map itself.

## Not used
- **onX / onX Backcountry**, no onX data, layers, tiles, or scraped content is
  used anywhere in this project. Data comes only from the sources listed above
  and the project's own surveyed/derived facts.

## Software
- **Mapbox GL JS**, **Font Awesome**, **Inter** font, under their respective
  licenses.
