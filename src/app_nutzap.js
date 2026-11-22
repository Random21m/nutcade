/* ===================== Nutzaps (1.28, NIP-61) ===================== */
/* Ecash zaps over Nostr, opt-in and off by default ("Receive nutzaps" in Settings, Privacy).
   - Your nutzap info: a kind 10019 event signed with this wallet's Nostr key (the npub of your ecash address), with a
     "relay" tag per relay you listen on, a "mint" tag per mint you use (with the unit "sat"; a blocked mint is never
     listed) and one "pubkey" tag: the P2PK key nutzaps must be locked to. That key is NOT the Nostr key (NIP-61 says so):
     it is derived from the 12 words at NZ_PATH (BIP-32, under the Cashu purpose 129372', branch 61' for NIP-61), with
     its private key negated when needed so that its public key starts with 02, and it is published as "02" + its x
     coordinate. So restoring the 12 words gives the same key back, and nutzaps that came while the wallet was away can
     still be claimed. Republished when the relays or mints change; turning nutzaps off replaces it with an empty one
     (and asks relays to delete it), so nobody is told to send any more.
   - Receiving: kind 9321 events tagged with your Nostr key ("p") are listened for on your relays. One is taken only
     when its signature is right, its "u" mint is one you trust (one you use, or one in the info you published), its
     unit is sat and EVERY proof is P2PK-locked to your receiving key ("data", with at most one signature asked for).
     Anything else is ignored and never shown. Each event is taken once: its id is kept (nzseen, per wallet, encrypted
     with the PIN), and coins already waiting in another line are never saved twice. Coins the mint already says are
     spent (a nutzap claimed before a restore, or by the same 12 words on another phone) are skipped. A nutzap taken is
     first saved as a waiting line ("Nutzap from ..."), then claimed with the usual claim of a saved token (one claim
     at a time, through the journal, signed with the receiving key): never credited before the mint swapped its coins,
     never twice. Mint down or refusing: the line waits and is tried again with backoff; coins it says are spent are
     dropped from the line (all of them: the line goes).
   - Sending: their kind 10019 is looked up on their relays (an nprofile's) and yours; no 10019, no receiving key that
     is a point on the curve or no mint with the unit sat: refused, nothing spent. Never an unlocked token instead. A
     mint you both accept that holds the amount is used (the active one first). The coins are made locked to their key
     ("02" + x, or their compressed key as given) with the usual send, so the journal covers a crash: the locked coins
     come back as the same nutzap. The kind 9321 event (a "proof" tag per coin, with its DLEQ proof, "u" with the mint
     exactly as their 10019 wrote it, "unit" sat, "p" their key, your comment as its content, signed with your Nostr
     key) is made once and kept on the line before it is sent, so sending it again is the same event. It goes to the
     relays in their 10019 (yours when it lists none); if none takes it, it is tried again later, until one does or
     they have claimed it. A nutzap is public: the screen says so.
   The duress PIN's wallet has none of this: nothing is published or listened to, and turning it on or sending one
   answers "isn't available right now". */
const NZ_PATH = "m/129372'/61'/0'/0'/0'";
const NZ_BACK = 7 * 86400, NZ_REPUB = 10 * 60e3, NZ_WAIT_MAX = 6 * 3600e3;
let nzKeyC = null;
function nzKeys() {
  const s = seedFor();
  if (!nzKeyC || nzKeyC.seed !== s) {
    const k = L.HDKey.fromMasterSeed(s).derive(NZ_PATH);
    const priv = evenPriv(hex(k.privateKey));
    nzKeyC = { seed: s, priv, pub: hex(L.getPubKeyFromPrivKey(L.hexToBytes(priv))) };
  }
  return nzKeyC;
}
const nzPriv = () => nzKeys().priv, nzPub = () => nzKeys().pub;
const nzAllowed = () => !!(S.seed && S.seed.backedUp && !(vault.on && vault.decoy));
const nzOn = () => nzAllowed() && S.prefs.nutzap === true;
const nzLive = () => nzOn() && !tabLocked && !(vault.on && !vault.open) && !writeGuard.paused;
const nzOff = () => keepErr(new Error("Nutzaps aren't available right now. Try again later."));
const nzMints = () => S.mints.map(m => m.url).filter(u => !isBlocked(u));
const nzTrusted = url => !isBlocked(url) && (nzMints().includes(url) || ((S.prefs.nzInfo || {}).mints || []).includes(url));
const nzWant = () => [relays().slice(0, 8).join(' '), nzMints().join(' '), nzPub()].join('|');
const nzSeen = new Set(raw.get('nzseen', []));
function nzMark(id) { if (!id || nzSeen.has(id)) return; nzSeen.add(id); raw.set('nzseen', [...nzSeen].slice(-1000)); }
// a receiving key someone published: "02" + x for an x-only key (NIP-61), a compressed key as it is; a point on the curve, or null
function nzKeyOf(v) {
  v = String(v || '').trim().toLowerCase();
  const k = /^[0-9a-f]{64}$/.test(v) ? '02' + v : validPub(v) ? v : null;
  return k && DQ.point(k) ? k : null;
}
// the key a coin is locked to (NUT-11), or null when it isn't a P2PK lock one key can open
function nzLock(secret) {
  let s; try { s = JSON.parse(secret); } catch (e) { return null; }
  if (!Array.isArray(s) || s[0] !== 'P2PK' || !s[1] || typeof s[1].data !== 'string') return null;
  const n = (Array.isArray(s[1].tags) ? s[1].tags : []).find(t => Array.isArray(t) && t[0] === 'n_sigs');
  if (n && num(n[1]) > 1) return null;
  return s[1].data.toLowerCase();
}
const nzWho = pk => { const c = S.contacts.find(x => x.pubkey === pk); return c ? c.name : shortNpub(pk); };

/* ---------- your nutzap info (kind 10019) ---------- */
let nzState = null, nzTry = 0;
async function nzPublish() {
  if (!nzOn()) return 0;
  const rl = relays().slice(0, 8), mints = nzMints(), pub = nzPub(), key = nzWant(), prev = S.prefs.nzInfo || {};
  const ts = Math.max(Math.floor(Date.now() / 1000), num(prev.at) + 1);
  const ev = L.finalizeEvent({ kind: 10019, created_at: ts, tags: rl.map(r => ['relay', r]).concat(mints.map(u => ['mint', u, 'sat']), [['pubkey', pub]]), content: '' }, nostrKey());
  nzState = 'saving'; nzTry = Date.now();
  const ok = await relayPublish(ev, 7000, rl, 1500);
  nzState = ok ? 'ok' : 'failed';
  if (ok && nzOn()) { S.prefs.nzInfo = { at: ts, mints, relays: rl, pub, key }; save(); }
  return ok;
}
async function nzUnpublish() {
  const prev = S.prefs.nzInfo; if (!prev || !S.seed || !nzAllowed()) return 0;
  const sk = nostrKey(), pk = L.nostrPub(sk), ts = Math.max(Math.floor(Date.now() / 1000), num(prev.at) + 1);
  const rl = [...new Set((prev.relays || []).concat(relays()))].slice(0, 8);
  nzTry = Date.now();
  const empty = L.finalizeEvent({ kind: 10019, created_at: ts, tags: [], content: '' }, sk);
  const del = L.finalizeEvent({ kind: 5, created_at: ts, tags: [['a', `10019:${pk}:`], ['k', '10019']], content: '' }, sk);
  const [ok] = await Promise.all([relayPublish(empty, 7000, rl, 1500), relayPublish(del, 7000, rl, 1500)]);
  if (ok && !S.prefs.nutzap) { delete S.prefs.nzInfo; save(); }
  return ok;
}
function nzToggled(on) {
  if (on && !nzAllowed()) { S.prefs.nutzap = false; save(); toast(nzOff().message, 'gold'); return; }
  nzState = null;
  if (on) { nzPublish().then(() => refresh()).catch(() => {}); setTimeout(nzListen, 0); }
  else { nzStop(); nzUnpublish().catch(() => {}); }
}
function nzSettingsHTML() {
  const on = S.prefs.nutzap === true && nzAllowed();
  return toggle('nutzap', 'Receive nutzaps', "Publishes your nutzap info on Nostr (NIP-61): your relays, the mints you use and a receiving key made from your 12 words, so people can send you ecash zaps. Nutzaps that arrive are claimed into this wallet. Off by default.")
    + (on ? `<div class="row between tiny"><span>Nutzap info</span><span style="color:${S.prefs.nzInfo && nzState !== 'failed' ? 'var(--lime)' : 'var(--gold)'}">${nzState === 'saving' ? 'SAVING…' : nzState === 'failed' ? 'RELAYS DIDN\'T ANSWER' : S.prefs.nzInfo ? 'PUBLISHED' : 'NOT YET'}</span></div>` : '');
}

/* ---------- receiving (kind 9321) ---------- */
let nzSocks = [], nzRetry = 0, nzNext = 0;
function nzListen() {
  if (!nzLive()) { nzStop(); return; }
  if (nzSocks.some(s => s.readyState <= 1) || Date.now() < nzNext) return;
  const f = { kinds: [9321], '#p': [L.nostrPub(nostrKey())] };
  if (S.prefs.nzSince) f.since = Math.max(0, num(S.prefs.nzSince) - NZ_BACK);   // (a restored wallet has none: everything sent to it is looked at)
  nzSocks = [];
  for (const r of relays()) {
    let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
    nzSocks.push(ws);
    ws.onopen = () => ws.send(JSON.stringify(['REQ', 'ncnz', f]));
    ws.onmessage = m => { let d; try { d = JSON.parse(m.data); } catch (e) { return; } if (d[0] === 'EVENT' && d[2]) nzQueue(d[2]); else if (d[0] === 'EOSE') nzRetry = 0; };
    ws.onclose = () => { if (nzSocks.includes(ws) && nzSocks.every(s => s.readyState >= 2)) { const d = Math.min(120e3, 3000 * 2 ** nzRetry++); nzNext = Date.now() + d; setTimeout(nzListen, d + 50); } };
  }
}
function nzStop() { const s = nzSocks; nzSocks = []; s.forEach(w => { try { w.close(); } catch (e) {} }); }
let nzChain = Promise.resolve();
function nzQueue(ev) { const r = nzChain.then(() => nzEvent(ev)).catch(() => 'error'); nzChain = r; return r; }   // (one at a time, in order)
// what became of an event: 'ok' (saved and claimed or waiting), or why it was skipped
async function nzEvent(ev) {
  if (!ev || typeof ev !== 'object' || ev.kind !== 9321 || typeof ev.id !== 'string' || !Array.isArray(ev.tags)) return 'bad';
  if (nzSeen.has(ev.id)) return 'seen';
  if (!nzAllowed() || tabLocked || (vault.on && !vault.open) || writeGuard.paused) return 'off';
  if (S.txs.some(t => t.nz && t.nz.id === ev.id)) { nzMark(ev.id); return 'seen'; }
  if (!L.verifyEvent(ev)) return 'bad';   // (not kept as seen: a forged copy must not hide the real one)
  const tg = k => ev.tags.filter(t => Array.isArray(t) && t[0] === k && typeof t[1] === 'string');
  if (!tg('p').some(t => t[1] === L.nostrPub(nostrKey()))) return 'bad';
  const skip = why => { nzMark(ev.id); return why; };
  const u = (tg('u')[0] || [])[1]; if (!u || !/^https?:\/\//i.test(u.trim())) return skip('bad');
  const mint = normUrl(u);
  const unit = (tg('unit')[0] || [])[1]; if (unit && unit !== 'sat') return skip('unit');
  if (!nzTrusted(mint)) return skip('untrusted');
  let proofs = [];
  for (const t of tg('proof')) {
    let p; try { p = JSON.parse(t[1]); } catch (e) { return skip('bad'); }
    const a = Number(p && p.amount);
    if (!p || typeof p.id !== 'string' || typeof p.secret !== 'string' || typeof p.C !== 'string' || !/^0[23][0-9a-f]{64}$/i.test(p.C) || !Number.isSafeInteger(a) || a <= 0) return skip('bad');
    proofs.push({ id: p.id, amount: a, secret: p.secret, C: p.C });
  }
  if (!proofs.length || proofs.length > 512 || new Set(proofs.map(p => p.secret)).size !== proofs.length) return skip('bad');
  const pub = nzPub();
  if (!proofs.every(p => nzLock(p.secret) === pub)) return skip('lock');
  const secs = new Set(proofs.map(p => p.secret));
  if (S.txs.some(t => t.status === 'pending' && t.incoming && (heldSecrets(t.incoming) || []).some(x => secs.has(x)))) return skip('dup');
  // coins the mint already says are spent are left out (claimed before: never shown again); a mint that doesn't answer: all are kept
  try {
    const w = await getWallet(mint), st = await inTime(w.checkProofsStates(proofs), 20000);
    if (st.length === proofs.length) proofs = proofs.filter((p, i) => !(st[i] && st[i].state === 'SPENT'));
  } catch (e) {}
  if (!proofs.length) return skip('spent');
  let token; try { token = L.getEncodedToken({ mint, proofs, unit: 'sat' }); } catch (e) { return skip('bad'); }
  if (nzSeen.has(ev.id) || S.txs.some(t => t.nz && t.nz.id === ev.id)) return 'seen';
  const c = String(ev.content || '').replace(/\s+/g, ' ').trim().slice(0, 120);
  const t = addTx({ type: 'in', method: 'ecash', amount: sum(proofs), mint, note: `Nutzap from ${nzWho(ev.pubkey)}${c ? ': ' + c : ''}`, status: 'pending', incoming: token, nz: { id: ev.id, from: ev.pubkey, at: num(ev.created_at) } });
  nzMark(ev.id);
  S.prefs.nzSince = Math.max(num(S.prefs.nzSince), Math.min(num(ev.created_at), Math.floor(Date.now() / 1000)));
  await saveNow();   // (the line and the seen id are on disk before the mint is asked)
  await nzClaim(t, true).catch(() => {});
  return 'ok';
}
// a waiting nutzap claimed with the usual claim of a saved token; the mint down or refusing leaves it waiting
async function nzClaim(t0, force) {
  const t = txById(t0.id); if (!t || t.type !== 'in' || t.status !== 'pending' || !t.incoming || !t.nz) return null;
  if (!force && t.nz.next && Date.now() < t.nz.next) return null;
  if (isBlocked(t.mint) || isOffline()) return null;
  try {
    const nt = await claimHeld(t);
    if (nt) { arrivalFrom(nt.id, 'nostr'); sfx('coin'); refresh(); arrToast(nt.id, `+${arrMoney(nt.amount)} nutzap received`, 'lime'); }
    return nt;
  } catch (e) {
    const cur = txById(t.id); if (!cur) return S.txs.find(x => x.fromIncoming === t.id) || null;
    if (!(netErr(e) || e.blocked || e.asked)) {   // the mint turned it down: which of its coins are still good?
      try {
        const w = await getWallet(cur.mint), ps = L.getDecodedToken(cur.incoming, Object.keys(S.counters)).proofs || [];
        const st = await inTime(w.checkProofsStates(ps), 20000);
        if (st.length === ps.length && !S.ops.some(o => o.follow && o.follow.k === 'incoming' && o.follow.txId === cur.id)) {
          const left = ps.filter((p, i) => !(st[i] && st[i].state === 'SPENT')).map(p => ({ id: p.id, amount: num(p.amount), secret: p.secret, C: p.C }));
          if (!left.length) { S.txs = S.txs.filter(x => x.id !== cur.id); save(); refresh(); return null; }
          if (left.length < ps.length) { updTx(cur.id, { incoming: L.getEncodedToken({ mint: cur.mint, proofs: left, unit: 'sat' }), amount: sum(left) }); await saveNow(); }
        }
      } catch (x) {}
    }
    const now = txById(t.id); if (!now) return null;
    const tries = num(now.nz.tries) + 1;
    updTx(now.id, { nz: Object.assign({}, now.nz, { tries, next: Date.now() + Math.min(NZ_WAIT_MAX, 30e3 * 2 ** Math.min(tries - 1, 10)) }) });
    return null;
  }
}

/* ---------- sending ---------- */
const nzNoInfo = () => keepErr(new Error("This person can't receive nutzaps: they haven't published nutzap info (NIP-61) on Nostr. Nothing was sent. Send ecash over Nostr or Lightning instead."));
async function nzFind(pubkey, extra) {
  if (!/^[0-9a-f]{64}$/.test(String(pubkey || ''))) throw new Error("That Nostr address can't be read. Paste an npub or nprofile.");
  const list = [...new Set((extra || []).filter(u => /^wss?:\/\//.test(u)).concat(relays()))].slice(0, 8);
  const evs = await relayQuery({ kinds: [10019], authors: [pubkey], limit: 5 }, 7000, list, 1500);
  const ev = evs.filter(e => e && e.kind === 10019 && e.pubkey === pubkey && Array.isArray(e.tags) && L.verifyEvent(e)).sort((a, b) => b.created_at - a.created_at)[0];
  if (!ev && !evs.answered) throw keepErr(new Error("Couldn't reach your Nostr relays to look up their nutzap info. Nothing was sent. Try again in a moment."));
  if (!ev) throw nzNoInfo();
  const tg = k => ev.tags.filter(t => Array.isArray(t) && t[0] === k && typeof t[1] === 'string');
  const pub = nzKeyOf((tg('pubkey')[0] || [])[1]);
  const mints = [];
  for (const t of tg('mint')) {
    if (t.length > 2 && !t.slice(2).includes('sat')) continue;   // (units listed, and sat isn't one of them)
    if (!/^https?:\/\//i.test(t[1].trim())) continue;
    const url = normUrl(t[1]); if (!mints.some(m => m.url === url)) mints.push({ u: t[1], url });
  }
  if (!pub || !mints.length) throw nzNoInfo();
  return { pub, mints, relays: tg('relay').map(t => t[1]).filter(u => /^wss?:\/\//.test(u)).slice(0, 8) };
}
const nzUsable = info => info.mints.filter(m => S.mints.some(x => x.url === m.url) && !isBlocked(m.url));
function nzPick(info, amount) {
  const mine = nzUsable(info);
  if (!mine.length) { const e = keepErr(new Error("They take nutzaps only at mints you don't use. Add one of their mints to send them a nutzap. Nothing was sent.")); e.raw = info.mints.map(m => host(m.url)).join(', '); throw e; }
  const ok = mine.filter(m => balanceOf(m.url) >= amount);
  if (!ok.length) { const e = keepErr(new Error("You don't have that much at a mint they take nutzaps at. Nothing was sent.")); e.raw = mine.map(m => `${host(m.url)}: ${money(balanceOf(m.url))}`).join(', '); throw e; }
  return ok.find(m => m.url === S.active) || ok.sort((a, b) => balanceOf(b.url) - balanceOf(a.url))[0];
}
const nzProof = p => Object.assign({ id: p.id, amount: num(p.amount), secret: p.secret, C: p.C }, p.dleq && p.dleq.e && p.dleq.s && p.dleq.r ? { dleq: { e: String(p.dleq.e), s: String(p.dleq.s), r: String(p.dleq.r) } } : {});
const nzRelaysFor = z => { const l = (z.relays || []).filter(u => /^wss?:\/\//.test(u)); return (l.length ? l : relays()).slice(0, 8); };
// the nutzap's event, made once and kept on its line before it is sent (sending it again is the same event)
async function nzDeliverOne(id) {
  let t = txById(id); if (!t || t.type !== 'out' || t.delivered || t.status !== 'pending' || !t.nz || !Array.isArray(t.sent) || !t.sent.length) return !!(t && t.delivered);
  if (!S.seed || (vault.on && vault.decoy)) return false;
  if (!t.nz.ev) {
    const z = t.nz, tags = t.sent.map(p => ['proof', JSON.stringify(nzProof(p))]).concat([['u', z.u], ['unit', 'sat'], ['p', z.to]]);
    updTx(t.id, { nz: Object.assign({}, z, { ev: L.finalizeEvent({ kind: 9321, created_at: Math.floor(Date.now() / 1000), content: z.c || '', tags }, nostrKey()) }) });
    await saveNow(); t = txById(id);
  }
  const ok = await relayPublish(t.nz.ev, 8000, nzRelaysFor(t.nz), 1500);
  const cur = txById(id); if (!cur) return !!ok;
  if (ok) { const z = Object.assign({}, cur.nz); delete z.next; delete z.tries; updTx(id, { delivered: true, nz: z }); return true; }
  const tries = num(cur.nz.tries) + 1;
  updTx(id, { nz: Object.assign({}, cur.nz, { tries, next: Date.now() + Math.min(30 * 60e3, 30e3 * 2 ** Math.min(tries - 1, 8)) }) });
  return false;
}
async function nzDeliver(force) {
  for (const t of S.txs.filter(t => t.type === 'out' && t.nz && !t.delivered && t.status === 'pending' && Array.isArray(t.sent) && t.sent.length)) {
    if (!force && t.nz.next && Date.now() < t.nz.next) continue;
    await single('nzsend:' + t.id, () => nzDeliverOne(t.id)).catch(() => {});
  }
}
async function nzSendTo(target, info, amount, comment) {
  if (!nzAllowed()) throw nzOff();
  if (isOffline()) throw new Error("You're offline. A nutzap needs a connection.");
  amount = num(amount); if (!Number.isSafeInteger(amount) || amount <= 0) throw new Error('Enter an amount in sats, like 1000.');
  if (!info || !nzKeyOf(info.pub)) throw nzNoInfo();
  const m = nzPick(info, amount), name = String(target.name || shortNpub(target.pubkey)).trim().slice(0, 40);
  const txx = { nz: { to: target.pubkey, u: m.u, relays: info.relays || [], c: String(comment || '').slice(0, 280) } };
  if (target.contactId) Object.assign(txx, { contactId: target.contactId, contactName: name });
  const tx = await sendEcash(amount, `Nutzap to ${name}`, nzKeyOf(info.pub), m.url, { txx });
  const ok = await single('nzsend:' + tx.id, () => nzDeliverOne(tx.id)).catch(() => false);
  return { tx: txById(tx.id) || tx, ok: !!ok };
}
async function nzSend(target, amount, comment) {
  if (!nzAllowed()) throw nzOff();
  return nzSendTo(target, await nzFind(target.pubkey, target.relays), amount, comment);
}

/* ---------- the nutzap screen, history, the background round ---------- */
let curNz = null;
async function openNutzap(target) {
  if (needMint()) return;
  curNz = null;
  const name = String(target.name || shortNpub(target.pubkey)).trim().slice(0, 40);
  const head = `<div class="label">To</div><div class="code" style="color:var(--ink)" data-noi18n>${esc(name)}</div>`;
  openSheet('Nutzap', busyHTML('LOOKING UP THEIR NUTZAP INFO') + '<div id="sheetErr"></div>');
  let info;
  try { if (!nzAllowed()) throw nzOff(); info = await nzFind(target.pubkey, target.relays); }
  catch (e) { if ($('#layer .sheet')) setBody(head + errHTML(friendly(e)) + '<button class="btn block" data-act="close">Close</button>'); return; }
  if (!$('#layer .sheet')) return;
  const mine = nzUsable(info), from = mine.find(m => m.url === S.active) || mine.slice().sort((a, b) => balanceOf(b.url) - balanceOf(a.url))[0];
  curNz = Object.assign({}, target, { name, info });
  setBody(`${head}
    <div class="tiny muted">They take nutzaps at</div><div class="tiny" data-noi18n>${info.mints.map(m => esc(host(m.url))).join(', ')}</div>
    ${from ? `<div class="tiny muted">From <b style="color:var(--ink)" data-noi18n>${esc(mintName(from.url))}</b> · ${money(balanceOf(from.url))} available</div>
    <div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="21" autocomplete="off"></div>
    <div class="field"><label for="nzComment">Comment (optional, public on Nostr)</label><input id="nzComment" class="inp" maxlength="280" autocomplete="off"></div>
    <div class="notice">A nutzap is public on Nostr: anyone can see who sent it, to whom and how much. Its ecash is locked to their key, so only they can claim it.</div>
    <button class="btn solid gold block" data-act="nzSend">Send nutzap</button>` : errHTML(keepErr(Object.assign(new Error("They take nutzaps only at mints you don't use. Add one of their mints to send them a nutzap. Nothing was sent."))))}
    <div id="sheetErr"></div>`);
}
// the history screen of a nutzap (src/app.js openTx)
function nzTxExtra(t) {
  if (!t.nz) return '';
  if (t.type === 'in' && t.status === 'pending' && t.incoming) return `<div class="notice">This nutzap is waiting to be claimed. NUTCADE claims it as soon as the mint can be reached.</div><button class="btn block lime" data-act="claimIncoming" data-id="${esc(t.id)}">Claim now</button>`;
  if (t.type === 'out' && t.status === 'pending') return `<div class="notice cyan">${t.delivered ? 'Sent as a nutzap over Nostr.' : 'Not delivered yet: no relay has taken this nutzap so far. NUTCADE keeps trying.'} Its ecash is locked to their key, so only they can claim it.</div>
    <div class="row" style="flex-wrap:wrap"><button class="btn sm" data-act="checkClaim" data-id="${esc(t.id)}">Check claimed</button>${t.delivered ? '' : `<button class="btn sm gold" data-act="nzRetry" data-id="${esc(t.id)}">Try now</button>`}</div>`;
  return '';
}
const nzTxRow = t => t.nz ? `<dt>${t.type === 'in' ? 'From' : 'To'}</dt><dd class="tiny" data-noi18n>${esc(shortNpub(t.type === 'in' ? t.nz.from : t.nz.to))}</dd>` : '';
// every background round: waiting nutzaps claimed, undelivered ones sent, the info kept up to date
let nzTicking = Promise.resolve();
function nzTick(force) { const r = nzTicking.catch(() => {}).then(() => nzTickNow(force)); nzTicking = r; return r; }
async function nzTickNow(force) {
  if (!S.seed || tabLocked || (vault.on && !vault.open) || (vault.on && vault.decoy) || writeGuard.paused) return;
  for (const t of S.txs.filter(t => t.type === 'in' && t.nz && t.status === 'pending' && t.incoming)) await nzClaim(t, force).catch(() => {});
  await nzDeliver(force).catch(() => {});
  const due = force || Date.now() - nzTry > NZ_REPUB;
  if (nzOn() && (S.prefs.nzInfo || {}).key !== nzWant() && due) await nzPublish().catch(() => {});
  else if (S.prefs.nutzap !== true && S.prefs.nzInfo && due) await nzUnpublish().catch(() => {});
  nzListen();
}
window.NutZap = {
  pub: () => nzPub(), me: () => L.nostrPub(nostrKey()), path: NZ_PATH, info: () => S.prefs.nzInfo || null, live: () => nzSocks.filter(s => s.readyState <= 1).length,
  event: ev => nzQueue(ev), tick: force => nzTick(!!force), seen: () => [...nzSeen], find: (pk, rl) => nzFind(pk, rl || []),
  send: (target, amount, comment) => nzSend(target, amount, comment), open: target => openNutzap(target), randomPub: () => hex(L.getPubKeyFromPrivKey(rnd(32)))
};
