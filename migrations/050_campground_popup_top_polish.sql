-- ============================================================
-- Devil's Lake Mapping Project — campground popup: declutter the top + widen
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Builds on 048/049. Changes (template + appended CSS):
--   * Top block decluttered: price + ★rating on one row; "Prices checked" is a
--     small muted line (icon dropped); the two drive times collapse onto ONE
--     line separated by "·" instead of two stacked icon rows.
--   * Popup widened ~20% (262px -> 314px). The host Popup maxWidth was raised to
--     320px in docs/index.html (CSS alone can't widen past that cap).
--   * "N photos" count under the gallery is hidden (.popup-photo-count) in the
--     campground popup.
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
        {{#if price_date_extracted}}<div class="cp-priced">Prices checked {{ price_date_extracted }}</div>{{/if}}
        {{#if drive_min_north_shore}}<div class="cp-drives"><i class="fa-solid fa-car-side"></i> <span>{{ drive_min_north_shore }} min to North Shore{{#if drive_min_south_shore}} · {{ drive_min_south_shore }} min to South Shore{{/if}}</span></div>{{/if}}
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
  .cp { width: 314px; }
  .cp-top { margin-bottom: 6px; }
  .cp-top-row { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 1px; }
  .cp-top-row .cp-price { display: flex; align-items: baseline; gap: 3px; }
  .cp-top-row .cp-rating { margin-top: 0; white-space: nowrap; }
  .cp-priced { font-size: 10px; color: #9aa890; margin: 0 0 5px; }
  .cp-drives { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #5a6a4a; margin: 5px 0; }
  .cp-drives i { color: #7a8a5a; }
  .cp-chips { display: flex; flex-wrap: wrap; gap: 5px; margin: 6px 0 2px; }
  .popup-photo-count { display: none; }
$css$
where slug = 'pois_camping';
