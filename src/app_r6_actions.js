/* Round 6 actions: treasure hunts and loaded cards */
Object.assign(A, {
  huntNew: () => { sfx('select'); openHuntNew(); },
  huntCreate: b => run(b, 'HIDING', async () => {
    const a = amt(), n = Math.round(+val('huntN')), k = Math.round(+val('huntK'));
    if (!(n >= 2 && n <= 12)) throw new Error('Use 2 to 12 clue cards.');
    if (!(k >= 1 && k <= n)) throw new Error(`The number needed has to be between 1 and ${n}.`);
    const days = +(($('#layer [data-act=giftDays][aria-pressed=true]') || {}).dataset || {}).days || 7;
    const h = await makeHunt(a, k, n, days, val('noteIn').trim());
    sfx('levelup'); refresh(); openHuntCards(h.pub);
  }),
  huntCards: b => openHuntCards(b.dataset.pub),
  huntShow: b => openHunt(b.dataset.pub),
  huntOpen: b => { b.disabled = true; openChest(b.dataset.pub); },
  huntPrint: () => { document.body.classList.add('print-hunt'); const done = () => { document.body.classList.remove('print-hunt'); window.removeEventListener('afterprint', done); }; window.addEventListener('afterprint', done); try { window.print(); } catch (e) { done(); } }
});
