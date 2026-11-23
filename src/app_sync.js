/* ===================== Wallet sync (1.30, a subset of NIP-60) ===================== */
/* Two or more devices with the same 12 words keep the same coins, through your Nostr relays, with THE MINT AS REFEREE.
   Opt-in ("Sync this wallet across devices", Settings, Privacy), off by default, per wallet (never in backup files).
   - Key: a dedicated Nostr key, sha256(seed ‖ "nutcade-nip60") (like the mint-list backup key), never your public Nostr
     identity. Every event is signed with it and its content NIP-44 encrypted to itself, so relays see only that some key
     publishes some events (how many, how big, when).
   - Events (NIP-60 shapes): kind 7375 holds your coins at one mint, {mint, unit: "sat", proofs, del: [ids it replaces]}, at
     most SY_PER_EV coins an event, and NUTCADE's own field "gone": [[h, time]] (at most SY_GONE_EV an event; h is sha256
     of a coin's secret cut to 32 hex) for coins of that mint this wallet handed out in a token nobody has claimed yet (an
     offline send keeps the very coins: the other device must never count or spend them), carried forward by every device
     that replaces the event, for SY_GONE_AGE. Kind 17375 (replaceable) holds the wallet: ["privkey", the nutzap receiving
     key (NIP-61), as NIP-60 says], ["mint", url], and NUTCADE's own tags ["counter", keyset, n] (NUT-13 counters, merged
     highest-wins, never lowered) and ["gone", h, time] (the newest SY_GONE marks, our own first: a quick copy). Kind 5
     deletes only our own events (the sync key's), and only ones NUTCADE read and accounted for. Events we cannot read are
     never touched. No kind 7376 history. Interop with cashu.me or Minibits is NOT a goal (they use another key).
   - Every event read is checked as it arrives (syQuery): the sync key, the kind, the size and the signature, before it is
     kept; the first good copy of an id wins and copies from all relays are put together, so a relay that answers first
     with a forged copy of a real id can't hide the real one. The wallet event is only ever written from scratch (none
     read) when most relays answered: a relay that answers "nothing" can't make us drop the marks and counters.
   - Reading (pulling): at start, when the tab comes back (at most once a minute), every SY_PERIOD, after an "already spent"
     error and on "Sync now". A coin (each one on its own: a bad one is skipped, the rest of its event is still read) must
     have an id, an amount that is a power of two, a plain secret of at most SY_SECRET characters (never a locked NUT-10
     one), a C point and a DLEQ proof. It is never counted until (1) it is at a mint already in your list (another mint is
     only shown, with a question; never added by itself), (2) its keyset and amount are that mint's, (3) its DLEQ proof
     (NUT-12) checks against the mint's saved key, so a made-up coin is never adopted, (4) no "gone" mark names it, and
     (5) the mint (checkstate, NUT-07) says it is UNSPENT. SPENT ones are left out for good; PENDING ones and ones the mint
     can't answer for are looked at again next time. Coins this wallet holds, handed out, has in a step still open, set
     aside or in Extra Life are never added again. At most SY_ADOPT coins a run. The merge is a set keyed by the secret:
     the same event twice, events in any order or an old event replayed change nothing. A coin we hold that no event lists
     any more makes us ask the mint (pruneSpent: spent coins dropped with a line, as always); a "gone" mark from our other
     device drops the coin with a line ("Sent from your other device").
   - Writing (pushing): after the money step that changed your coins at a mint has settled (no journal record open there),
     debounced: never inside a payment, and a failure never blocks or breaks one (retried with backoff). The wallet event
     (with the new gone marks) goes first; then a mint's coins are published again when the relays don't list them all
     or our gone marks, or when an event lists coins this wallet no longer has (spent, handed out): the new events come
     first, then the kind 5 deletion of the events they replace. While the wallet event could not be written, an event
     is not replaced on the strength of our own handing-out alone. Only coins that pass the reader's checks are published.
     What is compared is exactly what would be written (capped), so nothing is published again and again. Nothing is
     published before a successful read in this session.
   - Restore from the 12 words: one read of the sync key's events (nothing written, sync stays off): the scan leaves out
     the coins their gone marks name, and if a wallet event is there (not deleted by "Delete them from my relays"), the
     result asks whether to turn sync on here too.
   - Two devices spending the same coin at once: the mint takes one; the other gets "already spent", and spentRetry /
     pruneSpent drop the spent coins there (nothing new here). A coin handed out offline by one device and spent by the
     other before it heard about it: the mint lets only one through (the token's receiver may find it already spent).
   The duress PIN's wallet never reads or publishes (its switch looks like a wallet whose relays don't answer). A paused
   tab (open elsewhere) does nothing. */
const SY_TAG = 'nutcade-nip60';
const SY_PER_EV = 60, SY_MAX_PROOFS = 100, SY_MAX_EVENTS = 300, SY_MAX_BYTES = 120000, SY_ADOPT = 200, SY_SECRET = 512;
const SY_GONE = 400, SY_GONE_EV = 400, SY_GONE_MINT = 4000, SY_GONE_AGE = 30 * 86400, SY_FOCUS = 60e3, SY_PERIOD = 10 * 60e3, SY_OTHER = 5, SY_DEL = 100, SY_CTRS = 64, SY_MINTS = 20;
const SY_KINDS = [7375, 17375, 5];
let syKeyC = null;
function syKeys() {
  const s = seedFor();
  if (!syKeyC || syKeyC.seed !== s) {
    const tag = new TextEncoder().encode(SY_TAG), b = new Uint8Array(s.length + tag.length); b.set(s); b.set(tag, s.length);
    const sk = L.sha256(b), pk = L.nostrPub(sk);
    syKeyC = { seed: s, sk, pk, ck: L.nip44.v2.utils.getConversationKey(sk, pk) };
  }
  return syKeyC;
}
const syDecoy = () => !!(vault.on && vault.decoy);
const syAllowed = () => !!(S.seed && S.seed.backedUp && !syDecoy());
const syOn = () => syAllowed() && S.prefs.sync === true;
const syLive = () => syOn() && !tabLocked && !(vault.on && !vault.open) && !writeGuard.paused;
const syRelays = () => nzRelays(relays()).slice(0, 8);
const syHash = s => hex(L.sha256(new TextEncoder().encode(String(s)))).slice(0, 32);
const syEnc = obj => L.nip44.v2.encrypt(JSON.stringify(obj), syKeys().ck);
function syDec(c) { if (typeof c !== 'string' || !c || c.length > SY_MAX_BYTES) return null; try { return JSON.parse(L.nip44.v2.decrypt(c, syKeys().ck)); } catch (e) { return null; } }
const sySt = () => { const s = S.prefs.syncSt; return s && typeof s === 'object' ? s : (S.prefs.syncSt = { ts: 0, del: [], at: 0 }); };
function syNextTs(min) { const st = sySt(); st.ts = Math.max(Math.floor(Date.now() / 1000), num(st.ts) + 1, num(min)); return st.ts; }
// one of OUR mints for a mint address an event wrote (exact match once normalised), or null; the event's text is never used itself
function syMint(u) {
  if (typeof u !== 'string' || u.length > 300 || !/^https?:\/\/[^\s]+$/i.test(u.trim())) return null;
  const n = normUrl(u); return S.mints.some(m => m.url === n) ? n : null;
}
const syPow2 = a => Number.isSafeInteger(a) && a > 0 && a <= 2 ** 40 && Number.isInteger(Math.log2(a));
// a coin as an event wrote it, checked for shape only (null: this coin is skipped)
function syProof(p) {
  if (!p || typeof p !== 'object' || Array.isArray(p)) return null;
  const a = p.amount;
  if (typeof p.id !== 'string' || !/^[0-9a-f]{16,66}$/i.test(p.id) || typeof a !== 'number' || !syPow2(a)) return null;
  if (typeof p.secret !== 'string' || !p.secret || p.secret.length > SY_SECRET || /[\x00-\x1f\x7f]/.test(p.secret) || /^\s*\[/.test(p.secret)) return null;   // (a locked secret, NUT-10, is never one of our plain coins)
  if (typeof p.C !== 'string' || !/^0[23][0-9a-f]{64}$/i.test(p.C)) return null;
  const q = { id: p.id, amount: a, secret: p.secret, C: p.C.toLowerCase() };
  if (p.dleq != null) {
    const d = p.dleq; if (!d || typeof d !== 'object' || ![d.e, d.s, d.r].every(x => typeof x === 'string' && /^[0-9a-f]{1,64}$/i.test(x))) return null;
    q.dleq = { e: d.e, s: d.s, r: d.r };
  }
  return q;
}
const syOut = p => Object.assign({ id: p.id, amount: num(p.amount), secret: p.secret, C: p.C }, p.dleq && p.dleq.e && p.dleq.s && p.dleq.r ? { dleq: { e: String(p.dleq.e), s: String(p.dleq.s), r: String(p.dleq.r) } } : {});
// the coins at a mint that can be published: exactly those a reader would take (an old base64 keyset id, say, never is)
const syPub = url => (S.proofs[url] || []).map(syOut).filter(p => syProof(p));
// a "gone" list as an event wrote it: [[h, time]], at most `max`; anything else in it is skipped
function syMarks(list, max) {
  const out = new Map(); if (!Array.isArray(list)) return out;
  for (const g of list.slice(0, max)) if (Array.isArray(g) && typeof g[0] === 'string' && /^[0-9a-f]{32}$/.test(g[0]) && Number.isSafeInteger(g[1]) && g[1] > 0) out.set(g[0], Math.max(out.get(g[0]) || 0, g[1]));
  return out;
}
// every secret this wallet already accounts for: coins held (any mint), tokens sent, waiting incoming tokens, payments in
// flight, steps still open, Extra Life, coins the keyset check-up set aside
function syHeld(url) {
  const out = new Set();
  for (const ps of Object.values(S.proofs)) for (const p of ps || []) out.add(p.secret);
  for (const t of S.txs) {
    if (Array.isArray(t.sent)) for (const p of t.sent) if (p && p.secret) out.add(p.secret);
    if (t.incoming && t.status === 'pending') for (const s of heldSecrets(t.incoming) || []) out.add(s);
  }
  for (const p of S.pending) for (const x of p.proofs || []) out.add(x.secret);
  for (const o of S.ops) for (const s of o.inputs || []) out.add(s);
  if (S.extra && Array.isArray(S.extra.proofs)) for (const p of S.extra.proofs) out.add(p.secret);
  if (url) for (const p of asideOf(url)) out.add(p.secret);
  return out;
}
// our own gone marks: the coins of every token this wallet sent that nobody has claimed yet, newest first, [h, mint]
const syOwnGone = () => S.txs.filter(t => t.type === 'out' && t.status === 'pending' && Array.isArray(t.sent)).sort((a, b) => num(b.ts) - num(a.ts)).flatMap(t => t.sent.filter(p => p && p.secret).map(p => [syHash(p.secret), t.mint]));
// a counters-only repair scan (app.js restoreFromMintNow): with sync on, what it finds is the other device's
function syRepairOnly() { try { if (syOn()) { sySoon(); return true; } } catch (e) {} return false; }
// a coin our other device handed out in a token (a gone mark from the last read, or from a restore's read)
let syRestoreMarks = new Set();
function syGone(s) { try { const h = syHash(s); return syRestoreMarks.has(h) || !!(syView && syView.gone.has(h)); } catch (e) { return false; } }

/* ---------- what the last read found (memory only: every session reads before it writes) ---------- */
let syView = null;   // { live: [{ id, url, at, secrets: Set, gone: Map }], wallet: {...} | null, gone: Map (every mark read), sure }
let syState = null, syPullAt = 0, syLastRes = null, syNext = 0, syTries = 0, syDecoyT = 0, syTimer = 0, syPushing = false, syAgain = false;
const sySpent = new Set();   // secrets a mint said were spent (never asked about again in this session)
const syLeft = new Set();    // secrets this wallet held and no longer holds (spent or handed out here), since the session started
let syLocal = null;          // url -> Set of secrets held, at the last look (to notice what left)
function syNoteLeft() {
  const now = new Map(Object.entries(S.proofs).map(([u, ps]) => [u, new Set((ps || []).map(p => p.secret))]));
  if (syLocal) for (const [u, was] of syLocal) { const cur = now.get(u) || new Set(); for (const s of was) if (!cur.has(s)) syLeft.add(s); }
  if (syLeft.size > 5000) { const keep = [...syLeft].slice(-4000); syLeft.clear(); keep.forEach(s => syLeft.add(s)); }
  syLocal = now;
}
function syWalletOf(e, c) {
  if (!Array.isArray(c) || c.length > 2000) return null;
  const w = { at: num(e.created_at), id: e.id, counters: {}, gone: new Map(), mints: [] };
  for (const t of c) {
    if (!Array.isArray(t) || typeof t[0] !== 'string') continue;
    if (t[0] === 'mint' && typeof t[1] === 'string' && t[1].length <= 300 && /^https?:\/\/[^\s]+$/i.test(t[1]) && w.mints.length < SY_MINTS) { const u = normUrl(t[1]); if (!w.mints.includes(u)) w.mints.push(u); }
    else if (t[0] === 'counter' && typeof t[1] === 'string' && /^[0-9a-f]{16,66}$/i.test(t[1]) && Object.keys(w.counters).length < SY_CTRS) { const n = Number(t[2]); if (Number.isSafeInteger(n) && n >= 0 && n < 2 ** 31) w.counters[t[1]] = Math.max(w.counters[t[1]] || 0, n); }
    else if (t[0] === 'gone' && typeof t[1] === 'string' && /^[0-9a-f]{32}$/.test(t[1]) && w.gone.size < SY_GONE) { const ts = Number(t[2]); if (Number.isSafeInteger(ts) && ts > 0) w.gone.set(t[1], Math.max(w.gone.get(t[1]) || 0, ts)); }
  }
  return w;
}
// an event of the sync key, checked as it arrives: kind, size, shape and signature
const syValidEv = (e, pk, kinds) => !!e && typeof e === 'object' && typeof e.id === 'string' && /^[0-9a-f]{64}$/.test(e.id) && e.pubkey === pk && kinds.includes(e.kind) && typeof e.content === 'string' && e.content.length <= SY_MAX_BYTES && Array.isArray(e.tags) && e.tags.length <= 300 && Number.isSafeInteger(e.created_at) && L.verifyEvent(e);
// a read from every relay: each event is checked BEFORE it is kept, the first good copy of an id wins, and the copies from
// all relays are put together (a relay answering first with a forged copy of a real id hides nothing). answered: relays
// that finished (EOSE); total: relays asked
function syQuery(filter, kinds, timeout = 8000, list = syRelays(), early = 1500) {
  const pk = syKeys().pk;
  return new Promise(res => {
    const out = new Map(); let left = 0, answered = 0, bad = 0, soon = false, fin = false; const socks = [];
    const end = () => { if (fin) return; fin = true; socks.forEach(s => { try { s.close(); } catch (e) {} }); res({ evs: [...out.values()], answered, total: list.length, bad }); };
    for (const r of list) {
      let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
      socks.push(ws); left++;
      const drop = () => { if (ws._done) return; ws._done = true; if (--left <= 0) end(); };
      ws.onopen = () => ws.send(JSON.stringify(['REQ', 'ncsy', filter]));
      ws.onmessage = m => {
        let d; try { d = JSON.parse(m.data); } catch (e) { return; }
        if (d[0] === 'EVENT' && d[2]) { const e = d[2]; if (e && typeof e.id === 'string' && out.has(e.id)) return; if (syValidEv(e, pk, kinds)) out.set(e.id, e); else bad++; }
        else if (d[0] === 'EOSE' || d[0] === 'CLOSED') { if (d[0] === 'EOSE') { answered++; if (early && !soon) { soon = true; setTimeout(end, early); } } try { ws.close(); } catch (e) {} drop(); }
      };
      ws.onerror = drop; ws.onclose = drop;
    }
    if (!left) end();
    setTimeout(end, timeout);
  });
}
const syMost = q => q.total > 0 && q.answered * 2 > q.total;
// everything the sync key has on the relays, read and checked: live coin events, the wallet event, every gone mark
function syRead(q) {
  const k = syKeys(), r = { bad: q.bad, badCoins: 0 };
  const deleted = new Set(); let walletDelAt = 0;
  for (const e of q.evs) if (e.kind === 5) for (const t of e.tags.slice(0, 300)) {
    if (!Array.isArray(t)) continue;
    if (t[0] === 'e' && /^[0-9a-f]{64}$/.test(t[1])) deleted.add(t[1]);
    else if (t[0] === 'a' && t[1] === `17375:${k.pk}:`) walletDelAt = Math.max(walletDelAt, e.created_at);
  }
  const toks = [];
  for (const e of q.evs.filter(e => e.kind === 7375).sort((a, b) => b.created_at - a.created_at || (a.id < b.id ? -1 : 1)).slice(0, SY_MAX_EVENTS)) {
    const c = syDec(e.content);
    if (!c || typeof c !== 'object' || Array.isArray(c) || typeof c.mint !== 'string' || (c.unit != null && c.unit !== 'sat') || !Array.isArray(c.proofs) || c.proofs.length > SY_MAX_PROOFS) { r.bad++; continue; }
    const ps = [], seen = new Set();
    for (const x of c.proofs) { const p = syProof(x); if (!p || seen.has(p.secret)) { r.badCoins++; continue; } seen.add(p.secret); ps.push(p); }   // (a bad coin is skipped on its own)
    const gone = syMarks(c.gone, SY_GONE_EV);
    if (!ps.length && !gone.size) { r.bad++; continue; }
    if (Array.isArray(c.del) && c.del.length <= SY_DEL) for (const d of c.del) if (typeof d === 'string' && /^[0-9a-f]{64}$/.test(d)) deleted.add(d);
    toks.push({ id: e.id, at: e.created_at, mint: c.mint, url: syMint(c.mint), proofs: ps, gone });
  }
  let wallet = null, walletSeen = false;
  for (const e of q.evs.filter(e => e.kind === 17375).sort((a, b) => b.created_at - a.created_at || (a.id < b.id ? -1 : 1))) {
    if (e.created_at <= walletDelAt) { walletSeen = true; continue; }   // (deleted with "Delete them from my relays")
    const w = syWalletOf(e, syDec(e.content)); if (w) { wallet = w; break; }
    r.bad++;
  }
  const live = toks.filter(t => !deleted.has(t.id));
  const gone = new Map(wallet ? wallet.gone : []);
  for (const t of live) for (const [h, ts] of t.gone) gone.set(h, Math.max(gone.get(h) || 0, ts));
  return Object.assign(r, { live, wallet, gone, walletDeleted: !wallet && (walletSeen || walletDelAt > 0) });
}

/* ---------- reading ---------- */
async function syPullNow(why) {
  if (!syLive()) return null;
  const rl = syRelays(); if (!rl.length) return null;
  syState = 'busy';
  const q = await syQuery({ kinds: SY_KINDS, authors: [syKeys().pk], limit: SY_MAX_EVENTS }, SY_KINDS, 8000, rl, 1500);
  if (!syLive()) { syState = null; return null; }
  if (!q.answered) { syState = 'failed'; return null; }
  const rd = syRead(q), live = rd.live, wallet = rd.wallet, goneAll = new Map(rd.gone);
  const r = { why, adopted: 0, coins: 0, dropped: 0, spent: 0, pending: 0, unchecked: 0, bad: rd.bad, badCoins: rd.badCoins, other: [], live: live.length, ids: live.map(t => t.id), answered: q.answered, total: q.total };
  // NUT-13 counters: the highest wins, never lowered
  if (wallet) for (const [id, n] of Object.entries(wallet.counters)) if (n > (S.counters[id] || 0)) { try { await counterSource.advanceToAtLeast(id, n); } catch (e) {} }
  const own = new Set(syOwnGone().map(g => g[0]));
  for (const h of own) if (!goneAll.has(h)) goneAll.set(h, 1);
  const other = new Set();
  for (const t of live) if (!t.url && /^https?:\/\/[^\s]+$/i.test(t.mint.trim()) && t.mint.length <= 300) other.add(normUrl(t.mint));
  r.other = [...other].filter(u => !isBlocked(u)).slice(0, SY_OTHER);
  // 1. coins our other device handed out in a token: never counted here
  for (const m of S.mints) {
    const url = m.url, marked = p => { const h = syHash(p.secret); return rd.gone.has(h) && !own.has(h); };
    if (!(S.proofs[url] || []).some(marked)) continue;
    await mintLock(url, async () => {
      const busy = new Set(S.ops.filter(o => o.mint === url).flatMap(o => o.inputs || []));
      const out = (S.proofs[url] || []).filter(p => marked(p) && !busy.has(p.secret)); if (!out.length) return;
      const ids = new Set(out.map(p => p.secret));
      S.proofs[url] = (S.proofs[url] || []).filter(p => !ids.has(p.secret));
      addTx({ type: 'out', method: 'ecash', amount: sum(out), mint: url, note: 'Sent from your other device (wallet sync)', status: 'done', upkeep: true, sync: 1 });
      r.dropped += sum(out); await saveNow();
    }).catch(() => {});
  }
  // 2. coins we hold that no event lists any more: the mint says which are spent (dropped with a line, as always)
  const liveAt = url => new Set(live.filter(t => t.url === url).flatMap(t => t.proofs.map(p => p.secret)));
  for (const m of S.mints) {
    const url = m.url, mine = syPub(url); if (!mine.length || isBlocked(url)) continue;
    const ls = liveAt(url); if (mine.every(p => ls.has(p.secret))) continue;
    try { r.spent += num(await mintLock(url, () => pruneSpent(url))); } catch (e) {}
  }
  // 3. coins we don't have yet: checked, then only those the mint says are unspent
  const cand = new Map(), heldAt = new Map();   // url -> Map(secret -> proof)
  let n = 0;
  for (const t of live) {
    if (!t.url || isBlocked(t.url)) continue;
    if (!heldAt.has(t.url)) heldAt.set(t.url, syHeld(t.url));
    const held = heldAt.get(t.url), c = cand.get(t.url) || new Map();
    for (const p of t.proofs) {
      if (n >= SY_ADOPT) break;
      if (held.has(p.secret) || sySpent.has(p.secret) || goneAll.has(syHash(p.secret)) || c.has(p.secret)) continue;
      c.set(p.secret, p); n++;
    }
    cand.set(t.url, c);
  }
  for (const [url, c] of cand) {
    if (!c.size) continue;
    if (!S.mintkeys[url]) { try { await getWallet(url); } catch (e) {} }
    const ks = S.mintkeys[url];
    if (!ks) { r.unchecked += c.size; continue; }
    const ok = [];
    for (const p of c.values()) {
      const A = nzHas(ks, p.id) && nzHas(ks[p.id], String(p.amount)) ? ks[p.id][String(p.amount)] : null;
      if (!A || !DQ.wellFormed(p.dleq)) { r.unchecked++; continue; }   // (a keyset we don't know, or no DLEQ proof: can't be checked here, left out)
      if (!DQ.proofOk(p, A)) { r.bad++; continue; }                   // (not signed by this mint: never counted)
      ok.push(p);
    }
    if (!ok.length) continue;
    let w; try { w = await getWallet(url); } catch (e) { r.unchecked += ok.length; continue; }
    const size = Math.max(1, Math.min(mintMax(url) || 100, 100)), fresh = [];
    for (let i = 0; i < ok.length; i += size) {
      const part = ok.slice(i, i + size);
      let st = null; try { st = await inTime(w.checkProofsStates(part), 20000); } catch (e) { st = null; }
      if (!st || st.length !== part.length) { r.unchecked += part.length; continue; }
      part.forEach((p, j) => { const s = st[j] && st[j].state; if (s === 'UNSPENT') fresh.push(p); else if (s === 'SPENT') sySpent.add(p.secret); else r.pending++; });
    }
    if (!fresh.length) continue;
    await mintLock(url, async () => {
      const held = syHeld(url), mine = new Set(syOwnGone().map(g => g[0]));
      const add = fresh.filter(p => !held.has(p.secret) && !mine.has(syHash(p.secret)));   // (from the last look to the write, no wait)
      if (!add.length) return;
      S.proofs[url] = (S.proofs[url] || []).concat(plain(add.map(syOut)));
      addTx({ type: 'in', method: 'ecash', amount: sum(add), mint: url, note: 'From your other device (wallet sync)', status: 'done', upkeep: true, sync: 1 });
      r.adopted += sum(add); r.coins += add.length; await saveNow();
    }).catch(() => {});
  }
  if (sySpent.size > 20000) sySpent.clear();
  syView = { at: Date.now(), live: live.filter(t => t.url).map(t => ({ id: t.id, url: t.url, at: t.at, secrets: new Set(t.proofs.map(p => p.secret)), gone: t.gone })), wallet, gone: rd.gone, sure: syMost(q) };
  syNoteLeft();
  syPullAt = Date.now(); syState = 'ok'; syLastRes = r;
  sySt().at = Math.floor(Date.now() / 1000);
  S.prefs.syncOther = r.other; save();
  if (r.adopted || r.dropped || r.spent) refresh();
  return r;
}

/* ---------- writing ---------- */
// the wallet event we would write now: capped exactly as a reader caps it, so comparing it with what was read is exact
function syWalletWant(rw) {
  const now = Math.floor(Date.now() / 1000), okId = id => /^[0-9a-f]{16,66}$/i.test(id);
  const ctr = new Map();
  for (const [id, n] of Object.entries(S.counters).filter(([id, n]) => okId(id) && Number.isSafeInteger(n) && n > 0 && n < 2 ** 31).sort((a, b) => b[1] - a[1])) ctr.set(id, Math.max(n, rw ? rw.counters[id] || 0 : 0));
  if (rw) for (const [id, n] of Object.entries(rw.counters)) if (!ctr.has(id)) ctr.set(id, n);
  const cs = [...ctr].slice(0, SY_CTRS);
  const g = new Map();
  for (const [h] of syOwnGone()) if (!g.has(h)) g.set(h, now);   // (ours first, newest first: re-dated when written)
  if (rw) for (const [h, t] of [...rw.gone].sort((a, b) => b[1] - a[1])) if (!g.has(h) && now - t < SY_GONE_AGE) g.set(h, t);
  const gone = [...g].slice(0, SY_GONE);
  const mints = [...new Set(S.mints.map(m => m.url).concat(rw ? rw.mints : []))].slice(0, SY_MINTS);
  return { cs, gone, mints };
}
const syWalletNeed = (rw, w) => !rw || w.cs.some(([id, n]) => n > (rw.counters[id] || 0)) || w.gone.some(([h]) => !rw.gone.has(h)) || w.mints.some(u => !rw.mints.includes(u));
// the newest wallet event on the relays that we can read, and whether most relays answered
async function syWalletLatest(rl) {
  const q = await syQuery({ kinds: [17375, 5], authors: [syKeys().pk], limit: 50 }, [17375, 5], 6000, rl, 1000);
  const rd = syRead(q);
  return { wallet: rd.wallet, sure: syMost(q) || !!rd.wallet, answered: q.answered };
}
// a mint's gone marks to publish with its coins: ours for tokens from that mint, and every mark read from its live events
function syMintMarks(url, evs) {
  const now = Math.floor(Date.now() / 1000), g = new Map();
  for (const [h, m] of syOwnGone()) if (m === url && !g.has(h)) g.set(h, now);
  for (const e of evs) for (const [h, t] of [...e.gone].sort((a, b) => b[1] - a[1])) if (!g.has(h) && now - t < SY_GONE_AGE) g.set(h, t);
  return [...g].slice(0, SY_GONE_MINT);
}
async function syPushNow() {
  if (!syLive() || !syView) return 0;
  const k = syKeys(), rl = syRelays(); if (!rl.length) return 0;
  syNoteLeft();
  const st = sySt(); let sent = 0, failed = false, wrote = false;
  // deletions still owed from an earlier round
  if (Array.isArray(st.del) && st.del.length) {
    const d = L.finalizeEvent({ kind: 5, created_at: syNextTs(st.delAt), tags: st.del.slice(0, SY_DEL).map(i => ['e', i]).concat([['k', '7375']]), content: '' }, k.sk);
    if (await relayPublish(d, 7000, rl, 1500)) { st.del = st.del.slice(SY_DEL); wrote = true; } else failed = true;
  }
  // 1. the wallet event first (the new gone marks are out before any event that held those coins is replaced); compared
  //    capped, as it would be written; read again just before it is written; never written from scratch on a thin answer
  let walletOk = true;
  if (syWalletNeed(syView.wallet, syWalletWant(syView.wallet))) {
    const lt = await syWalletLatest(rl);
    if (lt.wallet && (!syView.wallet || lt.wallet.at > syView.wallet.at || (lt.wallet.at === syView.wallet.at && lt.wallet.id !== syView.wallet.id))) syView.wallet = lt.wallet;
    const rw = syView.wallet, want = syWalletWant(rw);
    if (!rw && !(lt.sure && syView.sure)) { walletOk = false; failed = true; }   // (most relays didn't answer: what is there may just not have arrived)
    else if (syWalletNeed(rw, want)) {
      const content = [['privkey', nzPriv()]].concat(want.mints.map(u => ['mint', u]), want.cs.map(([id, n]) => ['counter', id, String(n)]), want.gone.map(([h, t]) => ['gone', h, String(t)]));
      const ev = L.finalizeEvent({ kind: 17375, created_at: syNextTs(rw ? rw.at + 1 : 0), tags: [], content: syEnc(content) }, k.sk);
      if (await relayPublish(ev, 7000, rl, 1500)) { syView.wallet = syWalletOf(ev, content); sent++; wrote = true; } else { walletOk = false; failed = true; }
    }
  }
  // 2. each mint's coins and gone marks
  const remote = syView.gone;
  for (const m of S.mints) {
    const url = m.url;
    if (S.ops.some(o => o.mint === url)) continue;   // (a step still open here: published once it has settled)
    const local = syPub(url), lset = new Set(local.map(p => p.secret));
    const evs = syView.live.filter(e => e.url === url), ls = new Set(evs.flatMap(e => [...e.secrets])), lm = new Set(evs.flatMap(e => [...e.gone.keys()]));
    const ownM = syOwnGone().filter(g => g[1] === url).map(g => g[0]).slice(0, SY_GONE_MINT);
    // a coin we no longer hold is accounted for when the mint said it is spent, or it left here (spent or handed out) and
    // the wallet event with our marks is out; a mark another device wrote counts in any case
    const acc = s => lset.has(s) || sySpent.has(s) || remote.has(syHash(s)) || (walletOk && (syLeft.has(s) || ownM.includes(syHash(s))));
    const covered = local.every(p => ls.has(p.secret)) && ownM.every(h => lm.has(h));
    const stale = evs.some(e => [...e.secrets].some(s => !lset.has(s)) && [...e.secrets].every(acc));
    if (covered && !stale) continue;
    const retire = evs.filter(e => [...e.secrets].every(acc));
    const del = retire.map(e => e.id).slice(0, SY_DEL);
    const ts = syNextTs(Math.max(0, ...retire.map(e => e.at)));
    const marks = syMintMarks(url, evs);
    const coinCh = [], markCh = [];
    for (let i = 0; i < local.length; i += SY_PER_EV) coinCh.push(local.slice(i, i + SY_PER_EV));
    for (let i = 0; i < marks.length; i += SY_GONE_EV) markCh.push(marks.slice(i, i + SY_GONE_EV));
    const made = [], parts = [];
    for (let i = 0; i < Math.max(coinCh.length, markCh.length); i++) {
      const c = { mint: url, unit: 'sat', proofs: coinCh[i] || [], del };
      if (markCh[i]) c.gone = markCh[i];
      parts.push(c); made.push(L.finalizeEvent({ kind: 7375, created_at: ts, tags: [], content: syEnc(c) }, k.sk));
    }
    const oks = await Promise.all(made.map(e => relayPublish(e, 7000, rl, 1500)));
    made.forEach((e, i) => { if (oks[i]) syView.live.push({ id: e.id, url, at: ts, secrets: new Set(parts[i].proofs.map(p => p.secret)), gone: new Map(parts[i].gone || []) }); });
    sent += oks.filter(Boolean).length; if (oks.some(Boolean)) wrote = true;
    if (oks.some(x => !x)) { failed = true; continue; }   // (nothing replaced: the old events still list every coin and mark)
    if (del.length) {
      syView.live = syView.live.filter(e => !del.includes(e.id));
      st.del = [...new Set((st.del || []).concat(del))].slice(-500); st.delAt = ts;
      const d = L.finalizeEvent({ kind: 5, created_at: ts, tags: del.map(i => ['e', i]).concat([['k', '7375']]), content: '' }, k.sk);
      if (await relayPublish(d, 7000, rl, 1500)) st.del = st.del.filter(i => !del.includes(i)); else failed = true;
    }
  }
  if (wrote) save();
  if (failed) { syTries++; syNext = Date.now() + Math.min(30 * 60e3, 30e3 * 2 ** Math.min(syTries - 1, 6)); syState = 'failed'; }
  else { syTries = 0; syNext = 0; if (syState !== 'busy') syState = 'ok'; }
  return sent;
}
// one sync step at a time (reads and writes never overlap)
let syChain = Promise.resolve();
function syQueue(fn) { const r = syChain.catch(() => {}).then(fn); syChain = r.catch(() => {}); return r; }
async function syPushGuarded() { syPushing = true; try { return await syPushNow(); } finally { syPushing = false; } }
// read, then write what changed; a write alone needs a read in this session first
function syRun(why) {
  return syQueue(async () => { const r = await syPullNow(why); if (r) { await syPushGuarded().catch(() => {}); if (syState === 'busy') syState = 'ok'; } return r; });
}
function syPush() { return syQueue(async () => { if (!syView) { const r = await syPullNow('push'); if (!r) return 0; } return syPushGuarded(); }); }
// called by save(): the coins may have changed; written a moment later (after the money step has settled). A save made
// while a write is running (its own, or a payment's) is looked at once that write has ended, never in a loop
function syDirty() {
  if (!syLive()) return;
  if (syPushing) { syAgain = true; return; }
  if (syTimer) return;
  syTimer = setTimeout(() => {
    syTimer = 0; if (!syLive() || Date.now() < syNext) return;
    syAgain = false;
    syPush().then(() => { if (syAgain) { syAgain = false; syDirty(); } }).catch(() => {});
  }, 2000);
}
function sySoon(ms) { if (!syLive()) return; setTimeout(() => { if (syLive()) syRun('soon').catch(() => {}); }, ms || 3000); }
// every background round: a read at start and every SY_PERIOD, a write retried after a failure
async function syTick(startup) {
  if (!syLive()) return;
  if (startup || !syView || Date.now() - syPullAt > SY_PERIOD) { await syRun(startup ? 'start' : 'period'); return; }
  if (syNext && Date.now() >= syNext) await syPush();
}
document.addEventListener('visibilitychange', () => { if (!document.hidden && syLive() && Date.now() - syPullAt > SY_FOCUS) sySoon(500); });

/* ---------- restore from the 12 words: one read, nothing written, sync stays off until you say ---------- */
// Reads the sync key's coin, wallet and deletion events once: their gone marks keep the restore's scan from counting
// coins another device holding these words handed out in a token; true when a wallet event is there (and wasn't deleted
// with "Delete them from my relays"), so the result can ask whether to turn sync on here too
async function syRestoreLook(line) {
  syRestoreMarks = new Set();
  if (!syAllowed()) return false;
  line && line('Looking for wallet sync on your relays…');
  const q = await syQuery({ kinds: SY_KINDS, authors: [syKeys().pk], limit: SY_MAX_EVENTS }, SY_KINDS, 8000, syRelays(), 1500);
  if (!q.answered) return false;
  const rd = syRead(q);
  syRestoreMarks = new Set(rd.gone.keys());
  return !!rd.wallet;
}

/* ---------- on, off, and deleting what was published ---------- */
function syToggled(on) {
  if (syDecoy()) {   // the duress PIN's wallet: looks like a wallet whose relays don't answer; nothing is read or sent
    clearTimeout(syDecoyT); syState = on ? 'busy' : null;
    if (on) syDecoyT = setTimeout(() => { if (S.prefs.sync === true) { syState = 'failed'; refresh(); } }, 6000 + Math.floor(Math.random() * 2000));
    return;
  }
  if (on && !syAllowed()) { S.prefs.sync = false; save(); return; }
  syState = null; syView = null; syLocal = null;
  if (on) { syState = 'busy'; syRun('on').then(() => refresh()).catch(() => {}); }
  else openSyncOff();
}
function openSyncOff() {
  if (!S.prefs.syncSt) return;
  openSheet('Wallet sync is off', `<p style="margin:0">NUTCADE no longer publishes or reads your coins on your relays. Your coins stay in this wallet.</p>
    <div class="notice">The encrypted copies already on your relays stay there unless you delete them. A device that still has sync on publishes its own again.</div>
    <button class="btn block gold" data-act="syncDelete">Delete them from my relays</button><button class="btn block" data-act="close">Keep them</button><div id="sheetErr"></div>`);
}
// kind 5 for every event of ours we can read (coins and wallet); the coins in this wallet are never touched
async function syDeleteAll() {
  if (!syAllowed() || writeGuard.paused) return 0;
  const k = syKeys(), rl = syRelays();
  const q = await syQuery({ kinds: [7375, 17375, 7376], authors: [k.pk], limit: SY_MAX_EVENTS }, [7375, 17375, 7376], 8000, rl, 1500);
  if (!q.answered) throw new Error("Couldn't reach your relays. Nothing was deleted. Try again in a moment.");
  const mine = q.evs.filter(e => syDec(e.content) != null);
  const ts = syNextTs(Math.max(0, ...mine.map(e => e.created_at)));
  const ids = mine.filter(e => e.kind !== 17375).map(e => e.id);
  let ok = true;
  for (let i = 0; i < Math.max(1, ids.length); i += SY_DEL) {
    const tags = ids.slice(i, i + SY_DEL).map(x => ['e', x]).concat(i === 0 ? [['a', `17375:${k.pk}:`], ['k', '17375']] : [], [['k', '7375']]);
    if (!await relayPublish(L.finalizeEvent({ kind: 5, created_at: ts, tags, content: '' }, k.sk), 7000, rl, 1500)) ok = false;
  }
  if (!ok) throw new Error("A relay didn't confirm the deletion. Try again in a moment.");
  delete S.prefs.syncSt; S.prefs.syncOther = []; syView = null; save();
  return mine.length;
}
function sySettingsHTML() {
  const on = S.prefs.sync === true && !!S.seed;
  const st = syDecoy() ? (syState === 'busy' ? 'SYNCING…' : 'RELAYS DIDN\'T ANSWER') : syState === 'busy' ? 'SYNCING…' : syState === 'failed' ? 'RELAYS DIDN\'T ANSWER' : syView ? 'IN SYNC' : 'NOT YET';
  const other = on && !syDecoy() ? (S.prefs.syncOther || []).filter(u => typeof u === 'string').slice(0, SY_OTHER) : [];
  const left = on && syLastRes && !syDecoy() ? syLastRes.unchecked + syLastRes.pending : 0;
  return toggle('sync', 'Sync this wallet across devices', "Keeps your coins the same on every device that has your 12 words and this switch on. Your coins are kept on your Nostr relays, encrypted with a key made from your 12 words; each mint checks every coin before it counts. Relays can still see how many events you publish, how big they are and when: use your own relays if you can. It doesn't work with other wallets' sync (cashu.me, Minibits). Off by default.")
    + (on ? `<div class="row between tiny"><span>Wallet sync</span><span style="color:${st === 'IN SYNC' ? 'var(--lime)' : 'var(--gold)'}">${st}</span></div>`
      + other.map(u => `<div class="notice">Coins for a mint you don't use were found on your relays. NUTCADE doesn't add mints by itself: add it if you trust it, then sync again.</div><div class="tiny" data-noi18n>${esc(host(u))}</div><button class="btn sm" data-act="syncAddMint" data-u="${esc(u)}">Add this mint</button>`).join('')
      + (left ? `<div class="tiny muted">Some coins on your relays couldn't be checked with their mint yet: ${left}. NUTCADE tries again next time.</div>` : '')
      + `<button class="btn sm" data-act="syncNow">Sync now</button>`
      : (S.prefs.syncSt && !syDecoy() ? `<button class="btn sm" data-act="syncDelete">Delete synced coins from my relays</button>` : ''));
}
window.NutSync = {
  pk: () => syKeys().pk, on: () => syOn(), live: () => syLive(), pull: () => syRun('manual'), push: () => syPush(), last: () => syLastRes,
  state: () => ({ st: syState, at: syPullAt, view: syView ? { live: syView.live.map(e => e.id), wallet: !!syView.wallet, sure: syView.sure, gone: syView.gone.size } : null, other: S.prefs.syncOther || [], next: syNext }),
  states: (url, ps) => getWallet(url).then(w => w.checkProofsStates(ps)).then(s => s.map(x => x && x.state)), del: () => syDeleteAll(), hash: s => syHash(s),
  offline: (amount, note) => sendOffline(amount, note || '')   // (tests: the offline send, which hands out the very coins)
};
