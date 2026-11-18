/* Arrival notices: their buttons (src/app_arrive.js) */
Object.assign(A, {
  arrClose: b => { const c = b.closest('.arr-card'); if (c) { if (c.dataset.type === 'live') arrS().card = []; c.remove(); } sfx('blip'); },
  arrNotes: b => { const c = b.closest('.arr-card'); if (c) { if (c.dataset.type === 'live') arrS().card = []; c.remove(); } closeSheet(); tab = 'history'; render(); window.scrollTo(0, 0); sfx('select'); }
});
