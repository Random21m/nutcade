/* =====================================================================
   Round 4: chiptune transfer, refundable gifts, co-op bill split, mint health,
   cashier mode, high-score challenges, round-up piggy bank
===================================================================== */

/* ---------- chiptune transfer: codes as sound ---------- */
const CT = () => window.Chiptune;
const b64url = u8 => btoa(String.fromCharCode(...u8)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const unb64url = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4)), c => c.charCodeAt(0));
// Sound is slow (about 50 bytes a second), so tokens travel in a compact form only NUTCADE reads: hex secrets and
// signatures as raw bytes, no DLEQ proofs (the receiver swaps the ecash anyway). Anything else is sent as text.
const CT_MAGIC = 0xC1;
function packToken(d) {
  const out = []; const te = new TextEncoder();
  const vint = n => { n = Math.floor(n); do { let b = n % 128; n = Math.floor(n / 128); if (n) b |= 128; out.push(b); } while (n); };
  const str = s => { const b = te.encode(String(s || '')); vint(b.length); out.push(...b); };
  const hexb = h => { for (let i = 0; i < h.length; i += 2) out.push(parseInt(h.slice(i, i + 2), 16)); };
  out.push(CT_MAGIC); str(d.mint); str(d.unit || 'sat'); str(d.memo || '');
  const groups = new Map(); for (const p of d.proofs) { if (!groups.has(p.id)) groups.set(p.id, []); groups.get(p.id).push(p); }
  vint(groups.size);
  for (const [id, ps] of groups) {
    if (!/^[0-9a-f]+$/i.test(id) || id.length % 2) throw new Error('keyset id');
    vint(id.length / 2); hexb(id); vint(ps.length);
    for (const p of ps) {
      const hexSecret = /^[0-9a-f]{64}$/.test(p.secret), C = String(p.C);
      if (!/^0[23][0-9a-f]{64}$/i.test(C)) throw new Error('signature');
      vint(num(p.amount)); out.push((hexSecret ? 0 : 1) | (p.witness ? 2 : 0));
      if (hexSecret) hexb(p.secret); else str(p.secret);
      hexb(C);
      if (p.witness) str(typeof p.witness === 'string' ? p.witness : JSON.stringify(p.witness));
    }
  }
  return new Uint8Array(out);
}
function unpackToken(b) {
  let i = 1; const td = new TextDecoder();
  const vint = () => { let n = 0, m = 1, x; do { x = b[i++]; n += (x & 127) * m; m *= 128; } while (x & 128); return n; };
  const str = () => { const n = vint(); const s = td.decode(b.slice(i, i + n)); i += n; return s; };
  const hexs = n => { const s = hex(b.slice(i, i + n)); i += n; return s; };
  const mint = str(), unit = str(), memo = str(); const proofs = [];
  for (let g = vint(); g > 0; g--) {
    const id = hexs(vint());
    for (let k = vint(); k > 0; k--) {
      const amount = vint(), f = b[i++];
      const secret = f & 1 ? str() : hexs(32); const C = hexs(33);
      const p = { id, amount, secret, C }; if (f & 2) p.witness = str();
      proofs.push(p);
    }
  }
  if (i !== b.length) throw new Error('trailing bytes');
  return L.getEncodedToken(Object.assign({ mint, unit, proofs }, memo ? { memo } : {}));
}
function soundBytes(text) {
  const c = classify(text);
  if (c.kind === 'token') {
    try { const d = L.getDecodedToken(c.value, Object.keys(S.counters)); return packToken({ mint: d.mint, unit: d.unit, memo: d.memo, proofs: d.proofs }); } catch (e) {}
  }
  return new TextEncoder().encode(String(text));
}
function soundText(bytes) {
  if (bytes[0] === CT_MAGIC) return unpackToken(bytes);
  if (bytes.length > 5 && String.fromCharCode(...bytes.slice(0, 5)) === 'crawB') return 'cashuB' + b64url(bytes.slice(5));
  return new TextDecoder().decode(bytes);
}
const ctBtn = (text, label = 'Play as sound', cls = 'btn sm violet') => (CT() && CT().canPlay()) ? `<button class="${cls}" data-act="ctPlay" data-text="${esc(text)}"><svg class="ico-scan" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M2 6h3l4-4v12l-4-4H2zm9-1h1v6h-1zm2-2h1v10h-1z"/></svg>${label}</button>` : '';
const tapeHTML = (state, sub) => `<div class="tape" aria-hidden="true"><div class="tape-stripes"></div><div class="tape-reel l"></div><div class="tape-reel r"></div><div class="tape-win"><b id="ctState">${esc(state)}</b><span id="ctSub">${esc(sub || '')}</span></div></div>`;
function openSoundSend(text) {
  if (!CT() || !CT().canPlay()) { toast("This browser can't play sound here.", 'gold'); return; }
  let bytes; try { bytes = soundBytes(text); } catch (e) { toast(e.message, 'red'); return; }
  let secs = 0; try { secs = CT().seconds(bytes); } catch (e) { toast(e.message, 'red'); return; }
  const kind = classify(text).kind;
  openSheet('Play as sound', `
    ${tapeHTML('LOADING', `${CT().frameCount(bytes)} BLOCKS · ${Math.ceil(secs)} S A PASS`)}
    <div class="meter ct-meter"><i id="ctBar" style="width:0%"></i></div>
    <p style="margin:0">Hold this phone near the other phone. On that phone, open NUTCADE and tap Listen. Turn your volume up.</p>
    <div class="tiny muted">It plays on a loop until you stop it, so a block missed on one pass is caught on the next.</div>${kind === 'token' ? '<div class="tiny muted">Anyone close enough to hear it could catch the token, the same as photographing its QR code.</div>' : ''}
    <button class="btn solid gold block" id="ctToggle">Stop</button>
    <button class="btn block" data-act="close">Done</button>`, body => {
    let raf = 0, on = false;
    const bar = body.querySelector('#ctBar'), st = body.querySelector('#ctState'), btn = body.querySelector('#ctToggle'), tape = body.querySelector('.tape');
    const anim = () => { const p = CT().isPlaying() && on; if (!p) return; const t = (performance.now() - started) / 1000; bar.style.width = ((t % dur) / dur * 100).toFixed(1) + '%'; raf = requestAnimationFrame(anim); };
    let started = 0, dur = secs;
    const start = () => CT().play(bytes, (n, d) => { dur = d; if (n === 1) started = performance.now(); st.textContent = n === 1 ? 'LOADING' : `LOADING · PASS ${n}`; }).then(() => {
      on = true; S.prefs.ctUsed = true; save(); tape.classList.add('on'); btn.textContent = 'Stop'; cancelAnimationFrame(raf); raf = requestAnimationFrame(anim);
    }).catch(() => { st.textContent = 'NO SOUND'; btn.textContent = 'Play'; });
    btn.onclick = () => { if (on) { CT().stop(); on = false; tape.classList.remove('on'); st.textContent = 'STOPPED'; btn.textContent = 'Play'; bar.style.width = '0%'; } else start(); };
    start();
    return () => { cancelAnimationFrame(raf); CT().stop(); };
  });
}
function openListen() {
  if (!CT() || !CT().canListen()) { toast("This browser can't use the microphone here.", 'gold'); return; }
  openSheet('Listen', `
    ${tapeHTML('LISTENING', 'WAITING FOR SOUND')}
    <div class="meter ct-meter"><i id="ctBar" style="width:0%"></i></div>
    <div class="ct-level" aria-hidden="true"><i id="ctLevel"></i></div>
    <p style="margin:0">On the other phone, choose Play as sound and hold it close to this one. NUTCADE only listens while this screen is open.</p>
    <div id="sheetErr"></div>
    <button class="btn block" data-act="close">Cancel</button>`, body => {
    let alive = true, lvlT = 0;
    const st = body.querySelector('#ctState'), sub = body.querySelector('#ctSub'), bar = body.querySelector('#ctBar'), lvl = body.querySelector('#ctLevel'), tape = body.querySelector('.tape');
    CT().listen(bytes => {
      if (!alive) return; alive = false; CT().stop();
      let text = ''; try { text = soundText(bytes); } catch (e) {}
      S.prefs.ctUsed = true; save();
      sfx('levelup'); st.textContent = 'LOADED'; bar.style.width = '100%';
      setTimeout(() => { if (!text) { toast("That sound didn't carry anything NUTCADE can use.", 'gold'); closeSheet(); return; } handleScan(text); }, 350);
    }, (have, total) => { if (!alive) return; st.textContent = 'LOADING'; sub.textContent = `BLOCK ${have} OF ${total}`; bar.style.width = Math.round(have / total * 100) + '%'; tape.classList.add('on'); sfx('tick'); })
      .then(() => { const tick = () => { if (!alive) return; lvl.style.width = Math.min(100, Math.round(CT().level() * 260)) + '%'; lvlT = setTimeout(tick, 120); }; tick(); })
      .catch(e => { alive = false; st.textContent = 'NO MICROPHONE'; sub.textContent = ''; showErr(new Error(/NotAllowed|Permission|denied/i.test((e && e.name) + (e && e.message)) ? 'Microphone blocked. Allow it for this site in your browser settings, then try again.' : "Couldn't start the microphone.")); });
    return () => { alive = false; clearTimeout(lvlT); CT().stop(); };
  });
}

/* ---------- refundable gifts: ecash locked to one person, back to you after a date (NUT-11) ---------- */
// Locks use Nostr-style keys ("02" + x-only key), like cashu.me. Our key is the same Nostr key the Lightning address uses.
const N_ORDER = BigInt('0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141');
function evenPriv(privHex) {   // the private key whose public key starts with 02, so it matches "02" + x
  const pub = hex(L.getPubKeyFromPrivKey(L.hexToBytes(privHex)));
  return pub.startsWith('02') ? privHex : (N_ORDER - BigInt('0x' + privHex)).toString(16).padStart(64, '0');
}
const myLockPub = () => '02' + L.nostrPub(nostrKey());
const myLockPriv = () => evenPriv(hex(nostrKey()));
const allPrivs = () => p2pkPrivs().concat(S.seed ? [myLockPriv()] : []);
function lockPubFrom(v) {
  v = String(v || '').trim();
  if (validPub(v)) return v.toLowerCase();
  const n = parseNostrAddr(v); return n ? '02' + n.pubkey : null;
}
const GIFT_DAYS = [[1, '1 DAY'], [7, '1 WEEK'], [30, '1 MONTH']];
function giftFields() {
  const cs = S.contacts.filter(c => c.pubkey);
  return `<label class="toggle" for="giftOn"><span><span class="tl">Lock it to one person</span><span class="th">Only they can claim it. If they haven't by the date you pick, it comes back to you.</span></span><input id="giftOn" type="checkbox"></label>
    <div id="giftBox" class="gift-box" hidden>
      <div class="field"><label for="giftTo">Who</label><select id="giftTo" class="inp">${cs.map(c => `<option value="${esc(c.id)}" data-noi18n>${esc(c.name)}</option>`).join('')}<option value="">Someone else (paste their key)</option></select></div>
      <div class="field" id="giftKeyF" ${cs.length ? 'hidden' : ''}><label for="giftKey">Their npub or Cashu public key</label><input id="giftKey" class="inp" placeholder="npub1… or 02…" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
      <div class="field"><label>Comes back to you after</label><div class="seg three" role="group" aria-label="Comes back after">${GIFT_DAYS.map(([d, l]) => `<button type="button" data-act="giftDays" data-days="${d}" aria-pressed="${d === 7}">${l}</button>`).join('')}</div></div>
      <div class="tiny muted">They claim it with NUTCADE, or with cashu.me using the same 12 words. Locked ecash can't be sent offline.</div>
    </div>`;
}
const fmtDay = ms => new Date(ms).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: new Date(ms).getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
async function sendGift(amount, note, opts) {
  const pub = opts.pubkey, secs = Math.floor(Date.now() / 1000 + opts.seconds);
  const tx = await sendEcash(amount, note, pub, S.active, { locktime: secs });
  updTx(tx.id, { lockUntil: secs * 1000, giftTo: opts.name || '', contactId: opts.contactId || tx.contactId || null, contactName: opts.name || tx.contactName || '' });
  return txById(tx.id);
}
async function deliverToContact(c, tx) {
  const payload = { mint: tx.mint, unit: 'sat', proofs: tx.sent, memo: tx.note || undefined };
  const list = [...new Set((c.relays || []).concat(relays()))].slice(0, 8);
  const ev = L.nip17.wrapEvent(rnd(32), { publicKey: c.pubkey }, JSON.stringify(payload));
  const ok = await relayPublish(ev, 8000, list);
  updTx(tx.id, { delivered: !!ok });
  return !!ok;
}
async function takeBackGift(t) {
  if (t.lockUntil && Date.now() < t.lockUntil) throw new Error(`This gift is locked to ${t.giftTo || 'them'} until ${fmtDay(t.lockUntil)}. After that you can take it back.`);
  if (await checkClaim(t).catch(() => false)) return 'claimed';
  reclaiming.add(t.id);
  try { await receiveToken(t.token, `Gift came back${t.giftTo ? ' from ' + t.giftTo : ''}`); }
  catch (e) { if (/already spent|spent/i.test(e.message || '')) { updTx(t.id, { status: 'claimed' }); return 'claimed'; } throw e; }
  finally { setTimeout(() => reclaiming.delete(t.id), 5000); }
  updTx(t.id, { status: 'reclaimed' });
  return 'back';
}
async function refundExpiredGifts() {
  let back = 0;
  for (const t of S.txs.filter(t => t.status === 'pending' && t.method === 'ecash' && t.lockUntil && Date.now() > t.lockUntil + 30e3)) {
    try { const r = await takeBackGift(t); if (r === 'back') { back++; toast(t.hunt ? `Nobody opened your treasure in time, so ${money(t.amount)} came back` : t.bounty ? `Nobody won your bounty, so ${money(t.amount)} came back` : `${t.giftTo || 'They'} didn't claim your gift, so ${money(t.amount)} came back`, 'gold'); } } catch (e) {}
  }
  if (back) { sfx('coin'); refresh(); }
  return back;
}

/* ---------- co-op bill split: a payment request with a boss to defeat ---------- */
const BOSS = [
  '....r....r....',
  '...rr....rr...',
  '..rrrrrrrrrr..',
  '.rrwwrrrrwwrr.',
  '.rrwkrrrrkwrr.',
  'rrrrrrrrrrrrrr',
  'rr.rrrrrrrr.rr',
  'rr.rwrwrwrr.rr',
  '...rrrrrrrr...',
  '..rr.r..r.rr..',
  '.rr..r..r..rr.'
];
function bossSVG(hurt, dead) {
  const pal = { r: dead ? 'var(--faint)' : hurt ? 'var(--ink)' : 'var(--pink)', w: dead ? 'var(--void)' : 'var(--ink)', k: 'var(--void)' };
  let out = '';
  BOSS.forEach((row, y) => [...row].forEach((c, x) => { if (c !== '.') out += `<rect x="${x}" y="${y}" width="1" height="1" fill="${pal[c]}"/>`; }));
  return `<svg class="boss-sprite${dead ? ' dead' : ''}" viewBox="-1 -1 16 13" shape-rendering="crispEdges" aria-hidden="true">${out}</svg>`;
}
const splitOf = r => r && r.split;
// each payment counts as what the friend sent (before the mint's swap fee), up to one share
const hitOf = (r, x) => Math.min(r.split.share, num(x.amount) + num(x.fee));
const splitGot = r => r.paid.map(txById).filter(Boolean).reduce((t, x) => t + hitOf(r, x), 0);
const splitLeft = r => Math.max(0, r.split.need - splitGot(r));
const splitOpen = () => S.requests.filter(r => r.split && splitLeft(r) > 0 && Date.now() - r.created < 14 * 86400e3);
function openSplit() {
  if (needSeed()) return;
  openSheet('Split a bill', `
    <p style="margin:0">Paid for the group? Turn the bill into a boss. Each friend pays their share from any Cashu wallet, and every payment knocks off some of its health.</p>
    <div class="field"><label for="amtIn">Bill total (sat)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="40000" autocomplete="off"></div>
    <div class="field"><label for="splitN">People, including you</label><input id="splitN" class="inp" type="number" inputmode="numeric" min="2" max="30" value="4"></div>
    <div class="field"><label for="memoIn">What it's for (friends see this)</label><input id="memoIn" class="inp" maxlength="80" placeholder="Pizza night"></div>
    ${S.mints.length ? `<label class="toggle" for="onlyMine"><span><span class="tl">Only from my mints</span><span class="th">Friends must pay with ecash from a mint you use.</span></span><input id="onlyMine" type="checkbox" checked></label>` : ''}
    <button class="btn solid gold block" data-act="splitCreate">Summon the boss</button>
    <div id="sheetErr"></div>`);
}
function splitHTML(r, hurt) {
  const sp = r.split, left = splitLeft(r), dead = left === 0, pct = Math.round(left / sp.need * 100);
  const hits = r.paid.map(txById).filter(Boolean);
  return `<div class="boss ${dead ? 'won' : ''}">
      <div class="boss-name">${dead ? 'BOSS DEFEATED!' : 'BILL BOSS'}</div>
      ${bossSVG(hurt, dead)}
      <div class="boss-memo" data-noi18n>${esc(r.memo || '')}</div>
      <div class="hp"><span>HP</span><div class="hpbar" role="progressbar" aria-label="Amount still to collect" aria-valuemin="0" aria-valuemax="${sp.need}" aria-valuenow="${left}"><i style="width:${pct}%"></i></div><span>${fmt(left)}</span></div>
      ${hits.length ? `<ol class="hits">${hits.map((t, i) => `<li><b data-noi18n>P${i + 2}</b><span>HIT FOR ${fmt(hitOf(r, t))}</span></li>`).join('')}</ol>` : ''}
    </div>
    ${dead ? `<div class="notice cyan" style="text-align:center">Everyone paid their share: ${money(splitGot(r))} collected.</div><button class="btn solid gold block" data-act="close">Victory!</button>`
    : `<div class="tiny muted" style="text-align:center">${fmt(sp.total)} total · ${sp.people} players, you included</div><div class="split-share"><span>Each friend pays</span><b>${money(sp.share)}</b></div>
    ${qrBlock(r.encoded, 'Payment request QR')}
    <div class="row wrap" style="justify-content:center"><button class="btn sm" data-act="copy" data-text="${esc(r.encoded)}">Copy request</button>${ctBtn(r.encoded)}${nfcBtn('nfcWrite', 'Write to NFC', `data-text="${esc(r.encoded)}"`)}</div>
    <div class="tiny muted">Friends scan this with NUTCADE, cashu.me or another Cashu wallet. Their ecash comes straight to you over Nostr.</div>
    <button class="btn block" data-act="close">Close</button>`}`;
}
function showSplit(r) {
  let gotBefore = splitGot(r);
  openSheet('Split a bill', splitHTML(r), () => {
    dmListen();
    const on = e => {
      if (!e.detail || e.detail.id !== r.id) return;
      const now = splitGot(r); const dead = splitLeft(r) === 0;
      // redraw in place: setBody would also drop this listener, and the boss would stop reacting to later payments
      const body = document.querySelector('#layer .sheet-body'); if (body) body.innerHTML = splitHTML(r, !dead);
      if (dead) { sfx('levelup'); celebrate('in', now); } else { sfx('hit'); setTimeout(() => { const s = document.querySelector('.boss-sprite'); if (s && !dead) s.outerHTML = bossSVG(false, false); }, 260); }
      gotBefore = now;
    };
    document.addEventListener('nutcade:request', on);
    return () => document.removeEventListener('nutcade:request', on);
  });
}
function splitPanels() {
  return splitOpen().slice(0, 3).map(r => `<button class="panel boss-mini" data-act="splitShow" data-id="${esc(r.id)}"><span class="row between"><span class="h2" style="color:var(--pink)">Bill boss</span><span class="tiny muted">${r.paid.length}/${r.split.people - 1} paid</span></span><span class="tiny" data-noi18n>${esc(r.memo || '')}</span><span class="hp"><span>HP</span><span class="hpbar"><i style="width:${Math.round(splitLeft(r) / r.split.need * 100)}%"></i></span><span>${fmt(splitLeft(r))}</span></span></button>`).join('');
}

/* ---------- mint health: spread, response times, warnings, moving sats ---------- */
const health = {};   // url -> { ok, ms, at }
let healthBusy = false;
async function probeHealth(url) {
  const t0 = performance.now();
  try {
    const ac = new AbortController(); const tm = setTimeout(() => ac.abort(), 6000);
    const r = await fetch(url + '/v1/info', { cache: 'no-store', signal: ac.signal }); clearTimeout(tm);
    health[url] = { ok: r.ok, ms: Math.round(performance.now() - t0), at: Date.now() };
  } catch (e) { health[url] = { ok: false, ms: null, at: Date.now() }; }
  logProbe(url, health[url]);
  return health[url];
}
async function checkHealth() {
  if (healthBusy || isOffline()) return; healthBusy = true;
  try { await Promise.all(S.mints.map(m => probeHealth(m.url))); } finally { healthBusy = false; }
  if (tab === 'mints' && !$('#layer .sheet')) refresh();
}
const SPREAD_COLS = ['var(--gold)', 'var(--cyan)', 'var(--pink)', 'var(--lime)', 'var(--violet)', 'var(--red)'];
function healthOf(url) {
  const h = health[url];
  if (!h) return { cls: 'wait', label: 'CHECKING' };
  if (!h.ok) return { cls: 'bad', label: 'NOT ANSWERING' };
  if (h.ms > 2500) return { cls: 'slow', label: `SLOW · ${fmt(h.ms)} MS` };
  return { cls: 'good', label: `ONLINE · ${fmt(h.ms)} MS` };
}
function evenOut() {   // biggest mint down toward half, into the healthiest other mint that can take Lightning
  const tot = totalBalance(); if (S.mints.length < 2 || tot < 1000) return null;
  const by = S.mints.map(m => ({ m, bal: balanceOf(m.url) })).sort((a, b) => b.bal - a.bal);
  const top = by[0]; if (top.bal / tot <= 0.6 || !supports(top.m, 'melt', 'bolt11')) return null;
  const to = by.slice(1).filter(x => supports(x.m, 'mint', 'bolt11') && (!health[x.m.url] || health[x.m.url].ok)).sort((a, b) => a.bal - b.bal)[0];
  if (!to) return null;
  const amount = Math.floor(top.bal - tot / 2);
  return amount >= 10 ? { from: top.m.url, to: to.m.url, amount } : null;
}
function healthPanel() {
  if (!S.mints.length) return '';
  const tot = totalBalance();
  const rows = S.mints.map((m, i) => ({ m, bal: balanceOf(m.url), col: SPREAD_COLS[i % SPREAD_COLS.length] }));
  const notes = [];
  for (const r of rows) if (r.bal > 0 && health[r.m.url] && !health[r.m.url].ok) notes.push(`<div class="notice red">${esc(r.m.name)} isn't answering and holds ${money(r.bal)}. If it stays down, those sats are stuck until it's back. Move them once it answers again.</div>`);
  const top = rows.slice().sort((a, b) => b.bal - a.bal)[0];
  const share = tot ? top.bal / tot : 0;
  const ev = evenOut();
  if (tot >= 1000 && rows.length > 1 && share > 0.6) notes.push(`<div class="notice">${Math.round(share * 100)}% of your sats are at ${esc(top.m.name)}. Spreading them out means one mint going down can't take everything.</div>${ev ? `<button class="btn block violet" data-act="moveOpen" data-from="${esc(ev.from)}" data-to="${esc(ev.to)}" data-amt="${ev.amount}">Even out: move ${money(ev.amount)}</button>` : ''}`);
  else if (rows.length === 1 && tot >= 20000) notes.push(`<div class="notice">All your sats are at one mint. Adding a second mint and moving some there spreads the risk.</div><button class="btn block gold" data-act="pickMint">Add a mint</button>`);
  if (!notes.length) notes.push(Object.keys(health).length ? '<div class="notice cyan">Looking good: your mints are answering and no single mint holds most of your sats.</div>' : '');
  return `<div class="panel" id="mintHealth">
    <div class="row between"><span class="h2">Mint health</span><button class="btn sm" data-act="healthCheck">${healthBusy ? 'Checking…' : 'Check now'}</button></div>
    ${tot ? `<div class="spread" role="img" aria-label="How your sats are spread across mints">${rows.filter(r => r.bal).map(r => `<i style="flex:${r.bal};background:${r.col}"></i>`).join('')}</div>
    <div class="legend" data-noi18n>${rows.filter(r => r.bal).map(r => `<span><i style="background:${r.col}"></i>${esc(r.m.name)} ${Math.round(r.bal / tot * 100)}%</span>`).join('')}</div>` : '<div class="tiny muted">No sats yet. Health checks still show which mints answer.</div>'}
    ${notes.join('')}
    ${rows.filter(r => r.bal).length && S.mints.length > 1 ? '<button class="btn sm" data-act="moveOpen">Move sats between mints</button>' : ''}
  </div>`;
}
function mintHealthLine(m) {
  const h = healthOf(m.url);
  return `<div class="tiny health ${h.cls}"><span class="dot ${h.cls === 'bad' ? 'off' : ''}"></span><span>${h.label}</span>${health[m.url] ? `<span class="muted">${timeAgo(health[m.url].at)}</span>` : ''}</div>`;
}
function openMove(from, to, amount) {
  const src = S.mints.filter(m => balanceOf(m.url) > 0 && supports(m, 'melt', 'bolt11'));
  const dst = S.mints.filter(m => supports(m, 'mint', 'bolt11'));
  if (!src.length || dst.length < 2) { toast('Moving sats needs two mints that both handle Lightning.', 'gold'); return; }
  from = from || src.slice().sort((a, b) => balanceOf(b.url) - balanceOf(a.url))[0].url;
  to = to || (dst.find(m => m.url !== from) || {}).url;
  openSheet('Move sats', `
    <p style="margin:0">Moves sats from one of your mints to another over Lightning. The sending mint charges a small Lightning fee, shown before you confirm.</p>
    <div class="field"><label for="mvFrom">From</label><select id="mvFrom" class="inp">${src.map(m => `<option value="${esc(m.url)}" ${m.url === from ? 'selected' : ''} data-noi18n>${esc(m.name)} · ${fmt(balanceOf(m.url))}</option>`).join('')}</select></div>
    <div class="field"><label for="mvTo">To</label><select id="mvTo" class="inp">${dst.map(m => `<option value="${esc(m.url)}" ${m.url === to ? 'selected' : ''} data-noi18n>${esc(m.name)} · ${fmt(balanceOf(m.url))}</option>`).join('')}</select></div>
    <div class="field"><label for="amtIn">Amount (sat)</label><input id="amtIn" class="inp amount" inputmode="numeric" value="${amount ? esc(amount) : ''}" placeholder="5000" autocomplete="off"></div>
    <button class="btn solid gold block" data-act="moveQuote">Get quote</button>
    <div id="sheetErr"></div>`);
}
async function moveQuote(from, to, amount) {
  if (from === to) throw new Error('Pick two different mints.');
  const wTo = await getWallet(to), wFrom = await getWallet(from);
  const mintQ = await wTo.createMintQuoteBolt11(amount);
  const mq = await wFrom.createMeltQuoteBolt11(mintQ.request);
  const need = num(mq.amount) + num(mq.fee_reserve);
  if (balanceOf(from) < need) throw new Error(`${(S.mints.find(m => m.url === from) || {}).name || host(from)} holds ${money(balanceOf(from))}, not enough for ${money(amount)} plus up to ${money(num(mq.fee_reserve))} in fees. Try ${money(Math.max(1, balanceOf(from) - num(mq.fee_reserve) - 2))}.`);
  return { from, to, amount, mintQ, mq };
}
async function doMove(mv) {
  const nm = u => (S.mints.find(m => m.url === u) || {}).name || host(u);
  // the receiving side is recorded first, so if NUTCADE closes mid-move the deposit is still claimed later
  const inTx = addTx({ type: 'in', method: 'ln', amount: mv.amount, mint: mv.to, note: `Moved from ${nm(mv.from)}`, status: 'pending', request: mv.mintQ.request, quote: mv.mintQ.quote, move: true });
  const q = { kind: 'bolt11', quote: mv.mintQ.quote, request: mv.mintQ.request, amount: mv.amount, mint: mv.to, txId: inTx.id, expiry: mv.mintQ.expiry || null };
  S.quotes.push(q); save();
  internalMove = true;
  let out; try { out = await payMelt('ln', mv.mq, 0, `Moved to ${nm(mv.to)}`, mv.mintQ.request, mv.from); } finally { internalMove = false; }
  updTx(out.id, { move: true });
  if (out.status === 'failed') return { ok: false };
  for (let i = 0; i < 30; i++) { const r = await checkQuote(q).catch(() => null); if (r === 'paid') return { ok: true, fee: num(txById(out.id).fee) }; await sleep(1500); }
  return { ok: true, waiting: true };
}

/* ---------- CSV export (all transactions, or one day's sales) ---------- */
function exportCsv(list, name) {
    const q = v => { v = v == null ? '' : String(v); if (/^[=+\-@\t\r]/.test(v)) v = "'" + v; return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    const head = ['date', 'direction', 'method', 'amount_sat', 'fee_sat', 'status', 'mint', 'note', 'tags', 'contact', 'fiat_currency', 'btc_price', 'fiat_value'];
    const rows = list.map(t => [new Date(t.ts).toISOString(), t.type === 'in' ? 'received' : 'sent', { ln: 'lightning', ecash: 'ecash', onchain: 'on-chain' }[t.method] || t.method, t.amount || 0, t.fee || 0, t.status, t.mint, t.note || '', tagsOf(t.note).join(' '), t.contactName || '', t.fx ? t.fx.cur : '', t.fx ? t.fx.rate : '', t.fx && t.amount ? (t.amount / 1e8 * t.fx.rate).toFixed(2) : '']);
    const text = '\ufeff' + [head, ...rows].map(r => r.map(q).join(',')).join('\r\n');
    try {
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
      a.download = name; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000); toast(`Exported ${list.length} transactions`, 'lime');
    } catch (e) { toast("Couldn't save the file here.", 'red'); }
  }

/* ---------- cashier mode: a full-screen till for selling things ---------- */
const cash = { el: null, amount: '', unit: 'sat', label: '', mode: 'keys', method: 'ln', tx: null, req: null, poll: 0, holdT: 0, back: 0 };
const sameDay = (a, b) => new Date(a).toDateString() === new Date(b).toDateString();
const todaysSales = () => S.txs.filter(t => t.cashier && t.status === 'done' && sameDay(t.ts, Date.now()));
function cashSats() {
  const v = cash.amount; if (!v) return 0;
  if (cash.unit === 'fiat') { if (!canFiat()) return 0; return Math.round(parseFloat(v) / price.rate * 1e8) || 0; }
  return parseInt(v, 10) || 0;
}
function openCashier() {
  if (needMint()) return;
  closeSheet();
  if (!cash.el) { cash.el = document.createElement('div'); cash.el.className = 'cashier'; cash.el.setAttribute('role', 'dialog'); cash.el.setAttribute('aria-label', 'Cashier mode'); document.body.appendChild(cash.el); cash.el.addEventListener('click', cashierClick); }
  document.body.style.overflow = 'hidden';
  if (window.NutAudio) window.NutAudio.stopMusic();
  const m = activeMint();
  cash.method = supports(m, 'mint', 'bolt11') ? 'ln' : 'ecash';
  cash.mode = 'keys'; cash.amount = ''; cash.label = ''; cash.unit = S.prefs.amtFiat && canFiat() ? 'fiat' : 'sat';
  cashierRender();
}
function cashierTop() {
  const s = todaysSales(), tot = s.reduce((t, x) => t + num(x.amount), 0);
  return `<div class="cash-top"><button class="btn sm red" id="cashExit">Hold to exit</button><div class="cash-title">CASHIER</div><div class="cash-today"><span>TODAY</span><b>${fmt(tot)}</b><span>${s.length} SALE${s.length === 1 ? '' : 'S'}</span></div></div>`;
}
function cashierRender() {
  if (!cash.el) return;
  const m = activeMint();
  const curLabel = cash.unit === 'fiat' ? S.prefs.currency : 'SAT';
  let body = '';
  if (cash.mode === 'keys') {
    const sats = cashSats();
    const shown = cash.amount ? (cash.unit === 'fiat' ? cash.amount : fmt(cash.amount)) : '0';
    body = `<div class="cash-display"><div class="cash-amt" data-noi18n>${esc(shown)}<small>${esc(curLabel)}</small></div>
      <div class="cash-conv tiny muted">${cash.unit === 'fiat' ? (sats ? '≈ ' + money(sats) : '') : (sats && fiatOf(sats) ? '≈ ' + fiatOf(sats) : '')}</div>
      <input id="cashLabel" class="inp cash-label" maxlength="60" placeholder="Item (optional)" value="${esc(cash.label)}" autocomplete="off"></div>
      <div class="cash-keys">${['1', '2', '3', '4', '5', '6', '7', '8', '9', cash.unit === 'fiat' ? '.' : '00', '0', 'del'].map(k => `<button class="ck" data-ck="${k}" aria-label="${k === 'del' ? 'Delete' : k}">${k === 'del' ? '⌫' : k}</button>`).join('')}</div>
      <div class="cash-row"><button class="btn sm" data-ck="unit" data-noi18n ${canFiat() ? '' : 'disabled'}>${cash.unit === 'fiat' ? 'SAT' : esc(S.prefs.currency)}</button>
        <div class="seg cash-method" role="group" aria-label="Payment method"><button data-ck="m-ln" aria-pressed="${cash.method === 'ln'}" ${supports(m, 'mint', 'bolt11') ? '' : 'disabled'}>LIGHTNING</button><button data-ck="m-ecash" aria-pressed="${cash.method === 'ecash'}">ECASH</button></div>
        <button class="btn sm" data-ck="clear">Clear</button></div>
      <button class="btn solid lime block cash-charge" data-ck="charge" ${sats ? '' : 'disabled'}>Charge ${sats ? money(sats) : ''}</button>
      <div class="row" style="justify-content:center;gap:10px;flex-wrap:wrap"><span class="tiny muted">Into ${esc(m.name)}</span><button class="linkbtn tiny" data-ck="close">Close the till</button></div>`;
  } else if (cash.mode === 'charge') {
    const amtNow = cash.tx ? cash.tx.amount : cash.req.amount;
    const code = cash.tx ? 'lightning:' + cash.tx.request.toUpperCase() : cash.req.encoded;
    body = `<div class="cash-pay"><div class="label" style="text-align:center">${cash.label ? esc(cash.label) : 'Scan to pay'}</div>
      <div class="cash-amt" style="font-size:clamp(28px,9vw,44px)" data-noi18n>${fmt(amtNow)}<small>SAT</small></div>${fiatOf(amtNow) ? `<div class="tiny muted" style="text-align:center">≈ ${fiatOf(amtNow)}</div>` : ''}
      ${qrBlock(code, cash.tx ? 'Lightning invoice QR' : 'Ecash payment request QR')}
      <div class="tiny muted" style="text-align:center">${cash.tx ? 'Any Lightning wallet' : 'Any Cashu wallet, ecash from your mints only'}</div>
      <div class="row" style="justify-content:center"><span class="spinner">WAITING FOR COIN</span></div>
      <div class="row" style="justify-content:center;gap:10px">${ctBtn(cash.tx ? cash.tx.request : cash.req.encoded, 'Play as sound', 'btn sm violet')}<button class="btn sm red" data-ck="cancel">Cancel</button></div></div>`;
  } else if (cash.mode === 'paid') {
    body = `<div class="cash-paid"><div class="cash-big">PAID!</div><div class="cash-amt" data-noi18n>+${fmt(cash.paidAmt)}<small>SAT</small></div><div class="tiny muted">${cash.label ? esc(cash.label) : 'Sale complete'}</div><button class="btn solid gold block" data-ck="next">Next customer</button></div>`;
  }
  cash.el.innerHTML = `${cashierTop()}<div class="cash-body">${body}</div>`;
  const ex = cash.el.querySelector('#cashExit');
  const startHold = e => { e.preventDefault(); ex.classList.add('holding'); cash.holdT = setTimeout(() => closeCashier(), 900); };
  const endHold = () => { ex.classList.remove('holding'); clearTimeout(cash.holdT); };
  ex.addEventListener('pointerdown', startHold); ex.addEventListener('pointerup', endHold); ex.addEventListener('pointerleave', endHold); ex.addEventListener('pointercancel', endHold);
  ex.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') closeCashier(); });
  const lab = cash.el.querySelector('#cashLabel'); if (lab) lab.addEventListener('input', () => { cash.label = lab.value; });
  if (window.Nutcade && LANG !== 'en') trNode(cash.el);
}
function cashierClick(e) {
  const b = e.target.closest('[data-ck]'); if (!b || b.disabled) return;
  const k = b.dataset.ck;
  if (/^[0-9]$|^00$|^\.$/.test(k)) {
    if (cash.unit === 'fiat') { if (k === '.' && cash.amount.includes('.')) return; if (/\.\d\d$/.test(cash.amount)) return; }
    const next = (cash.amount === '0' && k !== '.' ? '' : cash.amount) + k;
    if (next.replace('.', '').length > 9) return;
    cash.amount = cash.unit === 'sat' ? String(parseInt(next, 10) || '') : next.replace(/^\./, '0.');
    sfx('blip'); return cashierRender();
  }
  if (k === 'del') { cash.amount = cash.amount.slice(0, -1); sfx('blip'); return cashierRender(); }
  if (k === 'clear') { cash.amount = ''; cash.label = ''; return cashierRender(); }
  if (k === 'unit') { if (!canFiat()) return; const n = cashSats(); cash.unit = cash.unit === 'fiat' ? 'sat' : 'fiat'; cash.amount = n ? (cash.unit === 'fiat' ? (n / 1e8 * price.rate).toFixed(2) : String(n)) : ''; return cashierRender(); }
  if (k === 'm-ln' || k === 'm-ecash') { cash.method = k.slice(2); sfx('select'); return cashierRender(); }
  if (k === 'charge') return cashierCharge(b);
  if (k === 'cancel') { cashierStopWatch(); if (cash.tx) updTx(cash.tx.id, { note: (cash.tx.note || '') + ' (cancelled at the till)' }); cash.mode = 'keys'; cash.tx = null; cash.req = null; return cashierRender(); }
  if (k === 'next') { cash.mode = 'keys'; cash.amount = ''; cash.label = ''; return cashierRender(); }
  if (k === 'close') { closeCashier(); openTill(); }
}
function cashierStopWatch() { cash.watch = false; clearTimeout(cash.poll); clearTimeout(cash.back); document.removeEventListener('nutcade:paid', cashOnPaid); document.removeEventListener('nutcade:request', cashOnReq); }
function cashOnPaid(e) { if (cash.tx && e.detail === cash.tx.quote) cashierPaid(cash.tx.id); }
function cashOnReq(e) {
  if (!cash.req || !e.detail || e.detail.id !== cash.req.id) return;
  const t = cash.req.paid.map(txById).filter(Boolean).pop(); if (t) cashierPaid(t.id);
}
function cashierPaid(txId) {
  const t = txById(txId); if (!t || cash.mode !== 'charge') return;
  cashierStopWatch();
  updTx(t.id, { cashier: true, note: `Sale${cash.label ? ': ' + cash.label : ''} #cashier` });
  cash.paidAmt = t.amount; cash.mode = 'paid'; cash.tx = null; cash.req = null;
  sfx('levelup'); celebrate('in', t.amount); cashierRender();
  cash.back = setTimeout(() => { if (cash.mode === 'paid' && cash.el) { cash.mode = 'keys'; cash.amount = ''; cash.label = ''; cashierRender(); } }, 6000);
}
async function cashierCharge(btn) {
  const sats = cashSats(); if (!sats) return;
  btn.disabled = true; btn.innerHTML = '<span class="spinner">ASKING MINT</span>';
  try {
    const note = `Sale${cash.label ? ': ' + cash.label : ''} #cashier`;
    if (cash.method === 'ln') { cash.tx = await lnMintQuote(sats, note); updTx(cash.tx.id, { cashierPending: true }); cash.req = null; }
    else { cash.req = newRequest(sats, cash.label || 'NUTCADE till', true); cash.req.cashier = true; store.set('requests', S.requests); cash.tx = null; }
    cash.mode = 'charge'; sfx('select'); cashierRender();
    cash.watch = true;
    document.addEventListener('nutcade:paid', cashOnPaid); document.addEventListener('nutcade:request', cashOnReq);
    if (cash.tx) {
      liveSync();
      const q = S.quotes.find(x => x.quote === cash.tx.quote);
      const poll = async () => { if (!cash.watch || !q) return; try { const r = await checkQuote(q); if (r === 'paid') { cashierPaid(q.txId); return; } } catch (e) {} cash.poll = setTimeout(poll, 2500); };
      cash.poll = setTimeout(poll, 1500);
    } else dmListen();
  } catch (e) { sfx('err'); toast(friendly(e, S.active).message, 'red'); cashierRender(); }
}
function closeCashier() {
  cashierStopWatch();
  if (cash.el) { cash.el.remove(); cash.el = null; }
  document.body.style.overflow = '';
  refresh();
}
function openTill() {
  const s = todaysSales(), tot = s.reduce((t, x) => t + num(x.amount), 0);
  openSheet("Today's till", `
    <div class="credit-num" style="font-size:30px;text-align:center">${fmt(tot)}<small>${unitTag()}</small></div>
    ${fiatOf(tot) ? `<div class="tiny muted" style="text-align:center">≈ ${fiatOf(tot)}</div>` : ''}
    <div class="tiny muted" style="text-align:center">${s.length} sale${s.length === 1 ? '' : 's'} today</div>
    ${s.length ? `<div class="txs">${s.map(txRow).join('')}</div>` : '<div class="empty-state"><b>NO SALES YET</b>Sales you take in cashier mode add up here.</div>'}
    <div class="row wrap">${s.length ? '<button class="btn sm" data-act="tillCsv">Export today as CSV</button>' : ''}<button class="btn sm gold" data-act="cashier">Open cashier</button></div>
    <button class="btn block" data-act="close">Done</button>`);
}

/* ---------- high-score challenges, signed with your NUTCADE key ---------- */
const CHAL_KIND = 20078;   // never published on its own: travels in a link or inside a private Nostr message
S.challenges = store.get('challenges', []);
const saveChallenges = () => { S.challenges = S.challenges.slice(0, 30); store.set('challenges', S.challenges); };
const gameById = id => window.Arcade && window.Arcade.games.find(g => g.id === id);
const pad6 = v => String(Math.max(0, Math.floor(v))).padStart(6, '0');
function signChallenge(body) {
  return L.finalizeEvent({ kind: CHAL_KIND, created_at: Math.floor(Date.now() / 1000), tags: [['t', 'nutcade']], content: JSON.stringify(body) }, nostrKey());
}
function readSigned(ev) {
  if (!ev || ev.kind !== CHAL_KIND || typeof ev.content !== 'string' || !L.verifyEvent(ev)) throw new Error("That challenge isn't valid.");
  const c = JSON.parse(ev.content);
  return Object.assign(c, { pubkey: ev.pubkey });
}
// a short replay rides along in the link; a long one only travels over Nostr (the link still works, without the ghost)
const challengeLink = (ev, replay) => location.origin + location.pathname + '#challenge=' + b64url(new TextEncoder().encode(JSON.stringify(ev))) + (replay && replay.length <= 6000 ? '&r=' + replay : '');
const replayHash = r => hex(L.sha256(new TextEncoder().encode(String(r))));
// replay a score on this phone; true when the replay reaches exactly the claimed score from the challenge's seed
async function checkReplay(game, seed, replay, score) { if (!replay || !window.Arcade || !Arcade.replay) return false; try { return (await Arcade.replay.verify(game, seed, replay, score)).ok; } catch (e) { return false; } }
function nameFor(pub) { const c = S.contacts.find(x => x.pubkey === pub); return c ? c.name : ''; }
function startChallenge(o) {   // called by the arcade after a game with a score
  if (!S.seed) return;
  const body = { v: 1, id: hex(rnd(6)), game: o.game, seed: o.seed >>> 0, score: Math.floor(o.score), by: String(o.by || 'AAA').slice(0, 3) };
  if (o.replay) body.rh = replayHash(o.replay);   // the signature covers the replay through its hash
  const ev = signChallenge(body);
  const c = readSigned(ev);
  S.challenges.unshift(Object.assign({ dir: 'out', id: c.id, game: c.game, seed: c.seed, score: c.score, by: c.by, at: Date.now(), ev, results: [] }, o.replay ? { replay: o.replay } : {})); saveChallenges();
  openChallengeSend(c.id);
}
function openChallengeSend(id) {
  const c = S.challenges.find(x => x.id === id && x.dir === 'out'); if (!c) return;
  const g = gameById(c.game); const link = challengeLink(c.ev, c.replay);
  const cs = S.contacts.filter(x => x.pubkey);
  openSheet('Challenge a friend', `
    <div class="chal-card"><span class="label">Beat my score</span><b>${pad6(c.score)}</b><span data-noi18n>${esc(g ? g.name : c.game)} · ${esc(c.by)}</span></div>
    <p style="margin:0">Your friend plays the same seed, so their game starts on the same layout as yours. The challenge is signed with your NUTCADE key.</p>
    ${c.replay ? '<div class="tiny muted">Your replay goes with it: their NUTCADE checks your score is real, and they race your ghost.</div>' : ''}
    ${(c.bounties || []).map(b => `<div class="notice ${b.state === 'open' ? '' : 'cyan'}"><span data-noi18n>${esc(b.name)}</span>: ${money(b.amount)} bounty · ${b.state === 'open' ? (Date.now() < b.until ? `open until ${fmtDay(b.until)}` : 'expired, coming back to you') : `won with ${pad6(b.score || 0)}`}</div>`).join('')}
    ${cs.length ? bountyField() : ''}
    ${cs.length ? `<div class="field"><label>Send to a contact over Nostr</label><div class="tagrow">${cs.map(x => `<button class="tag" data-act="chalSend" data-id="${esc(c.id)}" data-c="${esc(x.id)}">${esc(x.name)}</button>`).join('')}</div></div>` : '<div class="tiny muted">Add friends with a Nostr address in Contacts to send challenges straight to their NUTCADE.</div>'}
    <div class="field"><label>Or share a link</label><div class="code">${esc(link)}</div></div>
    <div class="row wrap"><button class="btn sm gold" data-act="copy" data-text="${esc(link)}">Copy link</button>${navigator.share ? `<button class="btn sm" data-act="chalShare" data-id="${esc(c.id)}">Share</button>` : ''}<button class="btn sm violet" data-act="chalQR" data-id="${esc(c.id)}">Show QR</button></div>
    <div id="sheetErr"></div>`);
}
function onChallenge(ev, via, bounty, from, replay) {
  let c; try { c = readSigned(ev); } catch (e) { return null; }
  if (!gameById(c.game) || !Number.isFinite(c.score) || !Number.isFinite(c.seed) || !c.id) return null;
  if (c.pubkey === L.nostrPub(nostrKey())) return S.challenges.find(x => x.id === c.id) || null;   // our own link
  let rec = S.challenges.find(x => x.id === c.id && x.dir === 'in');
  if (!rec) {
    rec = { dir: 'in', id: String(c.id).slice(0, 24), game: c.game, seed: c.seed >>> 0, score: Math.max(0, Math.floor(c.score)), by: String(c.by || '???').slice(0, 3).toUpperCase(), pubkey: c.pubkey, via, at: Date.now(), best: null };
    S.challenges.unshift(rec); saveChallenges();
    const who = nameFor(c.pubkey) || rec.by;
    if (via === 'nostr' && !bounty) { sfx('levelup'); toast(`Challenge from ${who}: beat ${pad6(rec.score)} on ${gameById(rec.game).name}`, 'gold'); if (tab === 'arcade' && !$('#layer .sheet')) refresh(); }
  }
  // a bounty only counts from the player who signed the challenge, and only if the sats are really locked to us
  if (bounty) attachBounty(rec, bounty, c.pubkey, from).catch(() => {});
  // the replay must match the hash the challenger signed; then this phone plays it to check the score
  if (replay && c.rh && !rec.replay && replayHash(replay) === c.rh) {
    rec.replay = replay; saveChallenges();
    checkReplay(rec.game, rec.seed, replay, rec.score).then(ok => { rec.verified = ok; saveChallenges(); const n = $('#layer [data-verify]'); if (n) n.outerHTML = verifyNote(rec); else if (tab === 'arcade' && !$('#layer .sheet')) refresh(); });
  }
  return rec;
}
async function onResult(ev, replay) {
  let r; try { r = readSigned(ev); } catch (e) { return; }
  const c = S.challenges.find(x => x.id === r.re && x.dir === 'out'); if (!c || !Number.isFinite(r.score)) return;
  // replay their game on this phone before believing the score (and before any bounty is paid)
  r.verified = !!(replay && r.rh && replayHash(replay) === r.rh && await checkReplay(c.game, c.seed, replay, r.score));
  if (r.verified) await bountyOnResult(c, r).catch(() => {});
  else if ((c.bounties || []).some(b => b.to === r.pubkey && b.state === 'open') && r.score > c.score) toast(`${nameFor(r.pubkey) || r.by} says they scored ${pad6(r.score)}, but their replay didn't check out. The bounty stays locked.`, 'pink');
  if (c.results.some(x => x.pubkey === r.pubkey && x.score >= r.score && (x.verified || !r.verified))) return;   // a verified score replaces an unverified higher one
  c.results = c.results.filter(x => x.pubkey !== r.pubkey).concat([{ pubkey: r.pubkey, by: String(r.by || '???').slice(0, 3), score: Math.floor(r.score), at: Date.now(), verified: r.verified }]); saveChallenges();
  const who = nameFor(r.pubkey) || r.by; const won = r.score > c.score;
  sfx(won ? 'over' : 'levelup'); toast(won ? `${who} beat your challenge with ${pad6(r.score)}` : `${who} scored ${pad6(r.score)}. Your ${pad6(c.score)} still stands!`, won ? 'pink' : 'lime');
  if (tab === 'arcade' && !$('#layer .sheet')) refresh();
}
function openChallengeIn(id) {
  const c = S.challenges.find(x => x.id === id && x.dir === 'in'); if (!c) return;
  const g = gameById(c.game); const who = nameFor(c.pubkey);
  openSheet('Challenge!', `
    <div class="chal-card"><span class="label">${who ? esc(who) + ' challenges you' : 'A player challenges you'}</span><b>${pad6(c.score)}</b><span data-noi18n>${esc(g.name)} · ${esc(c.by)}</span></div>
    ${c.bounty ? `<div class="notice bounty-note ${c.bounty.state === 'won' ? 'cyan' : ''}"><b>${money(c.bounty.amount)} BOUNTY</b> ${c.bounty.state === 'won' ? 'You won it! The sats are in your wallet.' : c.bounty.state === 'gone' ? 'This bounty is gone.' : Date.now() < c.bounty.until ? `Beat ${pad6(c.score)} by ${fmtDay(c.bounty.until)} and it's yours. The mint holds it locked to you until then.` : 'Time ran out on this bounty.'}</div>` : ''}
    ${verifyNote(c)}
    ${c.best != null ? `<div class="notice ${c.best > c.score ? 'cyan' : ''}">Your best on this challenge: ${pad6(c.best)} points. ${c.best > c.score ? 'You won!' : 'Not beaten yet.'}</div>` : ''}
    ${who ? '' : '<div class="tiny muted">This player isn\'t in your contacts. The challenge is signed, so you can save them if you know their key.</div>'}
    <button class="btn solid gold block" data-act="chalPlay" data-id="${esc(c.id)}">Accept: play ${esc(g.name)}</button>
    <button class="btn block" data-act="close">Later</button>`);
}
function verifyNote(c) {
  if (!c.replay) return '<div class="tiny muted" data-verify>No replay came with this challenge, so its score can\'t be checked.</div>';
  if (c.verified == null) return '<div class="tiny muted" data-verify>Checking their replay…</div>';
  return c.verified ? `<div class="tiny verified" data-verify>✓ Verified: their replay reaches ${pad6(c.score)}. Race their ghost.</div>` : '<div class="tiny bad" data-verify>Their replay doesn\'t reach that score. It may have been faked.</div>';
}
function challengeDone(id, score, by, replay) {   // the arcade reports the score of a challenge game (and a promise of its packed replay)
  const c = S.challenges.find(x => x.id === id && x.dir === 'in'); if (!c) return null;
  c.best = Math.max(c.best || 0, score); saveChallenges();
  const contact = S.contacts.find(x => x.pubkey === c.pubkey);
  const won = score > c.score, b = c.bounty && c.bounty.state === 'open' && Date.now() < c.bounty.until ? c.bounty : null;
  // with sats on the line, a winning score goes back to the challenger straight away so their NUTCADE can release the bounty
  if (won && b && contact) sendResult(id, score, by, replay).catch(() => {});
  return { won, target: c.score, canReply: !!contact, name: contact ? contact.name : '', bounty: b ? b.amount : 0, bountySent: !!(won && b && contact) };
}
async function sendResult(id, score, by, replay) {
  const c = S.challenges.find(x => x.id === id && x.dir === 'in'); if (!c) return false;
  const contact = S.contacts.find(x => x.pubkey === c.pubkey); if (!contact) return false;
  const packed = replay ? await Promise.resolve(replay).catch(() => null) : null;
  const ev = signChallenge(Object.assign({ v: 1, re: c.id, score: Math.floor(score), by: String(by || 'AAA').slice(0, 3) }, packed ? { rh: replayHash(packed) } : {}));
  const wrap = L.nip17.wrapEvent(rnd(32), { publicKey: contact.pubkey }, JSON.stringify(Object.assign({ t: 'nutcade-result', ev }, packed ? { replay: packed } : {})));
  const ok = await relayPublish(wrap, 8000, [...new Set((contact.relays || []).concat(relays()))].slice(0, 8));
  if (ok) { c.replied = Math.max(c.replied || 0, score); saveChallenges(); }
  return !!ok;
}
function challengePanel() {
  const list = S.challenges.slice(0, 8); if (!list.length) return '';
  return `<div class="panel" id="challenges"><span class="h2">Challenges</span><div class="txs">${list.map(c => {
    const g = gameById(c.game); if (!g) return '';
    if (c.dir === 'in') { const who = nameFor(c.pubkey) || c.by; const won = c.best != null && c.best > c.score;
      return `<button class="tx in" data-act="chalOpen" data-id="${esc(c.id)}"><span class="ico" aria-hidden="true">!</span><span class="mid"><div class="note" data-noi18n>${esc(who)}</div><div class="meta"><span data-noi18n>${esc(g.name)}</span>${c.bounty ? `<span class="chip ${c.bounty.state === 'won' ? 'ecash' : 'gift'}" data-noi18n>${fmt(c.bounty.amount)} SAT</span>` : ''}${won ? '<span class="chip ecash">WON</span>' : c.best != null ? `<span class="chip pending">BEST ${pad6(c.best)}</span>` : '<span class="chip ln">NEW</span>'}</div></span><span class="amt">${pad6(c.score)}</span></button>`; }
    const best = c.results.slice().sort((a, b) => b.score - a.score)[0];
    return `<button class="tx out" data-act="chalSendOpen" data-id="${esc(c.id)}"><span class="ico" aria-hidden="true">↑</span><span class="mid"><div class="note">Your challenge</div><div class="meta"><span data-noi18n>${esc(g.name)}</span>${best ? `<span class="chip ${best.score > c.score ? 'failed' : 'claimed'}" data-noi18n>${esc(nameFor(best.pubkey) || best.by)} ${pad6(best.score)}</span>${best.verified ? '<span class="chip ecash">✓</span>' : ''}` : '<span class="chip pending">NO REPLIES YET</span>'}</div></span><span class="amt">${pad6(c.score)}</span></button>`;
  }).join('')}</div></div>`;
}

/* ---------- round-up piggy bank ---------- */
S.piggy = store.get('piggy', { saved: 0 });
let internalMove = false, piggyOK = 0;
const piggySaved = () => S.prefs.piggy ? Math.max(0, Math.min(num(S.piggy.saved), totalBalance())) : 0;
function piggyRoundUp(t) {
  if (!S.prefs.piggy || internalMove || t.type !== 'out' || t.piggyBreak) return 0;
  const step = +S.prefs.piggyStep || 100, a = num(t.amount);
  const r = (step - a % step) % step; if (!r) return 0;
  S.piggy.saved = num(S.piggy.saved) + r; store.set('piggy', S.piggy);
  return r;
}
function piggyGuard(spend) {
  if (!S.prefs.piggy || internalMove || Date.now() < piggyOK) return;
  const saved = piggySaved();
  if (saved > 0 && totalBalance() - spend < saved) { const e = new Error('This payment dips into your piggy bank.'); e.piggy = { spend, saved }; throw e; }
}
const PIG = ['..pp....pp..', '.pppppppppp.', 'ppppppppppppp', 'ppwkppppppppp', 'pppppppppppp.', 'pnnppppppppp.', 'pnnppppppppp.', '.pppppppppp..', '.pp.pp..pp.pp', '.pp.pp..pp.pp'];
function pigSVG(cls = '') {
  const pal = { p: 'var(--pink)', w: 'var(--ink)', k: 'var(--void)', n: 'color-mix(in srgb,var(--pink) 60%,#000)' };
  let out = ''; PIG.forEach((row, y) => [...row].forEach((c, x) => { if (c !== '.') out += `<rect x="${x}" y="${y}" width="1" height="1" fill="${pal[c]}"/>`; }));
  return `<svg class="pig ${cls}" viewBox="-1 -1 15 12" shape-rendering="crispEdges" aria-hidden="true"><rect x="5" y="-1" width="3" height="1" fill="var(--gold)"/>${out}</svg>`;
}
function piggyPanel() {
  if (!S.prefs.piggy) return '';
  const saved = piggySaved(), goal = Math.max(1000, Math.ceil((saved + 1) / 10000) * 10000);
  return `<div class="panel piggy-panel"><div class="row" style="gap:12px;align-items:center">${pigSVG()}<div style="min-width:0;flex:1"><div class="row between"><span class="h2" style="color:var(--pink)">Piggy bank</span><span class="tiny" style="color:var(--gold)">${money(saved)}</span></div>
    <div class="meter" aria-hidden="true"><i style="width:${Math.min(100, Math.round(saved / goal * 100))}%"></i></div>
    <div class="tiny muted">Rounds up to the nearest ${fmt(+S.prefs.piggyStep || 100)} sat. Next goal: ${fmt(goal)} sat</div></div></div></div>`;
}
function piggyBreak(info, retry) {
  document.getElementById('piggyLayer')?.remove();
  const box = document.createElement('div'); box.id = 'piggyLayer';
  box.innerHTML = `<div class="scrim" style="align-items:center;z-index:260"><div class="sheet piggy-break" role="alertdialog" aria-modal="true" aria-label="Break the piggy bank?">
    ${pigSVG('big')}
    <div class="pb-h">BREAK THE PIGGY BANK?</div>
    <p style="margin:0">This payment dips into the ${money(info.saved)} you set aside from round-ups. If you go ahead, what's left in your wallet stays in the piggy bank.</p>
    <div class="pb-count"><span>CONTINUE?</span><b id="pbN" data-noi18n>10</b></div>
    <button class="btn solid pink block" id="pbYes" disabled>Wait…</button>
    <button class="btn block" id="pbNo">Keep saving</button></div></div>`;
  document.body.appendChild(box);
  if (LANG !== 'en') trNode(box);
  sfx('err');
  let n = 10; const yes = box.querySelector('#pbYes'), lab = box.querySelector('#pbN');
  const end = () => { clearInterval(t); box.remove(); };
  const t = setInterval(() => {
    n--; lab.textContent = n; sfx('tick');
    if (n === 5) { yes.disabled = false; yes.textContent = tr('Break it and pay'); }
    if (n <= 0) { end(); sfx('over'); toast('Payment cancelled. Your piggy bank is safe.', 'lime'); }
  }, 1000);
  box.querySelector('#pbNo').onclick = () => { end(); sfx('coin'); toast('Payment cancelled. Your piggy bank is safe.', 'lime'); };
  yes.onclick = () => { end(); S.piggy.saved = Math.max(0, totalBalance() - info.spend); store.set('piggy', S.piggy); piggyOK = Date.now() + 90e3; sfx('boom'); retry(); };
}
