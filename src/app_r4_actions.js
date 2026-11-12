/* Round 4 actions */
Object.assign(A, {
  ctPlay: b => { sfx('select'); openSoundSend(b.dataset.text); },
  ctListen: () => { sfx('select'); if (needSeed()) return; openListen(); },
  giftDays: b => { b.parentElement.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); sfx('blip'); },
  giftTake: b => run(b, 'CHECKING', async () => {
    const t = txById(b.dataset.id); const r = await takeBackGift(t);
    if (r === 'claimed') { toast(`${t.giftTo || 'They'} already claimed it`, 'lime'); closeSheet(); refresh(); return; }
    sfx('coin'); toast(`${money(t.amount)} came back to you`, 'lime'); closeSheet(); refresh();
  }),
  splitOpen: () => { sfx('select'); openSplit(); },
  splitCreate: b => run(b, 'SUMMONING', async () => {
    const total = amt(); const people = Math.round(+val('splitN'));
    if (!(people >= 2 && people <= 30)) throw new Error('Choose 2 to 30 people, including you.');
    const share = Math.ceil(total / people);
    if (share < 1) throw new Error('That bill is too small to split.');
    const r = newRequest(share, val('memoIn').trim() || 'Split the bill', !!($('#onlyMine') || {}).checked);
    r.split = { total, people, share, need: share * (people - 1) }; store.set('requests', S.requests);
    sfx('levelup'); showSplit(r); refresh();
  }),
  splitShow: b => { const r = S.requests.find(x => x.id === b.dataset.id); if (r) { sfx('select'); showSplit(r); } },
  healthCheck: b => { b.disabled = true; b.textContent = 'Checking…'; checkHealth().finally(() => { if (b.isConnected) refresh(); }); },
  moveOpen: b => openMove(b.dataset.from, b.dataset.to, b.dataset.amt),
  moveQuote: b => run(b, 'QUOTING', async () => {
    const from = val('mvFrom'), to = val('mvTo'), a = amt();
    const mv = await moveQuote(from, to, a);
    const nm = u => (S.mints.find(m => m.url === u) || {}).name || host(u);
    setBody(`<dl class="kv"><dt>Move</dt><dd>${money(a)}</dd><dt>From</dt><dd data-noi18n>${esc(nm(from))}</dd><dt>To</dt><dd data-noi18n>${esc(nm(to))}</dd><dt>Fee reserve</dt><dd>${money(num(mv.mq.fee_reserve))}</dd></dl>
      <div class="tiny muted">Unused fee reserve comes back as change.</div>
      <button class="btn solid gold block" id="mvGo">Move ${money(a)}</button><div id="sheetErr"></div>`, body => {
      body.querySelector('#mvGo').onclick = e => run(e.currentTarget, 'MOVING', async () => {
        const r = await doMove(mv); refresh();
        if (!r.ok) throw new Error("The move didn't go through, so the sats stayed where they were.");
        sfx('coin');
        setBody(`<div style="text-align:center;display:grid;gap:12px"><div style="font-family:var(--f-display);font-size:16px;color:var(--lime)">${r.waiting ? 'ON ITS WAY' : 'MOVED!'}</div><div class="credit-num" style="font-size:26px">${fmt(a)}<small>${unitTag()}</small></div>
          <div class="muted" data-noi18n>${esc(nm(from))} → ${esc(nm(to))}</div>${r.fee ? `<div class="tiny muted">Fee ${money(r.fee)}</div>` : ''}
          ${r.waiting ? '<div class="notice">The payment left. The receiving mint will confirm it shortly and NUTCADE claims it automatically.</div>' : ''}
          <button class="btn solid gold block" data-act="close">Continue</button></div>`);
        checkHealth();
      });
      return null;
    });
  }),
  cashier: () => { sfx('start'); openCashier(); },
  tillOpen: () => openTill(),
  tillCsv: () => exportCsv(todaysSales(), `nutcade-sales-${new Date().toISOString().slice(0, 10)}.csv`),
  chalOpen: b => openChallengeIn(b.dataset.id),
  chalSendOpen: b => openChallengeSend(b.dataset.id),
  chalPlay: b => {
    const c = S.challenges.find(x => x.id === b.dataset.id && x.dir === 'in'); if (!c || !window.Arcade) return;
    closeSheet(); window.Arcade.open(c.game, { challenge: { id: c.id, seed: c.seed, target: c.score, by: c.by, name: nameFor(c.pubkey) } });
  },
  chalSend: b => run(b, 'SENDING', async () => {
    const c = S.challenges.find(x => x.id === b.dataset.id && x.dir === 'out'); const k = contactById(b.dataset.c);
    if (!c || !k) return;
    const wrap = L.nip17.wrapEvent(rnd(32), { publicKey: k.pubkey }, JSON.stringify({ t: 'nutcade-challenge', ev: c.ev }));
    const ok = await relayPublish(wrap, 8000, [...new Set((k.relays || []).concat(relays()))].slice(0, 8));
    if (!ok) throw new Error('No Nostr relay accepted the challenge. Share the link instead.');
    c.sentTo = [...new Set((c.sentTo || []).concat(k.id))]; saveChallenges();
    sfx('coin'); toast(`Challenge sent to ${k.name}`, 'lime');
  }),
  chalShare: b => { const c = S.challenges.find(x => x.id === b.dataset.id); if (!c) return; const g = gameById(c.game); navigator.share({ text: `Beat my ${pad6(c.score)} on ${g ? g.name : c.game} in NUTCADE`, url: challengeLink(c.ev) }).catch(() => {}); },
  chalQR: b => { const c = S.challenges.find(x => x.id === b.dataset.id); if (!c) return; openSheet('Challenge QR', `${qrBlock(challengeLink(c.ev), 'Challenge link QR')}<button class="btn block" data-act="chalSendOpen" data-id="${esc(c.id)}">Back</button>`); },
  piggyEmpty: () => openSheet('Empty the piggy bank', `<p style="margin:0">This stops setting aside the ${money(piggySaved())} in your piggy bank. The sats were never moved, so your balance stays the same.</p><button class="btn solid pink block" data-act="piggyEmptyGo">Empty it</button><button class="btn block" data-act="close">Keep saving</button>`),
  piggyEmptyGo: () => { S.piggy.saved = 0; store.set('piggy', S.piggy); sfx('boom'); closeSheet(); refresh(); toast('Piggy bank emptied', 'gold'); }
});
