/* ===================== Send all (1.22.0): everything at the active mint, less the fees =====================
   "Send all" sends everything the active mint holds, less what sending it costs. Only that mint: the others are never
   touched, and every number here is that mint's. It is offered where you choose the amount: an ecash token, a Lightning
   address or LNURL, and an on-chain withdrawal. A Lightning invoice carries its own amount, so it has none.
   - Ecash: the biggest token whose swap fits the balance, with the library's own numbers (the token's outputs with the
     fee its receiver will pay, plus the mint's fee to spend every coin, NUT-02). Every coin goes into that one swap.
   - Lightning address / LNURL and on-chain: an amount is asked for and quoted, then lowered by whatever the quote's fee
     reserve and the mint's fees (at most) add beyond the balance, and quoted again, a few rounds at most, until amount +
     fees fit. The quote that fits is the one paid, so its fees are the mint's own and can't change before the payment
     (unused fee reserve comes back as change). On-chain, each fee speed gets its own amount and quote.
   Fees as big as the balance, or an amount left below the smallest payment the mint (or the address) takes, are refused
   with a sentence, before anything is sent. The confirm screen shows the amount and fees first; Cancel changes nothing.
   The payment then goes through the same steps as any other: the spending limit (and the PIN that lets one payment go
   over it), the piggy bank, the operation journal and the recovery of a payment that failed. If the coins or the fees
   changed in between (another tab, a coin that arrived or was spent), it stops with nothing sent. */
const allErr = msg => { const e = new Error(msg); e.keep = true; e.allKind = 'quote'; return e; };   // (allKind: what auto-move says about it, app_automove.js)
const allChanged = () => allErr('Your balance at this mint changed, so nothing was sent. Tap Send all again to see the new amount.');
const allNone = () => allErr('Nothing to send: this mint holds 0 SAT.');
const allFeeErr = (fees, bal) => Object.assign(allErr(`The fees (${money(fees)}) are as much as this mint's balance of ${money(bal)}, so nothing can be sent from it.`), { allKind: 'fee', fees, bal });
const allDustErr = (a, min) => Object.assign(allErr(`After the fees, ${money(a)} would be left to send, less than the smallest payment allowed here (${money(min)}). Nothing was sent.`), { allKind: 'dust' });
/* The token that takes everything at this mint: { amount (what the receiver gets), fee (the mint's fee for the swap and
   the fee the token carries for its receiver), spend (amount + fee: what leaves the balance), left (what stays: a SAT or
   two that one more SAT of token would cost more than) }. Throws a sentence when nothing can be sent. */
function allEcashPlan(w, have, url) {
  const total = sum(have);
  if (!(total > 0)) throw allNone();
  const m = mintMax(url);
  if (m && have.length > m) throw allErr(`This mint takes at most ${m} coins per request, and it holds ${have.length} of yours, so Send all can't be used there. Type an amount instead.`);
  if (!w._selectProofs) throw allErr("Send all isn't available with this mint right now. Type an amount instead.");
  let inFee = 0; try { inFee = num(w.getFeesForProofs(have)); } catch (e) { try { inFee = num(w.getFeesForKeyset(have.length, have[0].id)); } catch (x) {} }
  const coins = a => { let c = 0; for (let x = a; x > 0; x = Math.floor(x / 2)) c += x % 2; return c; };
  const recvFee = a => { let r = 0; try { for (let j = 0; j < 4; j++) r = num(w.getFeesForKeyset(coins(a + r), w.getOutputKeyset().id)); } catch (e) {} return r; };
  // the token's outputs for `a` with its receiver's fee, as the swap will make them (the library's own count)
  const outs = a => { try { const ks = w.getOutputKeyset(), ot = w.configureOutputs(w.parseAmount(a, 'limit'), ks, w.defaultOutputType(), true); return num(w.preparedTotal(ot)); } catch (e) { return a + recvFee(a); } };
  const spendOf = a => outs(a) + inFee;
  let a = Math.max(0, Math.min(maxSendable(w, have), total - inFee));
  for (let i = 0; i < 200 && a > 0 && spendOf(a) > total; i++) a -= Math.max(1, spendOf(a) - total);   // over: that much less
  for (let i = 0; i < 64 && a >= 0 && spendOf(a + 1) <= total; i++) a++;   // and as much as still fits
  if (!(a > 0) || spendOf(a) > total) throw allFeeErr(spendOf(1) - 1, total);
  const spend = spendOf(a);
  return { url, amount: a, fee: spend - a, spend, left: total - spend, total };
}
function showAllEcash(url, p, note) {
  setBody(`<div class="notice cyan">Send all: everything at this mint, less the mint's fee.</div>
    <dl class="kv"><dt>Token</dt><dd>${money(p.amount)}</dd><dt>Mint fee</dt><dd>${money(p.fee)}</dd>${p.left ? `<dt>Stays at this mint</dt><dd>${money(p.left)}</dd>` : ''}<dt>Leaves your balance</dt><dd>${money(p.spend)}</dd><dt>From</dt><dd class="tiny">${esc((S.mints.find(m => m.url === url) || {}).name || host(url))}</dd>${note ? `<dt>Note</dt><dd data-noi18n>${esc(note)}</dd>` : ''}</dl>
    <button class="btn solid pink block" id="allGo">Create token for ${money(p.amount)}</button>
    <button class="btn block" data-act="close">Cancel</button><div id="sheetErr"></div>`, body => {
    body.querySelector('#allGo').onclick = e => run(e.currentTarget, 'MINTING TOKEN', async () => {
      const tx = await sendEcash(p.amount, note, null, url, { all: p });
      sfx('coin'); refresh(); showToken(tx);
    });
    return null;
  });
}
/* Lightning address / LNURL and on-chain: the biggest amount whose quote, with its fees at most (the fee reserve and the
   mint's fees to spend the ecash, as the confirm screen shows them), fits this mint's balance. quoteFor(a) asks for a
   quote of exactly a; reserveOf(quote) is its fee reserve. lim: { min, max } the amounts allowed here.
   Returns { url, amount, mq, cost, capped } or throws a sentence; nothing is sent either way. */
async function allFit(url, quoteFor, reserveOf, lim = {}) {
  await getWallet(url);
  const bal = balanceOf(url);
  if (!(bal > 0)) throw allNone();
  const min = Math.max(1, num(lim.min) || 0), max = num(lim.max) > 0 ? num(lim.max) : Infinity;
  let a = Math.min(max, bal - meltCost(url, bal, 0).mintFee), best = null;
  const seen = new Set();
  for (let i = 0; i < 6 && a >= min && !seen.has(a); i++) {
    seen.add(a);
    const mq = await quoteFor(a);
    if (num(mq.amount) !== a) throw allErr(`The invoice asked for ${money(num(mq.amount))} instead of ${money(a)}. Nothing was sent.`);
    const r = reserveOf(mq); if (r == null) throw allErr("This mint didn't say what the payment costs. Nothing was sent.");
    const c = costShown(url, a, r);
    if (c.total <= bal) {
      if (!best || a > best.amount) best = { url, amount: a, mq, cost: c, capped: a >= max && c.total < bal, max };
      if (c.total === bal || a >= max) break;
      a = Math.min(max, a + (bal - c.total));   // room left over (a smaller fee than guessed): try a bit more, once
    } else {
      if (best) break;
      a -= c.total - bal;   // over by this much: that much less
    }
  }
  if (best) return best;
  if (a < 1) throw allFeeErr(bal - a, bal);
  if (a < min) throw allDustErr(a, min);
  throw allErr('The fees kept changing, so Send all could not settle on an amount. Nothing was sent. Try again.');
}
const chainSpeed = o => `~${o.estimated_blocks} block${o.estimated_blocks === 1 ? '' : 's'}`;
async function allOnchain(url, dest) {
  checkBtcAddr(dest, url);
  if (belowMin(url)) throw minErr(url);   // (on-chain is paid only from mints that take enough coins per request)
  const w = await getWallet(url), mi = methodInfo(S.mints.find(m => m.url === url), 'melt', 'onchain') || {};
  const quotes = new Map();   // amount -> quote: one quote gives every fee speed for that amount
  const quoteFor = a => { if (!quotes.has(a)) quotes.set(a, w.createMeltQuoteOnchain(dest, a).catch(e => { quotes.delete(a); throw e; })); return quotes.get(a); };
  const bal = balanceOf(url); if (!(bal > 0)) throw allNone();
  const first = await quoteFor(Math.max(1, num(mi.min) || 0, Math.min(num(mi.max) > 0 ? num(mi.max) : Infinity, bal - meltCost(url, bal, 0).mintFee)));
  const fits = []; let err = null;
  for (const o of first.fee_options || []) {
    try {
      const f = await allFit(url, quoteFor, mq => { const x = (mq.fee_options || []).find(y => y.fee_index === o.fee_index); return x ? num(x.fee_reserve) : null; }, { min: mi.min, max: mi.max });
      fits.push(Object.assign(f, { idx: o.fee_index, blocks: o.estimated_blocks, reserve: num(f.cost.reserve) }));
    } catch (e) { err = err || e; }
  }
  if (!fits.length) throw err || allErr("This mint didn't say what the payment costs. Nothing was sent.");
  return fits;
}
// the on-chain confirm screen: every fee speed with its own amount (its own quote); the one picked is what is paid
function showAllOnchain(url, fits, dest, note) {
  const head = $('#layer .sheet-head h3'); if (head) { head.textContent = tr('Pay'); head.closest('.sheet').setAttribute('aria-label', tr('Pay')); }
  const rows = f => `<dt>Pay</dt><dd>${money(f.amount)}</dd><dt>Network fee</dt><dd>${money(f.cost.reserve)}</dd>${f.cost.mintFee ? `<dt>Mint fee, at most</dt><dd>${money(f.cost.mintFee)}</dd>` : ''}<dt>Total, at most</dt><dd>${money(f.cost.total)}</dd><dt>To</dt><dd class="tiny">${esc(dest.length > 40 ? dest.slice(0, 18) + '…' + dest.slice(-14) : dest)}</dd>${note ? `<dt>Note</dt><dd data-noi18n>${esc(note)}</dd>` : ''}`;
  setBody(`<div class="notice cyan">Send all: everything at this mint, less the fees.</div>${fits.some(f => f.capped) ? `<div class="tiny muted">The most this mint pays out at once is ${money(fits.find(f => f.capped).max)}, so the rest stays at this mint.</div>` : ''}
    <div class="field"><label>Fee speed</label><div class="txs">${fits.map((f, i) => `<label class="tx out" style="cursor:pointer"><span class="ico"><input type="radio" name="fee" value="${i}" ${i === 0 ? 'checked' : ''} style="accent-color:var(--pink)"></span><span class="mid"><div class="note">${esc(tr(chainSpeed(f)))}</div><div class="meta">≈ ${Math.round(f.blocks * 10)} min</div></span><span class="amt">${fmt(f.reserve)}</span></label>`).join('')}</div></div>
    <dl class="kv" id="allKv">${rows(fits[0])}</dl>
    <button class="btn solid pink block" id="payBtn">Pay ${money(fits[0].amount)}</button>
    <button class="btn block" data-act="close">Cancel</button><div id="sheetErr"></div>`, body => {
    const pick = () => fits[parseInt((body.querySelector('input[name=fee]:checked') || {}).value || '0', 10)] || fits[0];
    body.querySelectorAll('input[name=fee]').forEach(r => { r.onchange = () => { const f = pick(); body.querySelector('#allKv').innerHTML = rows(f); body.querySelector('#payBtn').textContent = `Pay ${money(f.amount)}`; }; });
    body.querySelector('#payBtn').onclick = e => run(e.currentTarget, 'PAYING', async () => {
      const f = pick();
      if (S.active !== url) throw allChanged();
      const tx = await payMelt('onchain', f.mq, f.idx, note, dest, url, {});
      if (tx.status === 'done') showDone('out', f.amount, 'On-chain' + (tx.outpoint ? ' · ' + tx.outpoint.slice(0, 12) + '…' : ''));
      else { setBody(`<div class="notice">Payment is in flight. NUTCADE will settle it when the mint confirms. Check the transaction in your notes.</div><button class="btn block gold" data-act="close">OK</button>`); refresh(); }
    });
    return null;
  });
}
