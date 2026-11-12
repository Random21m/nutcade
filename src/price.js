/* NUTCADE live Bitcoin price chart (Coinbase Exchange REST candles + websocket ticker) */
(function () {
  'use strict';
  const API = 'https://api.exchange.coinbase.com';
  const RANGES = {
    '1H': { g: 60, span: 3600 },
    '1D': { g: 300, span: 86400 },
    '1W': { g: 3600, span: 7 * 86400 },
    '1M': { g: 21600, span: 30 * 86400 },
    '1Y': { g: 86400, span: 365 * 86400 }
  };
  const prefs = () => window.NutPrefs || {};
  const store = window.NutStore || { get: (k, d) => d, set() {} };
  const st = { range: store.get('priceRange', '1D'), pts: [], cur: null, key: '', loading: false, err: null, live: false, last: null, at: 0, hover: null, el: null };
  const cache = {};
  let ws = null, wsCur = null, wsRetry = 0, drawQueued = false, refreshTimer = null;

  const fmtMoney = (v, cur, dp) => v == null ? '—' : v.toLocaleString(undefined, { style: 'currency', currency: cur, maximumFractionDigits: dp ?? (v >= 1000 ? 0 : 2), minimumFractionDigits: dp ?? 0 });
  const tok = n => getComputedStyle(document.body).getPropertyValue('--' + n).trim() || '#fff';
  const pairFor = () => (prefs().currency || 'USD').toUpperCase();

  async function candles(cur, g, start, end) {
    const u = `${API}/products/BTC-${cur}/candles?granularity=${g}&start=${new Date(start * 1000).toISOString()}&end=${new Date(end * 1000).toISOString()}`;
    const r = await fetch(u);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json();
    if (!Array.isArray(j)) throw new Error('bad data');
    return j.map(c => ({ t: c[0], v: c[4] }));
  }
  async function load(force) {
    const R = RANGES[st.range]; let cur = pairFor();
    const key = cur + st.range;
    if (!force && cache[key] && Date.now() - cache[key].at < 60e3) { Object.assign(st, { pts: cache[key].pts, cur: cache[key].cur, key, err: null }); paint(); return; }
    st.loading = true; paint();
    const end = Math.floor(Date.now() / 1000), start = end - R.span;
    try {
      let pts;
      const get = async c => {
        if (R.span / R.g <= 300) return candles(c, R.g, start, end);
        const mid = end - 300 * R.g; // Coinbase returns at most 300 candles per request
        const [a, b] = await Promise.all([candles(c, R.g, mid, end), candles(c, R.g, start, mid)]);
        return a.concat(b);
      };
      try { pts = await get(cur); } catch (e) { if (cur !== 'USD') { cur = 'USD'; pts = await get('USD'); } else throw e; }
      const seen = new Set(); pts = pts.filter(p => !seen.has(p.t) && seen.add(p.t)).sort((a, b) => a.t - b.t);
      if (!pts.length) throw new Error('empty');
      cache[cur + st.range] = { pts, cur, at: Date.now() };
      Object.assign(st, { pts, cur, key: cur + st.range, err: null });
      if (st.last == null || st.cur !== wsCur) st.last = pts[pts.length - 1].v;
      connect(cur);
    } catch (e) {
      st.err = "Couldn't load the price. Check your connection.";
    }
    st.loading = false; paint();
  }

  function connect(cur) {
    if (ws && wsCur === cur && ws.readyState <= 1) return;
    try { if (ws) ws.close(); } catch (e) {}
    wsCur = cur; st.live = false;
    try { ws = new WebSocket('wss://ws-feed.exchange.coinbase.com'); } catch (e) { ws = null; return; }
    ws.onopen = () => { wsRetry = 0; ws.send(JSON.stringify({ type: 'subscribe', product_ids: ['BTC-' + cur], channels: ['ticker'] })); };
    ws.onmessage = e => {
      let m; try { m = JSON.parse(e.data); } catch (x) { return; }
      if (m.type !== 'ticker' || m.product_id !== 'BTC-' + wsCur) return;
      const v = parseFloat(m.price); if (!(v > 0)) return;
      st.live = true; st.last = v; st.at = Date.now();
      if (st.cur === wsCur && st.pts.length) {
        const t = Math.floor(Date.parse(m.time) / 1000), g = RANGES[st.range].g, lastP = st.pts[st.pts.length - 1];
        if (t >= lastP.t + g) st.pts.push({ t: lastP.t + g, v }); else lastP.v = v;
      }
      if (window.Nutcade && window.Nutcade.livePrice) window.Nutcade.livePrice(v, wsCur);
      queue();
    };
    ws.onclose = () => { st.live = false; ws = null; queue(); if (prefs().fiat && !document.hidden) setTimeout(() => { if (!ws && st.el && st.el.isConnected) connect(wsCur); }, Math.min(30000, 2000 * 2 ** wsRetry++)); };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  }
  function disconnect() { try { if (ws) { ws.onclose = null; ws.close(); } } catch (e) {} ws = null; st.live = false; }
  document.addEventListener('visibilitychange', () => { if (document.hidden) disconnect(); else if (st.el && st.el.isConnected && prefs().fiat) { connect(st.cur || pairFor()); load(true); } });

  const queue = () => { if (drawQueued) return; drawQueued = true; requestAnimationFrame(() => { drawQueued = false; paint(); }); };

  function shell(el) {
    el.innerHTML = `<div class="panel pc">
      <div class="row between" style="align-items:flex-start;gap:8px">
        <div style="min-width:0"><div class="row" style="gap:8px"><span class="h2">BTC / <span data-pc="cur">USD</span></span><span class="pc-live" data-pc="live"></span></div>
          <div class="pc-price" data-pc="price" aria-live="polite">—</div>
          <div class="pc-chg" data-pc="chg"></div></div>
      </div>
      <div class="seg pc-seg" role="group" aria-label="Time range">${Object.keys(RANGES).map(k => `<button type="button" data-range="${k}" aria-pressed="${k === st.range}">${k}</button>`).join('')}</div>
      <div class="pc-wrap"><canvas class="pc-canvas" tabindex="0" role="img" aria-label="Bitcoin price chart"></canvas><div class="pc-tip" hidden></div><div class="pc-msg" data-pc="msg" hidden></div></div>
      <div class="th pc-src">Prices from Coinbase · <button class="linkbtn" data-act="tab" data-tab="settings" style="font-size:inherit;padding:0">turn off in Settings</button></div>
    </div>`;
    el.querySelectorAll('[data-range]').forEach(b => b.onclick = () => {
      st.range = b.dataset.range; store.set('priceRange', st.range); st.hover = null;
      el.querySelectorAll('[data-range]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
      window.NutAudio && window.NutAudio.sfx('blip'); load();
    });
    const cv = el.querySelector('canvas');
    const pick = e => { const r = cv.getBoundingClientRect(); const x = (e.clientX - r.left) / r.width; st.hover = Math.max(0, Math.min(st.pts.length - 1, Math.round(x * (st.pts.length - 1)))); queue(); };
    cv.addEventListener('pointermove', pick);
    cv.addEventListener('pointerdown', e => { pick(e); });
    cv.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') { st.hover = null; queue(); } });
    cv.addEventListener('keydown', e => {
      if (!st.pts.length) return;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); const n = st.pts.length - 1; st.hover = Math.max(0, Math.min(n, (st.hover ?? n) + (e.key === 'ArrowRight' ? 1 : -1) * (e.shiftKey ? 10 : 1))); queue(); }
      if (e.key === 'Escape') { st.hover = null; queue(); }
    });
    cv.addEventListener('blur', () => { st.hover = null; queue(); });
    new ResizeObserver(() => queue()).observe(cv);
  }
  function offShell(el) {
    el.innerHTML = `<div class="panel pc"><div class="row between"><span class="h2">BTC price</span><button class="btn sm" data-act="priceOn">Show price</button></div>
      <div class="th">The live Bitcoin price chart is off. Turning it on fetches prices from coinbase.com.</div></div>`;
    const b = el.querySelector('[data-act=priceOn]'); b.onclick = e => { e.stopPropagation(); const p = prefs(); p.fiat = true; store.set('prefs', p); window.Nutcade && window.Nutcade.refresh(); };
  }

  function timeLabel(t, range) {
    const d = new Date(t * 1000);
    if (range === '1H' || range === '1D') return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    if (range === '1W') return d.toLocaleString(undefined, { weekday: 'short', hour: 'numeric' });
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: range === '1Y' ? '2-digit' : undefined });
  }

  function paint() {
    const el = st.el; if (!el || !el.isConnected || !el.querySelector('.pc-canvas')) return;
    const q = s => el.querySelector(`[data-pc="${s}"]`);
    const cur = st.cur || pairFor();
    q('cur').textContent = cur;
    const live = q('live'); live.textContent = st.live ? '● LIVE' : ''; live.className = 'pc-live' + (st.live ? ' on' : '');
    const pts = st.pts, last = st.last ?? (pts.length ? pts[pts.length - 1].v : null);
    q('price').textContent = fmtMoney(last, cur);
    const chg = q('chg');
    if (pts.length && last != null) {
      const first = pts[0].v, d = last - first, pct = d / first * 100, up = d >= 0;
      chg.textContent = `${up ? '▲' : '▼'} ${up ? "+" : "−"}${fmtMoney(Math.abs(d), cur, 0)} (${up ? '+' : '−'}${Math.abs(pct).toFixed(2)}%) · ${st.range}`;
      chg.className = 'pc-chg ' + (up ? 'up' : 'down');
    } else chg.textContent = '';
    const msg = q('msg');
    msg.hidden = !(st.err || (st.loading && !pts.length));
    msg.textContent = st.err || 'LOADING…';
    el.querySelector('.pc-wrap').style.opacity = st.loading && pts.length ? '.55' : '1';
    draw(el.querySelector('canvas'), el.querySelector('.pc-tip'), cur);
  }

  function draw(cv, tip, cur) {
    const pts = st.pts; const r = cv.getBoundingClientRect(); if (!r.width) return;
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    const W = Math.round(r.width), H = Math.round(r.height);
    if (cv.width !== W * dpr || cv.height !== H * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
    const x = cv.getContext('2d'); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, W, H);
    const C = { line: tok('cyan'), glow: tok('cyan'), grid: tok('grid'), dim: tok('dim'), ink: tok('ink'), gold: tok('gold'), hi: tok('lime'), lo: tok('red'), panel: tok('panel') };
    const padL = 6, padR = 6, padT = 22, padB = 22;
    // grid
    x.strokeStyle = C.grid; x.lineWidth = 1; x.globalAlpha = .55;
    for (let i = 0; i <= 4; i++) { const y = Math.round(padT + (H - padT - padB) * i / 4) + .5; x.beginPath(); x.setLineDash([2, 4]); x.moveTo(padL, y); x.lineTo(W - padR, y); x.stroke(); }
    x.setLineDash([]); x.globalAlpha = 1;
    if (pts.length < 2) { cv.setAttribute('aria-label', 'Bitcoin price chart, no data yet'); tip.hidden = true; return; }
    let lo = Infinity, hi = -Infinity, iLo = 0, iHi = 0;
    pts.forEach((p, i) => { if (p.v < lo) { lo = p.v; iLo = i; } if (p.v > hi) { hi = p.v; iHi = i; } });
    const span = (hi - lo) || hi * 0.001, yMin = lo - span * 0.08, yMax = hi + span * 0.08;
    const X = i => padL + (W - padL - padR) * i / (pts.length - 1);
    const Y = v => padT + (H - padT - padB) * (1 - (v - yMin) / (yMax - yMin));
    // area
    const g = x.createLinearGradient(0, padT, 0, H - padB); g.addColorStop(0, C.line + '55'); g.addColorStop(1, C.line + '00');
    x.beginPath(); x.moveTo(X(0), H - padB);
    pts.forEach((p, i) => { if (i) x.lineTo(X(i), Y(pts[i - 1].v)); x.lineTo(X(i), Y(p.v)); });
    x.lineTo(X(pts.length - 1), H - padB); x.closePath(); x.fillStyle = g; x.fill();
    // stepped neon line
    x.save(); x.shadowColor = C.glow; x.shadowBlur = 8; x.strokeStyle = C.line; x.lineWidth = 2; x.lineJoin = 'miter';
    x.beginPath(); pts.forEach((p, i) => { const px = Math.round(X(i)), py = Math.round(Y(p.v)); if (!i) x.moveTo(px, py); else { x.lineTo(px, Math.round(Y(pts[i - 1].v))); x.lineTo(px, py); } }); x.stroke(); x.restore();
    // HI / LO markers, arcade style
    x.font = '8px "Press Start 2P", monospace'; x.textBaseline = 'middle';
    const mark = (i, v, col, label, above) => {
      const px = X(i), py = Y(v); x.fillStyle = col; x.fillRect(Math.round(px) - 3, Math.round(py) - 3, 6, 6);
      const txt = `${label} ${fmtMoney(v, cur)}`; const tw = x.measureText(txt).width;
      const tx = Math.max(padL, Math.min(W - padR - tw, px - tw / 2)); const ty = above ? Math.max(8, py - 12) : Math.min(H - 8, py + 12);
      x.fillStyle = C.ink; x.fillText(txt, tx, ty);
    };
    mark(iHi, hi, C.hi, 'HI', true); mark(iLo, lo, C.lo, 'LO', false);
    // live end point
    const li = pts.length - 1; const blink = st.live && (Math.floor(Date.now() / 600) % 2 === 0);
    x.fillStyle = C.gold; x.shadowColor = C.gold; x.shadowBlur = blink ? 10 : 0; x.fillRect(Math.round(X(li)) - 3, Math.round(Y(pts[li].v)) - 3, 6, 6); x.shadowBlur = 0;
    // crosshair + tooltip
    if (st.hover != null && pts[st.hover]) {
      const p = pts[st.hover], px = Math.round(X(st.hover)) + .5, py = Y(p.v);
      x.strokeStyle = C.ink; x.globalAlpha = .6; x.setLineDash([3, 3]); x.beginPath(); x.moveTo(px, padT - 6); x.lineTo(px, H - padB + 4); x.stroke(); x.setLineDash([]); x.globalAlpha = 1;
      x.fillStyle = C.panel; x.strokeStyle = C.gold; x.lineWidth = 2; x.fillRect(px - 5, py - 5, 10, 10); x.strokeRect(px - 5, py - 5, 10, 10);
      tip.hidden = false; tip.textContent = '';
      const v = document.createElement('b'); v.textContent = fmtMoney(p.v, cur, p.v >= 1000 ? 0 : 2);
      const t = document.createElement('span'); t.textContent = timeLabel(p.t, st.range);
      tip.append(v, t);
      const tw = tip.offsetWidth; tip.style.left = Math.max(0, Math.min(W - tw, px - tw / 2)) + 'px';
    } else tip.hidden = true;
    cv.setAttribute('aria-label', `Bitcoin price in ${cur} over ${st.range}: now ${fmtMoney(pts[li].v, cur)}, high ${fmtMoney(hi, cur)}, low ${fmtMoney(lo, cur)}. Use left and right arrow keys to read values.`);
    if (st.live) setTimeout(queue, 600);
  }

  function mount(el) {
    if (!el) return;
    st.el = el;
    if (!prefs().fiat) { disconnect(); offShell(el); return; }
    shell(el);
    const cur = pairFor();
    if (st.cur && st.cur !== cur && cur !== 'USD') { st.pts = []; st.last = null; }
    load();
    clearInterval(refreshTimer);
    refreshTimer = setInterval(() => { if (st.el && st.el.isConnected && !document.hidden && prefs().fiat) load(true); else if (!(st.el && st.el.isConnected)) { clearInterval(refreshTimer); disconnect(); } }, 60e3);
  }
  window.PriceChart = { mount, disconnect, state: st };
})();
