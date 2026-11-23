/* NUTCADE service worker: lets the app open without a connection.
   The page itself is fetched from the network first, so a new release reaches you right away;
   the saved copy is used only when the network fails or takes longer than a few seconds.
   Requests to mints, Nostr relays and other sites are never touched. */
const CACHE = 'nutcade-v34';   // v34: 1.31.1 clearer wording about the offline signature check; v33: 1.31.0 dollars and euros (USD, EUR and CHF ecash); v32: 1.30.0 wallet sync (NIP-60 subset); v31: 1.29.0 Pay to Blinded Key (NUT-28); v30: 1.28.0 nutzaps (NIP-61); v29: 1.27.0 unclaimed-token reminders; v28: 1.26.0 offline token check (DLEQ, NUT-12); v27: 1.25.0 Content-Security-Policy; v26: 1.24.0 mint reliability from MintRadar (optional); v25: 1.23.1 polish (big balances at 320 px, home line next to NO PLAYS YET, phone backup leftovers); v24: 1.23.0 better backups (password on the backup file, Back up with my phone); v23: 1.22.3 hide unpaid on-chain receive note, price chart Settings link; v22: 1.22.2 security hardening; v21: 1.22.1 new support address; v20: 1.22.0 Send all; v19: 1.21.0 storage safety (save failures, storage use, iPhone Home Screen); v18: 1.20.2 two toast wordings; v17: 1.20.1 small fixes; v16: 1.20.0 Nut Bowl football; v15: 1.19.0 Acorn Links golf; v14: 1.18.0 recent-notes setting; v13: 1.17.1 fixes; v12: 1.17.0 Trust & help (v11: 1.16.0 arrival notices; v10: 1.15.0 printable tokens; v9: 1.14.2; v8: 1.14.1; v7: 1.14.0; v6: 1.13.2; v5: 1.13.1; v4: 1.13.0; v3: 1.12.1; v2: the new home-screen icon, 1.12.0)
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
