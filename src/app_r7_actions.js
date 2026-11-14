/* Round 7 actions: LNURL-withdraw, blocked mints, Wallet Connect, zaps */
Object.assign(A, {
  lnurlwGo: b => run(b, 'ASKING MINT', async () => {
    const v = curWd; if (!v) return;
    const sats = amt(), url = val('wdMint');
    const res = await withdrawVoucher(v, sats, url);
    sfx('blip'); refresh(); showWithdrawWait(res);
  }),
  blockMint: b => openBlock(b.dataset.url),
  blockMintGo: b => {
    const u = b.dataset.url, bal = balanceOf(u), n = mintName(u);
    blockMint(u); sfx('blip'); render();
    const canMove = bal > 0 && supports(S.mints.find(m => m.url === u), 'melt', 'bolt11') && S.mints.some(m => m.url !== u && !isBlocked(m.url) && supports(m, 'mint', 'bolt11'));
    setBody(`<div class="notice red">${esc(n)} is blocked. Tokens, payment requests and deposits from it will be refused, and NUTCADE will tell you each time.</div>
      ${bal ? `<div class="notice">Your ${money(bal)} at ${esc(n)} stays usable: you can still send it or move it to another mint.</div>` : ''}
      ${canMove ? `<button class="btn solid gold block" data-act="moveOpen" data-from="${esc(u)}">Move sats out</button><button class="btn block" data-act="close">Done</button>` : '<button class="btn solid gold block" data-act="close">Done</button>'}`);
  },
  unblockMint: b => {
    const u = b.dataset.id || b.dataset.url; if (!u) return;
    const n = (S.blocked.find(x => x.url === normUrl(u)) || {}).name || mintName(u);
    unblockMint(u); sfx('coin'); toast(`${n} unblocked`, 'lime');
    const er = b.closest('.notice'); if (er && b.closest('#layer')) er.remove();   // the refusal it answered goes; tap the main button again
    refresh();
  }
});
