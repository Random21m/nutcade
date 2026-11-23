/* ===================== Notices when money arrives (inlined inside app.js) =====================
   No server, no push service, no tracking: everything here is worked out by the open page from the wallet's own
   history, and nothing is sent anywhere.

   What counts: a history line of money coming in, once it is complete (status done, an amount above 0), as this
   wallet's own code writes it (addTx / updTx call arrivalSeen). Not an internal move between your own mints, not sats
   found by a restore or brought in by a backup, not the duress wallet's sats coming back. Each line is announced once:
   its id goes into a small record kept with the wallet (`arrivals`: in the PIN vault when there is a PIN, so the
   duress PIN's wallet has its own and never sees the other's), written in the same moment as the line itself. A
   reload, a second tab or a restore therefore never announces it again, and lines another tab or device wrote are
   that tab's or device's to announce.
     seen: [[id, ts]]   every line announced or waiting to be (kept 30 days)
     pend: [{id, k}]    lines not yet seen in the app: they make the "while you were away" summary
   On opening or unlocking, the app's own start-up checks run first (deposits, npub.cash, saved tokens, Nostr); what
   they and earlier, unseen arrivals bring is summed up per kind, exactly the history lines in question. After that,
   each arrival gets its own notice. In a background tab the notice waits on the page and, if turned on in Settings,
   a system notification says what came (shown by the page or its service worker, with the permission asked when the
   setting is turned on). When the app locks, those notifications are replaced by one that says only "Money arrived,
   unlock to see". With a duress PIN set, both wallets behave exactly as with a PIN alone (the same words, in the same
   cases), so neither a notification nor its absence ever tells anyone that a duress PIN exists. */
function arrS() {
  return arrS.s || (arrS.s = { base: Date.now(), log: [], card: [], items: {}, onPage: new Set(), away: 0, awayDone: false, tickDone: 0, awayIv: 0, flushT: 0, coinAt: 0, wasOpen: false, lockLine: false, unseen: new Set(), just: new Map() });
}
arrS();
const ARR_TAG = 'nutcade-arrival';
const ARR_KINDS = ['ln', 'onchain', 'npc', 'nwc', 'request', 'nostr', 'token', 'back'];
const ARR_LABEL = { ln: 'Lightning deposit', onchain: 'On-chain deposit', npc: 'Lightning address', nwc: 'Wallet Connect invoice', request: 'Payment request paid', nostr: 'Ecash over Nostr', token: 'Ecash claimed', back: 'Came back to you' };
function arrOpen() { return !!(S.seed && S.seed.backedUp) && !tabLocked && !writeGuard.paused && !(vault.on && !vault.open); }
function arrLedger() {
  const l = raw.get('arrivals', null);
  if (!(l && l.v === 1 && Array.isArray(l.seen) && Array.isArray(l.pend))) return { v: 1, since: arrS().base, seen: [], pend: [] };
  // (a damaged entry is dropped, never a reason for every later notice to stop)
  l.seen = l.seen.filter(x => Array.isArray(x) && typeof x[0] === 'string'); l.pend = l.pend.filter(p => p && typeof p.id === 'string');
  if (!(typeof l.since === 'number')) l.since = arrS().base;
  return l;
}
// one message per arrival: a receive's own toast ("+X received") is left out when its notice (now, after a game or
// in a summary) says it, and only then: never both lost. The notice says it when the line is the arrival
// in question: the arrival this very receive just put on the record (the line as it is now). A later receive that adds
// to a line announced before (a deposit recovered onto a line already done) gets its toast: it has no notice of its own.
function arrAnnounced(id) {
  try { const t = id && txById(id), j = arrS().just.get(id); return !!t && arrOpen() && j === num(t.amount) && arrLedger().seen.some(x => x[0] === id); } catch (e) { return false; }
}
function arrToast(id, msg, c) { if (!arrAnnounced(id)) toast(msg, c); }
// Not money arriving: your own coins coming back by your own hand or the wallet's upkeep, each marked on its line by the
// code that writes it (never read from its note: a received token's note is its sender's memo): a token (printed or not)
// you took back or pasted or scanned into Receive, a gift you took back, an Extra Life you cashed out, the duress PIN's
// wallet's sats coming back (back: 'hand', also after the mint's answer was lost or in parts), coins found by a restore,
// a sweep of another phrase or a backup (self), coins the keyset check-up set aside that the mint accepts again (upkeep).
// (A gift or a payment request's sats that came back by themselves are still announced: "Came back to you".)
function arrQual(t) {
  return !!t && t.type === 'in' && t.status === 'done' && num(t.amount) > 0 && !t.move && !t.upkeep && !t.self && t.back !== 'hand';
}
// the kind, from the line (and, for npub.cash, its deposit record, which is gone once it is credited)
function arrKind(t) {
  if (t.nwc) return 'nwc';
  if (t.method === 'onchain') return 'onchain';
  if (t.method === 'ln') { const q = S.quotes.find(q => q.quote === t.quote); return (q && q.npc) || t.note === 'Lightning address' ? 'npc' : /^Swapped from /.test(t.note || '') ? 'token' : 'ln'; }
  if (t.reqId) return 'request';
  return t.back === 'auto' ? 'back' : 'token';   // (your own token that came back by itself: from its mark, never from a memo)
}
// called right after a history line is written (addTx) or changed (updTx)
function arrivalSeen(t) {
  try {
    if (!t || !arrQual(t) || tabLocked || writeGuard.paused || (vault.on && !vault.open)) return;
    if (Date.now() - t.ts > 10 * 60e3) return;   // (an old line coming back changed, or one from another device's backup)
    const l = arrLedger(); if (!(t.ts >= l.since) || l.seen.some(x => x[0] === t.id)) return;
    l.seen.push([t.id, t.ts]); l.pend.push({ id: t.id, k: arrKind(t) }); const j = arrS().just; j.set(t.id, num(t.amount)); if (j.size > 2000) j.delete(j.keys().next().value);
    const old = Date.now() - 30 * 86400e3; l.seen = l.seen.filter(x => x[1] > old).slice(-6000); l.pend = l.pend.slice(-5000);   // (room for a busy shop away for days: a summary is exactly its lines)
    raw.set('arrivals', l); arrSchedule();
  } catch (e) {}
}
// where a receive knows more than its line says (ecash that came over Nostr)
function arrivalFrom(id, k) {
  try { const l = arrLedger(), p = l.pend.find(x => x.id === id); if (p && p.k !== 'request' && p.k !== 'back') { p.k = k; raw.set('arrivals', l); } } catch (e) {}
}
const arrItem = p => { const t = txById(p.id); if (!t || !arrQual(t)) return null; return { id: t.id, k: t.reqId ? 'request' : ARR_KINDS.includes(p.k) ? p.k : 'token', a: num(t.amount), m: t.mint, u: txUnit(t) }; };
function arrSeen(ids) {
  if (!ids.length || !arrOpen()) return;
  const l = arrLedger(), n = l.pend.length; l.pend = l.pend.filter(p => !ids.includes(p.id));
  if (l.pend.length !== n) raw.set('arrivals', l);
  ids.forEach(id => arrS().unseen.delete(id));
  arrCloseSys();
}
function arrSchedule() { const A = arrS(); clearTimeout(A.flushT); A.flushT = setTimeout(arrFlush, 700); }   // (a receive in parts, or a request's id written just after: one notice)
function arrCoin() { const A = arrS(); if (Date.now() - A.coinAt > 2500) sfx('coin'); }
if (window.NutAudio && !window.NutAudio.arrWrapped) {   // the app's own coin for an arrival is enough: the notice adds none then
  const f = window.NutAudio.sfx; window.NutAudio.sfx = n => { if (n === 'coin') arrS().coinAt = Date.now(); return f(n); }; window.NutAudio.arrWrapped = true;
}

/* ---------- the notices ---------- */
const arrCount = n => tr(n === 1 ? '1 payment' : `${fmt(n)} payments`);
// a group per kind AND unit: USD, EUR and CHF arrivals are never added to SAT ones
function arrGroups(items) {
  const g = new Map();
  for (const it of items) { const key = it.k + '|' + (it.u || 'sat'); const x = g.get(key) || { k: it.k, u: it.u || 'sat', n: 0, a: 0 }; x.n++; x.a += it.a; g.set(key, x); }
  return [...g.values()].sort((a, b) => ARR_KINDS.indexOf(a.k) - ARR_KINDS.indexOf(b.k) || UNIT_LIST.indexOf(a.u) - UNIT_LIST.indexOf(b.u));
}
// what arrived, per unit, as one line: "+1,000 SAT · +12.50 USD"
const arrTotals = items => UNIT_LIST.filter(u => items.some(x => (x.u || 'sat') === u)).map(u => '+' + arrMoneyU(items.filter(x => (x.u || 'sat') === u).reduce((t, x) => t + x.a, 0), u)).join(' · ');
// A notice is one short card over the logo bar, never over the balance, the lock or the mint (about 60 px high, at
// any size): the amount, Details, and what came (for a summary: "while you were away"). Details opens a sheet with
// everything: the kind and mint, or the summary's count and total per kind, and the way to the notes.
function arrCardHTML(type, items) {
  const total = arrTotals(items), one = items.length === 1 && type === 'live' ? items[0] : null;
  const sub = type === 'away' ? '<span class="arr-what">While you were away</span>'
    : one ? `<span class="arr-what">${esc(ARR_LABEL[one.k])}</span><span class="arr-mint" data-noi18n>${esc(mintName(one.m))}</span>` : `<span class="arr-what">${esc(arrCount(items.length))}</span>`;
  // (the amount has the first line to itself and is never cut; the second line, what came, gives way instead)
  return `<div class="arr-row"><span class="arr-ico" aria-hidden="true">↓</span><span class="arr-big" data-noi18n>${esc(total)}</span><span class="arr-sp"></span><button type="button" class="arr-x" data-act="arrClose" aria-label="Dismiss">×</button></div>
    <div class="arr-sub">${sub}<span class="arr-sp"></span><button type="button" class="btn sm arr-more" data-act="arrMore">Details</button></div>`;
}
function arrDetailsHTML(type, items) {
  const total = arrTotals(items), one = items.length === 1 && type === 'live' ? items[0] : null;
  const lines = one ? `<dl class="kv"><dt>Amount</dt><dd data-noi18n>+${esc(arrMoneyU(one.a, one.u))}</dd><dt>From</dt><dd>${esc(ARR_LABEL[one.k])}</dd><dt>Mint</dt><dd data-noi18n>${esc(mintName(one.m))}</dd></dl>`
    : `${type === 'away' ? '<div class="arr-note">Since you last had NUTCADE open</div>' : ''}<div class="arr-lines">${arrGroups(items).map(g => `<div class="arr-line" data-k="${g.k}" data-n="${g.n}" data-a="${g.a}"><span class="arr-k">${esc(ARR_LABEL[g.k])}</span><span class="arr-n">${esc(arrCount(g.n))}</span><span class="arr-a" data-noi18n>+${esc(arrMoneyU(g.a, g.u))}</span></div>`).join('')}</div>
      <div class="arr-total"><span>Total</span><span data-noi18n>${esc(total)}</span></div>`;
  return `<div class="arr-details" data-type="${type}" data-ids="${esc(items.map(x => x.id).join(' '))}">${lines}
    <div class="arr-acts"><button type="button" class="btn solid gold" data-act="arrNotes">Open notes</button><button type="button" class="btn" data-act="close">OK</button></div></div>`;
}
function arrShow(type, items) {
  let st = document.getElementById('arrStack');
  if (!st) { st = document.createElement('div'); st.id = 'arrStack'; st.className = 'arr-stack'; st.setAttribute('role', 'region'); st.setAttribute('aria-label', tr('Money arrived')); document.body.appendChild(st); }
  // (one card at a time: a summary already in front of you gives way to a new arrival)
  if (type === 'live') { const aw = st.querySelector('.arr-card[data-type=away]'); if (aw && !(aw.dataset.ids || '').split(' ').some(id => arrS().unseen.has(id))) aw.remove(); }
  let c = st.querySelector(`.arr-card[data-type="${type}"]`);
  if (!c) { c = document.createElement('div'); c.className = 'arr-card'; c.dataset.type = type; c.setAttribute('role', 'status'); c.setAttribute('aria-live', 'polite'); type === 'away' ? st.prepend(c) : st.appendChild(c); }
  c.dataset.ids = items.map(x => x.id).join(' '); c.dataset.at = document.hidden ? Date.now() + 864e5 : Date.now();
  c.innerHTML = arrCardHTML(type, items); arrS().items[type] = items.slice();
  clearTimeout(c.hideT);
  if (type === 'live') { const hide = () => { if (document.hidden) { c.hideT = setTimeout(hide, 3000); return; } c.remove(); arrS().card = []; }; c.hideT = setTimeout(hide, 20000); }
}
function arrClear() { const st = document.getElementById('arrStack'); if (st) st.remove(); arrS().card = []; }
function arrFlush() {
  const A = arrS(); A.flushT = 0;
  if (!arrOpen() || (A.away && !A.awayDone)) return;   // (while the opening's checks run, everything goes into the summary)
  const l = arrLedger();
  let fresh = l.pend.filter(p => !A.onPage.has(p.id)).map(arrItem).filter(Boolean);
  if (!fresh.length) return;
  if (arrCovered()) {   // a game or the till fills the screen: the till's own sale is on its PAID! screen; the rest wait
    const sale = fresh.filter(x => arrTillSale(txById(x.id)));
    if (sale.length && document.querySelector('.cashier') && !document.hidden) { sale.forEach(x => A.onPage.add(x.id)); arrSeen(sale.map(x => x.id)); }
    A.flushT = setTimeout(arrFlush, 2000); return;
  }
  fresh.forEach(x => A.onPage.add(x.id));
  A.card = A.card.concat(fresh);
  arrShow('live', A.card);
  A.log.push({ type: 'live', ids: fresh.map(x => x.id), at: Date.now() });
  arrCoin();
  if (document.hidden) { fresh.forEach(x => A.unseen.add(x.id)); arrSys(tr('Money arrived'), A.card.filter(x => A.unseen.has(x.id))); }
  else arrSeen(fresh.map(x => x.id));
}
function arrCovered() { return !!(document.querySelector('.cashier') || (window.Arcade && window.Arcade.playing && window.Arcade.playing())); }
// a sale taken at the till (a Lightning charge, or a payment request the till made)
function arrTillSale(t) { return !!t && !!(t.cashier || t.cashierPending || (t.reqId && S.requests.some(r => r.id === t.reqId && r.cashier))); }
// on opening or unlocking: the start-up checks first, then one summary of everything not yet seen
function arrAwayStart() {
  const A = arrS(); A.away = Date.now(); A.awayDone = false; A.tickDone = 0; clearInterval(A.awayIv);
  arrCloseSys();
  A.awayIv = setInterval(() => {
    if (!arrOpen()) return;
    const el = Date.now() - A.away;
    if (!A.tickDone && tickAt >= A.away && !tickRun) A.tickDone = Date.now();
    // (the start-up check begins within about a second of opening or unlocking; none by then: none is coming)
    if ((A.tickDone && Date.now() - A.tickDone > 2500) || (tickAt < A.away && el > 3500) || el > 45000) { clearInterval(A.awayIv); arrAwayEnd(); }
  }, 500);
}
function arrAwayEnd() {
  const A = arrS();
  if (arrCovered()) { setTimeout(arrAwayEnd, 2000); return; }   // (not under a game or the till, where nobody would see it)
  A.awayDone = true;
  const l = arrLedger(), items = l.pend.map(arrItem).filter(Boolean);
  if (items.length !== l.pend.length) { const ok = new Set(items.map(x => x.id)); l.pend = l.pend.filter(p => ok.has(p.id)); raw.set('arrivals', l); }   // (a line that is gone, or no longer an arrival)
  if (!items.length) return;
  items.forEach(x => A.onPage.add(x.id));
  arrShow('away', items);
  A.log.push({ type: 'away', ids: items.map(x => x.id), at: Date.now() });
  arrCoin();
  if (document.hidden) { items.forEach(x => A.unseen.add(x.id)); arrSys(tr('While you were away'), items); }
  else arrSeen(items.map(x => x.id));
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) return;
  const A = arrS(); document.querySelectorAll('#arrStack .arr-card').forEach(c => { if (+c.dataset.at > Date.now()) c.dataset.at = Date.now(); });   // (in front of you from now)
  if (A.unseen.size && document.getElementById('arrStack')) arrSeen([...A.unseen]);
});
// called at the start of every render: notices the wallet opening (NUTCADE starting with a wallet, or unlocking it;
// not a wallet just made or restored, which has been in front of you all along)
function arrRendered() {
  try {
    const A = arrS(), open = arrOpen(), unlocked = vault.on && vault.open;
    if (open && !A.wasOpen && (!A.rendered || (unlocked && !A.wasUnlocked))) arrAwayStart();
    A.rendered = true; A.wasUnlocked = unlocked;
    const mode = arrSysMode(); if (A.sysMode && mode !== A.sysMode && mode !== 'full') arrCloseSys(); A.sysMode = mode;   // (a PIN just set: none with an amount stays)
    if (!open && A.wasOpen) arrClear();
    A.wasOpen = open;
    // going to another tab: notices you have had in front of you for a moment are done
    if (A.lastTab !== undefined && A.lastTab !== tab && !document.hidden) document.querySelectorAll('#arrStack .arr-card').forEach(c => {
      if (Date.now() - (+c.dataset.at || 0) > 1000) { if (c.dataset.type === 'live') A.card = []; c.remove(); } });
    A.lastTab = tab;
  } catch (e) {}
}

/* ---------- system notifications (only when turned on in Settings) ---------- */
async function arrReg() {
  try { if (!('serviceWorker' in navigator)) return null; return await Promise.race([navigator.serviceWorker.getRegistration(), sleep(1500).then(() => null)]) || null; } catch (e) { return null; }
}
const arrSysOk = () => !!S.prefs.arrNotify && typeof Notification !== 'undefined' && Notification.permission === 'granted';
// what a system notification may say: no PIN, what came; a PIN, only that money came (a closed or discarded tab, or a
// phone's lock screen, would otherwise show it while the wallet is locked). A duress PIN changes nothing, in either
// wallet: the duress PIN's wallet is a wallet with a PIN, and the real one is too (silence would give the duress PIN away)
function arrSysMode() { return vault.on ? 'generic' : 'full'; }
function arrSysBody(items) {
  if (items.length === 1) { const x = items[0]; return `${tr(ARR_LABEL[x.k])}: +${arrMoneyU(x.a, x.u)} · ${mintName(x.m)}`; }
  return arrGroups(items).map(g => `${tr(ARR_LABEL[g.k])}: ${arrCount(g.n)} · +${arrMoneyU(g.a, g.u)}`).join('\n');
}
async function arrSys(title, items) {
  const mode = arrSysMode();
  if (!arrSysOk() || !items.length || mode === 'none') return;
  if (mode === 'generic') { title = 'NUTCADE'; }
  const opt = { body: mode === 'generic' ? tr('Money arrived. Open NUTCADE to see.') : arrSysBody(items), tag: ARR_TAG, renotify: true, icon: 'icon-192.png', silent: !S.prefs.sound, data: { g: 1 } };
  const reg = await arrReg();
  if (reg) { try { await reg.showNotification(title, opt); return; } catch (e) {} }
  try { const n = new Notification(title, opt); n.onclick = () => { try { window.focus(); } catch (e) {} n.close(); }; } catch (e) {}
}
async function arrCloseSys() { const reg = await arrReg(); if (!reg) return; try { (await reg.getNotifications({ tag: ARR_TAG })).forEach(n => n.close()); } catch (e) {} }
// locked: nothing of a wallet can be read, so an earlier notification can't stay as it was
async function arrLockedBoot() {
  if (!(vault.on && !vault.open)) return;
  const reg = await arrReg(); if (!reg) return;
  let ns = []; try { ns = await reg.getNotifications({ tag: ARR_TAG }); } catch (e) { return; }
  if (!ns.length) return;
  const generic = ns.some(n => n.data && n.data.g);
  ns.forEach(n => n.close());
  if (!generic) return;
  arrS().lockLine = true;
  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') { try { await reg.showNotification('NUTCADE', { body: tr('Money arrived, unlock to see.'), tag: ARR_TAG, icon: 'icon-192.png', silent: true, data: { g: 1 } }); } catch (e) {} }
  const pad = document.querySelector('.pinpad'); if (pad && vault.on && !vault.open && !document.querySelector('.arr-lock')) pad.insertAdjacentHTML('beforebegin', arrLockHTML());
}
function arrLockHTML() { return arrS().lockLine ? '<div class="notice cyan arr-lock" role="status"><span aria-hidden="true">↓ </span><span>Money arrived, unlock to see.</span></div>' : ''; }
setTimeout(() => { arrLockedBoot().catch(() => {}); }, 0);

/* ---------- Settings: Look & sound ---------- */
function arrHelp(p, asked) {
  if (p === 'unsupported') return "This browser can't show notifications.";
  if (asked && p === 'default') return "Notifications weren't allowed. Turn this on to be asked again, or allow them in your browser's settings.";
  if (p === 'denied') return "Notifications are blocked for NUTCADE in this browser's settings. Allow them there, then turn this on.";
  return 'When money arrives while NUTCADE is open in another tab or window. Shown by this device only: no push service, nothing is sent anywhere. With a PIN they show no amount, only “Money arrived. Open NUTCADE to see.”';
}
function arrSettingsHTML() {
  const p = typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;
  return `<label class="toggle set" for="p_arrNotify"><span><span class="tl">Notify me when money arrives</span><span class="th" id="arrNotifyHelp">${esc(arrHelp(p))}</span></span><input id="p_arrNotify" type="checkbox" ${S.prefs.arrNotify && p === 'granted' ? 'checked' : ''} ${p === 'unsupported' ? 'disabled' : ''}></label>`;
}
async function arrToggle(el) {
  if (!el.checked) { S.prefs.arrNotify = false; save(); sfx('blip'); return; }
  let p = typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;
  if (p === 'default') { try { p = await Notification.requestPermission(); } catch (e) { p = 'denied'; } }   // asked now, when you turn it on
  S.prefs.arrNotify = p === 'granted'; save();
  el.checked = S.prefs.arrNotify;
  const h = document.getElementById('arrNotifyHelp'); if (h) h.textContent = tr(arrHelp(p, true));
  sfx(S.prefs.arrNotify ? 'blip' : 'err');
}
document.addEventListener('change', e => { if (e.target && e.target.id === 'p_arrNotify') arrToggle(e.target); });

window.NutArrivals = { log: arrS().log, ledger: () => arrLedger(), awayDone: () => !arrS().away || arrS().awayDone };
