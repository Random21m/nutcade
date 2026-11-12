/* ===================== Round 5: high-score bounties and Extra Life ===================== */

/* ---------- high-score bounties: "beat my score, take the sats" (NUT-14 hash locks) ----------
   The sats are locked to your friend's key AND to a secret only your NUTCADE knows. The mint won't release them
   without both. When your friend's signed score beats yours, your NUTCADE sends them the secret and they claim.
   If nobody wins within a week, the lock's refund path lets you take the sats back (same as a gift). */
const BOUNTY_DAYS = 7;
const sha256hex = async bytes => hex(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)));
async function mintCan(url, nut) { try { const s = (await getWallet(url)).getMintInfo().isSupported(nut); return !!(s && s.supported && !s.disabled); } catch (e) { return false; } }
function bountyField() {
  return `<div class="field" id="bountyF"><label for="bountyAmt">Put sats on it (optional)</label><input id="bountyAmt" class="inp" inputmode="numeric" placeholder="0" autocomplete="off">
    <div class="th">The mint locks them so only the friend you send to can win them, and only by beating your score within ${BOUNTY_DAYS} days. If they don't, the sats come back to you.</div></div>`;
}
async function createBounty(c, k, amount) {
  if (!k.pubkey) throw new Error('Bounties need a contact with a Nostr address.');
  if (!(await mintCan(S.active, 14))) throw new Error(`${host(S.active)} can't lock sats to a secret (NUT-14). Pick another mint for bounties.`);
  const pre = rnd(32), H = await sha256hex(pre), until = Math.floor(Date.now() / 1000 + ((window.__nutcadeTest && __nutcadeTest.bountySecs) || BOUNTY_DAYS * 86400));
  const g = gameById(c.game);
  const tx = await sendEcash(amount, `Bounty for ${k.name}: beat ${pad6(c.score)} on ${g ? g.name : c.game}`, '02' + k.pubkey, S.active, { locktime: until, hashlock: H });
  updTx(tx.id, { lockUntil: until * 1000, giftTo: k.name, contactId: k.id, contactName: k.name, bounty: c.id });
  c.bounties = (c.bounties || []).concat([{ to: k.pubkey, name: k.name, txId: tx.id, pre: hex(pre), H, amount, until: until * 1000, state: 'open' }]);
  saveChallenges();
  return { tx: txById(tx.id), b: c.bounties[c.bounties.length - 1] };
}
// the winner's NUTCADE gets the secret; retried from the background check until a relay takes it
async function releaseBounty(c, b) {
  const k = S.contacts.find(x => x.pubkey === b.to);
  const wrap = L.nip17.wrapEvent(nostrKey(), { publicKey: b.to }, JSON.stringify({ t: 'nutcade-bounty', re: c.id, pre: b.pre }));
  const ok = await relayPublish(wrap, 8000, [...new Set(((k && k.relays) || []).concat(relays()))].slice(0, 8));
  b.state = ok ? 'paid' : 'won'; saveChallenges();
  return ok;
}
async function bountyOnResult(c, r) {
  const b = (c.bounties || []).find(x => x.to === r.pubkey && (x.state === 'open' || x.state === 'won'));
  if (!b || !(r.score > c.score)) return;
  if (Date.now() > b.until) return;   // too late: the refund path is open, so the sats come back to you
  b.state = 'won'; b.score = Math.floor(r.score); saveChallenges();
  await releaseBounty(c, b);
  sfx('coin'); toast(`${b.name} beat ${pad6(c.score)} and won your ${money(b.amount)} bounty`, 'pink');
}
async function retryBounties() {
  for (const c of S.challenges.filter(x => x.dir === 'out')) for (const b of (c.bounties || []).filter(x => x.state === 'won' && Date.now() < x.until)) await releaseBounty(c, b).catch(() => {});
}
// an incoming bounty: check the ecash really is locked to us and to the hash before showing it
function readBounty(bo, rec) {
  try {
    const tok = cleanToken(String(bo.token || '')); const d = L.getDecodedToken(tok, Object.keys(S.counters));
    let H = null;
    for (const p of d.proofs) {
      const sec = JSON.parse(p.secret); if (sec[0] !== 'HTLC') return null;
      const keys = ((sec[1].tags || []).find(t => t[0] === 'pubkeys') || []).slice(1);
      if (!keys.includes(myLockPub())) return null;
      if (H && sec[1].data !== H) return null; H = sec[1].data;
    }
    // the proofs carry a little extra for the mint's fee; show the amount the challenger put up when it's covered
    const amount = num(bo.amount) > 0 && num(bo.amount) <= sum(d.proofs) ? Math.floor(num(bo.amount)) : sum(d.proofs);
    return { token: tok, amount, mint: normUrl(d.mint), H, until: num(bo.until) || Date.now() + BOUNTY_DAYS * 86400e3, state: 'open', game: rec.game };
  } catch (e) { return null; }
}
async function claimBounty(rec, pre, from) {
  const b = rec.bounty; if (!b || b.state === 'won' || from !== rec.pubkey) return;
  if (await sha256hex(L.hexToBytes(pre)) !== b.H) return;
  const d = L.getDecodedToken(b.token, Object.keys(S.counters));
  const unlocked = L.getEncodedToken({ mint: d.mint, unit: 'sat', proofs: d.proofs.map(p => Object.assign({}, p, { witness: JSON.stringify({ preimage: pre }) })) });
  const who = nameFor(rec.pubkey) || rec.by, g = gameById(rec.game);
  try { await receiveToken(unlocked, `Bounty from ${who}: beat ${pad6(rec.score)} on ${g ? g.name : rec.game}`); }
  catch (e) { if (/spent/i.test(e.message || '')) { b.state = 'gone'; saveChallenges(); } return; }
  b.state = 'won'; saveChallenges();
  sfx('levelup'); celebrate('in', b.amount); toast(`You won ${who}'s ${money(b.amount)} bounty!`, 'lime'); refresh();
}

/* ---------- Extra Life: ecash inheritance with no custodian (NUT-11 time locks) ----------
   Your savings are locked to YOUR key, with your heir's key as the refund key after a date. You can spend them any
   time. Your heir holds a copy that only opens after the date. Each CONTINUE swaps the ecash for fresh ecash with a
   later date and sends your heir the new copy, which also makes their old copy worthless. Stop pressing CONTINUE
   (or lose your phone and your words) and after the date your heir's NUTCADE claims it. */
const EXTRA_PERIODS = [[90, '3 MONTHS'], [182, '6 MONTHS'], [365, '1 YEAR']];
S.extra = store.get('extra', null);         // ours: { mint, amount, proofs, heir:{pubkey,name}, until, days, auto, created, renewed }
S.heirlooms = store.get('heirlooms', []);   // theirs, held for us: { from, name, token, amount, mint, until, state }
const saveExtra = () => store.set('extra', S.extra);
const saveHeir = () => store.set('heirlooms', S.heirlooms.slice(0, 20));
const extraLeft = () => S.extra ? S.extra.until - Date.now() : 0;
const daysLeft = ms => Math.max(0, Math.ceil(ms / 86400e3));
async function lockExtra(url, amount, heirPub, until, extraInputs) {
  const w = await getWallet(url);
  const inputs = (extraInputs || []).concat(S.proofs[url] || []);
  if (sum(inputs) < amount) throw new Error(`Not enough credits. This mint holds ${money(sum(S.proofs[url] || []))}.`);
  const cfg = { send: { type: 'p2pk', options: { pubkey: myLockPub(), locktime: Math.floor(until / 1000), refundKeys: ['02' + heirPub] } }, keep: w.defaultOutputType() };
  const { keep, send } = await withRepair(url, () => w.send(amount, inputs, { includeFees: true }, cfg));
  S.proofs[url] = plain(keep); save();
  return plain(send);
}
const extraToken = () => S.extra && L.getEncodedToken({ mint: S.extra.mint, unit: 'sat', proofs: S.extra.proofs });
async function sendHeirCopy() {
  const x = S.extra; if (!x) return false;
  const k = S.contacts.find(c => c.pubkey === x.heir.pubkey);
  const body = { t: 'nutcade-extralife', v: 1, token: extraToken(), until: x.until, amount: x.amount };
  const wrap = L.nip17.wrapEvent(nostrKey(), { publicKey: x.heir.pubkey }, JSON.stringify(body));
  const ok = await relayPublish(wrap, 8000, [...new Set(((k && k.relays) || []).concat(relays()))].slice(0, 8));
  x.delivered = !!ok; saveExtra(); return !!ok;
}
async function startExtra(amount, heir, days, auto) {
  if (S.extra) throw new Error('You already have an Extra Life. Cash it out first to start a new one.');
  if (!heir || !heir.pubkey) throw new Error('Pick an heir with a Nostr address, or paste their npub.');
  if (heir.pubkey === L.nostrPub(nostrKey())) throw new Error("Your heir has to be someone else.");
  if (!(await mintCan(S.active, 11))) throw new Error(`${host(S.active)} can't lock ecash to a key (NUT-11). Pick another mint.`);
  piggyGuard(amount);
  const until = Date.now() + days * 86400e3;
  internalMove = true;
  try {
    const proofs = await lockExtra(S.active, amount, heir.pubkey, until);
    S.extra = { mint: S.active, amount, proofs, heir, until, days, auto: auto !== false, created: Date.now(), renewed: Date.now() }; saveExtra();
    addTx({ type: 'out', method: 'ecash', amount, fee: Math.max(0, sum(proofs) - amount), mint: S.active, note: `Extra Life for ${heir.name}`, status: 'done', extraLife: true });
  } finally { internalMove = false; }
  await sendHeirCopy().catch(() => false);
  return S.extra;
}
// CONTINUE: swap for fresh ecash with a later date. Fees come out of this mint's balance so the locked amount stays the same.
async function continueExtra(quiet) {
  const x = S.extra; if (!x) return;
  const w = await getWallet(x.mint);
  const fresh = plain(await withRepair(x.mint, () => w.receive(extraToken(), { privkey: [myLockPriv()] })));
  const until = Date.now() + x.days * 86400e3;
  let proofs;
  try { proofs = await lockExtra(x.mint, x.amount, x.heir.pubkey, until, fresh); }
  catch (e) {
    // the balance can't cover the fee: lock a little less rather than leave the sats unprotected
    const amount = Math.max(1, sum(fresh) - 2);
    try { proofs = await lockExtra(x.mint, amount, x.heir.pubkey, until, fresh); x.amount = amount; }
    catch (e2) { addProofs(x.mint, fresh); S.extra = null; saveExtra(); throw new Error("Couldn't lock your Extra Life again, so the sats are back in your balance."); }
  }
  Object.assign(x, { proofs, until, renewed: Date.now() }); saveExtra();
  await sendHeirCopy().catch(() => false);
  if (!quiet) { sfx('levelup'); toast(`CONTINUE! ${x.heir.name}'s copy now opens on ${fmtDay(until)}`, 'lime'); }
}
async function cashOutExtra() {
  const x = S.extra; if (!x) return;
  const tx = await receiveToken(extraToken(), `Extra Life cashed out (was for ${x.heir.name})`);
  S.extra = null; saveExtra();
  const k = S.contacts.find(c => c.pubkey === x.heir.pubkey);
  const wrap = L.nip17.wrapEvent(nostrKey(), { publicKey: x.heir.pubkey }, JSON.stringify({ t: 'nutcade-extralife-end', v: 1 }));
  relayPublish(wrap, 8000, [...new Set(((k && k.relays) || []).concat(relays()))].slice(0, 8)).catch(() => {});
  return tx;
}
// opening NUTCADE counts as proof of life: with auto on, once half the time has passed it continues by itself
async function extraTick() {
  const x = S.extra; if (!x) return;
  if (extraLeft() < 0) {
    // the date passed: if the heir already claimed, the Extra Life is over; if not, it's still ours to continue
    const st = await (await getWallet(x.mint)).checkProofsStates(x.proofs).catch(() => null);
    if (st && st.length && st.every(s => s.state === 'SPENT')) {
      S.extra = null; saveExtra();
      addTx({ type: 'out', method: 'ecash', amount: x.amount, mint: x.mint, note: `Extra Life passed to ${x.heir.name}`, status: 'done', extraLife: true, move: true, fx: null });
      toast(`Your Extra Life passed to ${x.heir.name}`, 'gold'); refresh(); return;
    }
  }
  if (x.auto && extraLeft() < x.days * 86400e3 / 2) await continueExtra(true).catch(() => {});
  else if (!x.delivered) await sendHeirCopy().catch(() => {});
}
// the heir's side
function onExtraLife(p, from) {
  if (p.t === 'nutcade-extralife-end') { S.heirlooms.filter(h => h.from === from && h.state === 'waiting').forEach(h => { h.state = 'ended'; }); saveHeir(); if (tab === 'wallet' && !$('#layer .sheet')) refresh(); return; }
  let d; try { d = L.getDecodedToken(cleanToken(String(p.token || '')), Object.keys(S.counters)); } catch (e) { return; }
  let until = 0;
  for (const pr of d.proofs) {
    let sec; try { sec = JSON.parse(pr.secret); } catch (e) { return; }
    if (sec[0] !== 'P2PK') return;
    const tags = sec[1].tags || [], refund = (tags.find(t => t[0] === 'refund') || []).slice(1), lt = num((tags.find(t => t[0] === 'locktime') || [])[1]);
    if (!refund.includes(myLockPub()) || !lt) return;   // only copies we could actually claim
    until = Math.max(until, lt * 1000);
  }
  const who = nameFor(from);
  const h = { from, name: who || 'A friend', token: cleanToken(String(p.token)), amount: sum(d.proofs), mint: normUrl(d.mint), until, state: 'waiting', at: Date.now() };
  const old = S.heirlooms.find(x => x.from === from && x.state === 'waiting');
  if (old && old.until >= until) return;
  S.heirlooms = S.heirlooms.filter(x => !(x.from === from && x.state === 'waiting')); S.heirlooms.unshift(h); saveHeir();
  if (!old) { sfx('select'); toast(`${h.name} made you the heir of their Extra Life`, 'gold'); }
  if (tab === 'wallet' && !$('#layer .sheet')) refresh();
}
async function claimHeirlooms() {
  for (const h of S.heirlooms.filter(x => x.state === 'waiting' && Date.now() > x.until + 30e3)) {
    try { await receiveToken(h.token, `Extra Life from ${h.name}`); h.state = 'claimed'; saveHeir(); sfx('coin'); toast(`${h.name}'s Extra Life passed to you: ${money(h.amount)}`, 'gold'); refresh(); }
    catch (e) { if (/spent/i.test(e.message || '')) { h.state = 'ended'; saveHeir(); } }
  }
}

/* ---------- screens ---------- */
const CONT_ICON = `<svg viewBox="0 0 12 12" width="22" height="22" fill="currentColor" aria-hidden="true"><path d="M1 3h2v1h1v1h1V4h1V3h2v1h1v1h1v2h-1v1H9v1H8v1H7v1H5v-1H4V9H3V8H2V7H1z"/></svg>`;
function extraPanel() {
  const x = S.extra, hs = S.heirlooms.filter(h => h.state === 'waiting');
  if (!x && !hs.length) return '';
  let html = '';
  if (x) {
    const left = daysLeft(extraLeft()), soon = left <= Math.min(30, x.days / 4);
    html += `<button class="panel extra-panel ${soon ? 'soon' : ''}" data-act="extraOpen"><span class="xl-heart">${CONT_ICON}</span><span class="mid"><span class="h2">Extra Life</span>
      <span class="tiny" data-noi18n>${money(x.amount)} → ${esc(x.heir.name)}</span><span class="tiny muted">${soon ? `CONTINUE? ${left} days left` : `Opens for them on ${fmtDay(x.until)}`}</span></span></button>`;
  }
  for (const h of hs) html += `<div class="panel extra-panel heir"><span class="xl-heart">${CONT_ICON}</span><span class="mid"><span class="h2">Extra Life from <span data-noi18n>${esc(h.name)}</span></span>
      <span class="tiny">${money(h.amount)}</span><span class="tiny muted">Yours after ${fmtDay(h.until)} if they stop pressing CONTINUE</span></span></div>`;
  return html;
}
function openExtra() {
  if (needSeed()) return;
  const x = S.extra;
  if (x) {
    const left = daysLeft(extraLeft());
    openSheet('Extra Life', `
      <div class="continue-box"><div class="cont-q">CONTINUE?</div><div class="cont-n">${left}</div><div class="tiny muted">days until ${esc(x.heir.name)} can claim it</div></div>
      <dl class="kv"><dt>Locked</dt><dd>${money(x.amount)}</dd><dt>Heir</dt><dd data-noi18n>${esc(x.heir.name)}</dd><dt>Opens for them</dt><dd>${fmtDay(x.until)}</dd><dt>Mint</dt><dd data-noi18n>${esc(host(x.mint))}</dd><dt>Their copy</dt><dd>${x.delivered ? 'Delivered over Nostr' : 'Not delivered yet'}</dd></dl>
      <label class="toggle set" for="xlAuto"><span><span class="tl">Continue when I open NUTCADE</span><span class="th">Once half the time has passed, opening NUTCADE counts as CONTINUE. Turn this off to press it yourself.</span></span><input id="xlAuto" type="checkbox" ${x.auto ? 'checked' : ''}></label>
      <button class="btn solid gold block" data-act="extraContinue">CONTINUE</button>
      <div class="row wrap"><button class="btn sm violet" data-act="extraCopy">Heir's copy</button><button class="btn sm red" data-act="extraCash">Cash out</button></div>
      <div class="tiny muted">You can spend these sats any time: Cash out puts them back in your balance and ${esc(x.heir.name)}'s copy stops working. Every CONTINUE does the same to their old copy and sends them a new one.</div>
      <div id="sheetErr"></div>`, body => { const t = body.querySelector('#xlAuto'); if (t) t.onchange = () => { x.auto = t.checked; saveExtra(); sfx('blip'); }; return null; });
    return;
  }
  const cs = S.contacts.filter(c => c.pubkey);
  openSheet('Extra Life', `
    <div class="continue-box"><div class="cont-q">EXTRA LIFE</div><div class="tiny">Savings that pass to someone you trust if you stop playing</div></div>
    <ol class="steps"><li>Lock some sats. They stay yours: spend them any time.</li><li>Your heir gets a copy that only opens after the date.</li><li>Press CONTINUE now and then (or just open NUTCADE) to push the date back.</li><li>If you stop, your heir's NUTCADE claims the sats once the date passes.</li></ol>
    <div class="field"><label for="amtIn">Amount (sat)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="10000" autocomplete="off"></div>
    <div class="field"><label for="xlTo">Heir</label><select id="xlTo" class="inp">${cs.map(c => `<option value="${esc(c.id)}" data-noi18n>${esc(c.name)}</option>`).join('')}<option value="">Someone else (paste their npub)</option></select></div>
    <div class="field" id="xlKeyF" ${cs.length ? 'hidden' : ''}><label for="xlKey">Their npub</label><input id="xlKey" class="inp" placeholder="npub1…" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
    <div class="field"><label>If I stop pressing CONTINUE, it opens for them after</label><div class="seg three" role="group" aria-label="Opens after">${EXTRA_PERIODS.map(([d, l]) => `<button type="button" data-act="giftDays" data-days="${d}" aria-pressed="${d === 182}">${l}</button>`).join('')}</div></div>
    <div class="notice">This depends on the mint still running when the date comes, so use a mint you trust for the long term. Your heir needs NUTCADE with Nostr turned on to receive their copy, or you can hand it to them yourself.</div>
    <button class="btn solid gold block" data-act="extraStart">Lock it in</button><div id="sheetErr"></div>`,
    body => { const sel = body.querySelector('#xlTo'); sel.onchange = () => { body.querySelector('#xlKeyF').hidden = !!sel.value; }; return null; });
}
function openHeirCopy() {
  const x = S.extra; if (!x) return;
  const t = extraToken();
  openSheet("Heir's copy", `<p style="margin:0">Give this to ${esc(x.heir.name)} if they didn't get it over Nostr. Nobody can use it before ${fmtDay(x.until)}, and after that only ${esc(x.heir.name)} can. Your next CONTINUE replaces it.</p>
    ${qrBlock(t, "Heir's copy QR")}<div class="row wrap"><button class="btn sm gold" data-act="copy" data-text="${esc(t)}">Copy</button>${ctBtn(t)}<button class="btn sm" data-act="extraOpen">Back</button></div>`);
}

/* ---------- mint report card ----------
   Grades a mint from what NUTCADE can check itself, with no outside rating service:
   uptime and speed from health checks, its track record with your own payments, its age (first seen by you, or
   earliest mention on Nostr), its key history (a changed identity key is a red flag; frequent keyset changes are
   worth knowing) and recommendations on Nostr (NIP-87). */
S.mintlog = store.get('mintlog', {});
const saveMlog = () => store.set('mintlog', S.mintlog);
function mlog(url) { if (!S.mintlog[url]) S.mintlog[url] = { first: Date.now(), pr: '', ms: [], ops: [0, 0], keysets: {}, changes: [] }; return S.mintlog[url]; }
function logProbe(url, h) {
  const l = mlog(url); l.pr = (l.pr + (h.ok ? '1' : '0')).slice(-200);
  if (h.ok && h.ms != null) l.ms = l.ms.concat([h.ms]).slice(-30);
  saveMlog();
}
// only failures that are the mint's fault count against it (it errored or didn't answer), not "not enough sats" and the like
function opMark(url, ok, e) {
  if (!url || !S.mints.find(m => m.url === url)) return;
  if (!ok && !/Failed to fetch|NetworkError|Load failed|timed? ?out|50[0-9]|Internal Server|Bad Gateway|Service Unavailable/i.test(String(e && (e.message || e)) + ' ' + ((e && e.status) || ''))) return;
  const l = mlog(url); l.ops[ok ? 0 : 1]++; saveMlog();
}
const GRADES = ['F', 'D', 'C', 'B', 'A'];
const gradeCls = g => ({ A: 'good', B: 'good', C: 'slow', D: 'slow', F: 'bad' })[g] || 'wait';
async function inspectMint(url) {
  const l = mlog(url), now = Date.now();
  const get = async p => { const ac = new AbortController(); const tm = setTimeout(() => ac.abort(), 7000); try { const r = await fetch(url + p, { cache: 'no-store', signal: ac.signal }); return r.ok ? await r.json() : null; } finally { clearTimeout(tm); } };
  const [info, ks] = await Promise.all([get('/v1/info').catch(() => null), get('/v1/keysets').catch(() => null)]);
  if (info && info.pubkey) {
    if (l.pub && l.pub !== info.pubkey && !(l.pubChanged && l.pubChanged.to === info.pubkey)) l.pubChanged = { from: l.pub, to: info.pubkey, at: now };
    if (!l.pub) l.pub = info.pubkey;
    l.info = { name: info.name || '', version: info.version || '', contact: (info.contact || []).length, motd: info.motd || '', tos: !!info.tos_url, nuts: Object.keys(info.nuts || {}).length };
  }
  if (ks && Array.isArray(ks.keysets)) {
    const had = Object.keys(l.keysets).length;
    for (const k of ks.keysets.filter(k => (k.unit || 'sat') === 'sat')) {
      const old = l.keysets[k.id];
      if (!old) { l.keysets[k.id] = { first: now, active: !!k.active }; if (had) l.changes.push({ at: now, kind: 'new', id: k.id }); }
      else if (old.active && !k.active) { old.active = false; l.changes.push({ at: now, kind: 'retired', id: k.id }); }
      else old.active = !!k.active;
    }
    l.ksTotal = ks.keysets.filter(k => (k.unit || 'sat') === 'sat').length;
    l.changes = l.changes.slice(-20);
  }
  l.checked = now; saveMlog();
  if (!l.nostr || now - l.nostr.at > 86400e3) await nostrRecord(url).catch(() => {});
  return l;
}
// recommendations (kind 38000) and announcements (kind 38172) that name this mint
function nostrRecord(url) {
  return new Promise(resolve => {
    const l = mlog(url), pubs = new Set(), stars = [], seen = new Set(); let since = 0, open = 0, finished = false;
    const variants = [...new Set([url, url + '/', url.replace(/^https:/, 'http:')])];
    const socks = [];
    const done = () => { if (finished) return; finished = true; socks.forEach(s => { try { s.close(); } catch (e) {} });
      l.nostr = { at: Date.now(), recs: pubs.size, stars: stars.slice(0, 50), since: since || null }; saveMlog(); resolve(l.nostr); };
    for (const r of relays().slice(0, 4)) {
      let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
      socks.push(ws); open++;
      ws.onopen = () => ws.send(JSON.stringify(['REQ', 'rc', { kinds: [38000, 38172], '#u': variants, limit: 300 }]));
      ws.onmessage = m => { let d; try { d = JSON.parse(m.data); } catch (e) { return; }
        if (d[0] === 'EVENT' && d[2] && !seen.has(d[2].id)) { const e = d[2]; seen.add(e.id);
          if (!since || e.created_at * 1000 < since) since = e.created_at * 1000;
          if (e.kind === 38000) { pubs.add(e.pubkey); const s = /\[(\d)\/5\]/.exec(e.content || ''); if (s) stars.push(+s[1]); } }
        else if (d[0] === 'EOSE') { try { ws.close(); } catch (e) {} if (--open <= 0) done(); } };
      ws.onerror = () => { if (--open <= 0) done(); };
    }
    if (!socks.length) done();
    setTimeout(done, 6000);
  });
}
function reportCard(url) {
  // each detail is a list of short parts, so every part translates on its own
  const l = mlog(url), now = Date.now(), rows = [];
  const band = (v, cuts) => { for (let i = 0; i < cuts.length; i++) if (v >= cuts[i]) return GRADES[4 - i]; return 'F'; };
  const pl = (n, one, many) => `${fmt(n)} ${n === 1 ? one : many}`;
  // uptime and speed
  const n = l.pr.length, up = n ? [...l.pr].filter(c => c === '1').length / n : 0;
  rows.push({ k: 'Uptime', g: n >= 5 ? band(up * 100, [99, 95, 90, 75]) : '?', d: n >= 5 ? [`${(up * 100).toFixed(up === 1 ? 0 : 1)}% of ${n} checks answered`] : [`Only ${n} checks so far`] });
  const ms = l.ms.slice().sort((a, b) => a - b), med = ms.length ? ms[Math.floor(ms.length / 2)] : null;
  rows.push({ k: 'Speed', g: med == null ? '?' : band(-med, [-500, -1000, -2500, -5000]), d: [med == null ? 'Not measured yet' : `Answers in about ${fmt(med)} ms`] });
  // age
  const viaNostr = !!(l.nostr && l.nostr.since && l.nostr.since < l.first);
  const since = viaNostr ? l.nostr.since : l.first, days = Math.floor((now - since) / 86400e3);
  const ageTxt = days >= 365 ? `Known for ${pl(Math.floor(days / 365), 'year', 'years')}` : days >= 60 ? `Known for ${Math.floor(days / 30)} months` : `Known for ${pl(days, 'day', 'days')}`;
  rows.push({ k: 'Age', g: band(days, [365, 180, 90, 30]), d: [ageTxt, viaNostr ? 'since its first mention on Nostr' : 'since you first used it'] });
  // keys
  const recent = (l.changes || []).filter(c => c.kind === 'new' && now - c.at < 90 * 86400e3).length;
  if (l.pubChanged) rows.push({ k: 'Keys', g: 'F', d: [`Its identity key changed on ${fmtDay(l.pubChanged.at)}. That can mean a new operator, so be careful.`], warn: true });
  else rows.push({ k: 'Keys', g: !l.pub ? '?' : recent === 0 ? 'A' : recent === 1 ? 'B' : recent <= 3 ? 'C' : 'D', d: !l.pub ? ['Not checked yet'] : ['Same identity key since you added it', recent ? `${pl(recent, 'new keyset', 'new keysets')} in 90 days` : 'no key changes in 90 days'].concat(l.ksTotal > 1 ? [`${l.ksTotal} keysets in its history`] : []) });
  // your own audit trail
  const [ok, bad] = l.ops, tot = ok + bad;
  rows.push({ k: 'Track record', g: tot >= 5 ? band(ok / tot * 100, [99, 95, 90, 80]) : '?', d: tot ? [`${ok} of ${tot} of your payments and swaps went through`].concat(bad ? [`${bad} failed on the mint's side`] : []) : ['No payments with it yet'] });
  // community
  const nr = l.nostr;
  const avg = nr && nr.stars.length ? nr.stars.reduce((a, b) => a + b, 0) / nr.stars.length : null;
  rows.push({ k: 'Reviews', g: !nr ? '?' : nr.recs === 0 ? 'D' : avg != null && avg < 3 ? 'D' : band(nr.recs, [10, 5, 2, 1]), d: !nr ? ['Not checked yet'] : nr.recs ? [`Recommended by ${pl(nr.recs, 'Nostr user', 'Nostr users')}`].concat(avg != null ? [`${avg.toFixed(1)}/5 from ${pl(nr.stars.length, 'rating', 'ratings')}`] : []) : ['Nobody recommends it on Nostr yet'] });
  const known = rows.filter(r => r.g !== '?');
  let overall = known.length >= 2 ? GRADES[Math.round(known.reduce((t, r) => t + GRADES.indexOf(r.g), 0) / known.length)] : '?';
  if (l.pubChanged && overall !== '?' && GRADES.indexOf(overall) > 1) overall = 'D';
  return { overall, rows };
}
function reportChip(url) {
  const r = reportCard(url);
  return `<button class="chip grade ${gradeCls(r.overall)}" data-act="reportOpen" data-url="${esc(url)}" title="Report card">GRADE <span data-noi18n>${r.overall}</span></button>`;
}
function openReport(url) {
  const m = S.mints.find(x => x.url === url) || { name: host(url), url };
  const draw = (busy) => {
    const r = reportCard(url), l = mlog(url);
    return `<div class="report"><div class="grade-big ${gradeCls(r.overall)}">${r.overall}</div><div><div class="h2" data-noi18n>${esc(m.name)}</div><div class="tiny muted" data-noi18n>${esc(host(url))}</div>${l.info && l.info.version ? `<div class="tiny muted" data-noi18n>${esc(l.info.version)}</div>` : ''}</div></div>
      <div class="report-rows">${r.rows.map(x => `<div class="rrow ${x.warn ? 'warn' : ''}"><span class="rg ${gradeCls(x.g)}">${x.g}</span><span><b>${x.k}</b><span class="tiny muted">${x.d.map(p => `<span>${p}</span>`).join(' · ')}</span></span></div>`).join('')}</div>
      ${l.info && l.info.motd ? `<div class="notice">Message from the mint: <span data-noi18n>${esc(l.info.motd)}</span></div>` : ''}
      <div class="tiny muted">Graded on this phone from health checks, your own payments with this mint, its keys and Nostr recommendations. A good grade isn't a guarantee: only keep what you can afford to lose at any one mint.</div>
      ${busy ? busyHTML('CHECKING THE MINT') : `<button class="btn sm" data-act="reportOpen" data-url="${esc(url)}" data-fresh="1">Check again</button>`}`;
  };
  openSheet('Report card', draw(true), body => {
    let live = true;
    Promise.all([inspectMint(url), probeHealth(url)]).finally(() => { if (live && body.isConnected) { body.innerHTML = draw(false); } });
    return () => { live = false; };
  });
}
