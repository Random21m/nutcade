/* Round 8 actions: spending limit, duress PIN */
Object.assign(A, {
  limOpen: () => { sfx('select'); openLimits(); },
  limSave: b => run(b, 'SAVING', async () => {
    const v = { per: readLimit('limPer'), day: readLimit('limDay') };
    if (!vault.on) { applyLimits(v); return; }
    limWant.v = v; pinUI.mode = 'limitSave'; pinUI.value = '';
    setBody(padHTML('ENTER PIN', 'Changing the spending limit needs your PIN.') + '<div id="sheetErr"></div>');
  }),
  limitNo: () => { limitClose(); sfx('blip'); },
  duressOpen: () => { sfx('select'); openDuress(); },
  duressChange: () => { duressUI.change = true; duressNewPad(); },
  duressOff: () => setBody(`<p style="margin:0">The duress PIN stops working. The sats in its wallet come back to this one.</p>
    <button class="btn solid red block" data-act="duressOffGo">Turn off duress PIN</button><button class="btn block" data-act="close">Keep it</button><div id="sheetErr"></div>`),
  duressOffGo: b => run(b, 'TURNING OFF', async () => { pinChangeCheck(); const back = await duressOff(); pinChangeUse(); duressUI.old = ''; closeSheet(); refresh(); sfx('blip'); toast(back ? `Duress PIN off. ${back} came back to this wallet.` : 'Duress PIN off', 'gold'); }),
  duressMake: b => run(b, 'SETTING UP', async () => {
    const a = parseSat(val('duressAmt'));
    if (a > 0 && a > balanceOf(S.active)) throw new Error(`Not enough funds. This mint holds ${money(balanceOf(S.active))}.`);
    await makeDuress(duressUI.pin, a); duressUI.pin = duressUI.old = '';
    sfx('levelup'); refresh();
    setBody(`<div style="text-align:center;display:grid;gap:12px"><div style="font-family:var(--f-display);font-size:15px;color:var(--lime)">DURESS PIN READY</div>
      <p style="margin:0">If someone forces you to unlock NUTCADE, enter your duress PIN instead. It opens a separate small wallet${a ? ` with ${money(a)}` : ''}, and nothing in it shows this one.</p>
      <button class="btn solid gold block" data-act="close">Done</button></div>`);
  })
});
