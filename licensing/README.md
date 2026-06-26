# Licensing (DRAFTS, pending legal review)

> ⚠️ **These files are DRAFTS and are NOT yet operative.** The repository's
> current operative license remains the root `/LICENSE.md` until these are
> reviewed by an attorney and promoted (steps below). Nothing here takes legal
> effect on its own. Placeholders like the copyright-holder name and the
> definition of "qualifying nonprofit" must be confirmed by counsel.

This project is intentionally **noncommercial + source-available** (not OSI
"open source"). Licensing is split by layer because each is a different kind of
work with different obligations:

| Layer | Draft file | License |
|-------|-----------|---------|
| Application code | `LICENSE.md` | PolyForm Noncommercial 1.0.0 + Permitted Uses |
| Operator model & permitted uses | `PERMITTED-USES.md` | Volunteer; no money flows through the operator |
| Original data + content | `DATA-AND-CONTENT-LICENSE.md` | CC BY-NC 4.0 |
| OpenStreetMap-derived data | `DATA-AND-CONTENT-LICENSE.md` | ODbL 1.0 (unavoidable, cannot be NC) |
| Names, logos & independence | `TRADEMARKS.md` | Reserved; **no** rights claimed in AAA marks |
| Independence & liability | `DISCLAIMER.md` | not affiliated w/ AAA, onX, DNR |
| Third-party credits | `ATTRIBUTION.md` | per source (no onX data used) |
| Community uploads (photos, etc.) | `TERMS-OF-SUBMISSION.md` | contributor license grant |

## Why noncommercial (and the trade-off)

A noncommercial restriction is a field-of-use limit, so this is **not** open
source by the OSI definition, and permissive/copyleft licenses (MIT, Apache,
AGPL) cannot be used for the code. The source is still public ("source
available"). Data contributed *upstream* to OpenStreetMap / OpenBeta must go
under **their** commercial-OK terms (ODbL / CC-BY-SA / CC0), that contributed
slice is a deliberate gift and is not bound by our NC terms. Facts (campsite
numbers, positions) are not copyrightable, so upstreaming facts is clean.

## Promotion steps (once counsel approves)

1. Confirm the copyright-holder legal entity throughout, must be **you or a
   separate entity you form** (keep ownership and liability with the project).
2. Use the project name ("Devil's Lake Mapping Project") consistently; surface a
   short `DISCLAIMER.md` in the app footer/About.
3. Confirm the volunteer operator model in `PERMITTED-USES.md` with counsel
   (gift-not-exchange framing; no funds through the operator).
4. Audit data provenance (`ATTRIBUTION.md`): confirm no onX data, and resolve the
   DNR-map source before redistributing the map image itself.
5. Replace the root `/LICENSE.md` (currently PolyForm Shield) with
   `licensing/LICENSE.md`, and delete the old Shield license.
6. Move `DATA-AND-CONTENT-LICENSE.md`, `TRADEMARKS.md`, `DISCLAIMER.md`,
   `ATTRIBUTION.md`, and `TERMS-OF-SUBMISSION.md` to the repo root (or keep here
   and link from the root `README`).
7. Wire `TERMS-OF-SUBMISSION.md` + a privacy policy into the upload flow before
   accepting any community photos.
