/* ---------- Batched deposits (1.34.0, NUT-29) ----------
   When several paid Lightning deposits wait at one mint and the mint advertises batched minting for bolt11 (nuts[29]),
   they are claimed with one request (cashu-ts prepareBatchMint / completeBatchMint) instead of one each. Nothing else
   changes: a mint without NUT-29, or a single paid deposit, takes exactly the 1.33.0 path (checkQuote).
   - Which: the app's own rounds (the background check, the 8-second check of fresh invoices, a mint's live "paid"
     update, npub.cash) go through depCheck / depAll. At a NUT-29 mint they gather for a moment into one round per mint
     (depRun): each waiting deposit's state is asked as before (one GET each); those PAID (and, if NUT-20 locked, with
     a key here) are claimed in batches of at most the mint's max_batch_size (cashu-ts caps it at 100), its request
     limit (NUT-06) in quotes and in outputs; a lone one left over goes on its own. UNPAID ones are not asked again in
     that round; anything else (ISSUED, PENDING, a failed look) gets the usual single check.
   - Crash safety: the batch's counters are written on every deposit in it, before the request leaves (q.ctr, with the
     batch's id `b` and total `t`; an earlier try's counters move to q.was as with a single claim). A lost answer is
     settled like a single one: the deposit's check finds it ISSUED and creditDepositRange restores the batch's range;
     coins there adding up to exactly the batch's total are that batch's, and every deposit of the batch still open is
     booked at once (btBook: one write, each its own line and amount). Never booked from a refused request.
   - Any batch failure: no answer -> the single checks that follow decide (ISSUED: credited from the batch's counters;
     PENDING: waits; PAID: claimed on its own). A refusal (not paid, already issued, unit, not supported, a login error,
     "Blind authentication failed" that auTruth can't explain) -> each claimed on its own in the same round, and no
     batch at that mint for BT_OFF_MS (one fallback per round, never a loop); but a keyset change only refreshes the
     keys, and an expired deposit is only left out of later batches (btRefused). A login mint with no BAT to be had sends
     no batch at all (authGate): the single checks give the usual login hint.
   - One at a time: every deposit in a batch is held with the same lock a single check takes ('quote:' + id, across
     tabs), taken in sorted order; a check of one of them started meanwhile in this tab joins the batch (flights). */
const BT_GATHER = 250, BT_OFF_MS = 30 * 60e3, BT_CAP = 100;
const bt = { rounds: new Map(), off: new Map(), skip: new Set() };   // (skip: deposits a batch was refused for, each claimed on its own from then on)
// the batch size the mint takes for Lightning deposits, or 0 (no NUT-29 for bolt11, its wallet not loaded, or turned off for now)
function btMax(url) {
  if ((bt.off.get(url) || 0) > Date.now()) return 0;
  const w = (wallets[url] || {}).ready; if (!w) return 0;
  try {
    const s = w.getMintInfo().isSupported(29); if (!s || !s.supported) return 0;
    const p = s.params || {}; if (Array.isArray(p.methods) && !p.methods.includes('bolt11')) return 0;
    let n = Math.min(BT_CAP, Math.floor(num(p.max_batch_size) || BT_CAP)); const m = mintMax(url); if (m) n = Math.min(n, m);
    return n >= 2 ? n : 0;
  } catch (e) { return 0; }
}
const btBits = n => { let c = 0; for (let x = BigInt(Math.max(0, Math.floor(num(n)))); x > 0n; x >>= 1n) c += Number(x & 1n); return c; };
// a deposit that may be paid now (a live update, the 8-second check): at a NUT-29 mint it joins that mint's next round
function depCheck(q) {
  if (q.kind !== 'bolt11' || !btMax(q.mint)) return checkQuote(q);
  return depRound(q.mint, [q]).then(m => { const v = m.get(q.quote); if (v instanceof Error) throw v; return v || 'waiting'; });
}
// these deposits, one mint after the other: a NUT-29 mint's in one round, any other mint's one at a time as before
async function depAll(qs, wrap = p => p) {
  const by = new Map(); for (const q of qs) { if (!by.has(q.mint)) by.set(q.mint, []); by.get(q.mint).push(q); }
  for (const [url, list] of by) {
    if (list.filter(q => q.kind === 'bolt11').length >= 2) await getWallet(url).catch(() => {});   // (loaded here as checkQuote would load it: no other request)
    if (btMax(url) && list.filter(q => q.kind === 'bolt11').length >= 2) {
      await wrap(depRound(url, list.filter(q => q.kind === 'bolt11'))).catch(() => {});
      for (const q of list.filter(q => q.kind !== 'bolt11')) await wrap(checkQuote(q)).catch(() => {});
    } else for (const q of list) await wrap(checkQuote(q)).catch(() => {});
  }
}
function depRound(url, qs) {
  let r = bt.rounds.get(url);
  if (!r) {
    r = { ids: new Set() }; bt.rounds.set(url, r);
    r.p = sleep(BT_GATHER).then(() => { if (bt.rounds.get(url) === r) bt.rounds.delete(url); return depRun(url, [...r.ids]); });
  }
  for (const q of qs) r.ids.add(q.quote);
  return r.p;
}
// one round at a mint: the batches, then a single check for every deposit they didn't settle
async function depRun(url, ids) {
  const res = new Map();
  try { if (btMax(url) && ids.length >= 2) await btClaim(url, ids, res); } catch (e) {}
  for (const id of ids) {
    if (res.has(id)) continue;
    const q = S.quotes.find(x => x.quote === id);
    if (!q) { const t = S.txs.find(x => x.quote === id); res.set(id, t && t.status === 'done' ? 'paid' : 'gone'); continue; }   // (as checkQuote says it)
    try { res.set(id, await inTime(checkQuote(q), STEP_MS)); } catch (e) { res.set(id, e instanceof Error ? e : new Error(String(e))); }
  }
  return res;
}
// the key a NUT-20 locked deposit is signed with (npub.cash locks to your Nostr key), or null
// (a deposit's own lock key first: every quote NUTCADE makes since 1.35 is locked to one, app.js newDepositQuote)
const quoteKey = pub => (S.quotes.find(q => q.lockPriv && q.lockPub === String(pub).toLowerCase()) || {}).lockPriv || npcPrivFor(pub) || (S.p2pk.find(x => hex(L.getPubKeyFromPrivKey(L.hexToBytes(x.priv))) === String(pub).toLowerCase()) || {}).priv || null;
async function btClaim(url, ids, res) {
  await syncIfStale();
  const w = await getWallet(url), max = btMax(url); if (!max) return;
  const free = q => q && q.kind === 'bolt11' && q.mint === url && !busyQuotes.has(q.quote) && !flights.has('quote:' + q.quote);
  const cand = ids.map(id => S.quotes.find(x => x.quote === id)).filter(free);
  if (cand.length < 2) return;
  // each one's state, asked as the single check asks it (and written down the same way)
  const st = new Map();
  await Promise.all(cand.map(async q => { const r = await inTime(w.checkMintQuoteBolt11(q.quote), MINT_MS).catch(() => null); if (r && r.quote === q.quote) st.set(q.quote, withLockPub(r, q.lockPub)); }));   // (the record's own lock key when the mint leaves it out: app.js
  const paid = [];
  for (const q0 of cand) {
    const r = st.get(q0.quote), q = S.quotes.find(x => x.quote === q0.quote); if (!r || !q) continue;
    if (q.state !== r.state) { q.state = r.state; save(); }
    if ((r.state === 'UNPAID' || r.state === 'PAID') && !q.rec) { q.rec = 1; save(); }
    if (r.state === 'UNPAID' && !(q.expiry && Date.now() / 1000 > q.expiry)) res.set(q.quote, 'waiting');   // (what the single check would say: not asked again this round)
    else if (r.state === 'PAID' && !bt.skip.has(q.quote) && (!r.pubkey || quoteKey(r.pubkey))) paid.push(q);
  }
  if (paid.length < 2) return;
  try { await authGate(url); } catch (e) { return; }   // (a mint with a login and no BAT to be had: no batch; the single checks say "log in")
  // in batches the mint takes: at most `max` deposits, and no more outputs than its request limit
  const lim = mintMax(url), groups = []; let cur = [], tot = 0;
  for (const q of paid) {
    if (cur.length && (cur.length >= max || (lim && btBits(tot + num(q.amount)) > lim))) { groups.push(cur); cur = []; tot = 0; }
    cur.push(q); tot += num(q.amount);
  }
  groups.push(cur);
  for (const g of groups) if (g.length >= 2 && btMax(url) && await btGroup(w, url, g, st, res) === 'refused') break;   // (one fallback per round)
}
// held like single checks (the same locks, in sorted order), from the freshest record, then asked
async function btGroup(w, url, g, st, res) {
  const ids = g.filter(q => !flights.has('quote:' + q.quote) && !busyQuotes.has(q.quote)).map(q => q.quote).sort();
  if (ids.length < 2) return;
  const out = new Map(); let done, how; const all = new Promise(r => { done = r; });
  for (const id of ids) flights.set('quote:' + id, all.then(m => m.get(id) || 'waiting'));
  try {
    const go = ids.reduceRight((f, id) => () => withLock('nutcade:quote:' + id, f), async () => {
      await syncIfStale();
      const qs = ids.map(id => S.quotes.find(x => x.quote === id)).filter(q => q && !busyQuotes.has(q.quote));
      if (qs.length < 2) return;
      qs.forEach(q => busyQuotes.add(q.quote));
      try { how = await btMint(w, url, qs, st, out); } finally { qs.forEach(q => busyQuotes.delete(q.quote)); }
    });
    await go();
  } finally {
    for (const id of ids) flights.delete('quote:' + id);
    done(out); for (const [k, v] of out) res.set(k, v);
  }
  return how;
}
/* A refused batch: what it was refused for decides what happens next time (each deposit of it is claimed on its own now).
   - The mint's keys changed (a keyset error): not about batching. The keys are fetched again (the library has done so
     when it could, as for a single claim) and the next round batches as before.
   - A deposit's request expired (the mint won't issue a paid deposit past its expiry): those of the batch past their
     expiry are left out of later batches (their single checks decide), the others still batch.
   - Anything else: no batch at that mint for BT_OFF_MS. */
async function btRefused(w, url, qs, e) {
  if (e && e.name === 'StaleKeysetError') { if (!e.repaired) await inTime(w.loadMint(true), MINT_MS).catch(() => {}); return; }
  const m = String((e && (e.message || e.detail)) || ''), late = qs.filter(q => q.expiry && Date.now() / 1000 > q.expiry);
  if ((num(e && e.code) === 20007 || (/expired/i.test(m) && !/keyset/i.test(m))) && late.length) { late.forEach(q => bt.skip.add(q.quote)); return; }
  bt.off.set(url, Date.now() + BT_OFF_MS);
}
async function btMint(w, url, qs, st, out) {
  const keys = []; for (const q of qs) { const r = st.get(q.quote); if (r.pubkey) keys.push(quoteKey(r.pubkey)); }
  const b = uid(), total = qs.reduce((t, q) => t + num(q.amount), 0);
  // the counters its coins are signed for are on every deposit's record before the mint is asked
  const onCountersReserved = u => { if (u && u.count > 0) { for (const q of qs) { retireCtr(q); q.ctr = { id: u.counterKey, start: u.start, n: u.count, b, t: total }; } save(); } };
  const prep = await w.prepareBatchMint('bolt11', qs.map(q => ({ quote: st.get(q.quote), amount: num(q.amount) })), Object.assign({ onCountersReserved }, keys.length ? { privkey: keys } : {}));
  const lim = mintMax(url); if (lim && (prep.outputData || []).length > lim) return;   // (never sent; the counters stay on record, unused)
  await saveNow();
  let proofs;
  try { proofs = await w.completeBatchMint(prep); }
  catch (e) {
    // (an HTTP 4xx with no error code counts too: a mint without the batch endpoint answers 404; not 429, a "slow down")
    if ((isRefusal(e) || (e && e.authMasked) || (e && e.status >= 400 && e.status < 500 && e.status !== 429)) && !pendingRefusal(e)) { await btRefused(w, url, qs, e); return 'refused'; }   // (refused: each on its own now)
    return;   // (each deposit's single check decides from what the mint says about it)
  }
  opMark(url, true);
  const got = btBook(url, qs, plain(proofs), []);
  sfx('coin'); refresh();
  for (const [q, a] of got) {
    out.set(q.quote, 'paid');
    document.dispatchEvent(new CustomEvent('nutcade:paid', { detail: q.quote }));
    if (a) arrToast(q.txId, `+${arrMoneyU(a, acctUnit(url))} received`, 'lime');
  }
  if (!$('#layer .sheet') && got.length) celebrate('in', got.reduce((t, x) => t + x[1], 0), acctUnit(url));
}
/* A batch's coins, booked in one write: every deposit of it gets its own line at its amount (up to what came in), any
   coin beyond them is "Recovered" (never more than came in), already held coins add nothing; the deposits are closed. */
function btBook(url, qs, found, away) {
  const held = new Set((S.proofs[url] || []).map(p => p.secret));
  found = found.filter(p => !held.has(p.secret)); away = away.filter(p => !held.has(p.secret));
  let left = sum(found) + sum(away), gone = sum(away); const got = [], now = Date.now(), out = new Map();
  S.proofs[url] = (S.proofs[url] || []).concat(found);
  // (coins already spent elsewhere count toward the deposits in turn, each part on the line its own import wrote, as a
  // single deposit's do: one "spent elsewhere" line per import line, any rest with the first deposit's)
  const away1 = (k, v) => { if (v > 0) out.set(k, (out.get(k) || 0) + v); };
  for (const q of qs) {
    const was = txById(q.txId), before = was && was.status === 'done' ? num(was.amount) : 0, a = Math.min(left, num(q.amount)), g = Math.min(gone, a);
    left -= a; gone -= g; got.push([q, a]); away1(q.impLine || null, g);
    updTx(q.txId, { status: 'done', amount: before + a, ts: now });
  }
  if (left > 0) addTx({ type: 'in', method: 'ecash', amount: left, mint: url, note: 'Recovered with recovery phrase', self: true });
  away1(qs.length && qs[0].impLine || null, gone);
  for (const [k, v] of out) spentElsewhere(url, v, k);
  const ids = new Set(qs.map(q => q.quote)); S.quotes = S.quotes.filter(x => !ids.has(x.quote)); save();
  return got;
}
