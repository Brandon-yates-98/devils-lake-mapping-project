-- ============================================================
-- Devil's Lake Mapping Project, campground popup: group price + drive times into columns
-- Applied via Supabase MCP; recorded for the repo log.
--
-- Wraps the price (+ "prices checked") in .cp-pricecol and the drive-time lines
-- in .cp-drivecol, both inside .cp-summary. Desktop renders them stacked as
-- before (block flow); the mobile bottom sheet lays the two columns side by side
-- (price left, drive times stacked on the right), see #feature-sheet .cp-summary
-- in docs/index.html. Structural change only; popup_css is unchanged.
-- ============================================================

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
      <div class="cp-actions">
        {{#if reservation_url}}<a class="cp-btn cp-btn-primary" href="{{ reservation_url }}" target="_blank" rel="noopener"><i class="fa-solid fa-calendar-check"></i> Reserve</a>{{/if}}
        {{#if website}}<a class="cp-btn cp-btn-ghost" href="{{ website }}" target="_blank" rel="noopener"><i class="fa-solid fa-circle-info"></i> Details</a>{{/if}}
      </div>
      <button class="popup-directions-btn"><i class="fa-solid fa-route"></i> Directions</button>
    </div>
  </div>$tpl$
where slug = 'pois_camping';

select slug, length(popup_template) as tpl_len from layer_templates where slug = 'pois_camping';
