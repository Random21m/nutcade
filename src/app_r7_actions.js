/* Round 7 actions: LNURL-withdraw, blocked mints, Wallet Connect, zaps */
Object.assign(A, {
  lnurlwGo: b => run(b, 'ASKING MINT', async () => {
    const v = curWd; if (!v) return;
    const sats = amt(), url = val('wdMint');
    const res = await withdrawVoucher(v, sats, url);
    sfx('blip'); refresh(); showWithdrawWait(res);
  }),
  blockMint: b => openBlock(b.dataset.url),
  blockMintGo: b => {
    const u = b.dataset.url, bal = balanceOf(u), n = mintName(u);
    blockMint(u); sfx('blip'); render();
    const canMove = canMoveFrom(u);
    setBody(`<div class="notice red">${esc(n)} is blocked. Tokens, payment requests and deposits from it will be refused, and NUTCADE will tell you each time.</div>
      ${bal ? `<div class="notice">Your ${money(bal)} at ${esc(n)} stays usable: you can still send it or move it to another mint.</div>` : ''}
      ${canMove ? `<button class="btn solid gold block" data-act="moveOpen" data-from="${esc(u)}">Move sats out</button><button class="btn block" data-act="close">Done</button>` : `${bal ? noMoveHTML(u) : ''}<button class="btn solid gold block" data-act="close">Done</button>`}`);
  },
  sendFrom: b => { S.active = b.dataset.url; save(); closeSheet(); render(); openSend('ecash');
  },
  unblockMint: b => {
    const u = b.dataset.id || b.dataset.url; if (!u) return;
    const n = (S.blocked.find(x => x.url === normUrl(u)) || {}).name || mintName(u);
    unblockMint(u); sfx('coin'); toast(`${n} unblocked`, 'lime');
    const er = b.closest('.notice'); if (er && b.closest('#layer')) er.remove();   // the refusal it answered goes; tap the main button again
    refresh();
  },
  zapOpen: b => { const t = parseNostrAddr(b.dataset.pk); if (t) openZap({ pubkey: t.pubkey, relays: t.relays, name: b.dataset.name || '' }); },
  zapContact: b => { const c = contactById(b.dataset.id); if (c && c.pubkey) openZap({ pubkey: c.pubkey, relays: c.relays || [], name: c.name, contactId: c.id }); },
  zapQuote: b => run(b, 'ASKING', async () => {
    const z = curZap; if (!z) return;
    const sats = amt(), comment = val('zapComment').trim();
    const { pr, zapReq } = await zapInvoice(z, sats, comment);
    const mq = await meltQuote('ln', pr);
    if (num(mq.amount) !== sats) throw serviceErr(`The invoice asked for ${money(num(mq.amount))} instead of ${money(sats)}. Nothing was sent.`);
    const note = z.zapOk ? `Zap to ${z.name}` : `To ${z.name}`;
    zapByQuote.set(mq.quote, z.zapOk ? { zap: { pubkey: z.pubkey, id: zapReq.id }, zapName: z.name } : { lnName: z.name });
    showMeltQuote('ln', mq, z.addr, note);
  }),
  nwcNew: () => { sfx('select'); openNwcNew(); },
  nwcCreate: b => run(b, 'CREATING', async () => {
    const budget = readBudget();
    const { c, uri } = nwcCreate(val('nwcName'), budget);
    sfx('coin'); refresh(); showNwcUri(c, uri);
  }),
  nwcEdit: b => openNwcEdit(b.dataset.id),
  nwcSave: b => run(b, 'SAVING', async () => {
    const c = S.nwc.find(x => x.id === b.dataset.id); if (!c) { closeSheet(); return; }
    const name = val('nwcName').trim().slice(0, 40); if (!name) throw new Error('Give the connection a name, like the app it is for.');
    const budget = readBudget();
    c.name = name; c.budget = budget; saveNwc(); sfx('coin'); closeSheet(); refresh(); toast(`${name} saved`, 'lime');
  }),
  nwcRevokeAsk: b => {
    const c = S.nwc.find(x => x.id === b.dataset.id); if (!c) return;
    openSheet('Revoke connection', `<p style="margin:0">Revoke ${esc(c.name)}? It stops working with this wallet right away. Payments it already made stay in your notes.</p>
      <button class="btn solid red block" data-act="nwcRevoke" data-id="${esc(c.id)}">Revoke</button><button class="btn block" data-act="close">Cancel</button>`);
  },
  nwcRevoke: b => { const c = S.nwc.find(x => x.id === b.dataset.id); if (!c) { closeSheet(); return; } nwcRevoke(c.id); sfx('blip'); closeSheet(); refresh(); toast(`${c.name} revoked. It can't use this wallet anymore.`, 'gold'); }
});
