/* NUTCADE service worker: lets the app open without a connection.
   The page itself is fetched from the network first, so a new release reaches you right away;
   the saved copy is used only when the network fails or takes longer than a few seconds.
   Requests to mints, Nostr relays and other sites are never touched. */
const CACHE = 'nutcade-v14';   // v14: 1.18.0 recent-notes setting; v13: 1.17.1 fixes; v12: 1.17.0 Trust & help (v11: 1.16.0 arrival notices; v10: 1.15.0 printable tokens; v9: 1.14.2; v8: 1.14.1; v7: 1.14.0; v6: 1.13.2; v5: 1.13.1; v4: 1.13.0; v3: 1.12.1; v2: the new home-screen icon, 1.12.0)
const CORE = ['./', './index.html', './zxing_reader.wasm', './manifest.webmanifest', './favicon.svg', './favicon-32.png', './apple-touch-icon.png', './icon-192.png', './icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
const timeout = (p, ms) => new Promise((res, rej) => { const t = setTimeout(() => rej(new Error('timeout')), ms); p.then(v => { clearTimeout(t); res(v); }, e => { clearTimeout(t); rej(e); }); });
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const isPage = req.mode === 'navigate' || /\/(index\.html)?$/.test(url.pathname);
  if (isPage) {
    e.respondWith((async () => {
      const cache = await caches.open(CACHE);
      try {
        const res = await timeout(fetch(req, { cache: 'no-store' }), 6000);
        if (res && res.ok) cache.put('./index.html', res.clone());
        return res;
      } catch (err) {
        return (await cache.match('./index.html')) || (await cache.match('./')) || Response.error();
      }
    })());
    return;
  }
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const hit = await cache.match(req, { ignoreSearch: true });
    const net = fetch(req).then(res => { if (res && res.ok && CORE.some(c => url.pathname.endsWith(c.slice(1)))) cache.put(req, res.clone()); return res; });
    if (hit) { net.catch(() => {}); return hit; }
    return net;
  })());
});
// A notice that money arrived (shown by the open page, never pushed from a server): tapping it brings NUTCADE forward.
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => { const c = cs.find(x => 'focus' in x); return c ? c.focus() : self.clients.openWindow('./'); }));
});
