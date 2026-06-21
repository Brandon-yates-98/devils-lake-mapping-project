-- ============================================================
-- Devil's Lake Mapping Project — campground popup: compact header + collapsible reviews
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Builds on migration 048. Changes:
--   * Compact, coherent top block: price and ★rating share one row; "prices
--     checked", drive times, and amenity chips stack tightly beneath.
--   * Recent reviews are now a native <details> (collapsed by default) with a
--     scrollable body, so long review text no longer stretches the popup.
--   * Adds a <!--DL_PHOTOS--> marker where docs/index.html injects the photo
--     gallery (custom templates can't emit the lightbox data attributes, so the
--     gallery is built host-side and slotted in here).
-- CSS is appended (later rules win); the dead cp-summary/cp-pricecol/cp-drivecol
-- rules from 040/048 are harmless.
-- ============================================================

update layer_templates
set popup_template = $tpl$  <div class="cp">
    <div class="cp-head">
      <div class="cp-title">{{ name }}</div>
      <div class="cp-tag"><i class="fa-solid fa-tent"></i> Campground</div>
    </div>
    <div class="cp-body">
      <div class="cp-top">
        <div class="cp-top-row">
          <div class="cp-price">
            <span class="cp-price-amt">${{ min_price }}{{#if max_price}}–${{ max_price }}{{/if}}</span>
            <span class="cp-price-unit">/ night</span>
          </div>
          {{#if google_rating}}<div class="cp-rating"><span class="cp-stars">★ {{ google_rating }}</span>{{#if google_rating_count}} <span class="cp-rating-count">({{ google_rating_count }} reviews)</span>{{/if}}</div>{{/if}}
        </div>
        {{#if price_date_extracted}}<div class="cp-meta"><i class="fa-solid fa-clock"></i> Prices checked {{ price_date_extracted }}</div>{{/if}}
        {{#if drive_min_north_shore}}<div class="cp-drives">
          <span class="cp-drive"><i class="fa-solid fa-car-side"></i> {{ drive_min_north_shore }} min to North Shore</span>
          {{#if drive_min_south_shore}}<span class="cp-drive"><i class="fa-solid fa-car-side"></i> {{ drive_min_south_shore }} min to South Shore</span>{{/if}}
        </div>{{/if}}
        <div class="cp-chips">
          {{#if google_wheelchair}}<span class="cp-chip"><i class="fa-solid fa-wheelchair"></i> Accessible</span>{{/if}}
          {{#if google_allows_dogs}}<span class="cp-chip"><i class="fa-solid fa-dog"></i> Dogs OK</span>{{/if}}
          {{#if google_restroom}}<span class="cp-chip"><i class="fa-solid fa-restroom"></i> Restroom</span>{{/if}}
          {{#if google_good_for_children}}<span class="cp-chip"><i class="fa-solid fa-child"></i> Family</span>{{/if}}
        </div>
      </div>
      <!--DL_PHOTOS-->
      {{#if google_description}}<p class="cp-desc">{{ google_description }}</p>{{/if}}
      {{#if google_hours_today}}<div class="cp-meta"><i class="fa-solid fa-clock"></i> {{ google_hours_today }}</div>{{/if}}
      {{#if google_phone}}<div class="cp-meta"><i class="fa-solid fa-phone"></i> <a href="tel:{{ google_phone }}">{{ google_phone }}</a></div>{{/if}}
      {{#if google_review_1_text}}<details class="cp-reviews">
        <summary class="cp-reviews-sum">Recent reviews</summary>
        <div class="cp-reviews-scroll">
          <div class="cp-review"><div class="cp-review-meta">★ {{ google_review_1_rating }} · {{ google_review_1_author }}</div><div class="cp-review-text">{{ google_review_1_text }}</div></div>
          {{#if google_review_2_text}}<div class="cp-review"><div class="cp-review-meta">★ {{ google_review_2_rating }} · {{ google_review_2_author }}</div><div class="cp-review-text">{{ google_review_2_text }}</div></div>{{/if}}
          {{#if google_review_3_text}}<div class="cp-review"><div class="cp-review-meta">★ {{ google_review_3_rating }} · {{ google_review_3_author }}</div><div class="cp-review-text">{{ google_review_3_text }}</div></div>{{/if}}
        </div>
      </details>{{/if}}
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

update layer_templates
set popup_css = coalesce(popup_css, '') || $css$
  .cp-top { margin-bottom: 4px; }
  .cp-top-row { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
  .cp-top-row .cp-price { display: flex; align-items: baseline; gap: 3px; }
  .cp-top-row .cp-rating { margin-top: 0; white-space: nowrap; }
  .cp-drives { display: flex; flex-wrap: wrap; gap: 2px 12px; margin: 3px 0; }
  .cp-drive { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: #5a6a4a; }
  .cp-reviews { margin-top: 8px; border-top: 1px solid #eee; padding-top: 6px; }
  .cp-reviews summary { cursor: pointer; list-style: revert; outline: none; }
  .cp-reviews-sum { font-size: 9.5px; font-weight: 800; letter-spacing: 1.1px; text-transform: uppercase; color: #7a8a5a; }
  .cp-reviews-scroll { max-height: 150px; overflow-y: auto; margin-top: 6px; padding-right: 4px; }
$css$
where slug = 'pois_camping';
