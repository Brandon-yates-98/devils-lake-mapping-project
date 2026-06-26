-- ============================================================
-- Devil's Lake Mapping Project, campground Google Places enrichment
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Adds the read/write plumbing for scripts/enrich_campgrounds_google.py and
-- surfaces the enriched fields in the pois_camping popup.
--
--   * campgrounds_needing_google_enrichment(refresh_days)  -> rows the batch
--     job should (re)fetch: never resolved, or last fetched > refresh_days ago.
--   * apply_campground_google_enrichment(...)              -> merges the Google
--     payload back into properties / photos / photo_meta and stamps the cache
--     control block at custom_data.google = { place_id, fetched_at, status }.
--
-- Both are SECURITY DEFINER so the batch job (service_role) can write through
-- RLS, and EXECUTE is revoked from anon/authenticated so the public anon key
-- gains no write path (see memory: supabase-write-constraints).
--
-- ToS notes baked into the design:
--   * place_id is the only Places field cacheable indefinitely; everything else
--     is treated as a 30-day delete-and-refetch cycle (refresh_days default 30).
--   * Google photo URIs are time-limited, so they MUST be refreshed on that same
--     cycle, storing them long-term is both a ToS and a broken-link problem.
--   * Photo author attribution + "Powered by Google" are rendered in the popup.
-- ============================================================

-- ── 1. Targets the batch job should process ─────────────────────────────────
create or replace function public.campgrounds_needing_google_enrichment(refresh_days int default 30)
returns table (id bigint, name text, lng double precision, lat double precision, place_id text)
language sql
security definer
set search_path = public, extensions
as $fn$
  select
    g.id,
    g.name,
    st_x(st_centroid(g.geometry))::double precision as lng,
    st_y(st_centroid(g.geometry))::double precision as lat,
    nullif(g.custom_data #>> '{google,place_id}', '') as place_id
  from osm_geometries g
  where g.source = 'pois_camping'
    and g.geometry is not null
    and (
      (g.custom_data #>> '{google,fetched_at}') is null
      or (g.custom_data #>> '{google,fetched_at}')::timestamptz < now() - make_interval(days => refresh_days)
    )
  order by g.name;
$fn$;

-- ── 2. Write the Google payload back, merging jsonb server-side ──────────────
-- p_props      : flat google_* keys to merge into properties (rating, description,
--                phone, hours, chips, flattened top-N reviews, maps uri, …).
-- p_photo_meta : Google photos as [{url, caption, source:'google'}] with author
--                attribution in the caption.
-- p_place_id   : resolved Place ID (stored once, kept indefinitely per ToS).
--
-- PHOTOS ARE APPEND-ONLY AND NON-DESTRUCTIVE. Community/editor photos (added by
-- approve_pending_image, untagged) are NEVER overwritten. On each refresh we keep
-- every non-Google entry untouched and replace only Google's own prior, now-stale
-- entries (its photo URIs are time-limited) with the fresh batch. photos[] is kept
-- in sync with photo_meta, which migration 024 defines as the authoritative list.
-- If Google returns no photos (p_photo_meta IS NULL), the gallery is left as-is.
create or replace function public.apply_campground_google_enrichment(
  p_id          bigint,
  p_props       jsonb,
  p_photo_meta  jsonb,
  p_place_id    text
)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $fn$
declare
  v_kept     jsonb;
  v_merged   jsonb;
  v_photos   text[];
begin
  if p_photo_meta is not null then
    -- every existing photo Google did NOT add (no source:'google' tag)
    select coalesce(jsonb_agg(elem), '[]'::jsonb)
      into v_kept
    from osm_geometries g
         cross join lateral jsonb_array_elements(coalesce(g.photo_meta, '[]'::jsonb)) elem
    where g.id = p_id
      and coalesce(elem ->> 'source', '') <> 'google';

    v_merged := v_kept || p_photo_meta;

    select coalesce(array_agg(e ->> 'url'), '{}')
      into v_photos
    from jsonb_array_elements(v_merged) e
    where coalesce(e ->> 'url', '') <> '';
  end if;

  update osm_geometries
  set properties = coalesce(properties, '{}'::jsonb) || coalesce(p_props, '{}'::jsonb),
      photo_meta = case when p_photo_meta is not null then v_merged else photo_meta end,
      photos     = case when p_photo_meta is not null then v_photos else photos end,
      custom_data = jsonb_set(
        coalesce(custom_data, '{}'::jsonb),
        '{google}',
        jsonb_build_object(
          'place_id',   p_place_id,
          'fetched_at', now(),
          'status',     'ok'
        ),
        true
      ),
      updated_at = now()
  where id = p_id and source = 'pois_camping';
end;
$fn$;

-- Only service_role (the batch job) may call these. Revoke from PUBLIC too -
-- functions grant EXECUTE to PUBLIC by default, so revoking from anon/authenticated
-- alone leaves the public path open.
revoke execute on function public.campgrounds_needing_google_enrichment(int) from public, anon, authenticated;
grant  execute on function public.campgrounds_needing_google_enrichment(int) to service_role;
revoke execute on function public.apply_campground_google_enrichment(bigint, jsonb, jsonb, text) from public, anon, authenticated;
grant  execute on function public.apply_campground_google_enrichment(bigint, jsonb, jsonb, text) to service_role;

-- ── 3. Surface the enriched fields in the pois_camping popup ─────────────────
-- Rebuilds the template around the existing summary/actions, adding: rating,
-- description, an amenity chip row, today's hours, phone, top reviews, an
-- "Open in Google Maps" action, and the required Google attribution line.
-- Reviews are pre-flattened by the script into google_review_{1,2,3}_* keys so
-- the template only needs {{#if}} (no {{#each}}).
update layer_templates
set popup_template = $tpl$  <div class="cp">
    <div class="cp-head">
      <div class="cp-title">{{ name }}</div>
      <div class="cp-tag"><i class="fa-solid fa-tent"></i> Campground</div>
    </div>
    <div class="cp-body">
      <div class="cp-summary">
        <div class="cp-pricecol">
          <div class="cp-price">
            <span class="cp-price-amt">${{ min_price }}{{#if max_price}} – ${{ max_price }}{{/if}}</span>
            <span class="cp-price-unit">/ night</span>
          </div>
          {{#if price_date_extracted}}<div class="cp-meta"><i class="fa-solid fa-clock"></i> Prices checked {{ price_date_extracted }}</div>{{/if}}
        </div>
        {{#if drive_min_north_shore}}<div class="cp-drivecol">
          <div class="cp-meta"><i class="fa-solid fa-car-side"></i> {{ drive_min_north_shore }} min to North Shore</div>
          {{#if drive_min_south_shore}}<div class="cp-meta"><i class="fa-solid fa-car-side"></i> {{ drive_min_south_shore }} min to South Shore</div>{{/if}}
        </div>{{/if}}
      </div>
      {{#if google_rating}}<div class="cp-rating"><span class="cp-stars">★ {{ google_rating }}</span>{{#if google_rating_count}} <span class="cp-rating-count">({{ google_rating_count }} reviews)</span>{{/if}}</div>{{/if}}
      {{#if google_description}}<p class="cp-desc">{{ google_description }}</p>{{/if}}
      {{#if google_hours_today}}<div class="cp-meta"><i class="fa-solid fa-clock"></i> {{ google_hours_today }}</div>{{/if}}
      {{#if google_phone}}<div class="cp-meta"><i class="fa-solid fa-phone"></i> <a href="tel:{{ google_phone }}">{{ google_phone }}</a></div>{{/if}}
      <div class="cp-chips">
        {{#if google_wheelchair}}<span class="cp-chip"><i class="fa-solid fa-wheelchair"></i> Accessible</span>{{/if}}
        {{#if google_allows_dogs}}<span class="cp-chip"><i class="fa-solid fa-dog"></i> Dogs OK</span>{{/if}}
        {{#if google_restroom}}<span class="cp-chip"><i class="fa-solid fa-restroom"></i> Restroom</span>{{/if}}
        {{#if google_good_for_children}}<span class="cp-chip"><i class="fa-solid fa-child"></i> Family</span>{{/if}}
      </div>
      {{#if google_review_1_text}}<div class="cp-reviews">
        <div class="cp-reviews-head">Recent reviews</div>
        <div class="cp-review"><div class="cp-review-meta">★ {{ google_review_1_rating }} · {{ google_review_1_author }}</div><div class="cp-review-text">{{ google_review_1_text }}</div></div>
        {{#if google_review_2_text}}<div class="cp-review"><div class="cp-review-meta">★ {{ google_review_2_rating }} · {{ google_review_2_author }}</div><div class="cp-review-text">{{ google_review_2_text }}</div></div>{{/if}}
        {{#if google_review_3_text}}<div class="cp-review"><div class="cp-review-meta">★ {{ google_review_3_rating }} · {{ google_review_3_author }}</div><div class="cp-review-text">{{ google_review_3_text }}</div></div>{{/if}}
      </div>{{/if}}
      <div class="cp-actions">
        {{#if reservation_url}}<a class="cp-btn cp-btn-primary" href="{{ reservation_url }}" target="_blank" rel="noopener"><i class="fa-solid fa-calendar-check"></i> Reserve</a>{{/if}}
        {{#if website}}<a class="cp-btn cp-btn-ghost" href="{{ website }}" target="_blank" rel="noopener"><i class="fa-solid fa-circle-info"></i> Details</a>{{/if}}
        {{#if google_maps_uri}}<a class="cp-btn cp-btn-ghost" href="{{ google_maps_uri }}" target="_blank" rel="noopener"><i class="fa-brands fa-google"></i> Google Maps</a>{{/if}}
      </div>
      <button class="popup-directions-btn"><i class="fa-solid fa-route"></i> Directions</button>
      {{#if google_rating}}<div class="cp-attrib">Ratings, reviews &amp; photos powered by Google</div>{{/if}}
    </div>
  </div>$tpl$
where slug = 'pois_camping';

-- Append the styles for the new blocks (append, so existing popup_css is kept).
update layer_templates
set popup_css = coalesce(popup_css, '') || $css$
  .cp-rating { margin-top: 6px; font-size: 13px; }
  .cp-rating .cp-stars { color: #e0a92e; font-weight: 800; }
  .cp-rating .cp-rating-count { color: #7a8a5a; font-size: 11.5px; }
  .cp-desc { margin: 7px 0 4px; font-size: 12.5px; line-height: 1.45; color: #3a463a; }
  .cp-chips { display: flex; flex-wrap: wrap; gap: 5px; margin: 6px 0; }
  .cp-chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
    border-radius: 999px; background: #eef3e6; color: #4a5a3a; font-size: 10.5px; font-weight: 700; }
  .cp-reviews { margin-top: 8px; border-top: 1px solid #eee; padding-top: 6px; }
  .cp-reviews-head { font-size: 9.5px; font-weight: 800; letter-spacing: 1.1px;
    text-transform: uppercase; color: #7a8a5a; margin-bottom: 5px; }
  .cp-review { margin-bottom: 6px; }
  .cp-review-meta { font-size: 11px; font-weight: 700; color: #4a5a3a; }
  .cp-review-text { font-size: 11.5px; line-height: 1.4; color: #555; }
  .cp-attrib { margin-top: 6px; font-size: 9.5px; color: #9aa890; text-align: center; }
$css$
where slug = 'pois_camping';

select slug, length(popup_template) as tpl_len, length(popup_css) as css_len
from layer_templates where slug = 'pois_camping';
