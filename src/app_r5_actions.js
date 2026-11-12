/* Round 5 actions: Extra Life */
Object.assign(A, {
  extraOpen: () => { sfx('select'); openExtra(); },
  extraStart: b => run(b, 'LOCKING', async () => {
    const a = amt();
    let heir = null; const sel = val('xlTo');
    if (sel) { const k = contactById(sel); if (k && k.pubkey) heir = { pubkey: k.pubkey, name: k.name }; }
    else { const n = parseNostrAddr(val('xlKey').trim()); if (n) heir = { pubkey: n.pubkey, name: nameFor(n.pubkey) || 'Your heir' }; }
    if (!heir) throw new Error('Pick an heir from your contacts, or paste their npub.');
    const days = +(($('#layer [data-act=giftDays][aria-pressed=true]') || {}).dataset || {}).days || 182;
    const x = await startExtra(a, heir, days, true);
    sfx('levelup'); refresh(); openExtra();
    toast(x.delivered ? `Extra Life set. ${heir.name} has their copy.` : `Extra Life set. Couldn't reach ${heir.name} over Nostr yet; NUTCADE keeps trying, or hand them their copy.`, x.delivered ? 'lime' : 'gold');
  }),
  extraContinue: b => run(b, 'CONTINUING', async () => { await continueExtra(); refresh(); openExtra(); }),
  extraCopy: () => openHeirCopy(),
  reportOpen: b => { sfx('select'); if (b.dataset.fresh && S.mintlog[b.dataset.url]) S.mintlog[b.dataset.url].nostr = null; openReport(b.dataset.url); },
  extraCash: () => { const x = S.extra; if (!x) return; openSheet('Cash out Extra Life', `<p style="margin:0">This puts ${money(x.amount)} back in your balance. ${esc(x.heir.name)}'s copy stops working and they'll see the Extra Life has ended.</p><button class="btn solid red block" data-act="extraCashGo">Cash out</button><button class="btn block" data-act="extraOpen">Back</button><div id="sheetErr"></div>`); },
  extraCashGo: b => run(b, 'CASHING OUT', async () => { const x = S.extra; await cashOutExtra(); sfx('coin'); closeSheet(); refresh(); toast(`${money(x.amount)} back in your balance`, 'lime'); })
});
