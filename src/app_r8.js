/* ===================== Round 8 (1.13): spending limit, duress PIN, request-size limits ===================== */

/* ---------- spending limit ----------
   Two optional limits for the whole wallet: "ask for the PIN above X SAT" for one payment, and "at most Y SAT a day"
   (the last 24 hours, rolling). They apply to every way sats leave: every payment goes through one of four steps
   (making a token, getting ecash ready for a Lightning or on-chain payment, handing over ecash offline, locking an
   Extra Life), and each of them asks limitGate() first, with the most the payment can cost: the amount plus every
   fee (the mint's fee to spend ecash, the fee a token carries for its receiver, the Lightning fee reserve).
   The day counts what really left: every outgoing line in the history of the last 24 hours (amount + fee; a failed
   payment only what the mint kept, a token taken back only its fee), every step written down but not finished yet
   (the journal: a payment interrupted by a reload, or in flight in another tab), and the payments in flight in this
   tab. The check and the hold on the amount happen together, in one go, so two taps (or two mints paying at once)
   can't both fit under what is left. The limits live with the wallet: inside the PIN vault when there is a PIN, and
   changing or removing them needs the PIN. Over a limit, the payment is held with the amount and when the day frees
   up; with a PIN, entering it lets that one payment go over. */
const DAY_MS = 86400e3;
S.limits = store.get('limits', null);   // { per, day } in SAT; 0 or missing = off
const limHolds = new Map();   // payments in flight in this tab: id -> { a, at }
let limitOK = null;           // the PIN was entered for the payment being retried: { until } (used once, and gone when that retry ends)
const limitsOn = () => !!(S.limits && (S.limits.per > 0 || S.limits.day > 0));
// what an outgoing history line took from the wallet
function limValue(t) {
  if (!isSatAcct(t.mint)) return 0;   // the spending limit counts SAT only: a USD, EUR or CHF payment is never added to it, nor compared with it
  if (t.status === 'failed' || t.status === 'expired') return 0;   // nothing left (what the mint kept is its own fee line)
  if (t.status === 'reclaimed') return num(t.fee);                  // the token came back: only its fee left
  return num(t.amount) + num(t.fee);
}
// every entry of the last 24 hours that counts toward the day: [{ at, v }]
function limEntries(now = Date.now()) {
  const since = now - DAY_MS, g = new Map(), out = [];
  const add = (id, at, v) => { if (!(v > 0)) return; if (!id) { out.push({ at, v }); return; } const x = g.get(id); if (x) { x.v += v; x.at = Math.min(x.at, at); } else g.set(id, { at, v }); };
  for (const t of S.txs) if (t.type === 'out' && (t.ts || 0) > since && t.note !== 'Ecash already spent elsewhere' && !t.upkeep) add(t.limId, t.ts, limValue(t));   // (a keyset check-up isn't spending: the coins stayed this wallet's)
  for (const o of S.ops) if (o.lim && (o.lim.at || o.created || 0) > since) add(o.lim.id, o.lim.at || o.created, num(o.lim.a));
  for (const [id, h] of limHolds) { const x = g.get(id); if (x) { x.v = Math.max(x.v, h.a); } else g.set(id, { at: h.at, v: h.a }); }
  return out.concat([...g.values()]);
}
const limitUsed = (now = Date.now()) => limEntries(now).reduce((t, e) => t + e.v, 0);
const limitLeft = () => S.limits && S.limits.day > 0 ? Math.max(0, S.limits.day - limitUsed()) : null;
// how long until `spend` fits in the day again (ms), or null if it never can
function limitWait(spend, now = Date.now()) {
  const day = S.limits.day; if (spend > day) return null;
  const es = limEntries(now).sort((a, b) => a.at - b.at); let used = es.reduce((t, e) => t + e.v, 0);
  for (const e of es) { used -= e.v; if (used + spend <= day) return Math.max(60e3, e.at + DAY_MS - now); }
  return 60e3;
}
const waitText = ms => { const m = Math.ceil(ms / 60e3), h = Math.floor(m / 60); return h ? `It frees up in ${h} h ${m % 60} min.` : `It frees up in ${m} min.`; };
function limitErr(kind, spend) {
  const L = S.limits, e = new Error('');
  if (kind === 'per') e.message = `This payment is ${money(spend)} with fees, over your limit of ${money(L.per)} a payment.`;
  else {
    const left = Math.max(0, L.day - limitUsed());
    e.message = spend > L.day ? `This payment is ${money(spend)} with fees, more than your limit of ${money(L.day)} a day.` : `This payment is ${money(spend)} with fees, and ${money(left)} of your ${money(L.day)} a day is left.`;
    const w = limitWait(spend); if (w != null) e.wait = waitText(w);
  }
  e.limit = { kind, spend }; e.keep = true;
  return e;
}
/* The one check every payment goes through. spend = the most it can take, fees included. Returns a hold, released by
   the caller once the payment is on record (or failed): { id, release() }. opts.grant: part of a payment already
   checked as a whole (several mints paying one invoice). */
function limitGate(spend, opts = {}) {
  spend = Math.max(0, Math.ceil(num(spend)));
  const none = { id: null, release() {} };
  if (opts.free) return none;
  if (opts.grant) return { id: opts.grant.id, part: true, release() {} };
  if (!limitsOn()) return none;
  const ok = opts.approved || (!opts.auto && limitOK && limitOK.until > Date.now());   // (an app paying through Wallet Connect never uses a PIN you entered here)
  if (ok) limitOK = null;   // the PIN was for this one payment
  else {
    if (S.limits.per > 0 && spend > S.limits.per) throw limitErr('per', spend);   // (Wallet Connect too: it can't ask for the PIN, so it is refused, and nothing is booked to its budget)
    if (S.limits.day > 0 && limitUsed() + spend > S.limits.day) throw limitErr('day', spend);
  }
  const id = uid(); limHolds.set(id, { a: spend, at: Date.now() });
  return { id, release() { limHolds.delete(id); } };
}
// what a step's journal record carries: the hold's amount (a part of a payment checked as a whole carries none: the whole is held)
const limRec = h => ({ id: h.id, a: !h.part && limHolds.has(h.id) ? limHolds.get(h.id).a : 0 });
// a payment made of several parts (several mints paying one invoice): checked once as a whole, the parts then use it
function limitGrant(total) { const h = limitGate(total); return { id: h.id || uid(), release: h.release }; }
/* The most a swap that makes `amount` (for a token, or for a payment) can take from the balance, and the coins it
   will use: the library's own numbers (the outputs with the receiver's fee, then the coins it picks), so the check
   and the swap agree to the SAT. */
function swapPlan(w, have, amount, sendOT, url) {
  try {
    const ks = w.getOutputKeyset(), ot = w.configureOutputs(w.parseAmount(amount, 'limit'), ks, sendOT || w.defaultOutputType(), true);
    const h = num(w.preparedTotal(ot)); let sel = w.selectProofsToSend(have, L.Amount.from(h), true);
    if (!sel.send.length) return null;
    const m = url ? mintMax(url) : 0;
    if (m && sel.send.length > m) { sel = capPick(w, have, h, m); if (!sel) return { tooMany: m, h, n: 0, spend: 0 }; }   // (never more coins in than the mint takes)
    return { spend: h + num(w.getFeesForProofs(sel.send)), sel, h, n: (ot.denominations || []).length || bitsOf(h) };   // (n: the outputs the library asks for: the amount's coins plus the receiver's fee as coins of its own)
  } catch (e) { return null; }
}
// until the swap: the library's own pick, so the swap spends exactly the coins the check counted
// (strict, tokens: a pick fixed in advance is used exactly, or the step stops: never another pick that could cost more)
async function withPick(w, sel, fn, strict) {
  if (strict && (!sel || !w._selectProofs)) throw new Error('These coins are no longer here. Nothing was sent.');
  if (!sel || !w._selectProofs) return fn();
  const pick = w._selectProofs, want = new Set(sel.send.map(p => p.secret));
  w._selectProofs = (ps, ...a) => { const send = ps.filter(p => want.has(p.secret)); if (send.length === want.size) return { keep: ps.filter(p => !want.has(p.secret)), send }; if (strict) throw new Error('These coins are no longer here. Nothing was sent.'); return pick.call(w, ps, ...a); };
  try { return await fn(); } finally { w._selectProofs = pick; }
}
function feeMax(w, have, amount) {   // when the library can't say: as if every coin is spent, plus the receiver's fee
  let f = 0; try { f = num(w.getFeesForProofs(have)); } catch (e) {}
  const coins = a => { let c = 0; for (let x = a; x > 0; x = Math.floor(x / 2)) c += x % 2; return c; };
  let r = 0; try { for (let j = 0; j < 4; j++) r = num(w.getFeesForKeyset(coins(amount + r), have[0].id)); } catch (e) {}
  return amount + f + r;
}
// (each part on its own, so each is translated whole)
const limitSummary = () => {
  if (!limitsOn()) return ['OFF'];
  const a = []; if (S.limits.per > 0) a.push(`PIN above ${money(S.limits.per)}`); if (S.limits.day > 0) a.push(`${money(S.limits.day)} a day`);
  return a;
};
function limitPanel() {
  return `<div class="row between tiny" style="align-items:flex-start;gap:10px"><span>Spending limit</span><span style="color:${limitsOn() ? 'var(--lime)' : 'var(--dim)'};text-align:right;display:grid">${limitSummary().map(x => `<span>${esc(x)}</span>`).join('')}</span></div>
    ${limitsOn() && S.limits.day > 0 ? `<div class="row between tiny"><span>Left today</span><span style="color:var(--ink)">${money(limitLeft())}</span></div>` : ''}
    <button class="btn sm" data-act="limOpen">${limitsOn() ? 'Change spending limit' : 'Set a spending limit'}</button>`;
}
function openLimits() {
  const L = S.limits || {};
  openSheet('Spending limit', `<p style="margin:0">Limits for every way sats leave this wallet: Lightning, ecash, gifts, requests, Wallet Connect, zaps and moves between mints. Fees count too.</p>
    <div class="tiny muted">The limit is in SAT and counts SAT only. USD, EUR and CHF ecash is outside it.</div>
    <div class="field"><label for="limPer">Ask for my PIN above (SAT, one payment)</label><input id="limPer" class="inp" inputmode="numeric" autocomplete="off" placeholder="Off" value="${L.per > 0 ? fmt(L.per) : ''}" ${vault.on ? '' : 'disabled'}>
      ${vault.on ? '' : '<div class="tiny muted">Set a PIN first to use this one.</div>'}</div>
    <div class="field"><label for="limDay">At most (SAT, any 24 hours)</label><input id="limDay" class="inp" inputmode="numeric" autocomplete="off" placeholder="Off" value="${L.day > 0 ? fmt(L.day) : ''}"></div>
    <div class="tiny muted">Leave a box empty to turn that limit off.${vault.on ? ' Changing or removing a limit needs your PIN, and your PIN lets one payment go over.' : ' Without a PIN anyone holding this phone can change them.'}</div>
    <button class="btn solid gold block" data-act="limSave">Save</button><div id="sheetErr"></div>`);
}
function readLimit(id) {
  const el = $('#' + id); if (!el) return 0;
  const s = String(el.value || '').trim(); if (!s) return 0;
  if (el.disabled) throw new Error('Set a PIN first to use the limit for one payment.');   // (never dropped without a word)
  const n = parseSat(s); if (!(n > 0)) throw new Error('Type a limit above 0, or leave the box empty to turn it off.');
  return n;
}
const limWant = { v: null };
function applyLimits(v) {
  S.limits = v.per || v.day ? { per: v.per || 0, day: v.day || 0 } : null;
  store.set('limits', S.limits); save();
  closeSheet(); refresh(); sfx('coin'); toast(S.limits ? 'Spending limit saved' : 'Spending limit off', 'lime');
}
/* Over a limit: the payment waits on a screen of its own (over the sheet it came from, which stays as it was). With a
   PIN, entering it lets this one payment through; without one, the limit is changed in Settings. */
let limitRetry = null;
function limitAsk(e, retry) {
  document.getElementById('limitLayer')?.remove();
  const box = document.createElement('div'); box.id = 'limitLayer';
  limitRetry = async () => { try { await retry(); } finally { limitOK = null; } };   // (the PIN is for this payment's retry only, whatever coins it ends up using)
  pinUI.mode = 'limitOK'; pinUI.value = ''; pinUI.limit = e.limit;
  box.innerHTML = `<div class="scrim" style="align-items:center;z-index:260"><div class="sheet lim-sheet" role="alertdialog" aria-modal="true" aria-label="Over your spending limit">
    <div class="pb-h">OVER YOUR LIMIT</div>
    <p class="lim-msg" style="margin:0">${esc(e.message)}</p>${e.wait ? `<p class="th" style="margin:0">${esc(e.wait)}</p>` : ''}
    ${vault.on ? padHTML('ENTER PIN', 'Enter your PIN to let this one payment through.') : `<p style="margin:0">Nothing was sent. You can change the limit in Settings → Security.</p>`}
    <button class="btn block" data-act="limitNo">Cancel</button></div></div>`;
  document.body.appendChild(box);
  if (LANG !== 'en') trNode(box);
  sfx('err');
}
function limitClose() { document.getElementById('limitLayer')?.remove(); limitRetry = null; if (pinUI.mode === 'limitOK') pinUI.mode = null; }

/* ---------- PIN guard ----------
   The spending limit protects an unlocked phone only if nothing hands over the whole wallet around it. So with a PIN,
   every step that could do that asks for it first: showing the recovery phrase, the backup file (downloading it or
   showing its text), importing a backup, restoring a wallet from 12 words, connecting or editing an app (Wallet Connect),
   resetting the wallet, exporting a mint's ecash and making a new phrase. (Changing the spending limit and every PIN
   change already need it.) Restoring asks whatever the balance: the phrase decides where every later deposit, refund,
   change and Lightning-address payment lands, not just today's sats.
   The PIN asked is the open wallet's own (in the duress PIN's wallet, its PIN), through the same pad, check, wrong-PIN
   count and wait as a payment over the limit, so every wallet asks the same way. Face ID / fingerprint isn't offered
   here, as for the limit. A step that opens a form (restore, import, Wallet Connect: connecting an app or editing one,
   reset) asks before the form opens, and the form's button goes ahead only while that same form is open. A PIN is
   for the pad it was typed on: if that pad was closed while the PIN was checked (another step started, the same one
   again included), nothing goes ahead and a guard pad opened meanwhile is closed too, so the step is started again
   and asks again. Without a PIN, and on the start screen before a wallet exists, nothing is asked. */
const GUARD = {
  seed: ['Recovery phrase', 'Enter your PIN to see your 12 words.'],
  backup: ['Backup file', 'Enter your PIN to get your backup file.'],
  import: ['Import backup', 'Enter your PIN to import a backup.'],
  restore: ['Restore wallet', 'Enter your PIN to restore a wallet from 12 words.'],
  nwc: ['Connect an app', 'Enter your PIN to connect an app to this wallet.'],
  nwcEdit: ['Wallet Connect', 'Enter your PIN to change this connection.'],
  reset: ['Reset wallet', 'Enter your PIN to reset this wallet.'],
  export: ['Export ecash', 'Enter your PIN to export your ecash.'],
  newseed: ['New recovery phrase', 'Enter your PIN to make a new recovery phrase.'],
  phone: ['Back up with my phone', 'Enter your PIN to back up your 12 words with your phone.']
};
const guard = { run: null, pass: null };
const guardOn = () => !!(vault.on && vault.open && (S.seed || anyBalance()));
function pinGuard(k, fn) {
  guard.pass = null;
  if (!guardOn()) return fn();
  openPinSheet('guard', GUARD[k][0], { title: 'ENTER PIN', text: GUARD[k][1] });
  guard.run = { k, fn, sheet: $('#layer .sheet') };
}
// the right PIN was entered on the guard's pad for step g (taken when OK was pressed): that step goes ahead, only
// while its own pad is still the one open (a form it opens keeps the pass while it is open). Otherwise nothing goes
// ahead, and a guard pad for another step (or the same step started again) opened meanwhile is closed: it asks again.
function guardGo(g) {
  const cur = guard.run;
  if (!g || cur !== g || !g.sheet || !g.sheet.isConnected || g.sheet !== $('#layer .sheet')) {
    if (cur && cur !== g) { guard.run = null; if (pinUI.mode === 'guard') pinUI.mode = null; if (cur.sheet && cur.sheet.isConnected) closeSheet(); }
    return;
  }
  guard.run = null; pinUI.mode = null;
  closeSheet(); g.fn();
  const sheet = $('#layer .sheet'); guard.pass = sheet ? { k: g.k, sheet } : null;
}
const guardHeld = k => !guardOn() || !!(guard.pass && guard.pass.k === k && guard.pass.sheet.isConnected && guard.pass.sheet === $('#layer .sheet'));

/* ---------- duress PIN ----------
   A second PIN that opens a small, separate wallet (its own 12 words, its own balance and history) instead of this
   one, for when someone forces you to unlock NUTCADE. The vault always has room for it: with a PIN set there is
   always a second part, filled with random bytes until a duress PIN is set, so the vault looks the same with or
   without one. Each PIN unlocks its own data key; every try runs both key derivations and both unwraps, so neither
   the time it takes nor the message says which part opened, or that there is a second one. With the duress PIN's
   wallet open, NUTCADE reads and writes only that wallet's encrypted part (the device's own settings aside): the
   real wallet's data is never decrypted, read or written, and it has no key in memory. The real wallet keeps the
   duress wallet's data key, so only the real PIN can set, change or remove the duress PIN. What it can't hide: see
   "Duress PIN" in the README (someone reading the browser's storage directly sees how big each part is, and the
   real wallet's plain settings such as its mint list). */
/* PIN changes (changing the PIN, setting, changing or turning off a duress PIN, removing the PIN) share one small
   allowance: 3 in any 24 hours, kept for the device (the same in every wallet, and not reset by unlocking). Past it,
   or for a step the open wallet can't take (inside the duress PIN's wallet: a new PIN that would open another part of
   the vault, a duress PIN of its own, removing the PIN, setting up Face ID), the answer is the same sentence, and the
   allowance is used up, so it reads exactly as when the allowance has run out. */
const PIN_CHANGES = 3;
const pinChanges = () => (lsGet('pinchg', []) || []).filter(t => t > Date.now() - DAY_MS);
const pinChangeLeft = () => PIN_CHANGES - pinChanges().length;
const pinChangeErr = () => { const e = new Error("PIN changes aren't available right now. Try again later."); e.keep = true; return e; };
function pinChangeCheck() { if (pinChangeLeft() <= 0) throw pinChangeErr(); }
function pinChangeUse(all) { const l = pinChanges(); do l.push(Date.now()); while (all && l.length < PIN_CHANGES); lsSet('pinchg', l); }
function pinChangeRefuse() { pinChangeUse(true); return pinChangeErr(); }
async function realOpens(pin) { const rec = raw.get('vault', {}); try { await unwrapDek(rec.pin, await kekFromPin(pin, b64d(rec.kdf.salt), rec.kdf.iter)); return true; } catch (e) { return false; } }
const randBox = n => ({ iv: b64e(rnd(12)), ct: b64e(rnd(n)) });
// an unused second part: random bytes shaped like a real one (salt, wrapped key, a small wallet's data)
function fillerSlot() { return { kdf: { alg: 'PBKDF2-SHA256', iter: PBKDF2_ITER, salt: b64e(rnd(16)) }, pin: randBox(48), data: randBox(1800 + ((r => (r[0] << 8 | r[1]) % 2400)(rnd(2)))) }; }
// one PIN try: both parts, always, in parallel
async function pinToKeys(pin) {
  const rec = raw.get('vault'), slot = rec.slot;
  const [k1, k2] = await Promise.all([kekFromPin(pin, b64d(rec.kdf.salt), rec.kdf.iter), kekFromPin(pin, slot ? b64d(slot.kdf.salt) : rnd(16), slot ? slot.kdf.iter : rec.kdf.iter)]);
  const [d1, d2] = await Promise.all([unwrapDek(rec.pin, k1).catch(() => null), slot ? unwrapDek(slot.pin, k2).catch(() => null) : unwrapDek(rec.pin, k2).catch(() => null)]);
  return d1 ? { dek: d1, decoy: false } : d2 && slot ? { dek: d2, decoy: true } : null;
}
async function slotOpens(pin) {
  const slot = raw.get('vault', {}).slot; if (!slot) return false;
  try { await unwrapDek(slot.pin, await kekFromPin(pin, b64d(slot.kdf.salt), slot.kdf.iter)); return true; } catch (e) { return false; }
}
async function openPart(dek, decoy) {
  vault.decoy = !!decoy;
  try { await openVault(dek); } catch (e) { vault.decoy = false; vault.open = false; vault.data = {}; throw e; }
  if (!decoy) {
    const rec = raw.get('vault'); if (!rec.slot) { rec.slot = fillerSlot(); raw.set('vault', rec); }   // (a vault from before 1.13 gets its second part)
    // records a vault from before 1.13 left in plain storage (the mint list, counters, logs, settings) move in
    const plain = plainWalletData(), d = vault.data; let moved = false;
    for (const [k, v] of Object.entries(plain)) {
      if (v == null || (k === 'prefs' && !Object.keys(v).length)) continue;
      moved = true;
      if (k === 'counters') { d.counters = d.counters || {}; for (const id in v) d.counters[id] = Math.max(d.counters[id] || 0, v[id] || 0); }
      else if (k === 'prefs') d.prefs = Object.assign({}, v, d.prefs || {});
      else if (d[k] === undefined || d[k] === null) d[k] = v;
    }
    if (moved) { queueVaultWrite(); await vault.chain; if (!vaultBad()) clearPlainWallet(); }   // (the plain copies stay until the vault holding them is saved)
  }
  if (lsGet('pinchg', null) == null) lsSet('pinchg', []);
}
// everything NUTCADE loaded from storage before the PIN, read again from the wallet that was opened
function loadWalletState() {
  const d = vault.data;
  for (const k in wallets) delete wallets[k];
  S.mints = d.mints || []; S.active = d.active || null; S.counters = d.counters || {}; S.opsdone = d.opsdone || [];
  for (const k of WALLET_PREFS) delete S.prefs[k];
  Object.assign(S.prefs, d.prefs || {});
  for (const k of WALLET_PREFS) if (S.prefs[k] === undefined && PREF_DEFAULTS[k] !== undefined) S.prefs[k] = PREF_DEFAULTS[k];   // (as a new wallet has them: the same screens either way)
  S.auth = d.auth || {}; try { au.mgr.clear(); au.out.clear(); au.cool.clear(); } catch (e) {}   // (each wallet its own mint logins: app_auth.js)
  S.piggy = d.piggy || { saved: 0 }; S.mintlog = d.mintlog || {}; S.mintkeys = d.mintkeys || {}; S.heirlooms = d.heirlooms || []; S.challenges = d.challenges || []; S.blocked = d.blocked || [];
  seenWraps.clear(); for (const x of d.dmseen || []) seenWraps.add(x);
  nwcSeen.clear(); for (const x of d.nwcseen || []) nwcSeen.add(x);
  nzSeen.clear(); for (const x of d.nzseen || []) nzSeen.add(x);
  myGen = raw.get('gen', 0);
  if (window.Trophies && window.Trophies.reload) window.Trophies.reload();
}
const duressOn = () => !!(vault.open && !vault.decoy && vault.data.duress);
function duressPanel() {
  if (!vault.on) return '';
  return `<div class="row between tiny"><span>Duress PIN</span><span style="color:${duressOn() ? 'var(--lime)' : 'var(--dim)'}">${duressOn() ? 'ON' : 'OFF'}</span></div>
    <p class="th" style="margin:0">A second PIN that opens a small separate wallet instead of this one, if someone ever forces you to unlock NUTCADE.</p>
    <button class="btn sm" data-act="duressOpen">${duressOn() ? 'Duress PIN settings' : 'Set a duress PIN'}</button>`;
}
const duressUI = { old: '', pin: '', change: false };
function openDuress() {
  duressUI.old = duressUI.pin = ''; duressUI.change = false;
  openPinSheet('duressOld', 'Duress PIN', { title: 'ENTER PIN', text: 'Enter your PIN first.' });
}
const duressNewPad = () => { nextPad('duressNew'); setBody(padHTML('CHOOSE A DURESS PIN', `${PIN_MIN} to ${PIN_MAX} digits, different from your PIN. It opens a small separate wallet instead of this one.`) + '<div id="sheetErr"></div>'); };
function duressMenu() {
  setBody(`<p style="margin:0">Your duress PIN opens a small separate wallet instead of this one. Anyone who unlocks NUTCADE with it sees only that wallet.</p>
    <button class="btn block gold" data-act="duressChange">Change duress PIN</button>
    <button class="btn block red" data-act="duressOff">Turn off duress PIN</button>
    <button class="btn block" data-act="close">Done</button><div id="sheetErr"></div>`);
}
function duressFund() {
  setBody(`<p style="margin:0">The duress PIN's wallet starts empty, with its own 12 words. Put a small amount in it from the mint you're using now, so it looks used.</p>
    <div class="field"><label for="duressAmt">Sats for it (SAT, optional)</label><input id="duressAmt" class="inp amount" inputmode="numeric" placeholder="0" autocomplete="off"></div>
    <button class="btn solid gold block" data-act="duressMake">Set duress PIN</button><div id="sheetErr"></div>`);
}
async function decoyKey() { return crypto.subtle.importKey('raw', b64d(vault.data.duress.dek), { name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']); }
async function sealBox(key, obj) { const iv = rnd(12); const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(JSON.stringify(obj))); return { iv: b64e(iv), ct: b64e(ct) }; }
async function openBox(key, box) { return JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(box.iv) }, key, b64d(box.ct)))); }
// set it up: the sats for it leave this wallet as a token, which the other wallet claims the first time it opens
async function makeDuress(pin, amount) {
  if (vault.decoy) throw pinChangeRefuse();
  if (vault.data.duress) throw new Error('A duress PIN is already set.');
  pinChangeCheck();
  const url = S.active, m = activeMint(); if (amount > 0 && !m) throw new Error('Add a mint first.');
  let token = null;
  if (amount > 0) { const tx = await sendEcash(amount, 'Sats for the duress PIN wallet', null, url, { approved: true }); token = tx.token; updTx(tx.id, { duressFund: true }); }   // (it counts toward the spending limit; the PIN just entered lets it through)
  const created = Date.now(), dek = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']);
  const data = { seed: { mnemonic: newMnemonic(), backedUp: true, created, secured: true }, mints: m ? [(({ ks, ...r }) => r)(JSON.parse(JSON.stringify(m)))] : [], active: m ? url : null, proofs: {}, pending: [], quotes: [], ops: [], opsdone: [], counters: {},
    txs: token ? [{ id: uid(), ts: created, type: 'in', method: 'ecash', amount, mint: url, note: '', status: 'pending', incoming: cleanToken(token), offline: true, fee: 0 }] : [], prefs: {}, requests: [], contacts: [], nwc: [] };
  const salt = rnd(16), kek = await kekFromPin(pin, salt, PBKDF2_ITER);
  const slot = { kdf: { alg: 'PBKDF2-SHA256', iter: PBKDF2_ITER, salt: b64e(salt) }, pin: await wrapDek(dek, kek), data: await sealBox(dek, data) };
  vault.data.duress = { dek: b64e(await crypto.subtle.exportKey('raw', dek)), at: created };
  queueVaultWrite(); await vault.chain;
  if (vaultBad()) { delete vault.data.duress; throw new Error("This browser won't save data. Free up space and try again."); }   // (its sats stay a token in this wallet's history, to take back)
  const rec = raw.get('vault'); rec.slot = slot; if (!raw.set('vault', rec)) throw new Error("This browser won't save data.");
  pinChangeUse();
  if (token) await fundDecoyNow(dek, data, url, token).catch(() => {});   // (if this can't finish, the token waits in that wallet and is claimed the first time it opens)
}
/* The sats for the duress PIN's wallet become its own coins right away (its 12 words, its counters), so a restore of
   the real 12 words never finds them and the real wallet can never spend them. Written down like any step: first the
   counters the mint will sign for, in that wallet's own journal (in its part of the vault), then the swap, then the
   coins. Interrupted, that wallet settles the step from its journal the first time it opens; refused, the token is
   left waiting for it, as before. */
async function fundDecoyNow(dek, data, url, token) {
  const ctrs = data.counters, cs = {
    async reserve(id, n) { const st = ctrs[id] || 0; if (n > 0) ctrs[id] = st + n; return { start: st, count: n }; },
    async reserveAt(id, start, count) { ctrs[id] = start + count; return { start, count }; },
    async advanceToAtLeast(id, m) { if ((ctrs[id] || 0) < m) ctrs[id] = m; },
    async snapshot() { return Object.assign({}, ctrs); }, async setNext(id, n) { ctrs[id] = n; } };
  const w = new L.Wallet(authMint(acctUrl(url)), { unit: acctUnit(url), bip39seed: L.mnemonicToSeedSync(data.seed.mnemonic), counterSource: cs }); await loadFresh(w);   // (with this device's login at a mint that asks for one)
  const ps = (w.decodeToken(cleanToken(token)).proofs || []), m = mintMax(url);
  const wait = (data.txs || []).find(t => t.incoming === cleanToken(token) && t.status === 'pending');   // (the token's line in that wallet: settled with the step, if it comes to that)
  const op = { id: uid(), kind: 'receive', mint: url, inputs: ps.map(p => p.secret), amount: 0, note: '', locked: false, extra: false, txId: null, tx: null, follow: wait ? { k: 'incoming', txId: wait.id, reqId: null } : null, own: null, created: Date.now(), ctr: [], outs: [], mk: 1 };
  const prepared = await w.prepareSwapToReceive(cleanToken(token), { onCountersReserved: u => { if (u && u.count > 0) op.ctr.push({ id: u.counterKey, start: u.start, n: u.count }); } });
  const outs = (prepared.keepOutputs || []).length + (prepared.sendOutputs || []).length;
  if (m && (ps.length > m || outs > m)) return;   // (more than the mint takes in one request: claimed in parts when that wallet opens)
  op.amount = (prepared.keepOutputs || []).reduce((t, o) => t + num(String(o.blindedMessage.amount)), 0);
  const fallback = data.txs, seal = async d => { const r = raw.get('vault'); if (!r || !r.slot) throw new Error('gone'); r.slot.data = await sealBox(dek, d); raw.set('vault', r); };
  data.txs = []; data.ops = [op]; await seal(data);
  let got;
  try { got = (await w.completeSwap(prepared)).keep; }
  // refused: the mint signed nothing for this request, and the token waits in that wallet as before. But "already
  // pending" (another copy of this very request is at work at the mint) keeps the step in that wallet's journal too, so
  // if that copy is signed, its coins are settled from the counters on record the first time it opens.
  catch (e) {
    if (isRefusal(e)) { data.txs = fallback; if (pendingRefusal(e)) { op.refused = 1; op.pendRef = 1; } else data.ops = []; await seal(data); }
    throw e;
  }
  const coins = plain(got), recvd = sum(coins);
  data.proofs = { [url]: coins }; data.ops = []; data.opsdone = [op.id];
  data.txs = [{ id: uid(), ts: Date.now(), type: 'in', method: 'ecash', amount: recvd, fee: Math.max(0, sum(ps) - recvd), mint: url, note: '', status: 'done' }];
  await seal(data);
  const t = S.txs.find(x => x.token === token); if (t && t.status === 'pending') updTx(t.id, { status: 'claimed' });
}
async function changeDuress(pin) {
  if (vault.decoy) throw pinChangeRefuse();
  const dek = await decoyKey(), salt = rnd(16), kek = await kekFromPin(pin, salt, PBKDF2_ITER);
  const rec = raw.get('vault'); rec.slot.kdf = { alg: 'PBKDF2-SHA256', iter: PBKDF2_ITER, salt: b64e(salt) }; rec.slot.pin = await wrapDek(dek, kek);
  raw.set('vault', rec);
}
// turn it off: its sats come back to this wallet. Each of its tokens and coins is saved here first (as ecash waiting to
// be claimed, in the same vault), then its part becomes random bytes again, then they are claimed: an interruption at
// any point loses nothing.
async function duressOff() {
  if (vault.decoy) throw pinChangeRefuse();
  if (!vault.data.duress) return 0;
  const rec = raw.get('vault'); let d = null;
  try { d = await openBox(await decoyKey(), rec.slot.data); } catch (e) {}
  const toks = [];
  if (d) {
    for (const [u, ps] of Object.entries(d.proofs || {})) if (ps && ps.length) toks.push(tokEnc({ mint: u, proofs: ps, unit: 'sat' }));
    for (const t of d.txs || []) if (t.status === 'pending' && t.incoming) toks.push(t.incoming);
    for (const t of d.txs || []) if (t.type === 'out' && t.status === 'pending' && t.token && !t.locked) toks.push(t.token);
    for (const p of d.pending || []) if (p.proofs && p.proofs.length && !p.paid) toks.push(tokEnc({ mint: p.mint, proofs: p.proofs, unit: 'sat' }));
  }
  const ids = [];
  for (const t of toks) { try { const meta = peekToken(t); if (!S.mints.find(m => m.url === meta.mint)) await addMint(meta.mint, { dropped: true }).catch(() => {}); const h = holdIncoming(t, "Back from the duress PIN's wallet"); updTx(h.id, { mine: true, back: 'hand' }); ids.push(h.id); } catch (e) {} }
  save(); await vault.chain;
  if (vaultBad()) throw new Error("This browser won't save data. Free up space and try again.");   // (its part is never wiped before its sats are saved here)
  const now = raw.get('vault') || rec; now.slot = fillerSlot(); raw.set('vault', now);   // (with the wallet as just saved, its sats from there included)
  delete vault.data.duress; queueVaultWrite(); await vault.chain;
  const back = {};   // (claimed now where the mint answers, one total per unit; the rest stays saved and is claimed later, like ecash saved offline)
  for (const id of ids) { const t = txById(id); if (!t) continue; try { const nt = await receiveToken(t.incoming, t.note, { follow: { k: 'incoming', txId: id, reqId: null } }); incomingClaimed({ txId: id, reqId: null }, nt); addUnit(back, txUnit(nt), nt.amount); } catch (e) {} }
  return listEmpty(back) ? '' : moneyList(back);
}
// Reset wallet, inside the duress PIN's wallet: that wallet starts over empty (still opened by its PIN); the rest of
// the vault, the real wallet included, is left exactly as it was
async function resetPart() { npcSocketStop(); dmStop(); nzStop(); vault.data = {}; queueVaultWrite(); await vault.chain; }
// the PIN of the wallet that is open, for the steps that need it (a limit, the duress PIN). live(): the pad it was
// typed on is still open for the same step (see pinSubmit); what the step acts on is taken when OK is pressed, and
// once the PIN is checked the step goes ahead only if nothing changed meanwhile (the PIN is never used for another step)
async function pinMore(m, v, busy, live) {
  const f = pinFails(); if (f.until > Date.now()) return pinError(`Wait ${Math.ceil((f.until - Date.now()) / 1000)}s before trying again.`);
  const check = async () => { busy('CHECKING…'); if (await pinToDek(v)) { raw.del('pinfails'); return true; } notePinFail(); if (live()) pinError('That PIN is wrong.'); return false; };   // (a wrong try is counted even on a pad closed meanwhile)
  if (m === 'limitOK') { const r = limitRetry; if (!(await check())) return; if (!live() || !r || limitRetry !== r) return; limitOK = { until: Date.now() + 120e3 }; limitClose(); sfx('coin'); r(); return; }
  if (m === 'limitSave') { const want = limWant.v; if (!(await check())) return; if (!live() || !want || limWant.v !== want) return; applyLimits(want); return; }
  if (m === 'guard') { const g = guard.run; if (!(await check())) return; guardGo(live() ? g : null); return; }
  if (m === 'duressOld') {
    if (!(await check())) return; if (!live()) return; duressUI.old = v;
    try { pinChangeCheck(); if (vault.decoy) throw pinChangeRefuse(); } catch (e) { return pinError(e.message); }   // (the duress PIN's wallet has no room for a duress PIN of its own)
    if (duressOn()) duressMenu(); else duressNewPad(); return;
  }
  if (m === 'duressNew') { if (v === duressUI.old) return pinError('Your duress PIN has to differ from your PIN.'); duressUI.pin = v; nextPad('duressConfirm'); setBody(padHTML('CONFIRM DURESS PIN', 'Type the same duress PIN again.') + '<div id="sheetErr"></div>'); return; }
  if (m === 'duressConfirm') {
    if (v !== duressUI.pin) { duressNewPad(); return pinError("Those didn't match. Start again."); }
    if (await realOpens(v)) { if (!live()) return; duressNewPad(); return pinError('Your duress PIN has to differ from your PIN.'); }
    if (!live()) return;
    if (duressUI.change) { busy('ENCRYPTING…'); pinChangeCheck(); await changeDuress(v); pinChangeUse(); duressUI.pin = duressUI.old = ''; closeSheet(); refresh(); sfx('coin'); toast('Duress PIN changed', 'lime'); return; }
    pinUI.mode = null; duressFund(); return;
  }
}

/* ---------- mints that take only a few items per request (NUT-06 max_array_length) ----------
   A mint may say how many items any list in a request can hold (inputs, outputs, Ys). Every Nutshell mint says 1,000,
   so for nearly every payment nothing changes. Restores and state checks are always asked in pieces of at most that
   size. A mint with a small limit (under 128) gets payments built in steps: swaps of at most that many coins in and
   out, each one written in the journal like any swap, until the wallet holds exactly the coins the payment needs; the
   token is then made of those coins (or a locked one with one last swap), and a Lightning payment spends them. A crash
   between steps leaves only finished swaps (their coins are in the balance) and at most one open record, which
   settles like any other. A token with more coins than the mint takes is claimed in parts, each saved first. A mint
   without the field keeps the old behaviour. */
/* The smallest request limit NUTCADE works with (NUT-06 max_array_length). Every amount is at most 21 million BTC,
   under 2^51 SAT, so any amount is at most 51 coins. The biggest request a normal step makes: a token or the swap
   before a payment, with the amount's coins (51), the coins for the receiver's fee (6 at most) and the change (51):
   108 outputs; a payment's change outputs (51 at most) and a deposit's coins (51) are fewer; inputs are picked to
   stay within the mint's limit. So 128. Nutshell mints say 1,000. A mint below it can't be added; a mint already
   here that starts saying less takes no new deposits, and the sats there can still be moved out (in steps). */
const MIN_REQ = 128;
const belowMin = url => { const m = mintMax(url); return m > 0 && m < MIN_REQ; };
const minErr = url => { const m = mintMax(url), name = (S.mints.find(x => x.url === normUrl(url)) || {}).name || host(url); const e = new Error(`${name} only accepts ${m} coins per request; NUTCADE needs at least ${MIN_REQ}. It takes no new deposits here; you can still move your sats out.`); e.keep = true; return e; };
/* Every way money goes into a mint is checked first (Receive, which the cashier, LNURL vouchers and Wallet Connect's
   invoices use; a move into it; a token swapped into it; an on-chain deposit; a token claimed there; Extra Life; the
   Lightning address's mint), so nothing is paid that the mint could then never issue. */
function quoteFitErr(url, amount) {
  if (belowMin(url)) return minErr(url);
  const m = mintMax(url); if (!m || amount == null || bitsOf(amount) <= m) return null;
  return minErr(url);
}
// what a restore did at a mint below the minimum: your sats there found (to move out), or nothing there (not kept). Never a silent 0.
function lowRestored(urls) {
  return [...new Set(urls.map(normUrl))].filter(u => belowMin(u)).map(u => {
    const m = S.mints.find(x => x.url === u), name = esc((m || {}).name || host(u)), n = mintMax(u);
    return m ? `<div class="notice red">${name} now accepts only ${n} coins per request; NUTCADE needs at least ${MIN_REQ}. Your sats there were found, but it takes no new deposits: move them to another mint.</div>`
      : `<div class="notice red">${name} only accepts ${n} coins per request; NUTCADE needs at least ${MIN_REQ}. Nothing of yours was found there, so it wasn't added.</div>`;
  }).join('');
}
function minNotice(url) {
  if (!belowMin(url)) return '';
  return `<div class="notice red">This mint now accepts only ${mintMax(url)} coins per request; NUTCADE needs at least ${MIN_REQ}. It takes no new deposits. Move your sats out to another mint.</div>`;
}
/* Coins for one swap on a mint with a limit: never more than it takes. The library's pick, or else the biggest coins
   first (the fewest); null when even those are too many. */
function capPick(w, have, h, m) {
  const desc = have.slice().sort((a, b) => num(b.amount) - num(a.amount)), send = [];
  let t = 0;
  for (const p of desc) { if (send.length >= m) break; send.push(p); t += num(p.amount); if (t >= h + feeOfPs(w, send)) { const ids = new Set(send.map(x => x.secret)); return { send, keep: have.filter(x => !ids.has(x.secret)) }; } }
  return null;
}
// what a pay or move sheet shows: from a mint below the minimum (sats moving out, in steps) the change may come back
// only in part, so the most it can cost includes the coins the payment spends as they are
function costShown(url, amount, reserve) {
  const c = meltCost(url, amount, reserve); if (!belowMin(url)) return c;
  const w = (wallets[normUrl(url)] || {}).ready, pm = w ? planMelt(w, url, num(amount) + num(reserve)) : null;
  return pm ? Object.assign({}, c, { total: Math.max(c.total, pm.T + pm.fees) }) : c;
}
const changeNote = url => belowMin(url) ? `<div class="tiny muted">This mint accepts only ${mintMax(url)} coins per request, so part of the unused fee reserve may be kept by the mint. The total above includes it.</div>` : '<div class="tiny muted">Unused fee reserve comes back as change.</div>';
const manyErr = (url, m) => { const e = new Error(`${(S.mints.find(x => x.url === normUrl(url)) || {}).name || host(url)} accepts at most ${m} coins per request, and this payment would need more of your coins there. Try a smaller amount.`); e.keep = true; return e; };
// the limit the mint advertises (0: it says none), as it says it (a whole number from 1 to 10,000)
function mintMax(url) {
  const w = (wallets[normUrl(url)] || {}).ready; if (!w) return 0;
  try { const i = w.getMintInfo(), v = i && i._mintInfo ? i._mintInfo.max_array_length : null; if (v == null) return 0; const n = Math.floor(num(v)); return n >= 1 ? Math.min(n, 10000) : 0; } catch (e) { return 0; }
}
const smallMint = mintMax;   // (any advertised limit is honoured; the steps below are only taken when a request would go over it)
const outsOf = (w, plan) => { const s = sum(plan.sel.send) - num(w.getFeesForProofs(plan.sel.send)) - plan.h; return plan.n + bitsOf(Math.max(0, s)); };
// would this swap's one request go over the mint's limit (coins in, or coins out)?
function overLimit(w, url, plan) { const m = mintMax(url); if (!m) return false; if (!plan) return true; try { return plan.sel.send.length > m || outsOf(w, plan) > m; } catch (e) { return true; } }
// "too many items" from a mint that started enforcing a limit after NUTCADE read its info
const isTooMany = e => (e && e.status === 422) || /at most \d+ item|too many (items|inputs|outputs)|max(imum)?[ _]?(array|request)[ _]?length|should have at most/i.test(String((e && (e.raw || e.message)) || '') + ' ' + String(e && e.detail || ''));
async function refreshMint(url) { url = normUrl(url); delete wallets[url]; await getWallet(url); return mintMax(url); }
// once: a request refused for being too long settles its record (the mint signed nothing), the mint's info is read
// again, and the step is tried again in pieces that fit
async function tooManyRetry(url, fn) {
  try { return await fn(); }
  catch (e) {
    if (!isTooMany(e)) throw e;
    if (!(await refreshMint(url).catch(() => 0))) throw e;   // (no limit after all: some other refusal)
    if (e.op) await settleOp(e.op.id).catch(() => {});   // (asked in pieces the mint takes, now that its limit is known)
    return fn();
  }
}
const bitsOf = n => { let c = 0; for (let x = n; x > 0; x = Math.floor(x / 2)) c += x % 2; return c; };
const splitAmt = n => { const out = []; for (let b = 2 ** 52; b >= 1; b /= 2) if (n >= b) { out.push(b); n -= b; } return out; };
const lowBit = n => { let b = 1; while (n % (b * 2) === 0) b *= 2; return b; };
// the nearest amounts made of at most m coin sizes, below and above n
function fitAmounts(n, m) { const s = splitAmt(n); if (s.length <= m) return [n]; const lo = s.slice(0, m).reduce((a, b) => a + b, 0); return [lo, lo + lowBit(lo)]; }
const feeOfK = (w, k, id) => { try { return num(w.getFeesForKeyset(k, id)); } catch (e) { return 0; } };
const feeOfPs = (w, ps) => { try { return ps.length ? num(w.getFeesForProofs(ps)) : 0; } catch (e) { return 0; } };
// locked ecash on a mint with a small limit: the last swap's coins in sum to the token plus its fees, with no change,
// all in at most m coins out (the outputs as the library makes them: the amount's coins, then the receiver's fee)
function lockedPlan(w, url, amount, sendOT) {
  const m = mintMax(url), held = heldFree(url), kid = (() => { try { return w.keysetId; } catch (e) { return held[0] && held[0].id; } })();
  let out = 0, h = 0; try { const ot = w.configureOutputs(w.parseAmount(amount, 'limit'), w.getOutputKeyset(), sendOT, true); out = (ot.denominations || []).length; h = num(w.preparedTotal(ot)); } catch (e) { const r = rfeeFor(w, amount, kid); out = bitsOf(amount) + bitsOf(r); h = amount + r; }
  let T = 0; for (let k = 1; k <= m && !T; k++) { const t = h + feeOfK(w, k, kid); if (bitsOf(t) <= k && out <= m) T = t; }
  if (!T) { const near = fitAmounts(amount, Math.max(1, m - 1)); throw new Error(`${host(url)} takes at most ${m} coins per request, so locked ecash there can be made of at most ${m} coin sizes. Try ${near.map(money).join(' or ')}.`); }
  const D = splitAmt(T), sim = simulateCoins(w, held, D, m);
  if (!sim) throw new Error(`${host(url)} takes at most ${m} coins per request, and the coins here can't be split that way for ${money(amount)}. Try a smaller amount.`);
  return { T, D, sim, m };
}
/* The coins of a token made on a mint with a small limit. Claimed whole if it can be (at most m coins, and what the
   claim gives back fits in m coins); otherwise each coin of the amount travels with coins worth the mint's fee for
   claiming it as a part of its own, so the receiver (or you, taking it back) can claim it in parts that fit and get the
   whole amount. On a mint without a fee that is just the amount's coins. */
function claimableCoins(w, amount, id, m) {
  const r = rfeeFor(w, amount, id), D = splitAmt(amount + r);
  if (D.length <= m && bitsOf(amount) <= m) return D;
  const out = [];
  for (const d of splitAmt(amount)) {
    let e = 0; for (let j = 0; j < 5; j++) e = feeOfK(w, 1 + bitsOf(e), id);
    out.push(d, ...splitAmt(e));
  }
  return out.sort((a, b) => b - a);
}
function rfeeFor(w, amount, id) { let r = 0; for (let j = 0; j < 5; j++) r = feeOfK(w, bitsOf(amount + r), id); return r; }
// chunked restore and recorded-output restore: never more outputs in one request than the mint takes
async function restoreRange(w, url, start, n, keysetId) {
  const m = mintMax(url) || n || 1, out = { proofs: [] };
  for (let i = 0; i < n; i += m) { const r = await inTime(w.restore(start + i, Math.min(m, n - i), { keysetId }), 30000); out.proofs = out.proofs.concat(r.proofs || []); if (r.lastCounterWithSignature != null) out.lastCounterWithSignature = r.lastCounterWithSignature; }
  return out;
}
/* Coins I (at most m) for a step that makes `target` in coins of its own plus change in at most `maxOut` coins:
   the fewest coins and the least change. Small searches only: m is small here. */
function pickInputs(w, free, target, m, maxOut) {
  const desc = free.slice().sort((a, b) => num(b.amount) - num(a.amount));
  let best = null;
  const tryIt = I => { const s = I.reduce((t, p) => t + num(p.amount), 0), c = s - feeOfPs(w, I) - target; if (c < 0 || bitsOf(c) > maxOut) return; if (!best || I.length < best.I.length || (I.length === best.I.length && c < best.c)) best = { I, c }; };
  if (m <= 3) {   // (a tiny limit: every pick of up to 3 of the 40 biggest coins)
    const cand = desc.slice(0, 40), n = cand.length;
    for (let a = 0; a < n; a++) { tryIt([cand[a]]); if (m < 2) continue; for (let b = a + 1; b < n; b++) { tryIt([cand[a], cand[b]]); if (m < 3) continue; for (let c = b + 1; c < n; c++) tryIt([cand[a], cand[b], cand[c]]); } }
  } else for (let k = 1; k <= Math.min(m, desc.length) && !best; k++) tryIt(desc.slice(0, k));   // (bigger limits: biggest coins first)
  return best && best.I;
}
// a step that only merges coins: at most m in, fewer out (never more than m)
function pickMerge(w, free, m) {
  const cand = free.slice().sort((a, b) => num(a.amount) - num(b.amount)).slice(0, m > 3 ? m : 40), n = cand.length;
  let best = null;
  const tryIt = I => { const s = I.reduce((t, p) => t + num(p.amount), 0) - feeOfPs(w, I); if (s <= 0) return; const out = bitsOf(s), gain = I.length - out; if (gain <= 0 || out > m) return; if (!best || gain > best.gain || (gain === best.gain && s > best.s)) best = { I, gain, s }; };
  if (m <= 3) { for (let a = 0; a < n; a++) for (let b = a + 1; b < n; b++) { if (m >= 2) tryIt([cand[a], cand[b]]); if (m >= 3) for (let c = b + 1; c < n; c++) tryIt([cand[a], cand[b], cand[c]]); } }
  else for (let k = Math.min(m, n); k >= 2 && !best; k--) tryIt(cand.slice(0, k));   // (as many of the smallest coins as the mint takes)
  return best && best.I;
}
// the next step toward holding coins of exactly the amounts in D, from the coins `held` (reserved: already set aside)
function nextStep(w, held, reserved, D, m) {
  const left = D.slice(); const res = new Set(reserved);
  for (const p of held) if (res.has(p.secret)) { const i = left.indexOf(num(p.amount)); if (i >= 0) left.splice(i, 1); }
  const free = held.filter(p => !res.has(p.secret));
  for (const p of free.slice().sort((a, b) => num(b.amount) - num(a.amount))) { const i = left.indexOf(num(p.amount)); if (i >= 0) { left.splice(i, 1); res.add(p.secret); } }   // coins already the right size
  if (!left.length) return { done: true, reserved: res };
  const free2 = held.filter(p => !res.has(p.secret));
  for (let j = Math.min(m, left.length); j >= 1; j--) {
    const C = left.slice(0, j), I = pickInputs(w, free2, C.reduce((t, x) => t + x, 0), m, m - j);
    if (I) return { reserved: res, I, C };
  }
  const I = pickMerge(w, free2, m);
  if (I) return { reserved: res, I, C: [] };
  const sp = pickSplit(w, free2, Math.max(...left), m);
  return sp ? { reserved: res, I: sp.I, C: [], outs: sp.outs } : { reserved: res, stuck: true };
}
/* a step that breaks a coin bigger than any still needed into up to m smaller ones, halving toward the size needed
   (4,096 for a 128: 2,048 + 1,024 + 1,024, then 512 + 256 + 256 ...). On a mint with a fee the coin goes with the
   fewest small coins that make what comes back fit. */
function pickSplit(w, free, t, m) {
  if (m < 2) return null;
  const big = free.filter(p => num(p.amount) > t).sort((a, b) => num(a.amount) - num(b.amount)), small = free.slice().sort((a, b) => num(a.amount) - num(b.amount)).slice(0, 12);
  for (const p of big) {
    const combos = [[]]; for (let a = 0; a < small.length && m >= 2; a++) { if (small[a] === p) continue; combos.push([small[a]]); for (let b = a + 1; b < small.length && m >= 3; b++) if (small[b] !== p) combos.push([small[a], small[b]]); }
    for (const c of combos) {
      const I = [p].concat(c), v = I.reduce((x, q) => x + num(q.amount), 0) - feeOfPs(w, I); if (v <= 0) continue;
      const outs = splitAmt(v); if (outs.length > m) continue;
      while (outs.length < m) { outs.sort((a, b) => b - a); if (outs[0] <= t || outs[0] < 2) break; const x = outs.shift(); outs.push(x / 2, x / 2); }
      if (Math.max(...outs) < num(p.amount)) return { I, outs: outs.sort((a, b) => b - a) };
    }
  }
  return null;
}
// the same steps on paper, for the most they can cost (fees), before anything is asked
function simulateCoins(w, held, D, m) {
  let ps = held.map(p => ({ amount: num(p.amount), id: p.id, secret: p.secret })), reserved = new Set(), fees = 0, n = 0;
  const kid = held[0] && held[0].id;
  for (let i = 0; i < 80; i++) {
    const st = nextStep(w, ps, reserved, D, m); reserved = st.reserved;
    if (st.done) return { fees, steps: n };
    if (st.stuck) return null;
    const ids = new Set(st.I.map(p => p.secret)), f = feeOfPs(w, st.I), c = st.I.reduce((t, p) => t + p.amount, 0) - f - st.C.reduce((t, x) => t + x, 0);
    ps = ps.filter(p => !ids.has(p.secret)); fees += f; n++;
    for (const a of st.C) { const p = { amount: a, id: kid, secret: 'sim' + i + ':' + hex(rnd(8)) }; ps.push(p); reserved.add(p.secret); }
    for (const a of st.outs || splitAmt(c)) ps.push({ amount: a, id: kid, secret: 'sim' + i + ':' + hex(rnd(8)) });
  }
  return null;
}
/* Runs the steps: each a journaled swap with at most m coins in and out (the outputs it asks for are exactly the
   coins the payment needs, plus the change). Returns the coins set aside, still in the balance. Each step's fee is
   written in the same save as its coins, on one line for the whole payment. */
async function makeCoins(w, url, D, m, feeLine) {
  let reserved = new Set();
  for (let i = 0; i < 80; i++) {
    const busy = new Set(S.ops.filter(o => o.mint === url).flatMap(o => o.inputs));
    const held = (S.proofs[url] || []).filter(p => !busy.has(p.secret));
    const st = nextStep(w, held, reserved, D, m); reserved = st.reserved;
    if (st.done) return held.filter(p => reserved.has(p.secret));
    if (st.stuck) throw new Error(`${host(url)} takes at most ${m} coins per request, and the coins here can't be split that way for this amount. Try a smaller amount.`);
    const I = st.I, C = st.outs || st.C, sendC = C.reduce((t, x) => t + x, 0);
    let res;
    if (!C.length) { const r0 = await journaled(url, 'swap', { inputs: I }, (cb, o) => rRecv(o, w, I, { onCountersReserved: cb })); res = { r: { keep: r0.r, send: [] }, op: r0.op }; }   // (only merging coins)
    else {
      const cfg = { send: Object.assign({}, w.defaultOutputType(), { denominations: C }), keep: w.defaultOutputType() };
      const pick = w._selectProofs; w._selectProofs = ps => ({ keep: [], send: ps });
      try { res = await journaled(url, 'swap', { inputs: I }, (cb, o) => rSend(o, w, sendC, I, { includeFees: false, onCountersReserved: cb }, cfg)); }
      finally { w._selectProofs = pick; }
    }
    const { r: { keep, send }, op } = res, used = new Set(I.map(p => p.secret));
    const fee = Math.max(0, sum(I) - sum(send) - sum(keep));
    S.proofs[url] = (S.proofs[url] || []).filter(p => !used.has(p.secret)).concat(plain(send), plain(keep));
    if (!st.outs) for (const p of send) reserved.add(p.secret);   // (a split step's coins are free coins, set aside next round if they are the right size)
    if (fee > 0) { const t = feeLine.id && txById(feeLine.id); if (t) t.fee = num(t.fee) + fee; else feeLine.id = addTx({ type: 'out', method: 'fee', amount: 0, fee, mint: url, note: 'Mint fee for splitting a payment into smaller requests', status: 'done', limId: feeLine.limId || undefined }).id; }
    closeOp(op); save();
  }
  throw new Error(`${host(url)} takes at most ${m} coins per request, and this payment needs too many steps there. Try a smaller amount.`);
}
const heldFree = url => { const busy = new Set(S.ops.filter(o => o.mint === url).flatMap(o => o.inputs)); return (S.proofs[url] || []).filter(p => !busy.has(p.secret)); };
// a token from a mint with a small limit: plain ecash is made of exactly the right coins (no last swap); locked ecash
// gets one last swap from exactly the right coins
async function sendBatched(w, amount, note, lockTo, url, opts, outCfg) {
  const m = smallMint(url), held = heldFree(url), kid = (() => { try { return w.keysetId; } catch (e) { return held[0] && held[0].id; } })();
  if (!lockTo) {
    const D = claimableCoins(w, amount, kid, m), rfee = D.reduce((t, x) => t + x, 0) - amount, sim = simulateCoins(w, held, D, m);
    if (!sim) throw new Error(`${host(url)} takes at most ${m} coins per request, and the coins here can't be split that way for ${money(amount)}. Try a smaller amount.`);
    const hold = limitGate(amount + rfee + sim.fees, { free: opts.noLimit, grant: opts.grant, approved: opts.approved });
    try {
      const coins = await makeCoins(w, url, D, m, { limId: hold.id });
      const ids = new Set(coins.map(p => p.secret));
      S.proofs[url] = (S.proofs[url] || []).filter(p => !ids.has(p.secret));
      const token = tokEnc({ mint: url, proofs: coins, unit: 'sat' });
      const tx = addTx(Object.assign({ type: 'out', method: 'ecash', amount, fee: Math.max(0, sum(coins) - amount), mint: url, note, status: 'pending', token, sent: plain(coins), locked: null }, opts.txx || {}, hold.id ? { limId: hold.id } : {}));
      save();
      return tx;
    } finally { hold.release(); }
  }
  const { T, D, sim } = lockedPlan(w, url, amount, outCfg.send);
  const hold = limitGate(T + sim.fees, { free: opts.noLimit, grant: opts.grant, approved: opts.approved });
  try {
    const coins = await makeCoins(w, url, D, m, { limId: hold.id });
    return await withPick(w, { send: coins }, () => sendEcashSwap(w, amount, note, lockTo, url, opts, outCfg, hold));
  } finally { hold.release(); }
}
// a Lightning payment from a mint with a small limit: the coins it spends, at most m, worth the amount, the fee
// reserve and the mint's fee to spend them (with as little over as can be)
function planMelt(w, url, need) {
  const m = smallMint(url), held = heldFree(url), kid = held[0] && held[0].id;
  const ceilFit = (n, k) => bitsOf(n) <= k ? n : fitAmounts(n, k)[1];
  let best = null;
  for (let k = 1; k <= m; k++) { const T = ceilFit(need + feeOfK(w, k, kid), k); if (!best || T < best.T) best = { T, k }; }
  if (!best) return null;
  const D = splitAmt(best.T), sim = simulateCoins(w, held, D, m);
  if (sim) return { T: best.T, D, fees: sim.fees, m };
  // no steps can make those coins (a mint with a fee and one big coin): the payment spends coins held as they are, at
  // most m of them, and the change comes back in at most m coins (what doesn't fit is kept by the mint, within the total)
  const desc = held.slice().sort((a, b) => num(a.amount) - num(b.amount)); let direct = null;
  for (const p of desc) if (num(p.amount) >= need + feeOfPs(w, [p])) { direct = [p]; break; }
  if (!direct) { const I = pickInputs(w, held, need, m, 64); if (I) direct = I; }
  return direct ? { T: sum(direct), D: direct.map(p => num(p.amount)), fees: 0, m, direct } : null;
}
async function meltInputsBatched(w, url, need) {
  const p = planMelt(w, url, need); if (!p) throw new Error(`${host(url)} takes at most ${smallMint(url)} coins per request, and the coins here can't be split that way for this payment.`);
  const coins = p.direct || await makeCoins(w, url, p.D, p.m, {});
  return { r: { keep: [], send: coins }, op: null, inputs: coins };
}
// how to claim a token on a mint with a small limit: parts of at most m coins, each giving at most m coins back
// (each part pays the mint's own fee for its coins, and what it gives back has to fit in m coins: on a mint with a
// fee a lone coin of 2^n gives back 2^n - 1, n coins, so parts are searched for, not just filled in order)
function tokenParts(w, proofs, m) {
  const ps = proofs.slice().sort((a, b) => num(b.amount) - num(a.amount));
  const ok = g => g.length <= m && sum(g) - feeOfPs(w, g) > 0 && bitsOf(sum(g) - feeOfPs(w, g)) <= m;
  const greedy = () => { const parts = []; for (const p of ps) { const g = parts.find(g => ok(g.concat([p]))); if (g) g.push(p); else parts.push([p]); } return parts.every(ok) ? parts : null; };
  const g0 = greedy(); if (g0) return g0;
  // each coin, biggest first, with the fewest of the smallest coins left that make its part fit (a coin and the fee for it)
  const paired = () => {
    const left = ps.slice(), parts = [];
    while (left.length) {
      const p = left.shift(), small = left.slice().reverse().slice(0, 12); let best = null;
      const tryIt = c => { const g = [p].concat(c); if (ok(g) && (!best || g.length < best.length)) best = g; };
      tryIt([]);
      for (let a = 0; a < small.length && m >= 2; a++) { tryIt([small[a]]); for (let b2 = a + 1; b2 < small.length && m >= 3; b2++) tryIt([small[a], small[b2]]); }
      if (!best) { const g = parts.find(g => ok(g.concat([p]))); if (!g) return null; g.push(p); continue; }   // (a coin left over joins a part it still fits in)
      for (const c of best.slice(1)) left.splice(left.indexOf(c), 1);
      parts.push(best);
    }
    return parts;
  };
  const g1 = paired(); if (g1 || ps.length > 14) return g1;
  let tries = 0; const parts = [];
  const go = i => {
    if (++tries > 60000) return false;
    if (i === ps.length) return parts.every(ok);
    for (const g of parts) if (g.length < m) { g.push(ps[i]); if (go(i + 1)) return true; g.pop(); }
    parts.push([ps[i]]); if (go(i + 1)) return true; parts.pop();
    return false;
  };
  return go(0) ? parts.map(g => g.slice()) : null;
}
async function receiveInParts(w, meta, token, note, parts, own, mine, back, extra) {   // (extra: kept on each part's line, a nutzap's mark)
  const n = parts.length, lines = parts.map((g, i) => addTx(Object.assign({ type: 'in', method: 'ecash', amount: sum(g), mint: meta.mint, note: [(note || meta.memo || '').trim(), `(part ${i + 1} of ${n})`].filter(Boolean).join(' '), status: 'pending', incoming: tokEnc({ mint: meta.mint, proofs: g, unit: 'sat' }), offline: true, mk: 1 }, mine ? { mine: true } : {}, back ? { back } : {}, extra || {})));   // (mk: its mark, or none for an Extra Life left to you, is what it says)
  save();   // (every part is saved before the first is claimed: if NUTCADE closes in between, the rest are claimed later)
  let got = 0, last = null, err = null;
  for (const t of lines) {
    try { const nt = await receiveTokenNow(t.incoming, t.note, { follow: { k: 'incoming', txId: t.id, reqId: null }, part: true }); incomingClaimed({ txId: t.id, reqId: null }, nt); got += num(nt.amount); last = nt; }
    catch (e) { if (!err) err = e; if (isSpentErr(e)) { const cur = txById(t.id); if (cur && cur.status === 'pending') updTx(t.id, { status: 'failed', note: (cur.note ? cur.note + ' · ' : '') + 'already claimed by someone else' }); } }   // (any other error: the part stays saved and is claimed later)
  }
  if (own && !err) updTx(own.id, { status: 'reclaimed' });   // (our own token, taken back in parts)
  if (!last && err) throw err;
  return Object.assign({}, last, { amount: got });
}

