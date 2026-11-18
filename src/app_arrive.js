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
   unlock to see" (or simply closed when a duress PIN is set up, so the duress wallet never has to explain it). */
function arrS() {
  return arrS.s || (arrS.s = { base: Date.now(), log: [], card: [], onPage: new Set(), away: 0, awayDone: false, tickDone: 0, awayIv: 0, flushT: 0, coinAt: 0, wasOpen: false, lockLine: false, unseen: new Set() });
}
arrS();
const ARR_TAG = 'nutcade-arrival';
const ARR_KINDS = ['ln', 'onchain', 'npc', 'nwc', 'request', 'nostr', 'token', 'back'];
const ARR_LABEL = { ln: 'Lightning deposit', onchain: 'On-chain deposit', npc: 'Lightning address', nwc: 'Wallet Connect invoice', request: 'Payment request paid', nostr: 'Ecash over Nostr', token: 'Ecash claimed', back: 'Came back to you' };
function arrOpen() { return !!(S.seed && S.seed.backedUp) && !tabLocked && !writeGuard.paused && !(vault.on && !vault.open); }
function arrLedger() {
  const l = raw.get('arrivals', null);
  return l && l.v === 1 && Array.isArray(l.seen) && Array.isArray(l.pend) ? l : { v: 1, since: arrS().base, seen: [], pend: [] };
}
function arrQual(t) {
  return !!t && t.type === 'in' && t.status === 'done' && num(t.amount) > 0 && !t.move
    && !/^(Recovered with recovery phrase|Restored from another phrase|Restored from backup$|Back from the duress PIN's wallet$)/.test(t.note || '');
}
// the kind, from the line (and, for npub.cash, its deposit record, which is gone once it is credited)
function arrKind(t) {
  if (t.nwc) return 'nwc';
  if (t.method === 'onchain') return 'onchain';
  if (t.method === 'ln') { const q = S.quotes.find(q => q.quote === t.quote); return (q && q.npc) || t.note === 'Lightning address' ? 'npc' : /^Swapped from /.test(t.note || '') ? 'token' : 'ln'; }
  if (t.reqId) return 'request';
  return /^(Reclaimed: |Gift came back|Payment request couldn't be delivered|Extra Life cashed out)/.test(t.note || '') ? 'back' : 'token';
}
// called right after a history line is written (addTx) or changed (updTx)
function arrivalSeen(t) {
  try {
    if (!t || !arrQual(t) || tabLocked || writeGuard.paused || (vault.on && !vault.open)) return;
    if (Date.now() - t.ts > 10 * 60e3) return;   // (an old line coming back changed, or one from another device's backup)
    const l = arrLedger(); if (!(t.ts >= l.since) || l.seen.some(x => x[0] === t.id)) return;
    l.seen.push([t.id, t.ts]); l.pend.push({ id: t.id, k: arrKind(t) });
    const old = Date.now() - 30 * 86400e3; l.seen = l.seen.filter(x => x[1] > old).slice(-600); l.pend = l.pend.slice(-200);
    raw.set('arrivals', l); arrSchedule();
  } catch (e) {}
}
// where a receive knows more than its line says (ecash that came over Nostr)
function arrivalFrom(id, k) {
  try { const l = arrLedger(), p = l.pend.find(x => x.id === id); if (p && p.k !== 'request') { p.k = k; raw.set('arrivals', l); } } catch (e) {}
}
const arrItem = p => { const t = txById(p.id); if (!t || !arrQual(t)) return null; return { id: t.id, k: t.reqId ? 'request' : ARR_KINDS.includes(p.k) ? p.k : 'token', a: num(t.amount), m: t.mint }; };
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
function arrGroups(items) {
  const g = {}; for (const it of items) { const x = g[it.k] || (g[it.k] = { k: it.k, n: 0, a: 0 }); x.n++; x.a += it.a; }
  return ARR_KINDS.filter(k => g[k]).map(k => g[k]);
}
function arrCardHTML(type, items) {
  const total = items.reduce((t, x) => t + x.a, 0), one = items.length === 1 && type === 'live' ? items[0] : null;
  // (one arrival: a compact card, so it covers little even on a phone held sideways)
  if (one) return `<div class="arr-head"><span class="arr-ico" aria-hidden="true">↓</span><span class="arr-title">MONEY ARRIVED</span><button type="button" class="arr-x" data-act="arrClose" aria-label="Dismiss">×</button></div>
    <div class="arr-one"><span class="arr-big" data-noi18n>+${esc(money(one.a))}</span><span class="arr-what">${esc(ARR_LABEL[one.k])}</span><span class="arr-mint" data-noi18n>${esc(mintName(one.m))}</span><button type="button" class="linkbtn arr-link" data-act="arrNotes">Open notes</button></div>`;
  const body = `${type === 'away' ? '<div class="arr-sub">Since you last had NUTCADE open</div>' : ''}<div class="arr-lines">${arrGroups(items).map(g => `<div class="arr-line" data-k="${g.k}" data-n="${g.n}" data-a="${g.a}"><span class="arr-k">${esc(ARR_LABEL[g.k])}</span><span class="arr-n">${esc(arrCount(g.n))}</span><span class="arr-a" data-noi18n>+${esc(money(g.a))}</span></div>`).join('')}</div>
      <div class="arr-total"><span>Total</span><span data-noi18n>+${esc(money(total))}</span></div>`;
  return `<div class="arr-head"><span class="arr-ico" aria-hidden="true">↓</span><span class="arr-title">${type === 'away' ? 'WHILE YOU WERE AWAY' : 'MONEY ARRIVED'}</span><button type="button" class="arr-x" data-act="arrClose" aria-label="Dismiss">×</button></div>
    ${body}
    <div class="arr-acts"><button type="button" class="btn sm" data-act="arrNotes">Open notes</button>${type === 'away' ? '<button type="button" class="btn sm" data-act="arrClose">OK</button>' : ''}</div>`;
}
function arrShow(type, items) {
  let st = document.getElementById('arrStack');
  if (!st) { st = document.createElement('div'); st.id = 'arrStack'; st.className = 'arr-stack'; st.setAttribute('role', 'region'); st.setAttribute('aria-label', tr('Money arrived')); document.body.appendChild(st); }
  let c = st.querySelector(`.arr-card[data-type="${type}"]`);
  if (!c) { c = document.createElement('div'); c.className = 'arr-card'; c.dataset.type = type; c.setAttribute('role', 'status'); c.setAttribute('aria-live', 'polite'); type === 'away' ? st.prepend(c) : st.appendChild(c); }
  c.dataset.ids = items.map(x => x.id).join(' '); c.dataset.at = document.hidden ? Date.now() + 864e5 : Date.now();
  c.innerHTML = arrCardHTML(type, items);
  clearTimeout(c.hideT);
  if (type === 'live') { const hide = () => { if (document.hidden) { c.hideT = setTimeout(hide, 3000); return; } c.remove(); arrS().card = []; }; c.hideT = setTimeout(hide, 20000); }
}
function arrClear() { const st = document.getElementById('arrStack'); if (st) st.remove(); arrS().card = []; }
function arrFlush() {
  const A = arrS(); A.flushT = 0;
  if (!arrOpen() || (A.away && !A.awayDone)) return;   // (while the opening's checks run, everything goes into the summary)
  if (window.Arcade && window.Arcade.playing && window.Arcade.playing()) { A.flushT = setTimeout(arrFlush, 2000); return; }
  const l = arrLedger();
  const fresh = l.pend.filter(p => !A.onPage.has(p.id)).map(arrItem).filter(Boolean);
  if (!fresh.length) return;
  fresh.forEach(x => A.onPage.add(x.id));
  if (document.querySelector('.cashier') && !document.hidden) { arrSeen(fresh.map(x => x.id)); return; }   // (the till shows its own PAID! screen)
  A.card = A.card.concat(fresh);
  arrShow('live', A.card);
  A.log.push({ type: 'live', ids: fresh.map(x => x.id), at: Date.now() });
  arrCoin();
  if (document.hidden) { fresh.forEach(x => A.unseen.add(x.id)); arrSys(tr('Money arrived'), A.card.filter(x => A.unseen.has(x.id))); }
  else arrSeen(fresh.map(x => x.id));
}
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
  const A = arrS(); A.awayDone = true;
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
// called at the start of every render: notices the wallet opening (start, unlock, a wallet just set up)
function arrRendered() {
  try {
    const A = arrS(), open = arrOpen();
    if (open && !A.wasOpen) arrAwayStart();
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
function arrSysBody(items) {
  if (items.length === 1) { const x = items[0]; return `${tr(ARR_LABEL[x.k])}: +${money(x.a)} · ${mintName(x.m)}`; }
  return arrGroups(items).map(g => `${tr(ARR_LABEL[g.k])}: ${arrCount(g.n)} · +${money(g.a)}`).join('\n');
}
async function arrSys(title, items) {
  if (!arrSysOk() || !items.length) return;
  // after a lock it may be replaced by "Money arrived, unlock to see"; not when a duress PIN is set up (or open)
  const opt = { body: arrSysBody(items), tag: ARR_TAG, renotify: true, icon: 'icon-192.png', silent: !S.prefs.sound, data: { g: vault.decoy || (vault.on && vault.data && vault.data.duress) ? 0 : 1 } };
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
  return 'When money arrives while NUTCADE is open in another tab or window. Shown by this device only: no push service, nothing is sent anywhere. While locked they show no amounts.';
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
