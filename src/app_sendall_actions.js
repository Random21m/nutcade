/* Send all actions: the "Send all" links on the ecash, Lightning address / LNURL and on-chain send screens (app_sendall.js) */
Object.assign(A, {
  allEcash: b => run(b, 'CHECKING', async () => {
    if (($('#giftOn') || {}).checked) throw new Error('Send all makes a token anyone can claim. Turn off the lock first, or type an amount.');
    if (isOffline()) throw new Error("Send all needs the mint, and you're offline. Try again online.");
    const url = S.active, note = val('noteIn').trim(), w = await getWallet(url);
    showAllEcash(url, allEcashPlan(w, S.proofs[url] || [], url), note);
  }),
  lnurlAll: b => run(b, 'ASKING', async () => {
    const t = b.dataset.t, note = val('noteIn').trim(), url = S.active;
    const reach = e => new Error(/fetch|network|load failed/i.test(e.message) ? "Couldn't reach that Lightning address. Check it and try again." : e.message);
    let base; try { base = await lnurlInfo(t); } catch (e) { throw reach(e); }
    const w = await getWallet(url), mi = methodInfo(S.mints.find(m => m.url === url), 'melt', 'bolt11') || {};
    const min = Math.max(Math.ceil(num(base.minSendable) / 1000), num(mi.min) || 0), max = Math.min(Math.floor(num(base.maxSendable) / 1000) || Infinity, num(mi.max) > 0 ? num(mi.max) : Infinity);
    const fit = await allFit(url, async a => { let pr; try { pr = await lnurlInvoice(t, a, '', base); } catch (e) { throw reach(e); } return w.createMeltQuoteBolt11(pr); }, mq => num(mq.fee_reserve), { min, max: max === Infinity ? 0 : max });
    showMeltQuote('ln', fit.mq, t, note, fit);
  }),
  allOnchain: b => run(b, 'QUOTING', async () => {
    const dest = val('destIn').trim().replace(/^bitcoin:/i, '').split('?')[0], note = val('noteIn').trim(), url = S.active;
    if (!dest) throw new Error('Paste the Bitcoin address first.');
    showAllOnchain(url, await allOnchain(url, dest), dest, note);
  })
});
