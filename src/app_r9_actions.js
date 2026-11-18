/* Round 9 actions: the keyset check-up */
Object.assign(A, {
  ksMove: b => run(b, '…', async () => {
    const u = normUrl(b.dataset.url), t0 = Date.now();
    await ksCheck(u, { agree: true, fee: num(b.dataset.fee), manual: true }); render();
    // (it waited for something still open at this mint, all or part of it: never "done")
    if (num(ksSkipped.get(u)) >= t0) toast('Something is still being settled at this mint. The keyset check-up will run at the next check.', 'cyan');
    else { sfx('coin'); toast('Keyset check-up done', 'cyan'); }
  }),
  ksNo: b => { const m = ksMint(b.dataset.url); if (m && m.ks) { m.ks.no = 1; save(); } render(); }
});
