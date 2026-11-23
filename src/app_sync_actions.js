/* Wallet sync: actions */
Object.assign(A, {
  syncNow: b => run(b, 'SYNCING', async () => {
    if (!syLive()) throw new Error('Wallet sync is off. Turn it on first.');
    const r = await syRun('manual');
    refresh();
    if (!r) throw new Error("Couldn't reach your relays. Nothing changed. Try again in a moment.");
    toast(r.adopted ? `+${money(r.adopted)} from your other device` : 'Wallet in sync', r.adopted ? 'lime' : 'cyan');
  }),
  syncDelete: b => run(b, 'DELETING', async () => {
    const n = await syDeleteAll();
    closeSheet(); refresh(); toast(n ? 'Synced coins deleted from your relays' : 'Nothing of yours was on your relays', 'cyan');
  }),
  syncRestoreOn: () => {
    if (!syAllowed()) return;
    S.prefs.sync = true; save(); syToggled(true);
    closeSheet(); refresh(); toast('Wallet sync is on', 'lime');
  },
  syncAddMint: b => run(b, 'ADDING', async () => {
    const u = String(b.dataset.u || '');
    if (!(S.prefs.syncOther || []).includes(u)) return;
    await addMint(u, { sat: true });   // (synced coins are SAT: the mint is added as its SAT account)
    S.prefs.syncOther = (S.prefs.syncOther || []).filter(x => x !== u); save();
    await syRun('manual').catch(() => {});
    refresh();
  })
});
