/* Unclaimed-token reminders: actions */
Object.assign(A, {
  rmTake: b => run(b, 'TAKING BACK', async () => {
    const r = await rmTakeAll(); refresh();
    if (r.back) { sfx('coin'); toast(r.back === 1 ? '1 token taken back' : `${r.back} tokens taken back`, 'lime'); }
    if (r.claimed) toast(r.claimed === 1 ? 'Someone had already claimed 1 of them. Your balance didn\'t change for it.' : `Someone had already claimed ${r.claimed} of them. Your balance didn't change for those.`, 'cyan');
    if (r.bad.length) { const e = new Error(r.bad.length === 1 ? "1 token couldn't be taken back." : `${r.bad.length} tokens couldn't be taken back.`); e.also = r.bad.join(' · '); e.keep = true; throw e; }
  }),
  rmLater: () => {
    const due = rmDue();
    S.prefs.rmLater = { until: Date.now() + (due.some(x => x.soon) ? RM_LATER_SOON : RM_LATER), soon: due.filter(x => x.soon).map(x => x.t.id) };
    save(); sfx('select'); refresh();
  }
});
