-- ============================================================
-- Devil's Lake Mapping Project — campground popup: remove the "Google Maps" button
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Drops the Open-in-Google-Maps action from the pois_camping popup. Same template
-- as migration 050 minus the {{#if google_maps_uri}} button. The google_maps_uri
-- property is still cached (harmless); only the button is removed.
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
      </div>
      <button class="popup-directions-btn"><i class="fa-solid fa-route"></i> Directions</button>
      {{#if google_rating}}<div class="cp-attrib">Ratings, reviews &amp; photos powered by Google</div>{{/if}}
    </div>
  </div>$tpl$
where slug = 'pois_camping';
