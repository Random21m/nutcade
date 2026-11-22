/* ---------- Mint reliability from MintRadar (1.24) ----------
   OFF by default (Settings > Privacy > Show mint reliability). When on, NUTCADE downloads MintRadar's whole public list of
   mint health (one GET, about every 5 minutes at most, with If-None-Match) and compares it with your mints ON THIS PHONE:
   it never asks about one mint (that would tell MintRadar which mint you use), and MintRadar sees only your phone's address.
   The list is shown as a small label: RELIABLE, SHAKY or DOWN (a symbol and a word, never colour alone). It is an
   operational health signal, NOT a statement that a mint holds your sats or is safe to deposit into: it never blocks,
   moves or chooses anything. Offline, 429, an error or a garbage reply are silent (no data = no label = nothing shown).
   The setting is not part of a backup file (a backup must never switch on a new service). */
const MR_API = 'https://mintradar.org/api/v1/wallets/mints?includeOffline=true&includeArchived=true&includeUnscored=true';
const MR_EVERY = 5 * 60e3, MR_KEEP = 20 * 60e3, MR_MAXBYTES = 3e6;
const radar = { at: 0, next: 0, etag: '', busy: false, gen: 0, map: new Map(), sugg: [] };
const radarOn = () => !!S.prefs.mintRadar;
const radarFresh = () => radar.map.size > 0 && Date.now() - radar.at < MR_KEEP;
// the list, checked field by field: anything that is not what the API documents is skipped, unknown fields are ignored
function radarParse(j) {
  if (!j || typeof j !== 'object' || !Array.isArray(j.mints)) return null;
  const map = new Map(), sugg = [];
  for (const x of j.mints.slice(0, 2000)) {
    if (!x || typeof x !== 'object' || typeof x.url !== 'string' || x.url.length > 300 || !/^https?:\/\//i.test(x.url)) continue;
    if (!['online', 'offline', 'degraded', 'archived'].includes(x.status)) continue;
    const url = normUrl(x.url), score = typeof x.score === 'number' && Number.isFinite(x.score) && x.score >= 0 && x.score <= 100 ? Math.round(x.score) : null;
    const off = x.mintDisabled === true || x.meltDisabled === true;
    const label = x.status !== 'online' ? 'down' : score === null ? null : (score >= 80 && !off ? 'good' : 'shaky');
    if (!label || map.has(url)) continue;
    map.set(url, { label });
    const nut = n => Array.isArray(x.nuts) ? x.nuts.map(String).includes(n) : !!x.nuts && typeof x.nuts === 'object' && !!x.nuts[n] && x.nuts[n].supported !== false;
    if (label === 'good' && x.eligibleForRecommendation === true && x.isTest !== true && /^https:\/\//i.test(url) && Array.isArray(x.units) && x.units.includes('sat') && nut('4') && nut('5')) {
      const nm = typeof x.name === 'string' ? x.name.replace(/[\u0000-\u001f\u007f<>\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g, '').trim().slice(0, 40) : '';
      sugg.push({ url, name: nm || host(url) });
    }
  }
  return { map, sugg: sugg.slice(0, 5) };
}
async function radarFetch() {
  if (radar.busy) return; radar.busy = true; const gen = radar.gen; const before = radarSig();
  try {
    const h = {}; if (radar.etag && radar.map.size) h['If-None-Match'] = radar.etag;
    const ctl = new AbortController(), tm = setTimeout(() => ctl.abort(), 12000);   // (covers the answer and its body)
    let r; try { r = await fetch(MR_API, { headers: h, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer', signal: ctl.signal });
    if (gen !== radar.gen) return;
    if (r.status === 304 && radar.map.size) { radar.at = Date.now(); radar.next = radar.at + MR_EVERY; return; }
    if (r.status === 429) { const s = parseInt(r.headers.get('Retry-After'), 10); radar.next = Date.now() + Math.min(Math.max((s > 0 ? s : 0) * 1000, MR_EVERY), 3600e3); return; }
    if (!r.ok) throw new Error('status');
    const cl = parseInt(r.headers.get('Content-Length'), 10); if (cl > MR_MAXBYTES) throw new Error('size');
    const txt = await r.text(); if (gen !== radar.gen) return; if (txt.length > MR_MAXBYTES) throw new Error('size');
    const p = radarParse(JSON.parse(txt)); if (!p) throw new Error('shape');
    radar.map = p.map; radar.sugg = p.sugg; radar.etag = r.headers.get('ETag') || ''; radar.at = Date.now(); radar.next = radar.at + MR_EVERY;
    } finally { clearTimeout(tm); }
  } catch (e) { if (gen === radar.gen) radar.next = Date.now() + MR_EVERY; }
  finally {
    if (gen === radar.gen) radar.busy = false;
    if (gen === radar.gen && radarOn()) { radarPaint(); if (radarSig() !== before && !$('#layer .sheet') && (tab === 'wallet' || tab === 'mints')) refresh(); }
  }
}
function radarEnsure() {
  if (!radarOn() || !S.seed || tabLocked || (vault.on && !vault.open) || radar.busy || Date.now() < radar.next || navigator.onLine === false) return;
  radarFetch();
}
function radarOff() { radar.gen++; radar.busy = false; radar.map = new Map(); radar.sugg = []; radar.etag = ''; radar.at = 0; radar.next = 0; }
const radarGet = url => (radarOn() && radarFresh() && radar.map.get(normUrl(url))) || null;
// what is on screen depends on this, so a change is redrawn
const radarSig = () => radarOn() ? (radarFresh() ? 'f' : 'x') + S.mints.map(m => (radarGet(m.url) || {}).label || '-').join('') + radar.sugg.map(s => s.url).join(' ') : 'off';
const RADAR_WORD = { good: ['✓', 'RELIABLE'], shaky: ['!', 'SHAKY'], down: ['✕', 'MINT DOWN'] };
function radarChip(url) {
  const e = radarGet(url); if (!e) return '';
  return `<span class="chip rdr ${e.label}"><span aria-hidden="true" data-noi18n>${RADAR_WORD[e.label][0]}</span> ${RADAR_WORD[e.label][1]}</span>`;
}
const radarSpan = url => `<span data-radar="${esc(url)}">${radarChip(url)}</span>`;
const radarNote = () => !radarOn() || !radarFresh() ? '' : `<div class="tiny muted">Reliable, Shaky and Mint down come from MintRadar (mintradar.org), from its own checks of each mint. It is an operational health signal: it is not a statement that a mint holds your sats or is safe to deposit into. It never moves your sats or changes which mint NUTCADE uses.</div>`;
function radarSuggHTML() {
  const note = radarNote(); if (!note) return '';
  const known = new Set(S.mints.map(m => normUrl(m.url)));
  const rows = radar.sugg.filter(s => !known.has(s.url) && !isBlocked(s.url));
  return note + (rows.length ? `<div class="field"><label>Suggested mints</label><div class="tiny muted">Online mints with a Reliability Score of 80 or more that handle sats. A good score is not a promise: only add mints you trust.</div><div class="txs">${rows.map(s => `<div class="panel" style="gap:8px;background:var(--panel-2)">
    <div class="row between" style="align-items:flex-start"><div style="min-width:0"><div class="uname" style="font-family:var(--f-display);font-size:10px;line-height:1.5;color:var(--gold)">${esc(s.name)}</div><div class="tiny muted" data-noi18n style="overflow-wrap:anywhere">${esc(host(s.url))}</div></div>
    <button class="btn sm lime" data-act="addMint" data-url="${esc(s.url)}">Add</button></div><div class="row" style="gap:6px;flex-wrap:wrap">${radarSpan(s.url)}</div></div>`).join('')}</div></div>` : '');
}
// the sheet that is open (Add mint) is filled in place; the screens are redrawn by radarFetch when something changed
function radarPaint() {
  const L = $('#layer'); if (!L) return;
  L.querySelectorAll('[data-radar]').forEach(el => { const h = radarChip(el.dataset.radar); if (el.innerHTML !== h) el.innerHTML = h; });
  const s = L.querySelector('#radarSugg'); if (s) { const h = radarSuggHTML(); if (s.innerHTML !== h) s.innerHTML = h; }
}
// a mint that holds your sats and is reported down: a notice only. Nothing is moved, blocked or switched.
function radarWarn() {
  if (!radarOn() || !radarFresh()) return '';
  return S.mints.filter(m => balanceOf(m.url) > 0 && (radarGet(m.url) || {}).label === 'down').map(m => `<div class="notice red" role="status"><div class="uname" data-noi18n>${esc(m.name)}</div><div>MintRadar reports this mint as down. You hold ${money(balanceOf(m.url))} there. This is a health signal, not a statement about your sats, and NUTCADE moves nothing by itself.</div></div>`).join('');
}
