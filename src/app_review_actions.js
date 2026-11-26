/* Mint reviews: actions */
Object.assign(A, {
  rvOpen: b => { sfx('select'); openReview(b.dataset.url); },
  rvStar: b => { if (!rvSt) return; sfx('blip'); rvSt.stars = +b.dataset.n; rvPrev(); },
  rvEdit: b => { const own = rvMine(b.dataset.url); if (!rvSt || !own) return; Object.assign(rvSt, { edit: true, ask: false, done: null, stars: own.stars || 0 }); rvDraw(rvSt.url); },
  rvDelAsk: b => { if (!rvSt) return; Object.assign(rvSt, { ask: true, done: null }); rvDraw(rvSt.url); },
  rvBack: b => { if (!rvSt) return; rvSt.ask = false; rvDraw(rvSt.url); },
  rvPublish: b => run(b, 'PUBLISHING', async () => {
    const st = rvSt; if (!st) return;
    const r = await rvPublish(st.url, st.stars, val('rvText'));
    sfx('coin'); refresh();
    if (rvSt !== st) return;
    Object.assign(st, { edit: false, ask: false, stars: 0, done: { pub: true, n: r.n, of: r.of, other: r.other || null } }); rvDraw(st.url);
    toast('Review published', 'lime');
  }),
  rvDelOld: b => run(b, 'DELETING', async () => {
    const st = rvSt; if (!st || !idHex(b.dataset.pk)) return;
    await rvDelete(st.url, b.dataset.pk);
    refresh(); if (rvSt !== st) return;
    if (st.done) st.done = Object.assign({}, st.done, { other: null }); rvDraw(st.url);
    toast('Earlier review deleted', 'lime');
  }),
  rvDel: b => run(b, 'DELETING', async () => {
    const st = rvSt; if (!st) return;
    const r = await rvDelete(st.url);
    refresh();
    if (rvSt !== st) return;
    Object.assign(st, { edit: false, ask: false, stars: 0, done: r ? { del: true, n: r.n, of: r.of } : null }); rvDraw(st.url);
    toast('Review deleted', 'lime');
  })
});
