/* ===================== Round 6: treasure hunts and loaded score cards ===================== */

/* ---------- treasure hunt: sats behind K of N clue cards ----------
   The prize is ecash locked (NUT-11) to a fresh key that nobody holds whole. The key is split with Shamir's secret
   sharing into N clue cards; any K of them rebuild it. The ecash itself waits on Nostr, encrypted with that same key,
   in an event signed by it, so the cards stay short enough to print. Scanning the K-th card rebuilds the key, fetches
   and decrypts the prize, and claims it. If nobody does by the date, the lock's refund path brings it back to you.
   A loaded score card is the same thing with one card: K = N = 1. */
const HUNT_KIND = 30078, HUNT_D = 'nutcade-hunt';
S.hunts = store.get('hunts', []);        // ours: { pub, k, n, amount, note, txId, until, created, cards: [url], loaded? }
S.found = store.get('found', {});        // clues we've scanned: pub -> { k, n, shares: { x: b64 }, state, amount, note }
const saveHunts = () => store.set('hunts', S.hunts.slice(0, 30));
const saveFound = () => store.set('found', S.found);

// Shamir's secret sharing over GF(256), byte by byte (the field AES uses: x^8 + x^4 + x^3 + x + 1)
const GF = (() => {
  const exp = new Uint8Array(512), log = new Uint8Array(256); let x = 1;
  for (let i = 0; i < 255; i++) { exp[i] = x; log[x] = i; x ^= (x << 1) ^ (x & 0x80 ? 0x11b : 0); x &= 255; }
  for (let i = 255; i < 512; i++) exp[i] = exp[i - 255];
  const mul = (a, b) => a && b ? exp[log[a] + log[b]] : 0;
  const div = (a, b) => a ? exp[log[a] + 255 - log[b]] : 0;
  return { mul, div };
})();
function shamirSplit(secret, n, k) {
  const shares = Array.from({ length: n }, (_, i) => ({ x: i + 1, y: new Uint8Array(secret.length) }));
  for (let j = 0; j < secret.length; j++) {
    const coef = [secret[j], ...rnd(k - 1)];
    for (const s of shares) { let y = 0; for (let d = coef.length - 1; d >= 0; d--) y = GF.mul(y, s.x) ^ coef[d]; s.y[j] = y; }
  }
  return shares;
}
function shamirJoin(shares) {
  const len = shares[0].y.length, out = new Uint8Array(len);
  for (let j = 0; j < len; j++) {
    let v = 0;
    for (const a of shares) { let w = 1; for (const b of shares) if (b !== a) w = GF.mul(w, GF.div(b.x, b.x ^ a.x)); v ^= GF.mul(a.y[j], w); }
    out[j] = v;
  }
  return out;
}
const huntBase = () => location.origin + location.pathname;
const cardUrl = (pub, x, k, n, y) => `${huntBase()}#hunt=${pub}.${x}.${k}.${n}.${b64url(y)}`;
async function huntKey(sk) { return crypto.subtle.importKey('raw', await crypto.subtle.digest('SHA-256', new TextEncoder().encode('nutcade-hunt:' + hex(sk))), 'AES-GCM', false, ['encrypt', 'decrypt']); }
async function makeHunt(amount, k, n, days, note, loaded) {
  if (!(n >= 1 && n <= 12 && k >= 1 && k <= n)) throw new Error('Pick 1 to 12 cards, and how many of them open the chest.');
  if (!(await mintCan(S.active, 11))) throw new Error(`${host(S.active)} can't lock ecash to a key (NUT-11). Pick another mint.`);
  // a fresh key whose public key starts with 02, so "02" + its Nostr key is its Cashu lock key too
  let sk; for (;;) { sk = rnd(32); try { if (hex(L.getPubKeyFromPrivKey(sk)).startsWith('02')) break; } catch (e) {} }
  const pub = L.nostrPub(sk), until = Math.floor(Date.now() / 1000 + days * 86400);
  const tx = await sendEcash(amount, note || (loaded ? 'Loaded score card' : 'Treasure hunt'), '02' + pub, S.active, { locktime: until });
  updTx(tx.id, { lockUntil: until * 1000, giftTo: loaded ? 'whoever scans the card' : 'the treasure hunters', hunt: pub });
  // the prize waits on Nostr, encrypted with the key the cards rebuild, in an event that key signs
  const iv = rnd(12), box = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await huntKey(sk), new TextEncoder().encode(txById(tx.id).token)));
  const content = JSON.stringify({ v: 1, k, n, amount, note: String(note || '').slice(0, 140), until: until * 1000, box: b64url(new Uint8Array([...iv, ...box])) });
  const ev = L.finalizeEvent({ kind: HUNT_KIND, created_at: Math.floor(Date.now() / 1000), tags: [['d', HUNT_D], ['t', 'nutcade-hunt'], ['expiration', String(until + 86400)]], content }, sk);
  const ok = await relayPublish(ev, 8000);
  if (!ok) throw new Error(`No Nostr relay took the prize. Your ${money(amount)} stay locked until ${fmtDay(until * 1000)}, then come back to you.`);
  const cards = shamirSplit(sk, n, k).map(s => cardUrl(pub, s.x, k, n, s.y));
  const h = { pub, k, n, amount, note: String(note || ''), txId: tx.id, until: until * 1000, created: Date.now(), cards, loaded: !!loaded };
  S.hunts.unshift(h); saveHunts();
  return h;
}
// a scanned clue card (or a loaded score card)
function readCard(str) {
  const m = /^([0-9a-f]{64})\.(\d{1,2})\.(\d{1,2})\.(\d{1,2})\.([A-Za-z0-9_-]{40,46})$/.exec(String(str || '').trim());
  if (!m) return null;
  const c = { pub: m[1], x: +m[2], k: +m[3], n: +m[4], y: m[5] };
  return c.k >= 1 && c.k <= c.n && c.n <= 12 && c.x >= 1 && c.x <= c.n ? c : null;
}
async function onHuntCard(str) {
  if (needSeed()) return;
  const c = readCard(str); if (!c) { toast("That clue card isn't valid.", 'gold'); return; }
  if (S.hunts.some(h => h.pub === c.pub)) { toast("That's one of your own cards. Hide it well!", 'gold'); return; }
  const f = S.found[c.pub] || (S.found[c.pub] = { k: c.k, n: c.n, shares: {}, state: 'hunting', at: Date.now() });
  const fresh = !f.shares[c.x]; f.shares[c.x] = c.y; saveFound();
  sfx(fresh ? 'coin' : 'blip');
  openHunt(c.pub);
  if (!f.amount) peekHunt(c.pub).then(() => { if ($('#layer [data-hunt]')) openHunt(c.pub); });
  if (Object.keys(f.shares).length >= f.k && f.state === 'hunting') openChest(c.pub);
}
async function fetchHunt(pub) {
  const evs = await relayQuery({ kinds: [HUNT_KIND], authors: [pub], '#d': [HUNT_D], limit: 3 }, 7000);
  const ev = evs.filter(e => { try { return L.verifyEvent(e); } catch (x) { return false; } }).sort((a, b) => b.created_at - a.created_at)[0];
  if (!ev) return null;
  try { return JSON.parse(ev.content); } catch (e) { return null; }
}
async function peekHunt(pub) {   // the prize and note are public, so hunters see what they're after from the first card
  const f = S.found[pub]; if (!f) return;
  const d = await fetchHunt(pub).catch(() => null);
  if (d) { f.amount = num(d.amount); f.note = String(d.note || '').slice(0, 140); f.until = num(d.until); saveFound(); }
}
async function openChest(pub) {
  const f = S.found[pub]; if (!f) return;
  const shares = Object.entries(f.shares).slice(0, f.k).map(([x, y]) => ({ x: +x, y: unb64url(y) }));
  const sk = shamirJoin(shares);
  if (L.nostrPub(sk) !== pub) { f.state = 'bad'; saveFound(); toast("These clue cards don't fit together. One of them may be from another hunt.", 'pink'); openHunt(pub); return; }
  f.state = 'opening'; saveFound(); openHunt(pub);
  try {
    const d = await fetchHunt(pub); if (!d || !d.box) throw new Error("Couldn't find the chest on Nostr relays. Try again in a moment.");
    const raw = unb64url(d.box);
    const token = new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: raw.slice(0, 12) }, await huntKey(sk), raw.slice(12)));
    // the rebuilt key unlocks the prize; keep it with our other unlock keys
    const priv = hex(sk);
    if (!S.p2pk.find(x => x.priv === priv)) { S.p2pk.push({ pub: '02' + pub, priv, created: Date.now() }); store.set('p2pk', S.p2pk); }
    const tx = await receiveToken(token, f.k === 1 && f.n === 1 ? 'Loaded score card' : `Treasure hunt: ${f.k} of ${f.n} clues`);
    f.state = 'won'; f.amount = tx.amount; saveFound();
    sfx('levelup'); celebrate('in', tx.amount); toast(`Treasure! ${money(tx.amount)} is yours`, 'lime'); refresh();
  } catch (e) {
    f.state = /spent/i.test(e.message || '') ? 'gone' : 'hunting'; saveFound();
    if (f.state === 'gone') { sfx('err'); toast('Someone opened this chest first!', 'pink'); }
    else showErr(e);
  }
  openHunt(pub);
}
const CHEST = ['..yyyyyyyy..', '.ybbbbbbbby.', 'ybbbbbbbbbby', 'yyyyyyyyyyyy', 'ybbbbyybbbby', 'ybbbbyybbbby', 'ybbbbbbbbbby', 'yyyyyyyyyyyy'];
const chestSVG = open => `<svg class="chest ${open ? 'open' : ''}" viewBox="0 0 12 8" width="96" height="64" aria-hidden="true">${CHEST.map((r, y) => [...r].map((ch, x) => ch === '.' ? '' : `<rect x="${x}" y="${y}" width="1" height="1" fill="${ch === 'y' ? 'var(--gold)' : open ? '#3a2410' : 'var(--brown,#b8651f)'}"/>`).join('')).join('')}</svg>`;
function openHunt(pub) {
  const f = S.found[pub]; if (!f) return;
  const got = Object.keys(f.shares).length, need = f.k;
  const pips = Array.from({ length: f.n }, (_, i) => `<span class="pip ${f.shares[i + 1] ? 'on' : ''}">${i + 1}</span>`).join('');
  const state = f.state === 'won' ? `<div class="hunt-big lime">TREASURE!</div><div class="tiny">${money(f.amount || 0)} landed in your wallet.</div>`
    : f.state === 'gone' ? '<div class="hunt-big pink">TOO LATE</div><div class="tiny">Someone opened this chest first.</div>'
    : f.state === 'bad' ? '<div class="hunt-big pink">WRONG CARDS</div><div class="tiny">These cards don\'t rebuild the same key.</div>'
    : f.state === 'opening' ? busyHTML('OPENING THE CHEST')
    : `<div class="hunt-big">CLUE ${Math.min(got, need)}/${need}</div><div class="tiny">${got >= need ? 'All the clues you need!' : `Find ${need - got} more clue card${need - got > 1 ? 's' : ''} to open the chest.`}</div>`;
  const body = `<div class="hunt" data-hunt>${chestSVG(f.state === 'won')}${state}
    ${f.n > 1 ? `<div class="pips" aria-label="${got} of ${f.n} cards found">${pips}</div>` : ''}
    ${f.amount ? `<div class="tiny muted">Prize: ${money(f.amount)}${f.until ? ` · until ${fmtDay(f.until)}` : ''}</div>` : ''}${f.note ? `<div class="notice" data-noi18n>${esc(f.note)}</div>` : ''}
    ${f.state === 'hunting' && got >= need ? `<button class="btn solid gold block" data-act="huntOpen" data-pub="${pub}">Open the chest</button>` : ''}
    ${f.state === 'hunting' && got < need ? '<button class="btn block violet" data-act="scan">Scan the next clue</button>' : ''}
    <div id="sheetErr"></div></div>`;
  if ($('#layer [data-hunt]')) setBody(body); else openSheet(f.n === 1 ? 'Loaded card' : 'Treasure hunt', body);
}

/* ---------- making a hunt ---------- */
function openHuntNew() {
  if (needSeed()) return;
  openSheet('Treasure hunt', `
    <div class="hunt">${chestSVG(false)}<div class="tiny">Hide sats behind clue cards. Whoever finds enough of them opens the chest.</div></div>
    <div class="field"><label for="amtIn">Prize (sat)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="2100" autocomplete="off"></div>
    <div class="row" style="gap:10px"><div class="field" style="flex:1"><label for="huntN">Clue cards</label><input id="huntN" class="inp" inputmode="numeric" value="5"></div>
    <div class="field" style="flex:1"><label for="huntK">Needed to open</label><input id="huntK" class="inp" inputmode="numeric" value="3"></div></div>
    <div class="field"><label for="noteIn">Message on every card (optional)</label><input id="noteIn" class="inp" maxlength="140" placeholder="Happy hunting! Clues are hidden around the park."></div>
    <div class="field"><label>Comes back to you after</label><div class="seg three" role="group" aria-label="Comes back after">${GIFT_DAYS.map(([d, l]) => `<button type="button" data-act="giftDays" data-days="${d}" aria-pressed="${d === 7}">${l}</button>`).join('')}</div></div>
    <div class="tiny muted">The prize is locked to a key split across the cards, so no single card can open it, and you can't be cheated by a copied card. It waits on Nostr, encrypted, until someone has enough cards.</div>
    <button class="btn solid gold block" data-act="huntCreate">Hide the treasure</button><div id="sheetErr"></div>`);
}
function huntCardsHTML(h) {
  return `<div class="hunt-cards">${h.cards.map((u, i) => `<div class="hunt-card"><div class="hc-top"><b>CLUE ${i + 1} OF ${h.n}</b><span>${h.k === h.n ? 'You need every card' : `Any ${h.k} open the chest`}</span></div>
    ${qrBlock(u, `Clue card ${i + 1}`)}<div class="hc-prize">${money(h.amount)} TREASURE</div>${h.note ? `<div class="hc-note" data-noi18n>${esc(h.note)}</div>` : ''}<div class="hc-foot">Scan with your phone camera · NUTCADE</div></div>`).join('')}</div>`;
}
function openHuntCards(pub) {
  const h = S.hunts.find(x => x.pub === pub); if (!h) return;
  const t = txById(h.txId), claimed = t && (t.status === 'claimed'), back = t && t.status === 'reclaimed';
  openSheet('Clue cards', `${claimed ? '<div class="notice cyan">Someone opened the chest!</div>' : back ? '<div class="notice">Nobody opened it in time, so the prize came back to you.</div>' : `<div class="tiny">Print the cards and hide them, or show them on screen. Unopened by ${fmtDay(h.until)}, the ${money(h.amount)} comes back to you.</div>`}
    <button class="btn sm gold" data-act="huntPrint">Print cards</button>${huntCardsHTML(h)}`);
}

/* ---------- loaded score cards ---------- */
async function loadCard(amount) {
  const h = await makeHunt(amount, 1, 1, 7, 'Loaded score card', true);
  return { url: h.cards[0], amount, until: h.until, pub: h.pub };
}

function huntsPanel() {
  const mine = S.hunts.filter(h => !h.loaded).slice(0, 4), found = Object.entries(S.found).filter(([, f]) => f.state === 'hunting' || f.state === 'opening').slice(0, 4);
  if (!mine.length && !found.length) return '';
  const st = h => { const t = txById(h.txId); return !t ? '' : t.status === 'claimed' ? '<span class="chip ecash">OPENED</span>' : t.status === 'reclaimed' ? '<span class="chip claimed">CAME BACK</span>' : `<span class="chip pending">${h.k} OF ${h.n}</span>`; };
  return `<div class="panel"><span class="h2">Treasure hunts</span><div class="txs">
    ${mine.map(h => `<button class="tx out" data-act="huntCards" data-pub="${h.pub}"><span class="ico" aria-hidden="true">✦</span><span class="mid"><div class="note">Your hunt</div><div class="meta">${st(h)}</div></span><span class="amt">${fmt(h.amount)}</span></button>`).join('')}
    ${found.map(([pub, f]) => `<button class="tx in" data-act="huntShow" data-pub="${pub}"><span class="ico" aria-hidden="true">?</span><span class="mid"><div class="note">Hunting</div><div class="meta"><span class="chip ln">CLUE ${Object.keys(f.shares).length}/${f.k}</span></div></span><span class="amt">${f.amount ? fmt(f.amount) : '???'}</span></button>`).join('')}
  </div></div>`;
}
