/* ---------- mint reviews (1.36, NIP-87 kind 38000) ----------
   You can review a mint you use: 1 to 5 stars and an optional short text, published to your Nostr relays as a NIP-87
   recommendation (kind 38000), the same event cashu.me writes and every NIP-87 reader reads:
     tags    ["k","38172"], ["d", <the mint's pubkey from /v1/info>], ["u", <mint address>, "cashu"] and, when the mint's
             kind 38172 announcement is known (seen by the report card, its d = that pubkey, its signature checked),
             ["a", "38172:<announcer>:<d>", <the relay it was seen on>, "cashu"]
     content "[N/5]" or "[N/5] text" (cashu.me's format; the report card reads the stars back from it)
   signed with the wallet's own Nostr key (nostrKey(): the same key as nutzaps, npub.cash and the mint-list backup).
   It is addressable (the d tag), so a new review of the same mint replaces the old one. Delete is a kind 5 with
   ["a", "38000:<you>:<d>"] (NIP-09), and the review is forgotten here; a copy a relay kept anyway is never counted again.
   Publishing is always a tap, after one plain warning line; nothing is queued: offline, it says it needs a connection.
   The last review you published is kept per mint (in the report card's log, S.mintlog: stars, text, time, d; no secret),
   and counted once: the report card counts other people's reviews from relays (one per person, their newest) plus yours.
   Never in a locked wallet; the duress PIN's wallet sends nothing and answers as relays that don't answer. */
const RV_MAX = 250;   // (characters in the text; with "[5/5] " it stays under the 280 that mint discovery shows)
// cashu.me's reading: the first "[N/5]", the text after it; only 1 to 5 are stars
function rvParse(c) {
  const s = typeof c === 'string' ? c : '';
  const m = /\[(\d)\s*\/\s*5\]\s*([\s\S]*)$/.exec(s);
  if (!m) return { stars: null, text: s.trim() };
  const n = +m[1];
  return { stars: n >= 1 && n <= 5 ? n : null, text: m[2].trim() };
}
// plain text, one line: control and direction-changing characters dropped, runs of spaces and line breaks made one space
const rvClean = s => clipText(String(s == null ? '' : s), 4000).replace(/\s+/g, ' ').trim();
const rvContent = (stars, text) => `[${stars}/5]` + (text ? ' ' + text : '');
const rvStarsTxt = n => '★'.repeat(n) + '☆'.repeat(5 - n);
const rvDecoy = () => !!(vault.on && vault.decoy);
const rvD = e => ((Array.isArray(e.tags) ? e.tags : []).find(t => Array.isArray(t) && t[0] === 'd' && typeof t[1] === 'string') || [])[1] || '';
const rvSig = e => { try { return !!L.verifyEvent(e); } catch (x) { return false; } };   // (a relay's event, whatever its shape)
// your review of this mint: the one published from here, or one with your key found on your relays (another device or
// app), whichever is newer; never one at or before a deletion you sent
function rvMine(url0) {
  const l = S.mintlog[acctUrl(url0)]; if (!l) return null;
  const del = num(l.revDel), seen = l.nostr && l.nostr.v === 2 && l.nostr.mine && num(l.nostr.mine.at) > del ? l.nostr.mine : null;
  const here = l.rev && num(l.rev.at) > del ? l.rev : null;
  return here && (!seen || num(seen.at) <= num(here.at)) ? here : seen;
}
// the mint's announcement (kind 38172) to point at: signed, its d the mint's pubkey; the newest if there are several
const rvAnn = (l, pub) => ((l.nostr && l.nostr.anns) || []).filter(a => a && a.d === pub && /^[0-9a-f]{64}$/.test(a.pubkey || '')).sort((a, b) => num(b.at) - num(a.at))[0] || null;
const rvNoRelay = of => keepErr(new Error(`No Nostr relay accepted the review (0 of ${of}). Try again in a moment.`));
const rvNoDel = of => keepErr(new Error(`No Nostr relay accepted the deletion (0 of ${of}). Your review is still published. Try again in a moment.`));
function rvCan(what) {
  if (vault.on && !vault.open) throw keepErr(new Error('Unlock NUTCADE first.'));
  if (!S.seed) throw keepErr(new Error('Set up your recovery phrase first.'));
  if (isOffline()) throw keepErr(new Error(what === 'del' ? "You're offline. Deleting a review needs a connection. Nothing was sent." : "You're offline. Publishing a review needs a connection. Nothing was sent."));
}
// the duress PIN's wallet: as long as relays that don't answer would take, then their answer; nothing is ever sent
const rvDecoyWait = async err => { await sleep(6500 + Math.floor(Math.random() * 1500)); throw err; };
async function rvMintPub(url) {
  let info = null;
  try {
    const ac = new AbortController(), tm = setTimeout(() => ac.abort(), 7000);
    const r = await fetch(url + '/v1/info', { cache: 'no-store', signal: ac.signal }).finally(() => clearTimeout(tm));
    info = r.ok ? await r.json() : null;
  } catch (e) {}
  const pub = info && typeof info.pubkey === 'string' ? info.pubkey : '';
  if (!/^0[23][0-9a-f]{64}$/.test(pub)) throw keepErr(new Error(`Couldn't reach ${host(url)} to read its identity key. Nothing was sent. Try again in a moment.`));
  return pub;
}
const rvDelEvent = (d, ts) => L.finalizeEvent({ kind: 5, created_at: ts, tags: [['a', `38000:${L.nostrPub(nostrKey())}:${d}`], ['k', '38000']], content: '' }, nostrKey());
async function rvPublish(url0, stars, text) {
  const url = acctUrl(url0);
  rvCan('pub');
  stars = Number(stars);
  if (!Number.isInteger(stars) || stars < 1 || stars > 5) throw keepErr(new Error('Pick 1 to 5 stars first.'));
  const t = rvClean(text);
  if (t.length > RV_MAX) throw keepErr(new Error(`A review can be at most ${RV_MAX} characters.`));
  const list = relays();
  if (rvDecoy()) return rvDecoyWait(rvNoRelay(list.length));
  const pub = await rvMintPub(url);
  const l = mlog(url), old = rvMine(url), ann = rvAnn(l, pub);
  const tags = [['k', '38172'], ['d', pub], ['u', url, 'cashu']].concat(ann ? [['a', `38172:${ann.pubkey}:${pub}`, ann.relay || '', 'cashu']] : []);
  const ts = Math.max(Math.floor(Date.now() / 1000), (old ? num(old.at) : 0) + 1, num(l.revDel) + 1);
  const ev = L.finalizeEvent({ kind: 38000, created_at: ts, tags, content: rvContent(stars, t) }, nostrKey());
  const n = await relayPublish(ev, 7000, list, 1500);
  if (!n) throw rvNoRelay(list.length);
  // the mint's pubkey changed since your last review: that one had another d, so it is withdrawn (best effort)
  if (old && old.d && old.d !== pub) relayPublish(rvDelEvent(old.d, ts), 7000, list, 1500).catch(() => {});
  l.rev = { stars, text: t, at: ts, d: pub, id: ev.id, n, of: list.length };
  saveMlog();
  return l.rev;
}
async function rvDelete(url0) {
  const url = acctUrl(url0);
  rvCan('del');
  const old = rvMine(url); if (!old) return null;
  const list = relays();
  if (rvDecoy()) return rvDecoyWait(rvNoDel(list.length));
  const ts = Math.max(Math.floor(Date.now() / 1000), num(old.at));
  const n = await relayPublish(rvDelEvent(old.d || '', ts), 7000, list, 1500);
  if (!n) throw rvNoDel(list.length);
  const l = mlog(url); delete l.rev; l.revDel = Math.max(num(l.revDel), ts);
  saveMlog();
  return { n, of: list.length };
}

/* ---------- the review sheet ---------- */
let rvSt = null;   // { url, stars, edit, ask, done }
const rvBtn = url0 => { const url = acctUrl(url0); return `<button class="btn sm violet" data-act="rvOpen" data-url="${esc(url)}">${rvMine(url) ? 'Your review' : 'Review this mint'}</button>`; };
function rvHTML(url) {
  const st = rvSt, own = rvMine(url), m = S.mints.find(x => acctUrl(x.url) === url) || { name: host(url) };
  const U = `data-url="${esc(url)}"`;
  const head = `<div><div class="h2 uname" data-noi18n>${esc(m.name)}</div><div class="tiny muted" data-noi18n style="overflow-wrap:anywhere">${esc(host(url))}</div></div>`;
  if (st.ask && own) return head + `<div class="notice">Delete your review? NUTCADE asks your relays to delete it (NIP-09). A relay that ignores deletions may keep a copy.</div>
    <button class="btn solid red block" data-act="rvDel" ${U}>Delete review</button><button class="btn block" data-act="rvBack" ${U}>Back</button><div id="sheetErr"></div>`;
  const done = st.done && st.done.pub ? `<div class="notice cyan" id="rvResult">Published: ${st.done.n} of ${st.done.of} relays accepted it.</div>`
    : st.done && st.done.del ? `<div class="notice cyan" id="rvGone">Review deleted: ${st.done.n} of ${st.done.of} relays accepted the deletion.</div>` : '';
  const mine = own ? `<div class="panel" id="rvMine" style="gap:8px"><div class="row between"><span class="label">Your review</span><span data-noi18n data-rvstars style="color:var(--gold)" aria-label="${own.stars || 0}/5">${own.stars ? rvStarsTxt(own.stars) : ''}</span></div>
    ${own.text ? `<div data-noi18n data-rvtext style="overflow-wrap:anywhere">${esc(own.text)}</div>` : ''}
    <div class="tiny muted">${rvWhen(own)}</div>
    ${st.edit ? '' : `<div class="row"><button class="btn sm" data-act="rvEdit" ${U}>Edit</button><button class="btn sm red" data-act="rvDelAsk" ${U}>Delete</button></div>`}</div>` : '';
  const form = !own || st.edit ? `<div id="rvForm" style="display:grid;gap:12px">
    <div class="field"><label>Stars</label><div class="seg rv-stars" role="group" aria-label="Stars">${[1, 2, 3, 4, 5].map(n => `<button type="button" data-act="rvStar" data-n="${n}" aria-pressed="${st.stars === n}" data-noi18n>${n}★</button>`).join('')}</div></div>
    <div class="field"><label for="rvText">Your review (optional)</label><textarea id="rvText" class="inp" maxlength="${RV_MAX}" rows="3" placeholder="What is it like to use? Plain text." autocomplete="off">${st.edit && own ? esc(own.text || '') : ''}</textarea><div class="tiny muted" id="rvCount" data-noi18n>0/${RV_MAX}</div></div>
    <div class="field"><label>What goes out</label><div class="code" id="rvPrev"></div><div class="tiny muted" id="rvPick">Pick 1 to 5 stars.</div></div>
    <div class="notice" data-rvwarn>Public: anyone can read it, it stays on Nostr relays, and it is linked to this wallet's Nostr identity.</div>
    ${isOffline() ? `<div class="tiny" id="rvOff" style="color:var(--gold)">You're offline. Publishing needs a connection.</div>` : ''}
    <button class="btn solid gold block" data-act="rvPublish" ${U}>Publish</button></div>` : '';
  return head + done + mine + form + '<div id="sheetErr"></div>';
}
const rvWhen = own => own.relay ? "Found on your relays, published with this wallet's key." : `Published on ${fmtDay(num(own.at) * 1000)}`;
function rvPrev() {
  const ta = $('#rvText'), pv = $('#rvPrev'); if (!ta || !pv || !rvSt) return;
  const t = rvClean(ta.value);
  pv.textContent = rvSt.stars ? rvContent(rvSt.stars, t) : '';
  const c = $('#rvCount'); if (c) c.textContent = `${ta.value.length}/${RV_MAX}`;
  const pk = $('#rvPick'); if (pk) pk.hidden = !!rvSt.stars;
  document.querySelectorAll('#layer [data-act=rvStar]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.n === rvSt.stars)));
}
function rvWire(body) { const ta = body.querySelector('#rvText'); if (ta) ta.addEventListener('input', rvPrev); rvPrev(); return null; }
function rvDraw(url) { setBody(rvHTML(url), rvWire); }
function openReview(url0) {
  const url = acctUrl(url0);
  rvSt = { url, stars: 0, edit: false, ask: false, done: null };
  openSheet('Review this mint', rvHTML(url), rvWire);
  // the mint's announcement and a review of yours from another device are read with the report card's Nostr look (daily)
  const l = mlog(url);
  if (!rvDecoy() && (!l.nostr || l.nostr.v !== 2 || Date.now() - l.nostr.at > 86400e3)) nostrRecord(url).catch(() => {});
}
// every text the review screens show (tests/review_qa.py checks each is translated)
const rvTexts = () => ['Review this mint', 'Your review', 'Stars', 'Your review (optional)', 'What is it like to use? Plain text.', 'What goes out', 'Pick 1 to 5 stars.',
  "Public: anyone can read it, it stays on Nostr relays, and it is linked to this wallet's Nostr identity.", "You're offline. Publishing needs a connection.", 'Publish', 'Edit', 'Delete',
  'Delete your review? NUTCADE asks your relays to delete it (NIP-09). A relay that ignores deletions may keep a copy.', 'Delete review', 'Back',
  'Published: 1 of 2 relays accepted it.', 'Review deleted: 1 of 2 relays accepted the deletion.', "Found on your relays, published with this wallet's key.", `Published on ${fmtDay(Date.UTC(2026, 10, 25, 12))}`,
  'No Nostr relay accepted the review (0 of 2). Try again in a moment.', 'No Nostr relay accepted the deletion (0 of 2). Your review is still published. Try again in a moment.',
  'Pick 1 to 5 stars first.', `A review can be at most ${RV_MAX} characters.`, "You're offline. Publishing a review needs a connection. Nothing was sent.", "You're offline. Deleting a review needs a connection. Nothing was sent.",
  "Couldn't reach mint.example.com to read its identity key. Nothing was sent. Try again in a moment.", 'Unlock NUTCADE first.', 'Review published', 'Review deleted'];
window.NutReview = { mine: u => rvMine(u), publish: (u, s, t) => rvPublish(u, s, t), del: u => rvDelete(u), parse: c => rvParse(c), clean: s => rvClean(s), open: u => openReview(u), texts: () => rvTexts(), max: RV_MAX };
