/* Devil's Lake Mapping Project, service worker for the public map.
 *
 * Caching policy:
 *  - App shell (the HTML page, manifest, icons): precached at install (so the
 *    app opens offline even on a fresh home-screen install), refreshed
 *    network-first on navigation. Navigations NEVER reject, worst case they
 *    get a friendly offline page; a rejected navigation hangs iOS PWAs on the
 *    splash screen forever.
 *  - CDN libraries & fonts (Mapbox GL JS itself, supabase-js, Font Awesome,
 *    Google Fonts, site logos): cache-first, versioned/immutable URLs.
 *  - Supabase REST reads (experience list, etc.): network-first, cache fallback.
 *  - Supabase Storage (feature photos): cache-first.
 *  - Open-source basemap tiles (OpenTopoMap/OSM): cache-first, "Save offline"
 *    prefetches the experience area; these MAY be cached, unlike Mapbox tiles.
 *  - Mapbox APIs (styles, tiles, glyphs, sprites, telemetry): NEVER cached -
 *    persisting Mapbox map content offline is not permitted by their TOS.
 *    Only the GL JS library files under /mapbox-gl-js/ are cached.
 *  - Layer GeoJSON arrives via Supabase RPC (POST), which Cache Storage can't
 *    key, the page persists those to IndexedDB itself (see rpcCached()).
 */

const VERSION = 'v3';
const SHELL = `dl-shell-${VERSION}`;
const CDN = `dl-cdn-${VERSION}`;
const DATA = `dl-data-${VERSION}`;
const MEDIA = `dl-media-${VERSION}`;
const TILES = `dl-tiles-${VERSION}`;
const ALL_CACHES = [SHELL, CDN, DATA, MEDIA, TILES];

// Canonical cache key for the app shell, the scope directory URL ('/…/').
// Navigations are stored and matched under this single string key; URL-string
// keys avoid WebKit quirks with navigation Request objects, and one key covers
// every ?experience= variant (the HTML is identical).
const SHELL_KEY = self.registration.scope;

const SHELL_PRECACHE = ['./', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-180.png'];

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
]);

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const shell = await caches.open(SHELL);
    // The page itself, stored under the canonical key
    try {
      const resp = await fetch('./', { cache: 'no-cache' });
      if (resp.ok) await shell.put(SHELL_KEY, resp);
    } catch (e) { /* offline install, runtime caching will fill in */ }
    await Promise.allSettled(
      SHELL_PRECACHE.slice(1).map(u => shell.add(u))
    );
    const cdn = await caches.open(CDN);
    // no-cors: these are plain <script>/<link> resources; opaque copies are fine
    await Promise.allSettled(
      CDN_PRECACHE.map(url => cdn.add(new Request(url, { mode: 'no-cors' })))
    );
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names.filter(n => n.startsWith('dl-') && !ALL_CACHES.includes(n)).map(n => caches.delete(n))
    );
    await self.clients.claim();
  })());
});

const OFFLINE_FALLBACK_HTML = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Offline, Devil's Lake Mapping Project</title></head>
<body style="background:#0a140a;color:rgba(255,255,255,0.7);font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;padding:24px">
<div><h2 style="color:#9bc23c">You're offline</h2>
<p>This map hasn't been saved on this device yet.<br>Connect once and tap "Save map for offline use".</p></div>
</body></html>`;

// Navigations must always resolve, a rejected navigation strands the user
// (iOS PWAs hang on the splash screen). Network first, then the precached
// shell, then a friendly offline page.
async function handleNavigation(request) {
  const cache = await caches.open(SHELL);
  try {
    const resp = await fetch(request);
    if (resp && resp.ok) {
      try { await cache.put(SHELL_KEY, resp.clone()); } catch (e) { /* quota/etc, non-fatal */ }
    }
    return resp;
  } catch (err) {
    const hit = await cache.match(SHELL_KEY)
      || await cache.match(request.url, { ignoreSearch: true });
    if (hit) return hit;
    return new Response(OFFLINE_FALLBACK_HTML, { status: 503, headers: { 'Content-Type': 'text/html' } });
  }
}

async function cacheFirst(cacheName, request) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request, { ignoreVary: true });
  if (hit) return hit;
  const resp = await fetch(request);
  if (resp && (resp.ok || resp.type === 'opaque')) {
    try { await cache.put(request, resp.clone()); } catch (e) { /* non-fatal */ }
  }
  return resp;
}

async function networkFirst(cacheName, request) {
  const cache = await caches.open(cacheName);
  try {
    const resp = await fetch(request);
    if (resp && (resp.ok || resp.type === 'opaque')) {
      try { await cache.put(request, resp.clone()); } catch (e) { /* non-fatal */ }
    }
    return resp;
  } catch (err) {
    const hit = await cache.match(request, { ignoreVary: true });
    if (hit) return hit;
    throw err;
  }
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return; // RPC POSTs etc. go straight to network

  const url = new URL(req.url);

  if (req.mode === 'navigate') {
    event.respondWith(handleNavigation(req));
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

  // Open-source basemap tiles (OpenTopoMap/OSM), unlike Mapbox tiles, these
  // may be cached; "Save offline" prefetches the experience area into here.
  if (url.hostname.endsWith('tile.opentopomap.org') || url.hostname === 'tile.openstreetmap.org') {
    event.respondWith(cacheFirst(TILES, req));
    return;
  }

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
