/* ===================== Unclaimed-token reminders (1.27) ===================== */
/* A token you sent stays on the keys it was made with until someone claims it. If nobody ever does and the mint drops
   those keys, its sats are lost for you and for whoever holds the token. So the wallet screen says so:
   "N tokens you sent are still unclaimed — take them back?"
   - which tokens: ordinary ecash tokens you sent (printed ones too) that are still unclaimed. Gifts, treasure hunts and
     bounties come back on their own, and a payment for someone's request is theirs: never counted;
   - when: once a token has waited RM_AGE (30 days), or at any age as soon as its mint is retiring its keys (a keyset
     the mint marks inactive, one whose final expiry is less than KS_SOON away, or one the mint no longer lists; known
     only once the mint has been loaded, as the keyset check-up knows it);
   - before saying so, the background check asks the mint (NUT-07, with "Check sent tokens" on, the default) whether
     those tokens were claimed meanwhile: a claimed one is marked claimed and not counted. A mint that doesn't answer
     changes nothing;
   - Take back is the usual take-back (the token claimed back into this wallet, through the journal, one at a time), so
     there is no new way to move money. One claimed by someone else first is said so and marked claimed;
   - Later hides the line for RM_LATER (7 days), or RM_LATER_SOON (1 day) when keys are retiring; a token whose keys
     start retiring after that shows it again at once. "Remind me about unclaimed tokens" in Settings turns it off.
   Each wallet (the duress PIN's too) has its own tokens and its own setting; nothing shows while the PIN screen is up. */
const RM_AGE = 30 * 86400e3, RM_LATER = 7 * 86400e3, RM_LATER_SOON = 86400e3, RM_RECHECK = 6 * 3600e3, RM_SHOW = 5;
// Never counted either: a token locked to someone's key (a payment for a locked request: only they can claim it), the
// duress PIN wallet's sats (a line settled from the journal may lack the flag, so its note counts too), a token being
// taken back right now (its receive step still open in the journal, its answer lost), a token whose coins already sit
// in saved lines waiting to be claimed (a take-back in parts that couldn't finish), and one someone claimed part of
// (rmPart: its coins can't come back as one token)
const rmOpen = t => !!t && t.type === 'out' && t.method === 'ecash' && t.status === 'pending' && !!t.token && !t.incoming
  && !t.lockUntil && !t.hunt && !t.bounty && !t.reqPay && !t.giftTo && !t.locked && !t.duressFund && !t.rmPart
  && t.note !== 'Sats for the duress PIN wallet' && !S.ops.some(o => o.kind === 'receive' && o.own === t.id) && !rmHeld(t);
// the coins of saved incoming lines still waiting to be claimed (cached until those lines change)
let rmHeldCache = { key: null, set: new Set() };
function rmHeld(t) {
  const open = S.txs.filter(x => x.status === 'pending' && x.incoming);
  const key = open.map(x => x.id).join(' ');
  if (key !== rmHeldCache.key) {
    const set = new Set();
    for (const x of open) { try { for (const p of L.getDecodedToken(cleanToken(x.incoming), Object.keys(S.counters)).proofs || []) set.add(String(p.secret)); } catch (e) {} }
    rmHeldCache = { key, set };
  }
  if (!rmHeldCache.set.size) return false;
  return (Array.isArray(t.sent) ? t.sent : []).some(p => p && rmHeldCache.set.has(String(p.secret)));
}
function rmKeysets(t) {
  let ps = Array.isArray(t.sent) ? t.sent : [];
  if (!ps.length) { try { ps = L.getDecodedToken(cleanToken(t.token), Object.keys(S.counters)).proofs || []; } catch (e) { ps = []; } }
  return [...new Set(ps.map(p => p && p.id).filter(Boolean))];
}
// its mint is retiring the keys of some of its coins (only known once the mint is loaded)
function rmRetiring(t, now = Date.now()) {
  const p = wallets[t.mint], w = p && p.ready; if (!w) return false;
  const all = ksAll(w); if (!all.length) return false;
  return rmKeysets(t).some(id => { const k = all.find(k => k.id === id); return k ? !k.isActive || ksSoon(k, now) : /^[0-9a-f]+$/i.test(id); });   // (an id the mint no longer lists: retiring, unless it is an old base64 id the mint may simply list differently)
}
function rmDue(now = Date.now()) {
  const out = [];
  for (const t of S.txs) { if (!rmOpen(t)) continue; const soon = rmRetiring(t, now); if (soon || now - num(t.ts) >= RM_AGE) out.push({ t, soon }); }
  return out;
}
function rmShown(now = Date.now()) {
  if (!S.seed || S.prefs.remind === false) return [];
  const due = rmDue(now); if (!due.length) return [];
  const l = S.prefs.rmLater || {}, saw = new Set(l.soon || []);
  return now >= num(l.until) || due.some(x => x.soon && !saw.has(x.t.id)) ? due : [];
}
// asked at the mint in the background, at most every RM_RECHECK per token: claimed meanwhile, or not
const rmAsked = new Map();
async function rmCheck(url) {
  if (!S.prefs.checkSent || S.prefs.remind === false) return;
  const now = Date.now();
  for (const { t } of rmDue(now).filter(x => x.t.mint === url && Array.isArray(x.t.sent) && x.t.sent.length && now - (rmAsked.get(x.t.id) || 0) > RM_RECHECK).slice(0, 20)) {
    rmAsked.set(t.id, now);
    try { if (!(await inTime(checkClaim(t), 20000))) await rmPartCheck(t); } catch (e) {}   // (a mint that doesn't answer: nothing changes, the next one is still asked)
  }
}
function rmPanel() {
  const due = rmShown(); if (!due.length) return '';
  const n = due.length, soon = due.filter(x => x.soon).length, total = moneyList(perUnit(due.map(x => x.t)));   // (one total per unit)
  const rows = due.slice(0, RM_SHOW).map(({ t, soon }) => `<button class="linkbtn rm-row" data-act="tx" data-id="${esc(t.id)}"><span data-noi18n>${esc(fmtDate(t.ts))}</span> · <span>${moneyU(t.amount, txUnit(t))}</span>${t.note ? ` · <span data-noi18n>${esc(t.note)}</span>` : ''}${soon ? ' · <span class="rm-soon">KEYS RETIRING</span>' : ''}</button>`).join('');
  return `<div class="panel rm-ask" data-n="${n}"><span class="h2">Unclaimed tokens</span>
    <span class="tiny">${n === 1 ? '1 token you sent is still unclaimed — take it back?' : `${n} tokens you sent are still unclaimed — take them back?`}</span>
    <span class="tiny">${total} in all. Taking a token back cancels it: whoever has it can no longer claim it.</span>
    ${soon ? `<span class="tiny rm-warn">${soon === 1 ? 'Its mint is retiring the keys of 1 of them. Once the mint drops those keys, its sats are lost for everyone.' : `Their mints are retiring the keys of ${soon} of them. Once a mint drops those keys, their sats are lost for everyone.`}</span>` : ''}
    <div class="rm-list">${rows}${n > RM_SHOW ? `<span class="tiny muted">${n - RM_SHOW} more in Notes</span>` : ''}</div>
    <div class="row wrap"><button class="btn sm gold" data-act="rmTake">${n === 1 ? 'Take it back' : 'Take them back'}</button><button class="btn sm" data-act="rmLater">Later</button></div></div>`;
}
// some of its coins spent, not all: someone claimed part of it, so it can't be taken back as a token: no longer counted
async function rmPartCheck(t) {
  const w = await getWallet(t.mint), st = await inTime(w.checkProofsStates(t.sent), 20000), cur = txById(t.id);
  if (cur && cur.status === 'pending' && st.some(s => s.state === 'SPENT') && !st.every(s => s.state === 'SPENT')) { updTx(t.id, { rmPart: true }); return true; }
  return false;
}
// the usual take-back of one token: 'back', 'claimed' (someone else got it first) or 'gone' (no longer open); throws
// when the mint can't be reached or refuses
async function rmTakeOne(t) {
  const cur = txById(t.id); if (!rmOpen(cur)) return cur && cur.status === 'claimed' ? 'claimed' : 'gone';
  reclaiming.add(t.id);
  try { await receiveToken(cur.token, 'Reclaimed: ' + (cur.note || 'ecash token'), { own: true, hand: true }); }
  catch (e) {
    if (isSpentErr(e) || /already spent/i.test(String(e && (e.raw || e.message)))) {
      const now = txById(t.id) || {}; if (now.status === 'reclaimed') return 'back';
      let claimed = false; try { claimed = await checkClaim(now); } catch (x) {}
      if (claimed || (txById(t.id) || {}).status === 'claimed') return 'claimed';
      let part = false; try { part = await rmPartCheck(now); } catch (x) {}
      if (part) return 'part';
    }
    throw e;
  } finally { setTimeout(() => reclaiming.delete(t.id), 5000); }
  if ((txById(t.id) || {}).status === 'pending') updTx(t.id, { status: 'reclaimed' });
  return 'back';
}
async function rmTakeAll() {
  const r = { back: 0, claimed: 0, part: 0, bad: [] };
  for (const { t } of rmShown()) {
    try { const x = await rmTakeOne(t); if (x === 'back') r.back++; else if (x === 'claimed') r.claimed++; else if (x === 'part') r.part++; }
    catch (e) { r.bad.push(`${moneyU(t.amount, txUnit(t))}: ${friendly(e, t.mint).message}`); }
  }
  return r;
}
window.NutRemind = { wallet: url => (wallets[url] || {}).ready || null, due: now => rmDue(now).map(x => ({ id: x.t.id, soon: x.soon })), shown: now => rmShown(now).map(x => x.t.id), check: url => rmCheck(url), open: t => rmOpen(t), AGE: RM_AGE };
