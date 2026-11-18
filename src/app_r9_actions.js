/* Round 9 actions: the keyset check-up */
Object.assign(A, {
  ksMove: b => run(b, '…', async () => { await ksCheck(b.dataset.url, { agree: true, fee: num(b.dataset.fee), manual: true }); sfx('coin'); render(); toast('Keyset check-up done', 'cyan'); }),
  ksNo: b => { const m = ksMint(b.dataset.url); if (m && m.ks) { m.ks.no = 1; save(); } render(); }
});
