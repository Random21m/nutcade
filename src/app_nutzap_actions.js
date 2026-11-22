/* Nutzaps: actions */
Object.assign(A, {
  nzOpen: b => {
    const c = b.dataset.id && contactById(b.dataset.id);
    if (c && c.pubkey) { openNutzap({ pubkey: c.pubkey, relays: c.relays || [], name: c.name, contactId: c.id }); return; }
    const t = parseNostrAddr(b.dataset.pk); if (t) openNutzap({ pubkey: t.pubkey, relays: t.relays, name: b.dataset.name || '' });
  },
  nzSend: b => run(b, 'SENDING', async () => {
    const z = curNz; if (!z) return;
    const sats = amt(), comment = val('nzComment').trim();
    const { ok } = await nzSendTo(z, z.info, sats, comment);
    sfx('coin'); refresh();
    if (ok) return showDone('out', sats, `Nutzap to ${z.name}`);
    setBody(`<div class="notice">The nutzap was made, but no Nostr relay has taken it yet. Its ecash is locked to them, and NUTCADE keeps trying to deliver it.</div><button class="btn block" data-act="close">Close</button>`);
  }),
  nzRetry: b => run(b, 'SENDING', async () => {
    const t = txById(b.dataset.id); if (!t || !t.nz) return;
    const ok = await single('nzsend:' + t.id, () => nzDeliverOne(t.id));
    refresh();
    if (!ok) throw new Error("No Nostr relay took the nutzap. NUTCADE keeps trying.");
    toast('Nutzap delivered', 'lime'); closeSheet();
  })
});
