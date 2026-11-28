/* ===================== Round 5: high-score bounties and Extra Life ===================== */

/* ---------- high-score bounties: "beat my score, take the sats" (NUT-14 hash locks) ----------
   The sats are locked to your friend's key AND to a secret only your NUTCADE knows. The mint won't release them
   without both. When your friend's signed score beats yours, your NUTCADE sends them the secret and they claim.
   If nobody wins within a week, the lock's refund path lets you take the sats back (same as a gift). */
const BOUNTY_DAYS = 7;
const sha256hex = async bytes => hex(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)));
async function mintCan(url, nut) { try { const s = (await getWallet(url)).getMintInfo().isSupported(nut); return !!(s && s.supported && !s.disabled); } catch (e) { return false; } }
function bountyField() {
  return `<div class="field" id="bountyF"><label for="bountyAmt">Put sats on it (optional)</label><input id="bountyAmt" class="inp" inputmode="numeric" placeholder="0" autocomplete="off">
    <div class="th">The mint locks them so only the friend you send to can win them, and only by beating your score within ${BOUNTY_DAYS} days. If they don't, the sats come back to you.</div></div>`;
}
// with a bounty the message is sealed with our own key, so Robin's NUTCADE can tell the sats really come from the challenger
const challengeWrap = (c, k, bounty) => L.nip17.wrapEvent(bounty ? nostrKey() : rnd(32), { publicKey: k.pubkey }, JSON.stringify(Object.assign({ t: 'nutcade-challenge', ev: c.ev }, bounty ? { bounty } : {}, c.replay ? { replay: c.replay } : {})));
function publishChallenge(c, k, bounty, wrap) {
  return relayPublish(wrap || challengeWrap(c, k, bounty), 8000, [...new Set((k.relays || []).concat(relays()))].slice(0, 8));
}
// a bounty whose swap was interrupted, settled from its record: it becomes the bounty it was going to be, and its
// challenge goes out (now, or from the background check until a relay takes it). Its message goes out at most once:
// it is made once and kept, so sending it again (a retry, the background check) is the same message, and it is marked
// sent when a relay takes it. A record that came in with a backup doesn't send it from here: the device that made the
// bounty does (the sats still come back after its date if nobody wins).
function bountyRecovered(f, tx, imported) {
  const c = S.challenges.find(x => x.id === f.chal && x.dir === 'out'); if (!c) return;
  if ((c.bounties || []).some(b => b.txId === tx.id || b.H === f.b.H)) return;
  const b = Object.assign({}, f.b, { txId: tx.id, state: 'open' }, imported ? {} : { unsent: f.contact || true });
  c.bounties = (c.bounties || []).concat([b]); updTx(tx.id, { bounty: c.id }); saveChallenges();
  if (!imported) setTimeout(() => sendRecoveredBounty(c, b).catch(() => {}), 0);
}
function sendRecoveredBounty(c0, b0) {
  return single('bsend:' + b0.H, async () => {
    await syncIfStale();
    const c = S.challenges.find(x => x.id === c0.id && x.dir === 'out'), b = c && (c.bounties || []).find(x => x.H === b0.H);
    if (!b || !b.unsent || b.state !== 'open') return false;   // sent already (here, or by another tab)
    const k = contactById(b.unsent) || S.contacts.find(x => x.pubkey === b.to), tx = txById(b.txId);
    if (!k || !tx || tx.status !== 'pending' || !tx.token) return false;
    if (!b.wrap) { b.wrap = challengeWrap(c, k, { token: tx.token, amount: b.amount, until: b.until }); saveChallenges(); await saveNow(); }
    if (!(await publishChallenge(c, k, null, b.wrap))) return false;
    delete b.unsent; delete b.wrap; c.sentTo = [...new Set((c.sentTo || []).concat(k.id))]; saveChallenges();
    return true;
  });
}
async function createBounty(c, k, amount) {
  if (!k.pubkey) throw new Error('Bounties need a contact with a Nostr address.');
  if (!(await mintCan(S.active, 14))) throw new Error(`${host(S.active)} can't lock sats to a secret (NUT-14). Pick another mint for bounties.`);
  const pre = rnd(32), H = await sha256hex(pre), until = Math.floor(Date.now() / 1000 + ((window.__nutcadeTest && __nutcadeTest.bountySecs) || BOUNTY_DAYS * 86400));
  const g = gameById(c.game);
  const tx = await sendEcash(amount, `Bounty for ${k.name}: beat ${pad6(c.score)} on ${g ? g.name : c.game}`, '02' + k.pubkey, S.active, { locktime: until, hashlock: H, blind: true, txx: { lockUntil: until * 1000, giftTo: k.name, contactId: k.id, contactName: k.name },
    follow: { k: 'bounty', chal: c.id, contact: k.id, b: { to: k.pubkey, name: k.name, pre: hex(pre), H, amount, until: until * 1000 } } });
  updTx(tx.id, { lockUntil: until * 1000, giftTo: k.name, contactId: k.id, contactName: k.name, bounty: c.id });
  c.bounties = (c.bounties || []).concat([{ to: k.pubkey, name: k.name, txId: tx.id, pre: hex(pre), H, amount, until: until * 1000, state: 'open' }]);
  saveChallenges();
  return { tx: txById(tx.id), b: c.bounties[c.bounties.length - 1] };
}
// the winner's NUTCADE gets the secret; retried from the background check until a relay takes it
async function releaseBounty(c, b) {
  const k = S.contacts.find(x => x.pubkey === b.to);
  const wrap = L.nip17.wrapEvent(nostrKey(), { publicKey: b.to }, JSON.stringify({ t: 'nutcade-bounty', re: c.id, pre: b.pre }));
  const ok = await relayPublish(wrap, 8000, [...new Set(((k && k.relays) || []).concat(relays()))].slice(0, 8));
  b.state = ok ? 'paid' : 'won'; saveChallenges();
  return ok;
}
async function bountyOnResult(c, r) {
  const b = (c.bounties || []).find(x => x.to === r.pubkey && (x.state === 'open' || x.state === 'won'));
  if (!b || !(r.score > c.score)) return;
  if (Date.now() > b.until) return;   // too late: the refund path is open, so the sats come back to you
  b.state = 'won'; b.score = Math.floor(r.score); saveChallenges();
  await releaseBounty(c, b);
  sfx('coin'); toast(`${b.name} beat ${pad6(c.score)} and won your ${money(b.amount)} bounty`, 'pink');
}
async function retryBounties() {
  for (const c of S.challenges.filter(x => x.dir === 'out')) for (const b of (c.bounties || []).filter(x => x.state === 'won' && Date.now() < x.until)) await releaseBounty(c, b).catch(() => {});
  for (const c of S.challenges.filter(x => x.dir === 'out')) for (const b of (c.bounties || []).filter(x => x.unsent && x.state === 'open' && Date.now() < x.until)) await sendRecoveredBounty(c, b).catch(() => {});
}
// Decoding a token needs its mint's keyset ids. A wallet that never held sats at that mint doesn't have them yet, so ask the mint.
async function decodeTok(t) {
  t = cleanToken(String(t || ''));
  const md = L.getTokenMetadata(t), u = String(md.unit || 'sat').toLowerCase();
  extUrl(md.mint);   // (the token's mint field is an address only: one with '|' in it is refused here, before anything reads it)
  try { return L.getDecodedToken(t, Object.keys(S.counters)); } catch (e) {}
  const w = await getWallet(acctKey(extUrl(md.mint), unitOk(u) ? u : 'sat'));   // (the token's mint is an address; its unit picks the account's keysets)
  return w.decodeToken(t);
}
// an incoming bounty: check the ecash really is locked to us and to the hash before showing it
async function readBounty(bo, rec) {
  try {
    const tok = cleanToken(String(bo.token || '')); const d = await decodeTok(tok);
    if (String(d.unit || 'sat').toLowerCase() !== 'sat') return null;   // (bounties are SAT only: one in another unit is not for us)
    let H = null;
    // (E is the sender's: no point math on more coins or keys than a bounty of ours ever has, app_p2bk.js)
    if (!d.proofs.length || d.proofs.length > P2BK_MAX_COINS) return null;
    const locks = [];
    for (const p of d.proofs) {   // the cheap checks of every coin first
      // (the lock as the library reads it, lockOf in app.js: a malformed one, or one needing more than one of its keys, is no bounty for us)
      const lk = lockOf(p.secret); if (!lk || lk.kind !== 'HTLC' || lk.nSigs !== 1) return null;
      const keys = lk.keys; if (!keys.length || keys.length > P2BK_MAX_KEYS || lk.refund.length > P2BK_MAX_KEYS) return null;
      if (p.p2pk_e !== undefined && !p2bkE(p.p2pk_e)) return null;
      // (a hash written in capitals: the library compares it in lower case (#1415), but the Nutshell mints refuse such a coin
      // outright ("invalid HTLC hash"), so nobody can claim it there: no bounty for us)
      if (lk.data !== lk.hash || (H && lk.hash !== H)) return null; H = lk.hash;
      locks.push(keys);
    }
    // our lock key, or one of the older words' kept lock keys (1.52.0: a bounty locked to you before you restored other 12 words)
    const mine = myLockPubs().map(pub => ({ pub, priv: lockPrivFor(pub) }));
    for (let i = 0; i < d.proofs.length; i++) {
      // our key, or (Pay to Blinded Key, app_p2bk.js) our key blinded with the coin's E: the "pubkeys" keys are slots 1, 2...
      // x(k·E) once per coin and key, r per slot from it
      const E = d.proofs[i].p2pk_e; if (E !== undefined && !p2bkE(E)) return null;
      if (!mine.some(({ pub, priv }) => { const zx = E === undefined ? null : p2bkX(priv, E); return (E === undefined || !!zx) && locks[i].some((k, j) => p2bkIs(k, pub, priv, zx, j + 1)); })) return null;
    }
    // the proofs carry a little extra for the mint's fee; show the amount the challenger put up when it's covered
    const amount = num(bo.amount) > 0 && num(bo.amount) <= sum(d.proofs) ? Math.floor(num(bo.amount)) : sum(d.proofs);
    return { token: tok, amount, mint: extUrl(d.mint), H, until: num(bo.until) || Date.now() + BOUNTY_DAYS * 86400e3, state: 'open', game: rec.game };
  } catch (e) { return null; }
}
async function attachBounty(rec, bounty, signer, from) {
  if (!bounty || from !== signer || (rec.bounty && rec.bounty.state === 'won')) return;
  const bo = await readBounty(bounty, rec);
  if (!bo || (rec.bounty && rec.bounty.token === bo.token)) return;
  rec.bounty = bo; saveChallenges();
  sfx('levelup'); toast(`${nameFor(signer) || rec.by} put ${money(bo.amount)} on beating ${pad6(rec.score)} on ${gameById(rec.game).name}`, 'gold');
  if (tab === 'arcade' && !$('#layer .sheet')) refresh();
}
function bountyWon(f) { const rec = S.challenges.find(x => x.id === f.rec && x.dir === 'in'); if (rec && rec.bounty && rec.bounty.state !== 'won') { rec.bounty.state = 'won'; saveChallenges(); } }
async function claimBounty(rec, pre, from) {
  const b = rec.bounty; if (!b || b.state === 'won' || from !== rec.pubkey) return;
  if (!/^[0-9a-f]{64}$/i.test(String(pre || '')) || await sha256hex(L.hexToBytes(pre)) !== String(b.H).toLowerCase()) return;   // (in lower case, as the library compares it)
  const d = await decodeTok(b.token);
  const unlocked = tokEnc({ mint: d.mint, unit: 'sat', proofs: d.proofs.map(p => Object.assign({}, p, { witness: JSON.stringify({ preimage: pre }) })) });
  const who = nameFor(rec.pubkey) || rec.by, g = gameById(rec.game);
  try { await receiveToken(unlocked, `Bounty from ${who}: beat ${pad6(rec.score)} on ${g ? g.name : rec.game}`, { follow: { k: 'bounty-won', rec: rec.id } }); }
  catch (e) { if (/spent/i.test(e.message || '') && b.state !== 'won') { if (e.op) await settleOp(e.op.id).catch(() => {}); if (b.state !== 'won') { b.state = 'gone'; saveChallenges(); } } return; }
  bountyWon({ rec: rec.id });
  sfx('levelup'); celebrate('in', b.amount); toast(`You won ${who}'s ${money(b.amount)} bounty!`, 'lime'); refresh();
}

/* ---------- Extra Life: ecash inheritance with no custodian (NUT-11 time locks) ----------
   Your savings are locked to YOUR key, with your heir's key as the refund key after a date. You can spend them any
   time. Your heir holds a copy that only opens after the date. Each CONTINUE swaps the ecash for fresh ecash with a
   later date and sends your heir the new copy, which also makes their old copy worthless. Stop pressing CONTINUE
   (or lose your phone and your words) and after the date your heir's NUTCADE claims it. */
const EXTRA_PERIODS = [[90, '3 MONTHS'], [182, '6 MONTHS'], [365, '1 YEAR']];
S.extra = store.get('extra', null);         // ours: { mint, amount, proofs, heir:{pubkey,name}, until, days, auto, created, renewed }
S.heirlooms = store.get('heirlooms', []);   // theirs, held for us: { from, name, token, amount, mint, until, state }
const saveExtra = () => store.set('extra', S.extra);
const saveHeir = () => store.set('heirlooms', S.heirlooms.slice(0, 20));
const extraLeft = () => S.extra ? S.extra.until - Date.now() : 0;
const daysLeft = ms => Math.max(0, Math.ceil(ms / 86400e3));
// Lock sats of the balance for the Extra Life (setting it up): to your key, with your heir's key as the refund key
// after the date. The journal has every output before the mint is asked, so an interrupted lock finishes as itself.
const extraLockCfg = (w, until, heirPub) => ({ send: { type: 'lock', options: { mainKeys: [myLockPub()], locktime: Math.floor(until / 1000), refundKeys: ['02' + heirPub] } }, keep: w.defaultOutputType() });
async function lockExtra(url, amount, heirPub, until, follow, ctx = {}) {
  return mintLock(url, async () => {
    const w = await getWallet(url), inputs = [...(S.proofs[url] || [])];
    if (belowMin(url)) throw minErr(url);   // (no new Extra Life at a mint below the minimum)
    if (sum(inputs) < amount) throw new Error(`Not enough funds. This mint holds ${money(sum(inputs))}.`);
    const cfg = extraLockCfg(w, until, heirPub), plan = swapPlan(w, inputs, amount, cfg.send, url);
    if (plan && plan.tooMany) throw manyErr(url, plan.tooMany);
    ctx.hold = limitGate(plan ? plan.spend : feeMax(w, inputs, amount));   // (released by startExtra once its line is written)
    const { r: { keep, send }, op } = await withPick(w, plan && plan.sel, () => journaled(url, 'send', { inputs, amount, locked: true, note: 'Extra Life', tx: { locked: myLockPub() }, follow, lim: limRec(ctx.hold) }, (cb, o) => rSend(o, w, amount, inputs, { includeFees: true, onCountersReserved: cb }, cfg)));
    const used = new Set(inputs.map(p => p.secret));   // (keep holds the coins the swap didn't need, as they were)
    S.proofs[url] = (S.proofs[url] || []).filter(p => !used.has(p.secret)).concat(plain(keep)); closeOp(op); save();
    return plain(send);
  });
}
const extraToken = () => S.extra && tokEnc({ mint: S.extra.mint, unit: 'sat', proofs: S.extra.proofs });
async function sendHeirCopy() {
  const x = S.extra; if (!x) return false;
  const k = S.contacts.find(c => c.pubkey === x.heir.pubkey);
  const body = { t: 'nutcade-extralife', v: 1, token: extraToken(), until: x.until, amount: x.amount };
  const wrap = L.nip17.wrapEvent(nostrKey(), { publicKey: x.heir.pubkey }, JSON.stringify(body));
  const ok = await relayPublish(wrap, 8000, [...new Set(((k && k.relays) || []).concat(relays()))].slice(0, 8));
  x.delivered = !!ok; saveExtra(); return !!ok;
}
async function startExtra(amount, heir, days, auto) {
  if (S.extra) throw new Error('You already have an Extra Life. Cash it out first to start a new one.');
  if (!heir || !heir.pubkey) throw new Error('Pick an heir with a Nostr address, or paste their npub.');
  if (heir.pubkey === L.nostrPub(nostrKey())) throw new Error("Your heir has to be someone else.");
  if (!(await mintCan(S.active, 11))) throw new Error(`${host(S.active)} can't lock ecash to a key (NUT-11). Pick another mint.`);
  piggyGuard(amount);
  const until = Date.now() + days * 86400e3;
  const ctx = {};
  try {
    const before = sum(S.proofs[S.active] || []);
    const proofs = await lockExtra(S.active, amount, heir.pubkey, until, { k: 'extra', heir, days, auto: auto !== false, until }, ctx);
    S.extra = { mint: S.active, amount, proofs, heir, until, days, auto: auto !== false, created: Date.now(), renewed: Date.now() }; saveExtra();
    addTx(Object.assign({ type: 'out', method: 'ecash', amount, fee: Math.max(0, before - sum(S.proofs[S.active] || []) - amount), mint: S.active, note: `Extra Life for ${heir.name}`, status: 'done', extraLife: true, move: true }, ctx.hold && ctx.hold.id ? { limId: ctx.hold.id } : {}));
  } finally { if (ctx.hold) ctx.hold.release(); }
  await sendHeirCopy().catch(() => false);
  return S.extra;
}
/* CONTINUE: one swap. The Extra Life's own locked coins go in (signed with your key) and new coins locked with the
   later date come out; nothing else goes in or out. No coin of your balance is touched, and there is never a moment
   when the Extra Life is plain ecash: if the answer is lost, its journal record (written, with every output, before
   the mint is asked) finishes it; if the request never reached the mint, the old coins and date simply stay. On a
   mint that charges a fee to spend ecash, that fee comes out of the Extra Life itself. */
async function continueExtra(quiet) {
  if (!S.extra) return;
  const url = S.extra.mint;
  const until = await mintLock(url, async () => {
    const x = S.extra; if (!x || x.mint !== url) return 0;
    if (S.ops.some(o => o.mint === url && o.follow && o.follow.k === 'extra-renew')) return 0;   // one is on its way: its record finishes it
    const w = await getWallet(url), ins = [...x.proofs];
    const fee = num(w.getFeesForProofs(ins)), target = sum(ins) - fee;
    if (target < 1) throw new Error("This Extra Life is too small to cover the mint's fee to renew it. Cash it out instead.");
    const until = Date.now() + x.days * 86400e3, follow = { k: 'extra-renew', until };
    const cfg = extraLockCfg(w, until, x.heir.pubkey);
    const pick = w._selectProofs; w._selectProofs = ps => ({ keep: [], send: ps });   // exactly the Extra Life's coins, all of them
    let res;
    try { res = await journaled(url, 'send', { inputs: ins, amount: target, locked: true, note: 'Extra Life', tx: { locked: myLockPub() }, follow }, (cb, o) => rSend(o, w, target, ins, { includeFees: false, privkey: x.unlocked ? undefined : [lockPrivFor(lockOf(ins[0].secret).data)], onCountersReserved: cb }, cfg)); }
    finally { w._selectProofs = pick; }
    const { r: { keep, send }, op } = res;
    if (keep.length) { addProofs(url, keep); addTx({ type: 'in', method: 'ecash', amount: sum(plain(keep)), mint: url, note: `Extra Life cashed out (was for ${x.heir.name})`, self: true }); }   // (none: the amount is exact)
    Object.assign(x, { proofs: plain(send), until, renewed: Date.now(), amount: Math.min(x.amount, sum(plain(send))) }); delete x.unlocked; saveExtra(); closeOp(op); save();
    return until;
  });
  if (!until) return;
  await sendHeirCopy().catch(() => false);
  if (!quiet) { sfx('levelup'); toast(`CONTINUE! ${S.extra.heir.name}'s copy now opens on ${fmtDay(until)}`, 'lime'); }
}
async function cashOutExtra() {
  const x = S.extra; if (!x) return;
  const f = { k: 'extra-end', heir: x.heir, secrets: x.proofs.map(p => p.secret) };
  const tx = await receiveToken(extraToken(), `Extra Life cashed out (was for ${x.heir.name})`, { own: true, hand: true, follow: f });
  extraEnded(f);
  return tx;
}
// the Extra Life these coins were is over: its record is closed (never a newer one), and the heir's copy is marked ended
function extraEnded(f) {
  if (S.extra && S.extra.proofs.some(p => f.secrets.includes(p.secret))) { S.extra = null; saveExtra(); }
  const k = S.contacts.find(c => c.pubkey === f.heir.pubkey);
  const wrap = L.nip17.wrapEvent(nostrKey(), { publicKey: f.heir.pubkey }, JSON.stringify({ t: 'nutcade-extralife-end', v: 1 }));
  relayPublish(wrap, 8000, [...new Set(((k && k.relays) || []).concat(relays()))].slice(0, 8)).catch(() => {});
}
// the sats left the balance when the Extra Life was set up (its "Extra Life for" line): that line now says where they
// went, and comes to the top, so the history still adds up to the balance
function extraPassed(x) {
  const t0 = S.txs.find(t => t.extraLife && t.mint === x.mint && /^Extra Life for /.test(t.note || ''));
  if (t0) { S.txs = [Object.assign(t0, { note: `Extra Life passed to ${x.heir.name}`, ts: Date.now(), passed: true })].concat(S.txs.filter(t => t !== t0)); save(); }
  else addTx({ type: 'out', method: 'ecash', amount: 0, mint: x.mint, note: `Extra Life passed to ${x.heir.name}`, status: 'done', extraLife: true, move: true, fx: null });
}
// opening NUTCADE counts as proof of life: with auto on, once half the time has passed it continues by itself
async function extraTick() {
  const x = S.extra; if (!x) return;
  // (an Extra Life left as plain coins by an earlier version: lock it again now)
  if (x.unlocked && !S.ops.some(o => o.mint === x.mint)) { await continueExtra(true).catch(() => {}); return; }
  if (extraLeft() < 0) {
    // the date passed: if the heir already claimed, the Extra Life is over; if not, it's still ours to continue
    const st = await (await getWallet(x.mint)).checkProofsStates(x.proofs).catch(() => null);
    if (st && st.length && st.every(s => s.state === 'SPENT')) {
      S.extra = null; saveExtra(); extraPassed(x);
      toast(`Your Extra Life passed to ${x.heir.name}`, 'gold'); refresh(); return;
    }
  }
  if (x.auto && extraLeft() < x.days * 86400e3 / 2) await continueExtra(true).catch(() => {});
  else if (!x.delivered) await sendHeirCopy().catch(() => {});
}
// the heir's side
async function onExtraLife(p, from) {
  if (p.t === 'nutcade-extralife-end') { S.heirlooms.filter(h => h.from === from && h.state === 'waiting').forEach(h => { h.state = 'ended'; }); saveHeir(); if (tab === 'wallet' && !$('#layer .sheet')) refresh(); return; }
  let d; try { d = await decodeTok(p.token); } catch (e) { return; }
  if (String(d.unit || 'sat').toLowerCase() !== 'sat') return;   // (Extra Life is SAT only: a copy in another unit is not for us)
  let until = 0;
  for (const pr of d.proofs) {
    // only copies we could actually claim, the lock read as the library reads it (lockOf, app.js): P2PK, our key among its
    // refund keys with one signature enough, and a locktime that ends (digits; "0" has ended already: claimable now)
    const lk = lockOf(pr.secret);
    if (!lk || lk.kind !== 'P2PK' || !lk.refund.some(k => myLockPubs().includes(k)) || lk.nSigsRefund !== 1 || lk.locktime === null) return;
    until = Math.max(until, lk.locktime * 1000);
  }
  const who = nameFor(from);
  const h = { from, name: who || 'A friend', token: cleanToken(String(p.token)), amount: sum(d.proofs), mint: extUrl(d.mint), until, state: 'waiting', at: Date.now() };
  // a renewal always replaces the copy we hold: the old one is dead at the mint once our friend continued,
  // even when two renewals land in the same second and carry the same date
  const old = S.heirlooms.find(x => x.from === from && x.state === 'waiting');
  if (old && (old.token === h.token || old.until > until)) return;
  S.heirlooms = S.heirlooms.filter(x => !(x.from === from && x.state === 'waiting')); S.heirlooms.unshift(h); saveHeir();
  if (!old) { sfx('select'); toast(`${h.name} made you the heir of their Extra Life`, 'gold'); }
  if (tab === 'wallet' && !$('#layer .sheet')) refresh();
}
const claimingHeir = new Set();
function heirClaimed(f) { const h = S.heirlooms.find(x => x.token === f.token); if (h && h.state !== 'claimed') { h.state = 'claimed'; saveHeir(); } }
async function claimHeirlooms() {
  for (const h of S.heirlooms.filter(x => x.state === 'waiting' && Date.now() > x.until + 30e3)) {
    if (claimingHeir.has(h.token)) continue;   // already being claimed: a second try would only find it spent
    claimingHeir.add(h.token);
    try { await receiveToken(h.token, `Extra Life from ${h.name}`, { follow: { k: 'heir', token: h.token } }); heirClaimed({ token: h.token }); sfx('coin'); toast(`${h.name}'s Extra Life passed to you: ${money(h.amount)}`, 'gold'); refresh(); }
    catch (e) {   // "already spent": our own claim's record is settled first (it may have got it after all), then it ended
      if (/spent/i.test(e.message || '') && h.state === 'waiting') { if (e.op) await settleOp(e.op.id).catch(() => {}); if (h.state === 'waiting') { h.state = 'ended'; saveHeir(); } }
    }
    finally { claimingHeir.delete(h.token); }
  }
}

/* ---------- screens ---------- */
const CONT_ICON = `<svg viewBox="0 0 12 12" width="22" height="22" fill="currentColor" aria-hidden="true"><path d="M1 3h2v1h1v1h1V4h1V3h2v1h1v1h1v2h-1v1H9v1H8v1H7v1H5v-1H4V9H3V8H2V7H1z"/></svg>`;
function extraPanel() {
  const x = S.extra, hs = S.heirlooms.filter(h => h.state === 'waiting');
  if (!x && !hs.length) return '';
  let html = '';
  if (x) {
    const left = daysLeft(extraLeft()), soon = left <= Math.min(30, x.days / 4);
    html += `<button class="panel extra-panel ${soon ? 'soon' : ''}" data-act="extraOpen"><span class="xl-heart">${CONT_ICON}</span><span class="mid"><span class="h2">Extra Life</span>
      <span class="tiny" data-noi18n>${money(x.amount)} → ${esc(x.heir.name)}</span><span class="tiny muted">${soon ? `CONTINUE? ${left} days left` : `Opens for them on ${fmtDay(x.until)}`}</span></span></button>`;
  }
  for (const h of hs) html += `<div class="panel extra-panel heir"><span class="xl-heart">${CONT_ICON}</span><span class="mid"><span class="h2">Extra Life from <span data-noi18n>${esc(h.name)}</span></span>
      <span class="tiny">${money(h.amount)}</span><span class="tiny muted">Yours after ${fmtDay(h.until)} if they stop pressing CONTINUE</span></span></div>`;
  return html;
}
function openExtra() {
  if (needSeed()) return;
  const x = S.extra;
  if (x) {
    const left = daysLeft(extraLeft());
    openSheet('Extra Life', `
      <div class="continue-box"><div class="cont-q">CONTINUE?</div><div class="cont-n">${left}</div><div class="tiny muted">days until ${esc(x.heir.name)} can claim it</div></div>
      <dl class="kv"><dt>Locked</dt><dd>${money(x.amount)}</dd><dt>Heir</dt><dd data-noi18n>${esc(x.heir.name)}</dd><dt>Opens for them</dt><dd data-noi18n>${fmtDay(x.until)}</dd><dt>Mint</dt><dd data-noi18n>${esc(host(x.mint))}</dd><dt>Their copy</dt><dd>${x.delivered ? 'Delivered over Nostr' : 'Not delivered yet'}</dd></dl>
      <label class="toggle set" for="xlAuto"><span><span class="tl">Continue when I open NUTCADE</span><span class="th">Once half the time has passed, opening NUTCADE counts as CONTINUE. Turn this off to press it yourself.</span></span><input id="xlAuto" type="checkbox" ${x.auto ? 'checked' : ''}></label>
      <button class="btn solid gold block" data-act="extraContinue">CONTINUE</button>
      <div class="row wrap"><button class="btn sm violet" data-act="extraCopy">Heir's copy</button><button class="btn sm red" data-act="extraCash">Cash out</button></div>
      <div class="tiny muted">You can spend these sats any time: Cash out puts them back in your balance and ${esc(x.heir.name)}'s copy stops working. Every CONTINUE does the same to their old copy and sends them a new one.</div>
      <div id="sheetErr"></div>`, body => { const t = body.querySelector('#xlAuto'); if (t) t.onchange = () => { x.auto = t.checked; saveExtra(); sfx('blip'); }; return null; });
    return;
  }
  const cs = S.contacts.filter(c => c.pubkey);
  openSheet('Extra Life', `
    <div class="continue-box"><div class="cont-q">EXTRA LIFE</div><div class="tiny">Savings that pass to someone you trust if you stop playing</div></div>
    <ol class="steps"><li>Lock some sats. They stay yours: spend them any time.</li><li>Your heir gets a copy that only opens after the date.</li><li>Press CONTINUE now and then (or just open NUTCADE) to push the date back.</li><li>If you stop, your heir's NUTCADE claims the sats once the date passes.</li></ol>
    <div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="10000" autocomplete="off"></div>
    <div class="field"><label for="xlTo">Heir</label><select id="xlTo" class="inp">${cs.map(c => `<option value="${esc(c.id)}" data-noi18n>${esc(c.name)}</option>`).join('')}<option value="">Someone else (paste their npub)</option></select></div>
    <div class="field" id="xlKeyF" ${cs.length ? 'hidden' : ''}><label for="xlKey">Their npub</label><input id="xlKey" class="inp" data-noi18n placeholder="npub1…" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
    <div class="field"><label>If I stop pressing CONTINUE, it opens for them after</label><div class="seg three" role="group" aria-label="Opens after">${EXTRA_PERIODS.map(([d, l]) => `<button type="button" data-act="giftDays" data-days="${d}" aria-pressed="${d === 182}">${l}</button>`).join('')}</div></div>
    <div class="notice">This depends on the mint still running when the date comes, so use a mint you trust for the long term. Your heir needs NUTCADE with Nostr turned on to receive their copy, or you can hand it to them yourself.</div>
    <button class="btn solid gold block" data-act="extraStart">Lock it in</button><div id="sheetErr"></div>`,
    body => { const sel = body.querySelector('#xlTo'); sel.onchange = () => { body.querySelector('#xlKeyF').hidden = !!sel.value; }; return null; });
}
function openHeirCopy() {
  const x = S.extra; if (!x) return;
  const t = extraToken();
  openSheet("Heir's copy", `<p style="margin:0">Give this to ${esc(x.heir.name)} if they didn't get it over Nostr. Nobody can use it before ${fmtDay(x.until)}, and after that only ${esc(x.heir.name)} can. Your next CONTINUE replaces it.</p>
    ${qrBlock(t, "Heir's copy QR")}<div class="row wrap"><button class="btn sm gold" data-act="copy" data-text="${esc(t)}">Copy</button>${ctBtn(t)}<button class="btn sm" data-act="extraOpen">Back</button></div>`);
}

/* ---------- mint report card ----------
   Grades a mint from what NUTCADE can check itself, with no outside rating service:
   uptime and speed from health checks, its track record with your own payments, its age (first seen by you, or
   earliest mention on Nostr), its key history (a changed identity key is a red flag; frequent keyset changes are
   worth knowing) and recommendations on Nostr (NIP-87). */
S.mintlog = keyMap(store.get('mintlog', {}), mintKeyOk);   // (no prototype; only mint addresses: app.js keyMap)
const saveMlog = () => store.set('mintlog', S.mintlog);
function mlog(url0) { const url = acctUrl(url0); if (!mintKeyOk(url)) return { first: Date.now(), pr: '', ms: [], ops: [0, 0], keysets: {}, changes: [] };   // (never stored under anything but a mint address)
  if (!S.mintlog[url]) S.mintlog[url] = { first: Date.now(), pr: '', ms: [], ops: [0, 0], keysets: {}, changes: [] }; return S.mintlog[url]; }
function logProbe(url, h) {
  const l = mlog(url); l.pr = (l.pr + (h.ok ? '1' : '0')).slice(-200);
  if (h.ok && h.ms != null) l.ms = l.ms.concat([h.ms]).slice(-30);
  saveMlog();
}
// only failures that are the mint's fault count against it (it errored or didn't answer), not "not enough sats" and the like
function opMark(url, ok, e) {
  if (!url || !S.mints.find(m => m.url === url)) return;
  if (!ok && !/Failed to fetch|NetworkError|Load failed|timed? ?out|50[0-9]|Internal Server|Bad Gateway|Service Unavailable/i.test(String(e && (e.message || e)) + ' ' + ((e && e.status) || ''))) return;
  const l = mlog(url); l.ops[ok ? 0 : 1]++; saveMlog();
}
const GRADES = ['F', 'D', 'C', 'B', 'A'];
const gradeCls = g => ({ A: 'good', B: 'good', C: 'slow', D: 'slow', F: 'bad' })[g] || 'wait';
async function inspectMint(url0) {
  const url = acctUrl(url0), l = mlog(url), now = Date.now();
  const get = async p => { const ac = new AbortController(); const tm = setTimeout(() => ac.abort(), 7000); try { const r = await fetch(url + p, { cache: 'no-store', signal: ac.signal }); return r.ok ? await r.json() : null; } finally { clearTimeout(tm); } };
  const [info, ks] = await Promise.all([get('/v1/info').catch(() => null), get('/v1/keysets').catch(() => null)]);
  if (info && info.pubkey) {
    if (l.pub && l.pub !== info.pubkey && !(l.pubChanged && l.pubChanged.to === info.pubkey)) l.pubChanged = { from: l.pub, to: info.pubkey, at: now };
    if (!l.pub) l.pub = info.pubkey;
    l.info = mintInfoOf(info);   // (what the report card used, plus the contact, terms and description Mints → Details shows: see app_trust.js)
  }
  if (ks && Array.isArray(ks.keysets)) {
    // only the units this wallet holds at the mint are watched (SAT as in 1.30 when none is held yet); a unit watched for the
    // first time has its keysets noted without a change, so adding USD at a mint never reads as "new keys"
    const held = new Set(S.mints.filter(m => acctUrl(m.url) === url).map(m => acctUnit(m.url))); if (!held.size) held.add('sat');
    const uOf = v => (v && v.unit) || 'sat', had = new Set(Object.values(l.keysets).map(uOf));
    for (const k of ks.keysets.filter(k => k && okKey(k.id) && held.has(k.unit || 'sat'))) {   // (a keyset id is the mint's string: never __proto__ and the like)
      const old = l.keysets[k.id], ku = k.unit || 'sat';
      if (!old) { l.keysets[k.id] = Object.assign({ first: now, active: !!k.active }, ku === 'sat' ? {} : { unit: ku }); if (had.has(ku)) l.changes.push({ at: now, kind: 'new', id: k.id }); }
      else if (old.active && !k.active) { old.active = false; l.changes.push({ at: now, kind: 'retired', id: k.id }); }
      else old.active = !!k.active;
    }
    l.ksTotal = ks.keysets.filter(k => held.has(k.unit || 'sat')).length;
    l.changes = l.changes.slice(-20);
  }
  l.checked = now; saveMlog();
  if (!l.nostr || l.nostr.v !== 2 || l.nostr.me !== rvMe() || now - l.nostr.at > 86400e3) await nostrRecord(url).catch(() => {});   // (v 2: 1.36, one rating per person, yours apart)
  return l;
}
// recommendations (kind 38000) and announcements (kind 38172) that name this mint. One rating per person (their newest
// review; "[N/5]" with N from 1 to 5, as cashu.me reads it). Your own review (this wallet's Nostr key, its signature
// checked; any key of yours: app_identity.js idKeys) is kept apart, one per key, as `mines` (`mine` its newest), never one at or before
// that key's deletion, so the report card counts yours once (app_review.js, rvAllMine/rvMine); announcements with a good
// signature are kept (at most 10) for the review's "a" tag.
function nostrRecord(url) {
  return new Promise(resolve => {
    const l = mlog(url), per = new Map(), anns = [], seen = new Set(), mines = new Map(); let since = 0, open = 0, finished = false;
    let me = null, keys = []; try { me = rvMe(); keys = rvKeys(); } catch (e) {}   // (every key of yours: app_identity.js)
    const variants = [...new Set([url, url + '/', url.replace(/^https:/, 'http:')])];
    const socks = [];
    const done = () => { if (finished) return; finished = true; socks.forEach(s => { try { s.close(); } catch (e) {} });
      const stars = [...per.values()].map(x => x.stars).filter(Boolean);
      if (me !== rvMe()) { resolve(l.nostr); return; }   // (other 12 words or another identity meanwhile: this look was for the old keys, nothing is kept)
      const ms = [...mines.values()].sort((a, b) => b.at - a.at);
      l.nostr = { v: 2, at: Date.now(), recs: per.size, stars: stars.slice(0, 50), since: since || null, mine: ms[0] || null, mines: ms, anns, me }; saveMlog(); resolve(l.nostr); };
    for (const r of relays().slice(0, 4)) {
      let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
      socks.push(ws); open++;
      ws.onopen = () => ws.send(JSON.stringify(['REQ', 'rc', { kinds: [38000, 38172], '#u': variants, limit: 300 }]));
      ws.onmessage = m => { let d; try { d = JSON.parse(m.data); } catch (e) { return; }
        if (d[0] === 'EVENT' && d[2] && !seen.has(d[2].id)) { const e = d[2]; seen.add(e.id);
          if (!since || e.created_at * 1000 < since) since = e.created_at * 1000;
          const at = num(e.created_at);
          if (e.kind === 38000 && typeof e.pubkey === 'string') {
            if (keys.includes(e.pubkey)) {   // (yours, under any key of yours: kept apart, one per key, never one at or before that key's deletion)
              if (at > rvDelOf(l, e.pubkey) && (!mines.has(e.pubkey) || at > mines.get(e.pubkey).at) && rvSig(e)) { const p = rvParse(e.content); mines.set(e.pubkey, { stars: p.stars, text: rvClean(p.text).slice(0, RV_MAX), at, d: rvD(e), id: e.id, relay: true, pk: e.pubkey }); }
            }
            else { const o = per.get(e.pubkey); if (!o || at > o.at) per.set(e.pubkey, { at, stars: rvParse(e.content).stars }); }
          } else if (e.kind === 38172 && anns.length < 10 && typeof e.pubkey === 'string' && rvSig(e)) anns.push({ pubkey: e.pubkey, d: rvD(e), relay: r, at }); }
        else if (d[0] === 'EOSE') { try { ws.close(); } catch (e) {} if (--open <= 0) done(); } };
      ws.onerror = () => { if (--open <= 0) done(); };
    }
    if (!socks.length) done();
    setTimeout(done, 6000);
  });
}
function reportCard(url) {
  // each detail is a list of short parts, so every part translates on its own
  const l = mlog(url), now = Date.now(), rows = [];
  const band = (v, cuts) => { for (let i = 0; i < cuts.length; i++) if (v >= cuts[i]) return GRADES[4 - i]; return 'F'; };
  const pl = (n, one, many) => `${fmt(n)} ${n === 1 ? one : many}`;
  // uptime and speed
  const n = l.pr.length, up = n ? [...l.pr].filter(c => c === '1').length / n : 0;
  rows.push({ k: 'Uptime', g: n >= 5 ? band(up * 100, [99, 95, 90, 75]) : '?', d: n >= 5 ? [`${(up * 100).toFixed(up === 1 ? 0 : 1)}% of ${n} checks answered`] : [`Only ${n} checks so far`] });
  const ms = l.ms.slice().sort((a, b) => a - b), med = ms.length ? ms[Math.floor(ms.length / 2)] : null;
  rows.push({ k: 'Speed', g: med == null ? '?' : band(-med, [-500, -1000, -2500, -5000]), d: [med == null ? 'Not measured yet' : `Answers in about ${fmt(med)} ms`] });
  // age
  const viaNostr = !!(l.nostr && l.nostr.since && l.nostr.since < l.first);
  const since = viaNostr ? l.nostr.since : l.first, days = Math.floor((now - since) / 86400e3);
  const ageTxt = days >= 365 ? `Known for ${pl(Math.floor(days / 365), 'year', 'years')}` : days >= 60 ? `Known for ${Math.floor(days / 30)} months` : `Known for ${pl(days, 'day', 'days')}`;
  // a mint you only just met isn't failing, it's new: NEW until it's 30 days old, and it doesn't pull the overall grade down
  rows.push({ k: 'Age', g: days < 30 ? 'NEW' : band(days, [365, 180, 90, 30]), d: [ageTxt, viaNostr ? 'since its first mention on Nostr' : 'since you first used it'] });
  // keys
  const recent = (l.changes || []).filter(c => c.kind === 'new' && now - c.at < 90 * 86400e3).length;
  if (l.pubChanged) rows.push({ k: 'Keys', g: 'F', d: [`Its identity key changed on ${fmtDay(l.pubChanged.at)}. That can mean a new operator, so be careful.`], warn: true });
  else rows.push({ k: 'Keys', g: !l.pub ? '?' : recent === 0 ? 'A' : recent === 1 ? 'B' : recent <= 3 ? 'C' : 'D', d: !l.pub ? ['Not checked yet'] : ['Same identity key since you added it', recent ? `${pl(recent, 'new keyset', 'new keysets')} in 90 days` : 'no key changes in 90 days'].concat(l.ksTotal > 1 ? [`${l.ksTotal} keysets in its history`] : []) });
  // your own audit trail
  const [ok, bad] = l.ops, tot = ok + bad;
  rows.push({ k: 'Track record', g: tot >= 5 ? band(ok / tot * 100, [99, 95, 90, 80]) : '?', d: tot ? [`${ok} of ${tot} of your payments and swaps went through`].concat(bad ? [`${bad} failed on the mint's side`] : []) : ['No payments with it yet'] });
  // community
  // (other people from the relays, one each, plus your own review once: app_review.js)
  const own = l.nostr && l.nostr.v === 2 && l.nostr.me === rvMe() ? rvMine(url) : null;   // (read for another key: yours isn't apart, so not added)
  const nr = l.nostr && { recs: l.nostr.recs + (own ? 1 : 0), stars: l.nostr.stars.concat(own && own.stars ? [own.stars] : []) };
  const avg = nr && nr.stars.length ? nr.stars.reduce((a, b) => a + b, 0) / nr.stars.length : null;
  rows.push({ k: 'Reviews', g: !nr ? '?' : nr.recs === 0 ? 'D' : avg != null && avg < 3 ? 'D' : band(nr.recs, [10, 5, 2, 1]), d: !nr ? ['Not checked yet'] : nr.recs ? [`Recommended by ${pl(nr.recs, 'Nostr user', 'Nostr users')}`].concat(avg != null ? [`${avg.toFixed(1)}/5 from ${pl(nr.stars.length, 'rating', 'ratings')}`] : []) : ['Nobody recommends it on Nostr yet'] });
  const known = rows.filter(r => r.g !== '?' && r.g !== 'NEW');
  let overall = known.length >= 2 ? GRADES[Math.round(known.reduce((t, r) => t + GRADES.indexOf(r.g), 0) / known.length)] : '?';
  if (l.pubChanged && overall !== '?' && GRADES.indexOf(overall) > 1) overall = 'D';
  return { overall, rows };
}
function reportChip(url) {
  const r = reportCard(url);
  return `<button class="chip grade ${gradeCls(r.overall)}" data-act="reportOpen" data-url="${esc(url)}" title="Report card">GRADE <span data-noi18n>${r.overall}</span></button>`;
}
function openReport(url) {
  const m = S.mints.find(x => x.url === url) || { name: host(url), url };
  const draw = (busy) => {
    const r = reportCard(url), l = mlog(url);
    return `<div class="report"><div class="grade-big ${gradeCls(r.overall)}"${r.overall.length > 1 ? '' : ' data-noi18n'}>${r.overall}</div><div><div class="h2 uname" data-noi18n>${esc(m.name)}</div><div class="tiny muted" data-noi18n>${esc(host(url))}</div>${l.info && l.info.version ? `<div class="tiny muted" data-noi18n>${esc(l.info.version)}</div>` : ''}</div></div>
      <div class="report-rows">${r.rows.map(x => `<div class="rrow ${x.warn ? 'warn' : ''}"><span class="rg ${gradeCls(x.g)}${x.g.length > 1 ? ' word' : ''}"${x.g.length > 1 ? '' : ' data-noi18n'}>${x.g}</span><span><b>${x.k}</b><span class="tiny muted">${x.d.map(p => `<span>${p}</span>`).join(' · ')}</span></span></div>`).join('')}</div>
      ${l.info && l.info.motd ? `<div class="notice">Message from the mint: <span data-noi18n>${esc(l.info.motd)}</span></div>` : ''}
      <div class="tiny muted">Graded on this phone from health checks, your own payments with this mint, its keys and Nostr recommendations. A good grade isn't a guarantee: only keep what you can afford to lose at any one mint.</div>
      ${busy ? busyHTML('CHECKING THE MINT') : `<div class="row wrap"><button class="btn sm" data-act="reportOpen" data-url="${esc(url)}" data-fresh="1">Check again</button>${rvBtn(url)}</div>`}`;
  };
  openSheet('Report card', draw(true), body => {
    let live = true;
    Promise.all([inspectMint(url), probeHealth(url)]).finally(() => { if (live && body.isConnected) { body.innerHTML = draw(false); } });
    return () => { live = false; };
  });
}
