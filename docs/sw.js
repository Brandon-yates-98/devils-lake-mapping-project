/* Apex Adventure Alliance — service worker for the public map.
 *
 * Caching policy:
 *  - App shell (the HTML page, manifest, icons): network-first, cache fallback,
 *    so users always get fresh code online but the app still opens offline.
 *  - CDN libraries & fonts (Mapbox GL JS itself, supabase-js, Font Awesome,
 *    Google Fonts, site logos): cache-first — versioned/immutable URLs.
 *  - Supabase REST reads (experience list, etc.): network-first, cache fallback.
 *  - Supabase Storage (feature photos): cache-first.
 *  - Mapbox APIs (styles, tiles, glyphs, sprites, telemetry): NEVER cached —
 *    persisting Mapbox map content offline is not permitted by their TOS.
 *    Only the GL JS library files under /mapbox-gl-js/ are cached.
 *  - Layer GeoJSON arrives via Supabase RPC (POST), which Cache Storage can't
 *    key — the page persists those to IndexedDB itself (see rpcCached()).
 */

const VERSION = 'v1';
const SHELL = `apex-shell-${VERSION}`;
const CDN = `apex-cdn-${VERSION}`;
const DATA = `apex-data-${VERSION}`;
const MEDIA = `apex-media-${VERSION}`;
const ALL_CACHES = [SHELL, CDN, DATA, MEDIA];

const CDN_PRECACHE = [
  'https://api.mapbox.com/mapbox-gl-js/v3.12.0/mapbox-gl.css',
  'https://api.mapbox.com/mapbox-gl-js/v3.12.0/mapbox-gl.js',
  'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.108.1',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap',
];

const CDN_HOSTS = new Set([
  'cdn.jsdelivr.net',
  'cdnjs.cloudflare.com',
  'fonts.googleapis.com',
  'fonts.gstatic.com',
  'apexadventurealliance.com',
]);

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CDN);
    // no-cors: these are plain <script>/<link> resources; opaque copies are fine
    await Promise.allSettled(
      CDN_PRECACHE.map(url => cache.add(new Request(url, { mode: 'no-cors' })))
    );
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names.filter(n => n.startsWith('apex-') && !ALL_CACHES.includes(n)).map(n => caches.delete(n))
    );
    await self.clients.claim();
  })());
});

async function cacheFirst(cacheName, request) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request, { ignoreVary: true });
  if (hit) return hit;
  const resp = await fetch(request);
  if (resp && (resp.ok || resp.type === 'opaque')) cache.put(request, resp.clone());
  return resp;
}

async function networkFirst(cacheName, request, { ignoreSearch = false } = {}) {
  const cache = await caches.open(cacheName);
  try {
    const resp = await fetch(request);
    if (resp && (resp.ok || resp.type === 'opaque')) cache.put(request, resp.clone());
    return resp;
  } catch (err) {
    const hit = await cache.match(request, { ignoreSearch, ignoreVary: true });
    if (hit) return hit;
    throw err;
  }
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return; // RPC POSTs etc. go straight to network

  const url = new URL(req.url);

  // The page itself — any ?experience= variant falls back to the cached copy
  if (req.mode === 'navigate') {
    event.respondWith(networkFirst(SHELL, req, { ignoreSearch: true }));
    return;
  }

  // Mapbox: cache only the GL JS library; styles/tiles/glyphs stay network-only
  if (url.hostname === 'api.mapbox.com') {
    if (url.pathname.startsWith('/mapbox-gl-js/')) {
      event.respondWith(cacheFirst(CDN, req));
    }
    return;
  }
  if (url.hostname === 'events.mapbox.com') return;

  if (CDN_HOSTS.has(url.hostname)) {
    event.respondWith(cacheFirst(CDN, req));
    return;
  }

  if (url.hostname.endsWith('.supabase.co')) {
    if (url.pathname.startsWith('/storage/')) {
      event.respondWith(cacheFirst(MEDIA, req));
    } else if (url.pathname.startsWith('/rest/')) {
      event.respondWith(networkFirst(DATA, req));
    }
    return;
  }

  // Same-origin assets (manifest, icons)
  if (url.origin === self.location.origin) {
    event.respondWith(networkFirst(SHELL, req));
  }
});
