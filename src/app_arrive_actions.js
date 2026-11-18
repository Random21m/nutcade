/* Arrival notices: their buttons (src/app_arrive.js) */
Object.assign(A, {
  arrClose: b => { const c = b.closest('.arr-card'); if (c) { if (c.dataset.type === 'live') arrS().card = []; c.remove(); } sfx('blip'); },
  arrMore: b => {
    const c = b.closest('.arr-card'); if (!c) return;
    const type = c.dataset.type, items = arrS().items[type] || [];
    if (type === 'live') arrS().card = []; c.remove(); sfx('select');
    openSheet(type === 'away' ? 'While you were away' : 'Money arrived', arrDetailsHTML(type, items));
  },
  arrNotes: b => { const c = b.closest('.arr-card'); if (c) { if (c.dataset.type === 'live') arrS().card = []; c.remove(); } closeSheet(); tab = 'history'; render(); window.scrollTo(0, 0); sfx('select'); }
});
