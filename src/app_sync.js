/* ===================== Wallet sync (1.30, a subset of NIP-60) ===================== */
/* Two or more devices with the same 12 words keep the same coins, through your Nostr relays, with THE MINT AS REFEREE.
   Opt-in ("Sync this wallet across devices", Settings, Privacy), off by default, per wallet (never in backup files).
   - Key: a dedicated Nostr key, sha256(seed ‖ "nutcade-nip60") (like the mint-list backup key), never your public Nostr
     identity. Every event is signed with it and its content NIP-44 encrypted to itself, so relays see only that some key
     publishes some events (how many, how big, when).
   - Events (NIP-60 shapes): kind 7375 holds your coins at one mint, {mint, unit: "sat", proofs, del: [ids it replaces]}, at
     most SY_PER_EV coins an event; kind 17375 (replaceable) holds the wallet: ["privkey", the nutzap receiving key (NIP-61,
     as NIP-60 says)], ["mint", url] for each mint, and NUTCADE's own tags (not NIP-60): ["counter", keyset, n] (NUT-13
     counters, merged highest-wins, so devices rarely reuse each other's counters), ["gone", h, time] (h: sha256 of a coin's
     secret, cut to 32 hex) for coins this wallet handed out in a token nobody has claimed yet (an offline send keeps the
     very coins: the other device must not count or spend them). Kind 5 deletes only our own events (the sync key's), and
     only ones NUTCADE read and accounted for. Events we cannot decrypt or read are never touched. No kind 7376 history.
     Interop with cashu.me or Minibits is NOT a goal (they use another key) and nothing here reads their events.
   - Reading (pulling): at start, when the tab comes back (at most once a minute), every SY_PERIOD, after an "already
     spent" error and on "Sync now". Every event is checked: the sync key's signature, its size, its content decrypts and
     has the right shape (mint, at most SY_MAX_PROOFS coins, each with an id, an amount that is a power of two, a secret of
     at most SY_SECRET characters that is not a locked (NUT-10) secret, a C point and a DLEQ proof). A coin is never
     counted until (1) it is at a mint already in your list (another mint is only shown, with a question; never added by
     itself), (2) its keyset and amount are that mint's, (3) its DLEQ proof (NUT-12) checks against the mint's saved key,
     so a made-up coin is never adopted, and (4) the mint (checkstate, NUT-07) says it is UNSPENT. SPENT ones are left out
     for good; PENDING ones and ones the mint can't answer for are looked at again next time. Coins this wallet holds,
     handed out, has in a step still open, set aside or in Extra Life are never added again. At most SY_ADOPT coins a run.
     The merge is a set keyed by the secret: the same event twice, events in any order or an old event replayed change
     nothing. A coin we hold that no event lists any more makes us ask the mint (pruneSpent: spent coins dropped with a
     line, as always); a "gone" mark from our other device drops the coin with a line ("Sent from your other device").
   - Writing (pushing): after the money step that changed your coins at a mint has settled (no journal record open there),
     debounced: never inside a payment, and a failure never blocks or breaks one (retried with backoff). A mint's coins are
     published again when the relays don't list them all, or when an event lists coins this wallet no longer has (spent,
     handed out); the new events come first, then the kind 5 deletion of the events they replace (ours, and any other
     device's whose every coin we hold or know to be spent or handed out). Nothing is published before a successful read
     in this session, so a wallet event is always merged with the one on the relays first.
   - Two devices spending the same coin at once: the mint takes one; the other gets "already spent", and spentRetry /
     pruneSpent drop the spent coins there (nothing new here). A coin handed out offline by one device and spent by the
     other before it heard about it: the mint lets only one through (the token's receiver may find it already spent).
   The duress PIN's wallet never reads or publishes (its switch looks like a wallet whose relays don't answer). A paused
   tab (open elsewhere) does nothing. */
const SY_TAG = 'nutcade-nip60';
const SY_PER_EV = 60, SY_MAX_PROOFS = 100, SY_MAX_EVENTS = 300, SY_MAX_BYTES = 120000, SY_ADOPT = 200, SY_SECRET = 512;
const SY_GONE = 400, SY_GONE_AGE = 30 * 86400, SY_FOCUS = 60e3, SY_PERIOD = 10 * 60e3, SY_OTHER = 5, SY_DEL = 100, SY_CTRS = 64, SY_MINTS = 20;
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
// a coin as an event wrote it, checked for shape only (null: the whole event is ignored)
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
// coins this wallet handed out in a token nobody has claimed yet (hashed): the "gone" marks it publishes
// a counters-only repair scan (app.js restoreFromMintNow): with sync on, what it finds is the other device's
function syRepairOnly() { try { if (syOn()) { sySoon(); return true; } } catch (e) {} return false; }
// a coin our other device handed out in a token (its "gone" mark, from the last read)
function syGone(s) { try { return !!(syView && syView.wallet && syView.wallet.gone.has(syHash(s))); } catch (e) { return false; } }
const syOwnGone = () => S.txs.filter(t => t.type === 'out' && t.status === 'pending' && Array.isArray(t.sent)).flatMap(t => t.sent.map(p => p && p.secret ? syHash(p.secret) : null)).filter(Boolean).slice(0, SY_GONE);

/* ---------- what the last read found (memory only: every session reads before it writes) ---------- */
let syView = null;   // { live: [{ id, url, at, secrets: Set }], wallet: { at, id, counters, gone: Map, mints: [] } | null }
let syState = null, syPullAt = 0, syLastRes = null, syNext = 0, syTries = 0, syDecoyT = 0, syTimer = 0;
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
  if (!Array.isArray(c) || c.length > 1000) return null;
  const w = { at: num(e.created_at), id: e.id, counters: {}, gone: new Map(), mints: [] };
  for (const t of c) {
    if (!Array.isArray(t) || typeof t[0] !== 'string') continue;
    if (t[0] === 'mint' && typeof t[1] === 'string' && t[1].length <= 300 && /^https?:\/\/[^\s]+$/i.test(t[1]) && w.mints.length < SY_MINTS) { const u = normUrl(t[1]); if (!w.mints.includes(u)) w.mints.push(u); }
    else if (t[0] === 'counter' && typeof t[1] === 'string' && /^[0-9a-f]{16,66}$/i.test(t[1]) && Object.keys(w.counters).length < SY_CTRS) { const n = Number(t[2]); if (Number.isSafeInteger(n) && n >= 0 && n < 2 ** 31) w.counters[t[1]] = Math.max(w.counters[t[1]] || 0, n); }
    else if (t[0] === 'gone' && typeof t[1] === 'string' && /^[0-9a-f]{32}$/.test(t[1]) && w.gone.size < SY_GONE) { const ts = Number(t[2]); if (Number.isSafeInteger(ts) && ts > 0) w.gone.set(t[1], Math.max(w.gone.get(t[1]) || 0, ts)); }
  }
  return w;
}

// the newest wallet event on the relays that we can read (null: none, or the relays didn't answer)
async function syWalletLatest(k, rl) {
  const got = await relayQuery({ kinds: [17375], authors: [k.pk], limit: 5 }, 6000, rl, 1000);
  for (const e of got.filter(e => e && e.pubkey === k.pk && e.kind === 17375 && Number.isSafeInteger(e.created_at) && typeof e.content === 'string' && e.content.length <= SY_MAX_BYTES).sort((a, b) => b.created_at - a.created_at || (a.id < b.id ? -1 : 1))) {
    if (!L.verifyEvent(e)) continue;
    const w = syWalletOf(e, syDec(e.content)); if (w) return w;
  }
  return null;
}

/* ---------- reading ---------- */
async function syPullNow(why) {
  if (!syLive()) return null;
  const k = syKeys(), rl = syRelays(); if (!rl.length) return null;
  syState = 'busy';
  const got = await relayQuery({ kinds: [7375, 17375, 5], authors: [k.pk], limit: SY_MAX_EVENTS }, 8000, rl, 1500);
  if (!syLive()) { syState = null; return null; }
  if (!got.answered) { syState = 'failed'; return null; }
  const r = { why, adopted: 0, coins: 0, dropped: 0, spent: 0, pending: 0, unchecked: 0, bad: 0, other: [], live: 0, ids: [] };
  const seen = new Set(), evs = [];
  for (const e of got) {
    if (!e || typeof e !== 'object' || typeof e.id !== 'string' || seen.has(e.id)) continue;
    if (e.pubkey !== k.pk || ![7375, 17375, 5].includes(e.kind) || typeof e.content !== 'string' || e.content.length > SY_MAX_BYTES || !Array.isArray(e.tags) || e.tags.length > 300 || !Number.isSafeInteger(e.created_at) || !L.verifyEvent(e)) { r.bad++; continue; }
    seen.add(e.id); evs.push(e);
  }
  // deletions: kind 5 (e tags; an "a" tag for the wallet event) and the "del" lists of token events, all signed by the sync key
  const deleted = new Set(); let walletDelAt = 0;
  for (const e of evs) if (e.kind === 5) for (const t of e.tags.slice(0, 300)) {
    if (!Array.isArray(t)) continue;
    if (t[0] === 'e' && /^[0-9a-f]{64}$/.test(t[1])) deleted.add(t[1]);
    else if (t[0] === 'a' && t[1] === `17375:${k.pk}:`) walletDelAt = Math.max(walletDelAt, e.created_at);
  }
  const toks = [];
  for (const e of evs.filter(e => e.kind === 7375).sort((a, b) => b.created_at - a.created_at || (a.id < b.id ? -1 : 1)).slice(0, SY_MAX_EVENTS)) {
    const c = syDec(e.content);
    if (!c || typeof c !== 'object' || Array.isArray(c) || typeof c.mint !== 'string' || (c.unit != null && c.unit !== 'sat') || !Array.isArray(c.proofs) || !c.proofs.length || c.proofs.length > SY_MAX_PROOFS) { r.bad++; continue; }
    if (c.del != null && (!Array.isArray(c.del) || c.del.length > SY_DEL || !c.del.every(x => typeof x === 'string' && /^[0-9a-f]{64}$/.test(x)))) { r.bad++; continue; }
    const ps = c.proofs.map(syProof);
    if (ps.some(p => !p) || new Set(ps.map(p => p.secret)).size !== ps.length) { r.bad++; continue; }
    for (const d of c.del || []) deleted.add(d);
    toks.push({ id: e.id, at: e.created_at, mint: c.mint, url: syMint(c.mint), proofs: ps });
  }
  let wallet = null;
  for (const e of evs.filter(e => e.kind === 17375 && e.created_at > walletDelAt).sort((a, b) => b.created_at - a.created_at || (a.id < b.id ? -1 : 1))) {
    const w = syWalletOf(e, syDec(e.content)); if (w) { wallet = w; break; }
    r.bad++;
  }
  const live = toks.filter(t => !deleted.has(t.id));
  r.live = live.length; r.ids = live.map(t => t.id);
  // NUT-13 counters: the highest wins, never lowered
  if (wallet) for (const [id, n] of Object.entries(wallet.counters)) if (n > (S.counters[id] || 0)) { try { await counterSource.advanceToAtLeast(id, n); } catch (e) {} }
  const goneAll = new Map(wallet ? wallet.gone : []);
  for (const h of syOwnGone()) goneAll.set(h, goneAll.get(h) || Math.floor(Date.now() / 1000));
  const other = new Set();
  for (const t of live) if (!t.url && /^https?:\/\/[^\s]+$/i.test(t.mint.trim()) && t.mint.length <= 300) other.add(normUrl(t.mint));
  r.other = [...other].filter(u => !isBlocked(u)).slice(0, SY_OTHER);
  // 1. coins our other device handed out in a token: never counted here
  const own = new Set(syOwnGone());
  for (const m of S.mints) {
    const url = m.url, marks = wallet ? wallet.gone : new Map();
    if (!(S.proofs[url] || []).some(p => marks.has(syHash(p.secret)) && !own.has(syHash(p.secret)))) continue;
    await mintLock(url, async () => {
      const busy = new Set(S.ops.filter(o => o.mint === url).flatMap(o => o.inputs || []));
      const out = (S.proofs[url] || []).filter(p => marks.has(syHash(p.secret)) && !busy.has(p.secret)); if (!out.length) return;
      const ids = new Set(out.map(p => p.secret));
      S.proofs[url] = (S.proofs[url] || []).filter(p => !ids.has(p.secret));
      addTx({ type: 'out', method: 'ecash', amount: sum(out), mint: url, note: 'Sent from your other device (wallet sync)', status: 'done', upkeep: true, sync: 1 });
      r.dropped += sum(out); await saveNow();
    }).catch(() => {});
  }
  // 2. coins we hold that no event lists any more: the mint says which are spent (dropped with a line, as always)
  const liveAt = url => new Set(live.filter(t => t.url === url).flatMap(t => t.proofs.map(p => p.secret)));
  for (const m of S.mints) {
    const url = m.url, mine = S.proofs[url] || []; if (!mine.length || isBlocked(url)) continue;
    const ls = liveAt(url); if (mine.every(p => ls.has(p.secret))) continue;
    try { r.spent += num(await mintLock(url, () => pruneSpent(url))); } catch (e) {}
  }
  // 3. coins we don't have yet: checked, then only those the mint says are unspent
  const cand = new Map();   // url -> Map(secret -> proof)
  let n = 0;
  const heldAt = new Map();
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
      const held = syHeld(url), add = fresh.filter(p => !held.has(p.secret));   // (from the last look to the write, no wait)
      if (!add.length) return;
      S.proofs[url] = (S.proofs[url] || []).concat(plain(add.map(syOut)));
      addTx({ type: 'in', method: 'ecash', amount: sum(add), mint: url, note: 'From your other device (wallet sync)', status: 'done', upkeep: true, sync: 1 });
      r.adopted += sum(add); r.coins += add.length; await saveNow();
    }).catch(() => {});
  }
  if (sySpent.size > 20000) sySpent.clear();
  syView = { at: Date.now(), live: live.filter(t => t.url).map(t => ({ id: t.id, url: t.url, at: t.at, secrets: new Set(t.proofs.map(p => p.secret)) })), wallet };
  syNoteLeft();
  syPullAt = Date.now(); syState = 'ok'; syLastRes = r;
  sySt().at = Math.floor(Date.now() / 1000);
  S.prefs.syncOther = r.other; save();
  if (r.adopted || r.dropped || r.spent) refresh();
  return r;
}

/* ---------- writing ---------- */
const syAcc = (url, lset, goneAll) => s => lset.has(s) || sySpent.has(s) || syLeft.has(s) || goneAll.has(syHash(s));
async function syPushNow() {
  if (!syLive() || !syView) return 0;
  const k = syKeys(), rl = syRelays(); if (!rl.length) return 0;
  syNoteLeft();
  const st = sySt(); let sent = 0, failed = false;
  const goneAll = new Map(syView.wallet ? syView.wallet.gone : []); for (const h of syOwnGone()) goneAll.set(h, 1);
  // deletions still owed from an earlier round
  if (Array.isArray(st.del) && st.del.length) {
    const d = L.finalizeEvent({ kind: 5, created_at: syNextTs(st.delAt), tags: st.del.slice(0, SY_DEL).map(i => ['e', i]).concat([['k', '7375']]), content: '' }, k.sk);
    if (await relayPublish(d, 7000, rl, 1500)) { st.del = st.del.slice(SY_DEL); save(); } else failed = true;
  }
  for (const m of S.mints) {
    const url = m.url;
    if (S.ops.some(o => o.mint === url)) continue;   // (a step still open here: published once it has settled)
    const local = (S.proofs[url] || []).map(syOut), lset = new Set(local.map(p => p.secret)), acc = syAcc(url, lset, goneAll);
    const evs = syView.live.filter(e => e.url === url), ls = new Set(evs.flatMap(e => [...e.secrets]));
    const covered = local.every(p => ls.has(p.secret));
    const stale = evs.some(e => [...e.secrets].some(s => !lset.has(s)) && [...e.secrets].every(acc));
    if (covered && !stale) continue;
    const retire = evs.filter(e => [...e.secrets].every(acc));
    const del = retire.map(e => e.id).slice(0, SY_DEL);
    const ts = syNextTs(Math.max(0, ...retire.map(e => e.at)));
    const chunks = [];
    for (let i = 0; i < local.length; i += SY_PER_EV) chunks.push(local.slice(i, i + SY_PER_EV));
    const made = chunks.map(ch => L.finalizeEvent({ kind: 7375, created_at: ts, tags: [], content: syEnc({ mint: url, unit: 'sat', proofs: ch, del }) }, k.sk));
    const oks = await Promise.all(made.map(e => relayPublish(e, 7000, rl, 1500)));
    made.forEach((e, i) => { if (oks[i]) syView.live.push({ id: e.id, url, at: ts, secrets: new Set(chunks[i].map(p => p.secret)) }); });
    sent += oks.filter(Boolean).length;
    if (oks.some(x => !x)) { failed = true; continue; }   // (nothing replaced: the old events still list every coin)
    if (del.length) {
      syView.live = syView.live.filter(e => !del.includes(e.id));
      st.del = [...new Set((st.del || []).concat(del))].slice(-500); st.delAt = ts;
      const d = L.finalizeEvent({ kind: 5, created_at: ts, tags: del.map(i => ['e', i]).concat([['k', '7375']]), content: '' }, k.sk);
      if (await relayPublish(d, 7000, rl, 1500)) st.del = st.del.filter(i => !del.includes(i)); else failed = true;
    }
    save();
  }
  // the wallet event, merged with the one on the relays (counters highest-wins, gone marks kept for 30 days, mints added).
  // Read again just before it is written, so another device's marks written since our last read are kept
  const wNeed = rw => !rw || Object.entries(S.counters).some(([id, n]) => /^[0-9a-f]{16,66}$/i.test(id) && n > (rw.counters[id] || 0)) || syOwnGone().some(h => !rw.gone.has(h)) || S.mints.some(m => !rw.mints.includes(m.url));
  if (wNeed(syView.wallet)) {   // (only then: a write is coming)
    const latest = await syWalletLatest(k, rl);
    if (latest && (!syView.wallet || latest.at > syView.wallet.at || (latest.at === syView.wallet.at && latest.id !== syView.wallet.id))) syView.wallet = latest;
  }
  const rw = syView.wallet, now = Math.floor(Date.now() / 1000);
  const ctr = Object.assign({}, rw ? rw.counters : {}); for (const [id, n] of Object.entries(S.counters)) if (/^[0-9a-f]{16,66}$/i.test(id) && Number.isSafeInteger(n) && n > 0) ctr[id] = Math.max(ctr[id] || 0, n);
  const gone = new Map([...(rw ? rw.gone : new Map())].filter(([, t]) => now - t < SY_GONE_AGE)); for (const h of syOwnGone()) if (!gone.has(h)) gone.set(h, now);
  const mints = [...new Set(S.mints.map(m => m.url).concat(rw ? rw.mints : []))].slice(0, SY_MINTS);
  if (wNeed(rw)) {
    const g = [...gone].sort((a, b) => b[1] - a[1]).slice(0, SY_GONE), cs = Object.entries(ctr).slice(0, SY_CTRS);
    const content = [['privkey', nzPriv()]].concat(mints.map(u => ['mint', u]), cs.map(([id, n]) => ['counter', id, String(n)]), g.map(([h, t]) => ['gone', h, String(t)]));
    const ts = syNextTs(rw ? rw.at + 1 : 0);
    const ev = L.finalizeEvent({ kind: 17375, created_at: ts, tags: [], content: syEnc(content) }, k.sk);
    if (await relayPublish(ev, 7000, rl, 1500)) { syView.wallet = syWalletOf(ev, content); sent++; } else failed = true;
    save();
  }
  if (failed) { syTries++; syNext = Date.now() + Math.min(30 * 60e3, 30e3 * 2 ** Math.min(syTries - 1, 6)); syState = 'failed'; }
  else { syTries = 0; syNext = 0; if (syState !== 'busy') syState = 'ok'; }
  return sent;
}
// one sync step at a time (reads and writes never overlap)
let syChain = Promise.resolve();
function syQueue(fn) { const r = syChain.catch(() => {}).then(fn); syChain = r.catch(() => {}); return r; }
// read, then write what changed; a write alone needs a read in this session first
function syRun(why) {
  return syQueue(async () => { const r = await syPullNow(why); if (r) { await syPushNow().catch(() => {}); if (syState === 'busy') syState = 'ok'; } return r; });
}
function syPush() { return syQueue(async () => { if (!syView) { const r = await syPullNow('push'); if (!r) return 0; } return syPushNow(); }); }
// called by save(): the coins may have changed; written a moment later (after the money step has settled)
function syDirty() {
  if (!syLive() || syTimer) return;
  syTimer = setTimeout(() => { syTimer = 0; if (syLive() && Date.now() >= syNext) syPush().catch(() => {}); }, 2000);
}
function sySoon(ms) { if (!syLive()) return; setTimeout(() => { if (syLive()) syRun('soon').catch(() => {}); }, ms || 3000); }
// every background round: a read at start and every SY_PERIOD, a write retried after a failure
async function syTick(startup) {
  if (!syLive()) return;
  if (startup || !syView || Date.now() - syPullAt > SY_PERIOD) { await syRun(startup ? 'start' : 'period'); return; }
  if (syNext && Date.now() >= syNext) await syPush();
}
document.addEventListener('visibilitychange', () => { if (!document.hidden && syLive() && Date.now() - syPullAt > SY_FOCUS) sySoon(500); });

/* ---------- restore from the 12 words: the coins on your relays first (the NUT-13 scan still runs after it) ---------- */
async function syRestore(urls, line) {
  if (!syAllowed()) return 0;
  const k = syKeys();
  const evs = await relayQuery({ kinds: [17375], authors: [k.pk], limit: 5 }, 8000, syRelays(), 1500);
  if (!evs.some(e => e && e.pubkey === k.pk && e.kind === 17375 && L.verifyEvent(e) && syWalletOf(e, syDec(e.content)))) return 0;
  S.prefs.sync = true; save();   // (this wallet had sync on: it stays on, and the switch in Settings turns it off)
  line && line('Looking for your coins on your relays…');
  for (const u of urls) if (!S.mints.some(m => m.url === normUrl(u))) { try { await addMint(u, { dropped: true }); } catch (e) {} }
  const r = await syRun('restore').catch(() => null);
  return r ? r.adopted : 0;
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
  const got = await relayQuery({ kinds: [7375, 17375, 7376], authors: [k.pk], limit: SY_MAX_EVENTS }, 8000, rl, 1500);
  if (!got.answered) throw new Error("Couldn't reach your relays. Nothing was deleted. Try again in a moment.");
  const mine = got.filter(e => e && e.pubkey === k.pk && Number.isSafeInteger(e.created_at) && L.verifyEvent(e) && syDec(e.content) != null);
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
  state: () => ({ st: syState, at: syPullAt, view: syView ? { live: syView.live.map(e => e.id), wallet: !!syView.wallet } : null, other: S.prefs.syncOther || [], next: syNext }),
  states: (url, ps) => getWallet(url).then(w => w.checkProofsStates(ps)).then(s => s.map(x => x && x.state)), del: () => syDeleteAll(), hash: s => syHash(s)
};
