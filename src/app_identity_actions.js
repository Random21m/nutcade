/* Your own Nostr identity: actions (src/app_identity.js) */
Object.assign(A, {
  idExt: b => run(b, 'WAITING FOR YOUR SIGNER', async () => { sfx('select'); await idSignInExt(); sfx('coin'); toast('Signed in', 'lime'); refresh(); }),
  idBunker: () => { sfx('select'); openIdBunker(); },
  idScan: () => openScanner("Point at your signer's bunker:// QR code."),
  idConnect: b => run(b, 'WAITING FOR YOUR SIGNER', async () => {
    const box = $('#idLink'), v = box ? box.value : '';
    if (!String(v).trim()) throw keepErr(new Error('Paste a bunker:// link first.'));
    const p = idParse(v);
    if (!p.ok) { if (p.error === ID_E_NSEC && box) box.value = ''; throw keepErr(new Error(p.error)); }   // (a private key is never kept, not even in the field)
    await idSignInBunker(v);
    if (box) box.value = '';
    sfx('coin'); closeSheet(); toast('Signed in', 'lime'); refresh();
  }),
  idOut: () => { sfx('select'); openIdOut(); },
  idOutGo: b => run(b, 'WAITING FOR YOUR SIGNER', async () => {
    const w = !!($('#idOutWithdraw') || {}).checked;
    await idSignOut(w);
    closeSheet(); toast('Signed out', 'cyan'); refresh();
  }),
  idRetract: b => run(b, 'WITHDRAWING', async () => {
    const pk = b.dataset.pk; if (!idHex(pk)) return;
    await nzRetractOld(pk);
    toast('Old nutzap info withdrawn', 'lime'); refresh();
  })
});
