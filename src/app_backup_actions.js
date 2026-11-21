/* Better backups actions (app_backup.js): the locked backup file, Back up with my phone, Restore with my phone */
Object.assign(A, {
  bkLockGo: b => !guardHeld('backup') ? closeSheet() : run(b, 'LOCKING', async () => {
    const pw = val('bkPw');
    if (pw.length < 8) throw new Error('Use at least 8 characters for the password.');
    if (pw !== val('bkPw2')) throw new Error("The two passwords don't match.");
    const data = await lockBackup(backupData(), pw);
    for (const id of ['bkPw', 'bkPw2']) { const i = $('#' + id); if (i) i.value = ''; }
    try { saveBackupFile(data); closeSheet(); if (tab === 'settings') refresh(); toast('Locked backup file downloaded. Keep the password safe.', 'lime'); }
    catch (e) { showBackupText(data); }
  }),
  phoneOpen: () => pinGuard('phone', () => openSheet('Back up with my phone', `<div class="notice">Your Apple or Google account becomes a key to your wallet: anyone who gets into it can use the passkey to get your 12 words back. Keep that account safe, with two-step sign-in.</div>
    <p style="margin:0">NUTCADE makes a passkey on this phone (kept in iCloud Keychain or Google Password Manager), locks your 12 words with it and saves the locked copy on Nostr relays. No server of ours is involved.</p>
    <div class="th">Keep your 12 words on paper too. They are still your main backup.</div>
    <button class="btn solid gold block" data-act="phoneGo">${pbRec() ? 'Back up again' : 'Back up with my phone'}</button><div id="sheetErr"></div>`)),
  phoneGoForce: b => A.phoneGo(b, true),
  phoneGo: (b, force) => !guardHeld('phone') ? closeSheet() : run(b, 'WAITING', pbOnce(async () => {
    const n = await phoneBackup(force === true); sfx('coin');
    setBody(`<div style="text-align:center;display:grid;gap:12px"><div style="font-family:var(--f-display);font-size:15px;color:var(--lime)">BACKED UP!</div>
      <p style="margin:0">Your 12 words are locked with your passkey and saved on ${n} relay${n === 1 ? '' : 's'}. On a new phone, tap Restore with my phone.</p>
      <button class="btn solid gold block" data-act="close">Done</button></div>`);
    if (tab === 'settings') refresh();
  })),
  phoneRemoveAsk: () => pinGuard('phone', () => openSheet('Remove phone backup', `<p style="margin:0">NUTCADE asks the Nostr relays to delete the locked copy of your 12 words. A relay that is down or ignores the request can keep it, still locked with your passkey.</p>
    <div class="notice red">After this, Restore with my phone will not bring this wallet back. Keep your 12 words.</div>
    <div class="th">You can also delete the passkey in your password manager.</div>
    <button class="btn solid red block" data-act="phoneRemoveGo">Remove phone backup</button><div id="sheetErr"></div>`)),
  phoneRemoveGo: b => !guardHeld('phone') ? closeSheet() : run(b, 'REMOVING', async () => { await phoneRemove(); closeSheet(); refresh(); toast('Phone backup removed.', 'gold'); }),
  // the start screen (no wallet yet: nothing to ask), or the Restore wallet sheet (opened through the PIN guard)
  gatePhone: b => guardOn() ? pinGuard('restore', openRestore) : run(b, 'WAITING', pbOnce(async () => { const r = await phoneFetch(); openRestore(); phoneFill(r); })),
  phoneRestore: b => !guardHeld('restore') ? closeSheet() : run(b, 'WAITING', pbOnce(async () => { phoneFill(await phoneFetch()); }))
});
