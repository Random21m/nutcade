/* Printable tokens + the logo in QR codes: actions */
Object.assign(A, {
  ptOpen: () => { sfx('select'); openPrint(); },
  ptStyle: b => {
    ptUI.style = b.dataset.s === 'ink' ? 'ink' : 'arcade';
    document.querySelectorAll('[data-act=ptStyle]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.s === ptUI.style)));
    const h = $('#ptStyleHelp'); if (h) h.textContent = tr(ptUI.style === 'ink' ? 'Black on white.' : 'Full color. The QR code is always dark on light.');
    sfx('blip');
  },
  ptNext: b => run(b, 'CHECKING', ptSummary),
  ptMake: b => run(b, 'MAKING TOKENS', () => ptMakeBatch(b)),
  ptPrint: b => { ptPrintNow(b.dataset.b).then(() => sfx('select'), showErr); },
  ptList: () => { sfx('select'); ptListOpen(); },
  ptReprint: b => run(b, 'CHECKING CODES', () => ptReady(b.dataset.b)),
  ptCheck: b => run(b, 'CHECKING', async () => {
    const r = await ptCheckAll(); ptListOpen(true); refresh();
    if (r.down.length) { const e = new Error(`Couldn't reach ${r.down.map(host).join(', ')}. Nothing changed for its tokens: check again when it answers.`); e.keep = true; throw e; }
    toast(r.got ? `${r.got} claimed since the last check` : 'No new claims', 'cyan');
  }),
  ptTake: b => run(b, 'TAKING BACK', async () => {
    const t = txById(b.dataset.id); if (!t) { ptListOpen(true); return; }
    if (t.status === 'claimed') { ptListOpen(true); const e = new Error(`Someone already claimed token #${t.print ? t.print.code : ''}, so there is nothing to take back. Your balance didn't change.`); e.keep = true; throw e; }   // (found claimed meanwhile)
    if (t.status !== 'pending') { ptListOpen(true); return; }
    try { await ptTakeOne(t); } finally { ptListOpen(true); refresh(); }
    sfx('coin'); toast('Token taken back', 'lime');
  }),
  ptTakeAll: b => run(b, 'TAKING BACK', async () => {
    const open = printedTxs().filter(t => t.status === 'pending'), bad = []; let n = 0;
    for (const t of open) { try { await ptTakeOne(t); n++; } catch (e) { bad.push(`#${t.print.code}: ${friendly(e, t.mint).message}`); } }
    ptListOpen(true); refresh();
    if (n) { sfx('coin'); toast(n === 1 ? '1 token taken back' : `${n} tokens taken back`, 'lime'); }
    if (bad.length) { const e = new Error(bad.length === 1 ? "1 token couldn't be taken back." : `${bad.length} tokens couldn't be taken back.`); e.also = bad.join(' · '); e.keep = true; throw e; }
  }),
  qrLogo: b => { S.prefs.qrLogo = b.dataset.v === 'none' ? 'none' : 'acorn'; save(); refresh(); sfx('select'); }
});
