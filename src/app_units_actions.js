/* Units (1.31): actions */
Object.assign(A, {
  // one unit of a mint already in the list, added as its own account; nothing of the others changes
  addUnit: b => run(b, 'ADDING', async () => {
    const sh = sheetOf(b), key = acctKey(normUrl(b.dataset.url), b.dataset.u);
    if (isBlocked(key)) throw blockedErr(key, 'add');
    const m = await addMint(key, { activate: true });
    sfx('coin'); toast(`${acctName(m)} added`, 'lime'); closeSheetOf(sh); render();
  })
});
