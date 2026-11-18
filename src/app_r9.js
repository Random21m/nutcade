/* ===================== Round 9 (1.14): keyset check-up ===================== */

/* ---------- keyset check-up ----------
   Mints rotate their keys (NUT-02 keysets): a new keyset becomes active and the old one inactive. Coins of an
   inactive keyset are still accepted as inputs, but the mint may stop accepting them once it drops that keyset, and a
   keyset can carry a final expiry (final_expiry), after which the mint no longer has to honour it. So each mint gets a
   check-up when NUTCADE opens, when you tap Refresh on it, and at the regular background check (which asks the mint
   nothing when there is nothing to do, and asks again only with backoff when it couldn't):
   - coins of a keyset the mint marks inactive, or whose final expiry is less than 7 days away (KS_SOON), are moved to
     the mint's active keyset (one that doesn't expire soon, the cheapest first): a swap of those coins for new coins of
     the same total less the mint's input fee;
   - many tiny coins (KS_TIDY_MIN or more coins of at most KS_TINY SAT, when combining them saves at least KS_TIDY_SAVE
     coins) are combined into fewer in the same swap, as Minibits' "Optimize ecash" does.
   The swap is an ordinary journaled swap: written down before the mint is asked, booked only from what the mint signed
   (an interrupted one is settled from its record, a refused one books nothing), in requests no bigger than the mint
   takes (NUT-06; the 1.13 minimum of 128 applies as everywhere), one step at a time per mint (the mint lock), never
   with the coins of a step still open. First the coins are checked with the mint (NUT-07): what is spent already was
   spent by a device holding this wallet and gets the usual "Ecash already spent elsewhere" line (never a fee); what is
   in flight is left alone. The fee is the mint's input fee (NUT-02 input_fee_ppk) on the coins moved, and only what
   the mint kept is written down as the fee. With no fee and "Keyset check-up" on in Settings (the default) it simply
   happens; with a fee, or with the setting off, NUTCADE asks once, with the fee shown, on the wallet screen (and the
   mint's line in Mints keeps a Move button).
   It isn't spending: the coins stay this wallet's, at the same mint. The swap's outputs are all this wallet's own
   (no token, no lock, nothing leaves the mint), so neither the move nor its fee counts toward the spending limit, and
   it can't take any payment past the limit either.
   Coins the mint says it can no longer accept (their keyset is unknown to it, 12001, or expired, 12003) can't be spent:
   they are set aside, out of the balance, with a history line, kept in the wallet (and in its backup), and offered to
   the mint again at each check-up; if it takes them after all, they come back with a line. */
const KS_SOON = 7 * 86400e3, KS_TINY = 8, KS_TIDY_MIN = 24, KS_TIDY_SAVE = 16, KS_CAP = 1000;
const ksExp = k => { const v = k && k.expiry; return v ? num(v) * 1000 : 0; };   // (final_expiry is in seconds)
const ksSoon = (k, now = Date.now()) => !!ksExp(k) && ksExp(k) - now < KS_SOON;
function ksAll(w) { try { return w.keyChain.getKeysets().filter(k => k.unit === 'sat'); } catch (e) { return []; } }
const ksMint = url => S.mints.find(m => m.url === normUrl(url || ''));
const asideOf = url => ((ksMint(url) || {}).ks || {}).aside || [];
// where new coins go: an active keyset that doesn't expire soon, the cheapest, the one expiring last
function ksTarget(w, now = Date.now()) {
  let cur = null; try { cur = w.keysetId; } catch (e) {}
  const ok = ksAll(w).filter(k => k.isActive && k.hasHexId && k.hasKeys);
  ok.sort((a, b) => (ksSoon(a, now) - ksSoon(b, now)) || (num(a.fee) - num(b.fee)) || (((ksExp(b) || Infinity) - (ksExp(a) || Infinity)) || 0) || ((b.id === cur) - (a.id === cur)));
  return ok[0] || null;
}
// a wallet whose cheapest active keyset expires soon makes its new coins on one that doesn't, when the mint has one
function ksBind(w) { try { const t = ksTarget(w), cur = ksAll(w).find(k => k.id === w.keysetId); if (t && cur && t.id !== cur.id && ksSoon(cur)) w.bindKeyset(t.id); } catch (e) {} }
// what a check-up would do here now (no request to the mint): coins on old keys, tiny coins to combine
function ksPlan(w, url, now = Date.now()) {
  const t = ksTarget(w, now); if (!t) return null;
  const known = new Map(ksAll(w).map(k => [k.id, k]));
  // (coins of a step waiting aside, S.oplate, may be moved: if its late request reaches the mint first, those coins
  // are spent and the check-up leaves them to lateCheck, which settles that step as itself; if the check-up is first,
  // the late request is refused and that step finds nothing of its coins left to book)
  const busy = new Set(S.ops.filter(o => o.mint === url).flatMap(o => o.inputs || []));
  const free = (S.proofs[url] || []).filter(p => !busy.has(p.secret));
  const old = free.filter(p => { const k = known.get(p.id); return !k || (k.id !== t.id && (!k.isActive || ksSoon(k, now))); });   // (a keyset the mint doesn't list: tried, and set aside if it refuses)
  const oldS = new Set(old.map(p => p.secret));
  const small = free.filter(p => !oldS.has(p.secret) && num(p.amount) <= KS_TINY);
  let tidy = [];
  if (small.length >= KS_TIDY_MIN) { const v = sum(small) - feeOfPs(w, small); if (v > 0 && small.length - bitsOf(v) >= KS_TIDY_SAVE) tidy = small; }
  const exp = old.map(p => ksExp(known.get(p.id))).filter(Boolean);
  return { t, old, tidy, known, soon: exp.length ? Math.min(...exp) : 0, sig: [...new Set(old.map(p => p.id))].sort().join(',') + (tidy.length ? '+tidy' : '') };
}
// the swaps for these coins: at most what the mint takes per request (a mint below the 128 minimum: in parts that fit
// in and out); a group worth no more than its fee isn't moved. Coins of keysets the mint lists first.
function ksGroups(w, url, ps, known) {
  const m = mintMax(url), out = [];
  for (const set of [ps.filter(p => known.has(p.id)), ps.filter(p => !known.has(p.id))]) {
    if (!set.length) continue;
    if (m && m < MIN_REQ) { out.push(...(tokenParts(w, set, m) || [])); continue; }
    const cap = Math.min(m || KS_CAP, KS_CAP), d = set.slice().sort((a, b) => num(b.amount) - num(a.amount));
    for (let i = 0; i < d.length; i += cap) out.push(d.slice(i, i + cap));
  }
  return out.filter(g => sum(g) - feeOfPs(w, g) > 0);
}
const ksFee = (w, url, ps, known) => ksGroups(w, url, ps, known).reduce((t, g) => t + feeOfPs(w, g), 0);
const ksCode = e => e ? (num(e.code) || (e.cause ? num(e.cause.code) : 0)) : 0;
// the mint can't take these coins any more: their keyset is unknown to it (after a refresh) or expired
const ksDead = e => !!e && ([12001, 12003].includes(ksCode(e)) || (e.name === 'UnknownKeysetError' && !!e.refreshed) || /keyset (has )?expired|keyset is not known|not a keyset of this mint/i.test(String(e.raw || e.message || '') + ' ' + String((e.cause && e.cause.message) || '')));
const ksNote = (n, t, k) => n && t ? `Keyset check-up: ${n === 1 ? '1 coin' : fmt(n) + ' coins'} moved to the mint's new keys and ${fmt(t)} small coins combined`
  : n ? `Keyset check-up: ${n === 1 ? '1 coin' : fmt(n) + ' coins'} moved to the mint's new keys` : `Keyset check-up: ${fmt(t)} small coins combined into ${fmt(k)}`;
const ksBackoff = ks => { ks.tries = (ks.tries || 0) + 1; return Date.now() + Math.min(30 * 60e3, 60e3 * 2 ** (ks.tries - 1)); };

/* Anything at this mint that is being collected or settled comes first, and the check-up doesn't run beside it: its
   swap takes the wallet's next counters and its clean-up books spent coins, so neither may happen while a deposit is
   being collected (or may be, any moment: an invoice under an hour old, one the mint says is paid, one with counters
   on record, one from before 1.12), while a payment, a journaled step, a backup's waiting part or a restore scan is
   open there. It runs at the next check once they have settled (it is asked again at every regular check). */
const quoteBusy = q => { if (busyQuotes.has(q.quote)) return true; if (q.kind !== 'bolt11') return false; const t = txById(q.txId); return q.state === 'PAID' || q.state === 'ISSUED' || !!q.ctr || legacyQuote(q) || (!!t && t.status === 'pending' && Date.now() - num(t.ts) < 60 * 60e3); };
function ksBusy(url) {
  return S.ops.some(o => o.mint === url) || S.pending.some(p => p.mint === url) || (S.imports || []).some(r => r.mint === url)
    || S.quotes.some(q => q.mint === url && quoteBusy(q)) || flights.has('restore:' + url);
}
/* opts: startup (NUTCADE just opened or unlocked), manual (Refresh), agree + fee (you tapped Move with that fee shown) */
function ksCheck(url, opts = {}) { url = normUrl(url); if (!ksMint(url)) return Promise.resolve(null); return tooManyRetry(url, () => mintLock(url, () => ksNow(url, opts))); }
async function ksNow(url, opts) {
  const m = ksMint(url); if (!m || !S.seed) return null;
  const ks = m.ks || (m.ks = {}), now = Date.now(), deep = !!(opts.startup || opts.manual || opts.agree);
  if (ksBusy(url)) return ks;   // (whatever is being collected or settled here goes first; the check-up comes after it)
  if (!deep && ks.due && now < ks.due) return ks;
  let w; try { w = await getWallet(url); } catch (e) { ks.due = ksBackoff(ks); save(); return ks; }   // (mint down: nothing changes, nothing to alarm about; asked again later)
  if (deep && (ks.aside || []).length) await ksBack(w, url, ks).catch(() => {});
  let plan = ksPlan(w, url, now);
  const nothing = p => !p || !ksGroups(w, url, p.old.concat(p.tidy), p.known).length;   // (coins worth less than the fee to move them stay as they are)
  if (nothing(plan)) { if (deep || ks.st !== 'ok' || !ks.at) { Object.assign(ks, { at: now, st: 'ok', due: 0, tries: 0, sig: '', no: 0 }); save(); } return ks; }
  if (!deep && ks.st === 'ask' && ks.sig === plan.sig) return ks;   // (asked already; nothing new to ask the mint)
  // coins spent already (by a device holding this wallet): their own line, never a fee; coins in flight: left alone
  const cand = plan.old.concat(plan.tidy);
  let st; try { st = await inTime(w.checkProofsStates(cand), 30000); } catch (e) { ks.due = ksBackoff(ks); save(); return ks; }
  const spent = new Set(cand.filter((p, i) => st[i] && st[i].state === 'SPENT').map(p => p.secret)), held = new Set(cand.filter((p, i) => st[i] && st[i].state !== 'UNSPENT').map(p => p.secret));
  const res = { n: 0, t: 0, k: 0, fee: 0, aside: 0, asideA: 0, spentN: 0, spentA: 0, why: '' };
  if (ksBusy(url)) return ks;   // (something started meanwhile: next time)
  if (spent.size) { await ksPrune(url, cand, res); plan = ksPlan(w, url, now); }
  const old = plan.old.filter(p => !held.has(p.secret)), tidy = plan.tidy.filter(p => !held.has(p.secret));
  const auto = S.prefs.ksAuto !== false, fAll = ksFee(w, url, old.concat(tidy), plan.known), fOld = ksFee(w, url, old, plan.known);
  let move = [];
  if (opts.agree && fAll <= num(opts.fee)) move = old.concat(tidy);   // (what you agreed to, at most the fee you were shown)
  else if (auto && fAll === 0) move = old.concat(tidy);
  else if (auto && fOld === 0) move = old;   // (the free part now; combining the small coins costs a fee: asked)
  if (move.length) await ksMove(w, url, plan, move, res);
  if (res.again && !res.why && !res.busy) {   // (once more for what is left of a part that met coins spent elsewhere)
    const mine = new Set((S.proofs[url] || []).map(p => p.secret)), more = move.filter(p => mine.has(p.secret));
    res.again = false; if (more.length) await ksMove(w, url, plan, more, res);
  }
  if (res.n || res.t) ks.last = { at: now, n: res.n, t: res.t, k: res.k, fee: res.fee };
  if (res.spentN) ks.spent = { at: now, n: res.spentN, a: res.spentA };
  if (res.why) { Object.assign(ks, { at: now, st: res.why, due: ksBackoff(ks) }); save(); return ks; }
  if (res.busy) { save(); return ks; }
  ks.tries = 0; ks.due = 0;
  // what is left to ask about: the coins not moved now that a swap would move (never ones worth less than their fee)
  const moved = new Set(move.map(p => p.secret)), mine = new Set((S.proofs[url] || []).map(p => p.secret)), left = p => !moved.has(p.secret) && mine.has(p.secret);
  const lg = new Set(ksGroups(w, url, old.concat(tidy).filter(left), plan.known).flat().map(p => p.secret));
  const lo = old.filter(p => lg.has(p.secret)), lt = tidy.filter(p => lg.has(p.secret));
  if (lo.length || lt.length) {
    const sig = plan.sig, again = ks.st === 'ask' && ks.sig === sig;
    Object.assign(ks, { at: now, st: 'ask', n: lo.length, a: sum(lo), t: lt.length, fee: ksFee(w, url, lo.concat(lt), plan.known), soon: plan.soon, no: again ? ks.no || 0 : 0, sig });
  } else Object.assign(ks, { at: now, st: 'ok', sig: '', no: 0 });
  save();
  return ks;
}
/* Coins the mint says are spent: dropped the one way every spent coin is (pruneSpent): first any step of this wallet
   whose request reached the mint late is settled as itself (lateCheck), and a step still open keeps its coins; only
   what is left is "Ecash already spent elsewhere". */
async function ksPrune(url, cand, res) {
  const v = await pruneSpent(url).catch(() => 0), held = new Set((S.proofs[url] || []).map(p => p.secret));
  if (v > 0) { res.spentN += cand.filter(p => !held.has(p.secret)).length; res.spentA += v; }
}
async function ksMove(w, url, plan, move, res) {
  const tidyS = new Set(plan.tidy.map(p => p.secret));
  let line = null;
  for (const g of ksGroups(w, url, move, plan.known)) {
    if (ksBusy(url)) { res.busy = true; break; }   // (a deposit, payment or scan started here meanwhile: the rest waits for the next check)
    const n = g.filter(p => !tidyS.has(p.secret)).length;
    let r;
    try { r = await journaled(url, 'swap', { inputs: g, follow: { k: 'keyset', n, t: g.length - n } }, (cb, o) => rRecv(o, w, g, { keysetId: plan.t.id, onCountersReserved: cb })); }
    catch (e) {
      if (isTooMany(e)) throw e;   // (the mint's limit is read again and the check-up runs again in pieces that fit)
      if (ksDead(e)) { ksAside(url, g, res); continue; }
      if (isRefusal(e) || isSpentErr(e)) {   // (turned down because some of these coins were spent since the check a moment ago, by a device holding this wallet: they get that line, the rest are tried again)
        const st = await inTime(w.checkProofsStates(g), 30000).catch(() => null);
        if (st && st.some(x => x && x.state === 'SPENT')) { await ksPrune(url, g, res); res.again = true; continue; }
      }
      res.why = e.asked && !isRefusal(e) ? 'wait' : isRefusal(e) ? 'refused' : 'down'; break;
    }
    // one write: these coins out, the new ones in, the line, the record closed
    const fresh = r.r, used = new Set(g.map(p => p.secret));
    S.proofs[url] = (S.proofs[url] || []).filter(p => !used.has(p.secret)).concat(plain(fresh));
    res.n += n; res.t += g.length - n; res.k += fresh.length; res.fee += Math.max(0, sum(g) - sum(fresh));
    const note = ksNote(res.n, res.t, res.k);
    if (line && txById(line)) updTx(line, { fee: res.fee, note });
    else line = addTx({ type: 'out', method: 'fee', amount: 0, fee: res.fee, mint: url, note, status: 'done', upkeep: true }).id;
    closeOp(r.op); save();
  }
}
function ksAside(url, g, res) {
  const m = ksMint(url), ids = new Set(g.map(p => p.secret)), out = (S.proofs[url] || []).filter(p => ids.has(p.secret)); if (!m || !out.length) return;
  S.proofs[url] = (S.proofs[url] || []).filter(p => !ids.has(p.secret));
  const ks = m.ks || (m.ks = {}), have = new Set((ks.aside || []).map(p => p.secret));
  ks.aside = (ks.aside || []).concat(plain(out).filter(p => !have.has(p.secret))); ks.asideAt = Date.now();
  addTx({ type: 'out', method: 'ecash', amount: sum(out), mint: url, note: 'Set aside: the mint no longer accepts these coins', status: 'done', upkeep: true });
  res.aside += out.length; res.asideA += sum(out);
}
// coins set aside, offered to the mint again: spent ones are dropped (they left the balance when set aside); the rest are
// swapped back into the balance if the mint takes them now
async function ksBack(w, url, ks) {
  const ps = ks.aside || []; if (!ps.length) return;
  const st = await inTime(w.checkProofsStates(ps), 30000);
  const spent = new Set(ps.filter((p, i) => st[i] && st[i].state === 'SPENT').map(p => p.secret));
  if (spent.size) { ks.aside = ps.filter(p => !spent.has(p.secret)); save(); }
  const t = ksTarget(w), known = new Map(ksAll(w).map(k => [k.id, k]));
  const live = (ks.aside || []).filter((p, i) => known.has(p.id)); if (!t || !live.length) return;   // (a keyset the mint still doesn't list: nothing to ask)
  for (const g of ksGroups(w, url, live, known)) {
    let r;
    try { r = await journaled(url, 'swap', { inputs: g, follow: { k: 'keyset-back' } }, (cb, o) => rRecv(o, w, g, { keysetId: t.id, onCountersReserved: cb })); }
    catch (e) { if (isTooMany(e)) throw e; return; }   // (still refused: they stay aside, nothing changes)
    const fresh = r.r, used = new Set(g.map(p => p.secret));
    ks.aside = (ks.aside || []).filter(p => !used.has(p.secret));
    S.proofs[url] = (S.proofs[url] || []).concat(plain(fresh));
    addTx({ type: 'in', method: 'ecash', amount: sum(fresh), fee: Math.max(0, sum(g) - sum(fresh)), mint: url, note: 'Coins the mint accepts again', status: 'done', upkeep: true });
    closeOp(r.op); save();
  }
}
// a check-up step whose answer never came, settled from its record (settleOpNow): its line, as if it had finished
function ksSettled(op, signed, fee, k) {
  const f = op.follow || {}, m = ksMint(op.mint);
  if (f.k === 'keyset-back') {
    if (signed && m && m.ks) { m.ks.aside = (m.ks.aside || []).filter(p => !op.inputs.includes(p.secret)); }
    return 'back';
  }
  if (!signed) return null;
  addTx({ type: 'out', method: 'fee', amount: 0, fee, mint: op.mint, note: ksNote(num(f.n), num(f.t), k), status: 'done', upkeep: true, settled: true });
  if (m) { const ks = m.ks || (m.ks = {}); ks.last = { at: Date.now(), n: num(f.n), t: num(f.t), k, fee }; if (ks.st === 'wait') ks.st = 'ok'; }
  return 'line';
}

/* ---------- what it shows ---------- */
const ksRecent = x => !!x && Date.now() - num(x.at) < 7 * 86400e3;
function ksAskText(ks) {
  const out = [];
  if (ks.n && ks.t) out.push(ks.n === 1 ? `1 coin (${money(ks.a)}) is on an old keyset, and ${fmt(ks.t)} small coins can be combined into fewer.` : `${fmt(ks.n)} coins (${money(ks.a)}) are on an old keyset, and ${fmt(ks.t)} small coins can be combined into fewer.`);
  else if (ks.n) out.push(ks.n === 1 ? `1 coin (${money(ks.a)}) is on an old keyset.` : `${fmt(ks.n)} coins (${money(ks.a)}) are on an old keyset.`);
  else if (ks.t) out.push(`${fmt(ks.t)} small coins can be combined into fewer.`);
  if (ks.n && ks.soon) { const d = Math.ceil((ks.soon - Date.now()) / 86400e3); out.push(d <= 0 ? 'Those keys have expired.' : d === 1 ? 'Those keys expire within a day.' : `Those keys expire within ${d} days.`); }
  out.push(ks.fee ? `It costs ${money(ks.fee)} in mint fees.` : 'It costs no fee.');
  return out;
}
// the mint's line in Mints
function ksLine(m) {
  const ks = m.ks; if (!ks || !ks.at) return '';
  const say = [], aside = ks.aside || [];
  if (ks.st === 'ask') say.push(...ksAskText(ks));
  if (ksRecent(ks.last)) { if (ks.last.n) say.push(ks.last.n === 1 ? '1 coin moved off an old keyset' : `${fmt(ks.last.n)} coins moved off an old keyset`); if (ks.last.t) say.push(`${fmt(ks.last.t)} small coins combined`); if (ks.last.fee) say.push(`Fee ${money(ks.last.fee)}`); }
  if (ksRecent(ks.spent)) say.push(ks.spent.n === 1 ? '1 coin was already spent elsewhere' : `${fmt(ks.spent.n)} coins were already spent elsewhere`);
  if (aside.length) say.push(aside.length === 1 ? `1 coin (${money(sum(aside))}) is set aside: the mint no longer accepts it.` : `${fmt(aside.length)} coins (${money(sum(aside))}) are set aside: the mint no longer accepts them.`, 'NUTCADE offers them to the mint again at each check-up.');
  if (ks.st === 'refused') say.push('The mint turned the check-up down. Your coins stay as they are; NUTCADE tries again later.');
  if (ks.st === 'wait') say.push("Waiting for the mint's answer about the check-up.");
  if (ks.st === 'down') say.push("Couldn't reach the mint for the check-up. NUTCADE tries again later.");
  if (!say.length) say.push('Nothing to do');
  const btn = ks.st === 'ask' ? `<div class="row wrap"><button class="btn sm gold" data-act="ksMove" data-url="${esc(m.url)}" data-fee="${num(ks.fee)}">${ks.n ? 'Move them' : 'Combine them'}</button></div>` : '';
  return `<div class="ks-line tiny muted" data-ks="${esc(m.url)}"><span class="ks-h">Keyset check-up</span>${say.map(s => `<span>${s}</span>`).join('')}</div>${btn}`;
}
// asked once, on the wallet screen
function ksAskPanel() {
  return S.mints.filter(m => m.ks && m.ks.st === 'ask' && !m.ks.no).map(m => `<div class="panel ks-ask" data-ksask="${esc(m.url)}"><span class="h2">Keyset check-up</span>
    <span class="tiny" data-noi18n style="color:var(--gold)">${esc(m.name)}</span>${ksAskText(m.ks).map(s => `<span class="tiny">${s}</span>`).join('')}
    <div class="row wrap"><button class="btn sm gold" data-act="ksMove" data-url="${esc(m.url)}" data-fee="${num(m.ks.fee)}">${m.ks.n ? 'Move them' : 'Combine them'}</button><button class="btn sm" data-act="ksNo" data-url="${esc(m.url)}">Not now</button></div></div>`).join('');
}
