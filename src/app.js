/* NUTCADE wallet core + UI */
(function(){
'use strict';
const L = window.CashuLib;
const $ = (s, r=document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = a => a == null ? 0 : (typeof a === 'object' && typeof a.toNumber === 'function') ? a.toNumber() : Number(a) || 0;
const sum = ps => (ps || []).reduce((t, p) => t + num(p.amount), 0);
// Amounts group digits the way the app's language does: 30,000 (English), 30.000 (es, pt, de), 30 000 (fr).
// Only for showing numbers; amounts are always stored, sent and parsed as plain integers.
const numLocale = () => { try { return ({ en: 'en-US', es: 'es-ES', pt: 'pt-BR', de: 'de-DE', fr: 'fr-FR' })[LANG] || 'en-US'; } catch (e) { return 'en-US'; } };
const fmt = n => Math.round(num(n)).toLocaleString(numLocale(), { useGrouping: 'always' });
const fmtEn = n => Math.round(num(n)).toLocaleString('en-US');   // share cards and share text, which are in English
const unitTag = () => (window.NutPrefs && window.NutPrefs.btcSymbol) ? '' : 'SAT';
const money = n => (window.NutPrefs && window.NutPrefs.btcSymbol) ? '₿' + fmt(n) : fmt(n) + ' SAT';
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
// One spelling per mint: lowercase scheme and host, no default port (:443, :80), no trailing slash. The path keeps
// its case, since servers may treat /Mint and /mint differently.
const normUrl = u => {
  u = String(u || '').trim(); if (!/^https?:\/\//i.test(u)) u = 'https://' + u;
  try { const x = new URL(u); return (x.protocol + '//' + x.host + x.pathname + x.search).replace(/\/+$/, ''); } catch (e) { return u.replace(/\/+$/, ''); }
};
const host = u => { try { const x = new URL(u); return x.host + (x.pathname === '/' ? '' : x.pathname); } catch (e) { return u; } };
const plain = ps => (ps || []).map(p => { const o = {}; for (const k in p) o[k] = p[k]; o.amount = num(p.amount); return o; });
const hex = b => Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ---------- storage ---------- */
/* Storage. When a PIN is set, the sensitive keys live only inside an encrypted vault:
   AES-GCM with a random data key, which is wrapped by a PIN-derived key (PBKDF2) and,
   optionally, by a passkey PRF secret (Face ID / fingerprint). */
/* With a PIN set, plain storage holds only what belongs to the device, never to a wallet: the vault record itself,
   wrong-PIN tries and PIN changes, the display settings, the arcade's tables and pad. Everything of a wallet (its mint
   list, counters, settings like the Lightning address, trophies, logs...) is read from and written to the encrypted
   part of the vault that is open (the real wallet's, or the duress PIN's: see "duress PIN" in app_r8.js), and while
   it is locked nothing of a wallet is read or written at all. So storage looks the same whichever wallet is open, and
   with or without a duress PIN. */
const DEVICE_KEYS = new Set(['vault', 'pinfails', 'pinchg', 'gen', 'probe', 'pad', 'initials', 'priceRange']);
const devKey = k => DEVICE_KEYS.has(k) || /^scores:/.test(k);
const lsGet = (k, d) => { try { const v = localStorage.getItem('nutcade:' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem('nutcade:' + k, JSON.stringify(v)); return true; } catch (e) { return false; } };
const lsDel = k => { try { localStorage.removeItem('nutcade:' + k); } catch (e) {} };
// the settings that belong to a wallet, not to the device (with a PIN they live in the vault)
const WALLET_PREFS = ['npc', 'npcMint', 'npcSince', 'npcName', 'mintBackupAt', 'mintBackupList', 'nostrBackup', 'nostrInbox', 'dmSince', 'checkSent', 'piggy', 'piggyStep'];
const devPrefs = p => { const o = {}; for (const k of Object.keys(p || {})) if (!WALLET_PREFS.includes(k)) o[k] = p[k]; return o; };
const walletPrefs = p => { const o = {}; for (const k of Object.keys(p || {})) if (WALLET_PREFS.includes(k)) o[k] = p[k]; return o; };
const inVault = k => vault.on && !devKey(k);
const raw = {
  get(k, d) {
    if (k === 'prefs' && vault.on) return Object.assign(devPrefs(lsGet('prefs', {})), vault.open ? JSON.parse(JSON.stringify(vault.data.prefs || {})) : {});
    if (inVault(k)) { const v = vault.open ? vault.data[k] : undefined; return v === undefined || v === null ? d : JSON.parse(JSON.stringify(v)); }
    return lsGet(k, d);
  },
  set(k, v) {
    if (k === 'prefs' && vault.on) { if (writeGuard.paused) return false; if (vault.open) { vault.data.prefs = walletPrefs(v); queueVaultWrite(); } return lsSet('prefs', devPrefs(v)); }
    if (inVault(k)) { if (!vault.open || writeGuard.paused) return false; vault.data[k] = v === undefined ? null : JSON.parse(JSON.stringify(v)); queueVaultWrite(); return true; }
    return lsSet(k, v);
  },
  del(k) { if (inVault(k)) { if (vault.open && !writeGuard.paused) { delete vault.data[k]; queueVaultWrite(); } return; } lsDel(k); }
};
// everything that holds ecash, keys or anything that can spend: with a PIN, only inside the encrypted vault
const VAULT_KEYS = ['seed', 'proofs', 'pending', 'quotes', 'txs', 'p2pk', 'requests', 'contacts', 'nwc', 'ops', 'extra', 'hunts', 'found', 'imports', 'limits'];
const vault = { on: false, open: false, data: {}, dek: null, chain: Promise.resolve(), queued: false, decoy: false };
vault.on = raw.get('vault', null) != null;
// A tab paused because NUTCADE opened in another tab never writes the wallet again: work it still had in flight can't
// overwrite what the active tab saved. (Counters still advance, so no secret is ever issued twice.)
const writeGuard = { paused: false };
const pausedErr = () => Object.assign(new Error('NUTCADE is open in another tab.'), { paused: true, asked: true });
/* Every request to a mint has a time limit, so one mint that accepts a request and never answers can't hold anything
   else up: 20 s, or 2 minutes for a payment (a Lightning payment can take a while). A request cut off this way is
   a lost answer, which the records below settle with the mint afterwards. */
const MINT_MS = 20000, MELT_MS = 120000, STEP_MS = 150000;
{
  const _fetch = window.fetch && window.fetch.bind(window);
  if (_fetch) window.fetch = (input, init) => {
    const u = String(typeof input === 'string' ? input : (input && input.url) || '').split('?')[0];
    if (!/\/v1\/(info|keys|keysets|swap|mint|melt|checkstate|restore)\b/.test(u)) return _fetch(input, init);
    // A paused tab (NUTCADE opened in another tab) asks a mint nothing more: not even the next step of something it
    // started, whose result it could never write down. The tab in charge settles what it left, from its records.
    if (writeGuard.paused) return Promise.reject(pausedErr());
    const ms = /\/v1\/melt\/(bolt11|onchain)$/.test(u) ? MELT_MS : MINT_MS, ac = new AbortController(), t = setTimeout(() => ac.abort(new Error("The mint didn't answer in time.")), ms);
    const sig = init && init.signal; if (sig) { if (sig.aborted) ac.abort(); else sig.addEventListener('abort', () => ac.abort(), { once: true }); }
    return _fetch(input, Object.assign({}, init, { signal: ac.signal })).finally(() => clearTimeout(t));
  };
}
const store = {
  get(k, d) { if (vault.on && VAULT_KEYS.includes(k)) return vault.open && vault.data[k] !== undefined ? vault.data[k] : d; return raw.get(k, d); },
  set(k, v) {
    if (writeGuard.paused && k !== 'counters') return false;
    if (vault.on && VAULT_KEYS.includes(k)) { if (!vault.open) return false; vault.data[k] = v; queueVaultWrite(); return true; }
    return raw.set(k, v);
  }
};
// (in slices: spreading a large buffer into one call overflows the stack, and the vault holds the whole wallet)
const b64e = u8 => { const a = new Uint8Array(u8); let s = ''; for (let i = 0; i < a.length; i += 0x8000) s += String.fromCharCode.apply(null, a.subarray(i, i + 0x8000)); return btoa(s); };
const b64d = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const rnd = n => crypto.getRandomValues(new Uint8Array(n));
const PBKDF2_ITER = 600000;
async function kekFromPin(pin, salt, iter) {
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(String(pin)), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'PBKDF2', salt, iterations: iter, hash: 'SHA-256' }, base, { name: 'AES-GCM', length: 256 }, false, ['wrapKey', 'unwrapKey']);
}
async function kekFromSecret(secret) {
  const base = await crypto.subtle.importKey('raw', secret, 'HKDF', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: new TextEncoder().encode('nutcade-vault-v1'), info: new TextEncoder().encode('passkey') }, base, { name: 'AES-GCM', length: 256 }, false, ['wrapKey', 'unwrapKey']);
}
async function wrapDek(dek, kek) { const iv = rnd(12); const ct = await crypto.subtle.wrapKey('raw', dek, kek, { name: 'AES-GCM', iv }); return { iv: b64e(iv), ct: b64e(ct) }; }
async function unwrapDek(w, kek) { return crypto.subtle.unwrapKey('raw', b64d(w.ct), kek, { name: 'AES-GCM', iv: b64d(w.iv) }, { name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']); }
async function sealData() {
  const iv = rnd(12);
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, vault.dek, new TextEncoder().encode(JSON.stringify(vault.data)));
  const rec = raw.get('vault', null), box = { iv: b64e(iv), ct: b64e(ct) };
  if (!rec) return;   // (the vault was removed, by Remove PIN or a reset: a write still queued never brings it back)
  if (vault.decoy) { if (!rec.slot) throw new Error("This browser won't save data."); rec.slot.data = box; } else rec.data = box;
  if (!raw.set('vault', rec)) throw new Error("This browser won't save data.");
}
function queueVaultWrite() {
  if (vault.queued) return; vault.queued = true;
  vault.chain = vault.chain.then(() => { vault.queued = false; return sealData(); }).catch(() => { vault.queued = false; });
}
async function openVault(dek) {
  const rec = raw.get('vault'), box = vault.decoy ? rec.slot.data : rec.data;
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(box.iv) }, dek, b64d(box.ct));
  vault.data = JSON.parse(new TextDecoder().decode(pt)); vault.dek = dek; vault.open = true;
}
async function createVault(pin) {
  const dek = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']);
  const salt = rnd(16), kek = await kekFromPin(pin, salt, PBKDF2_ITER);
  vault.data = plainWalletData(); for (const k of VAULT_KEYS) vault.data[k] = S[k] !== undefined ? S[k] : null;
  vault.dek = dek;
  if (!raw.set('vault', { v: 1, kdf: { alg: 'PBKDF2-SHA256', iter: PBKDF2_ITER, salt: b64e(salt) }, pin: await wrapDek(dek, kek), slot: fillerSlot() })) throw new Error("This browser won't save data.");
  await sealData();
  // prove it decrypts before deleting the plain copies
  const check = await unwrapDek(raw.get('vault').pin, kek); const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(raw.get('vault').data.iv) }, check, b64d(raw.get('vault').data.ct));
  if (JSON.parse(new TextDecoder().decode(pt)).seed?.mnemonic !== S.seed?.mnemonic) throw new Error('Encryption check failed. Your wallet was not changed.');
  vault.on = true; vault.open = true;
  clearPlainWallet();
  if (lsGet('pinchg', null) == null) lsSet('pinchg', []);
}
// every record of the wallet kept in plain storage (no PIN), and clearing them once they are in the vault
function plainWalletData() {
  const d = {};
  for (let i = 0; i < localStorage.length; i++) { const key = localStorage.key(i); if (!key || !key.startsWith('nutcade:')) continue; const k = key.slice(8); if (devKey(k) || k === 'prefs') continue; d[k] = lsGet(k, null); }
  d.prefs = walletPrefs(lsGet('prefs', {}));
  return d;
}
function clearPlainWallet() {
  const ks = []; for (let i = 0; i < localStorage.length; i++) { const key = localStorage.key(i); if (key && key.startsWith('nutcade:') && !devKey(key.slice(8)) && key !== 'nutcade:prefs') ks.push(key.slice(8)); }
  for (const k of ks) lsDel(k);
  lsSet('prefs', devPrefs(lsGet('prefs', {})));
}
// the data key of the wallet that is open (the real one, or the duress PIN's), from its PIN
async function pinToDek(pin) {
  const rec = raw.get('vault'), part = vault.decoy ? rec.slot : rec;
  const kek = await kekFromPin(pin, b64d(part.kdf.salt), part.kdf.iter);
  try { return await unwrapDek(part.pin, kek); } catch (e) { return null; }
}
// (the PIN of the wallet that is open: with the duress PIN's wallet open, that wallet's PIN)
async function changePin(oldPin, newPin) {
  const dek = await pinToDek(oldPin); if (!dek) throw new Error('Current PIN is wrong.');
  if (!vault.decoy && await slotOpens(newPin)) throw new Error("Pick a PIN that isn't your duress PIN.");
  if (vault.decoy && await realOpens(newPin)) throw pinChangeRefuse();   // (never a PIN of the thief's choosing that opens the real wallet)
  const salt = rnd(16), kek = await kekFromPin(newPin, salt, PBKDF2_ITER);
  const rec = raw.get('vault'), part = vault.decoy ? rec.slot : rec;
  part.kdf = { alg: 'PBKDF2-SHA256', iter: PBKDF2_ITER, salt: b64e(salt) }; part.pin = await wrapDek(dek, kek);
  raw.set('vault', rec);
}
async function removeVault(pin) {
  const dek = await pinToDek(pin); if (!dek) throw new Error('PIN is wrong.');
  if (vault.decoy) throw pinChangeRefuse();   // (that would mean writing over the device's storage)
  if (vault.data.duress) await duressOff().catch(() => 0);   // the duress PIN's wallet lives inside the vault: its sats come back here first
  await vault.chain;
  delete vault.data.duress;
  const d = vault.data;
  vault.on = false; vault.open = false; vault.dek = null; vault.data = {};
  for (const k of Object.keys(d)) { if (k === 'prefs' || d[k] == null) continue; lsSet(k, d[k]); }
  lsSet('prefs', Object.assign(devPrefs(lsGet('prefs', {})), walletPrefs(d.prefs || {})));
  lsDel('vault');
}
const pinFails = () => raw.get('pinfails', { n: 0, until: 0 });
function notePinFail() { const f = pinFails(); f.n++; if (f.n >= 5) f.until = Date.now() + Math.min(15 * 60e3, 30e3 * 2 ** (f.n - 5)); raw.set('pinfails', f); return f; }

const S = {
  mints: store.get('mints', []),          // [{url,name,methods:{mint:[],melt:[]}}]
  active: store.get('active', null),
  proofs: store.get('proofs', {}),        // url -> proofs
  pending: store.get('pending', []),      // [{id,mint,proofs,quote,kind,txId}]
  txs: store.get('txs', []),              // newest first
  quotes: store.get('quotes', []),        // pending mint quotes
  prefs: store.get('prefs', { sound: true, crt: true })
};
S.seed = store.get('seed', null);        // {mnemonic, backedUp, created}
S.ops = store.get('ops', []);            // swaps written down before the mint is asked (see "the operation journal")
S.opsdone = store.get('opsdone', []);    // ids of the last records settled here (an imported backup never settles one twice)
S.counters = store.get('counters', {});  // keysetId -> next counter (NUT-13)
/* Older versions kept a mint's URL as typed, so HTTP://Mint.example and http://mint.example could be saved as two
   mints. On load every saved URL is respelled with normUrl and such twins are merged into one: their ecash is
   combined (each coin once), and every stored record that names a mint points at the merged one: history,
   pending payments, quotes, payment requests, Extra Life, heirlooms, challenges and bounties, treasure hunts and
   the mint report log. Nothing is lost. It runs once everything is loaded (and again when the PIN vault opens). */
function mergeMintSpellings() {
  let changed = false; const seen = new Map(), fix = u => { if (typeof u !== 'string' || !u) return u; const n = normUrl(u); if (n !== u) changed = true; return n; };
  for (const m of S.mints) { const u = fix(m.url); if (seen.has(u)) { changed = true; continue; } seen.set(u, Object.assign(m, { url: u })); }
  S.mints = [...seen.values()];
  const proofs = {};
  for (const [u, ps] of Object.entries(S.proofs || {})) { const k = fix(u), have = proofs[k] || (proofs[k] = []), ids = new Set(have.map(p => p.secret)); for (const p of ps || []) if (!ids.has(p.secret)) { have.push(p); ids.add(p.secret); } }
  if (changed) S.proofs = proofs;
  S.active = fix(S.active);
  // any record, at any depth, with a "mint" field or a "mints" list
  const walk = (o, d) => {
    if (!o || typeof o !== 'object' || d > 5) return;
    if (Array.isArray(o)) { for (const x of o) walk(x, d + 1); return; }
    for (const k of Object.keys(o)) {
      if (k === 'mint' && typeof o[k] === 'string' && /^https?:/i.test(o[k])) o[k] = fix(o[k]);
      else if (k === 'mints' && Array.isArray(o[k]) && o[k].every(x => typeof x === 'string')) { const n = [...new Set(o[k].map(fix))]; if (n.length !== o[k].length) changed = true; o[k] = n; }
      else if (k !== 'proofs' && k !== 'sent' && o[k] && typeof o[k] === 'object') walk(o[k], d + 1);
    }
  };
  const stores = { pending: S.pending, quotes: S.quotes, txs: S.txs, ops: S.ops, requests: S.requests, extra: S.extra, heirlooms: S.heirlooms, challenges: S.challenges, hunts: S.hunts, found: S.found };
  for (const v of Object.values(stores)) walk(v, 0);
  if (S.mintlog) for (const u of Object.keys(S.mintlog)) {   // the mint report's log is keyed by URL: twins' logs are combined
    const n = fix(u); if (n === u) continue;
    const a = S.mintlog[n], b = S.mintlog[u];
    S.mintlog[n] = !a ? b : Object.assign(a, { first: Math.min(a.first || Infinity, b.first || Infinity), ms: (a.ms || []).concat(b.ms || []).slice(-50), ops: [(a.ops || [0, 0])[0] + (b.ops || [0, 0])[0], (a.ops || [0, 0])[1] + (b.ops || [0, 0])[1]], keysets: Object.assign({}, b.keysets, a.keysets), changes: (b.changes || []).concat(a.changes || []) });
    delete S.mintlog[u];
  }
  if (!changed) return;
  save();
  for (const k of ['requests', 'extra', 'heirlooms', 'challenges', 'hunts', 'found', 'mintlog']) if (S[k] !== undefined) store.set(k, S[k]);
}
let storageOk = store.set('probe', 1);
// every save stamps a generation number: a tab that sees someone else's stamp re-reads the wallet before working on it
let myGen = raw.get('gen', 0);
function save() {
  if (writeGuard.paused) return;
  for (const k of ['mints', 'active', 'proofs', 'pending', 'txs', 'quotes', 'prefs', 'ops', 'opsdone']) storageOk = store.set(k, S[k]) && storageOk;
  myGen = (raw.get('gen', 0) || 0) + 1; raw.set('gen', myGen);
}
async function syncIfStale() {
  if ((raw.get('gen', 0) || 0) === myGen) return;
  if (vault.on) { if (!vault.open || !vault.dek) return; await vault.chain; await openVault(vault.dek); const d = vault.data; S.proofs = d.proofs || {}; S.pending = d.pending || []; S.txs = d.txs || []; S.quotes = d.quotes || []; S.ops = d.ops || []; S.extra = d.extra || null; }
  else { S.proofs = raw.get('proofs', {}); S.pending = raw.get('pending', []); S.txs = raw.get('txs', []); S.quotes = raw.get('quotes', []); S.ops = raw.get('ops', []); S.extra = raw.get('extra', null); }
  S.opsdone = raw.get('opsdone', []);
  const c = raw.get('counters', {}); for (const k in c) S.counters[k] = Math.max(S.counters[k] || 0, c[k] || 0);
  myGen = raw.get('gen', 0) || 0;
}

/* ---------- recovery phrase (NUT-13 deterministic secrets) ---------- */
let seedBytes = null;
function seedFor() {
  if (!S.seed) throw new Error('Set up your recovery phrase first.');
  if (!seedBytes) seedBytes = L.mnemonicToSeedSync(S.seed.mnemonic);
  return seedBytes;
}
function persistCounters() {
  // Counters must be on disk before blinded messages go to a mint, or the same secret could be issued twice.
  if (!store.set('counters', S.counters)) throw new Error("This browser won't save data, so NUTCADE stopped before using your recovery phrase. Open it in a normal browser tab.");
}
// (the duress PIN's wallet keeps its counters inside its encrypted part: written before anything goes to a mint)
const persistCountersNow = async () => { persistCounters(); if (vault.on) await vault.chain; };
const counterSource = {
  async reserve(id, n) { const start = S.counters[id] || 0; if (n > 0) { S.counters[id] = start + n; await persistCountersNow(); } return { start, count: n }; },
  async reserveAt(id, start, count) { const cur = S.counters[id] || 0; if (start < cur) throw new Error('Counter range already used.'); S.counters[id] = start + count; await persistCountersNow(); return { start, count }; },
  async advanceToAtLeast(id, minNext) { if ((S.counters[id] || 0) < minNext) { S.counters[id] = minNext; await persistCountersNow(); } },
  async snapshot() { return Object.assign({}, S.counters); },
  async setNext(id, next) { S.counters[id] = next; await persistCountersNow(); }
};
function setSeed(mnemonic, backedUp) {
  const changed = !S.seed || S.seed.mnemonic !== mnemonic;
  S.seed = { mnemonic, backedUp: !!backedUp, created: Date.now() };
  seedBytes = null;
  if (changed && S.prefs) { S.prefs.npc = false; S.prefs.npcSince = 0; S.prefs.npcName = ''; S.prefs.mintBackupAt = 0; S.prefs.mintBackupList = ''; if (typeof npcSocketStop === 'function') npcSocketStop(); }
  for (const k in wallets) delete wallets[k];
  if (!store.set('seed', S.seed)) throw new Error("This browser won't save data. Open NUTCADE in a normal browser tab.");
  requestPersist();
}
const newMnemonic = () => L.generateMnemonic(L.wordlist, 128);
const cleanPhrase = s => String(s || '').toLowerCase().replace(/[^a-z\s]/g, ' ').trim().split(/\s+/).filter(Boolean).join(' ');
const validPhrase = s => { try { return L.validateMnemonic(cleanPhrase(s), L.wordlist); } catch (e) { return false; } };
let persisted = null;
async function requestPersist() {
  try { if (navigator.storage && navigator.storage.persist) { persisted = await navigator.storage.persisted() || await navigator.storage.persist(); } } catch (e) { persisted = false; }
}
if (S.seed) requestPersist();

/* Swap every proof a mint holds into fresh outputs derived from the current phrase. */
function secureMint(url) { return mintLock(url, () => secureMintNow(url)); }
async function secureMintNow(url) {
  const ps = [...(S.proofs[url] || [])]; if (!ps.length) return 0;
  const w = await getWallet(url), mm = mintMax(url);
  if (mm && (ps.length > mm || (smallMint(url) && bitsOf(sum(ps) - feeOfPs(w, ps)) > mm))) {   // more coins than the mint takes at once: in parts
    const parts = tokenParts(w, ps, mm); if (!parts) throw new Error(`${host(url)} takes at most ${mm} coins per request, and these coins can't be moved there in parts that size.`);
    let fee = 0; for (const g of parts) fee += await securePart(url, w, g); return fee;
  }
  return securePart(url, w, ps);
}
async function securePart(url, w, ps) {
  const { r: fresh, op } = await journaled(url, 'swap', { inputs: ps }, (cb, o) => rRecv(o, w, ps, { onCountersReserved: cb }));
  const used = new Set(ps.map(p => p.secret)), fee = sum(ps) - sum(fresh);
  S.proofs[url] = (S.proofs[url] || []).filter(p => !used.has(p.secret)).concat(plain(fresh));
  if (fee > 0) addTx({ type: 'out', method: 'fee', amount: 0, fee, mint: url, note: 'Mint fee for moving ecash under your phrase', status: 'done' });
  closeOp(op); save();
  return fee;
}
async function secureAll(onStep) {
  let fees = 0;
  for (const m of S.mints) { if (!(S.proofs[m.url] || []).length) continue; onStep && onStep(m); fees += await secureMint(m.url); }
  S.seed.secured = true; store.set('seed', S.seed);
  return fees;
}
/* One scan at a time per mint. A caller that joins a scan already running doesn't lose what it asked for: the
   deposits it brings are added to the ones that scan credits (read when it credits, not when it started), and if
   it joined too late for that, it gets a scan of its own. */
const restoreDeposits = {};
async function restoreFromMint(url, onStep, opts = {}) {
  url = normUrl(url);
  const mine = (opts.deposits || []).map(q => q.quote);
  if (mine.length) { const s = restoreDeposits[url] || (restoreDeposits[url] = new Set()); mine.forEach(id => s.add(id)); }
  const r = await single('restore:' + url, () => restoreFromMintNow(url, onStep, opts));
  if (mine.some(id => S.quotes.some(q => q.quote === id && !(q.empty >= 3)) && (restoreDeposits[url] || new Set()).has(id))) return single('restore:' + url, () => restoreFromMintNow(url, onStep, opts));
  return r;
}
async function restoreFromMintNow(url, onStep, opts) {
  await syncIfStale();
  if (!S.mints.find(m => m.url === url)) await addMint(url);
  const w = await getWallet(url);
  // Coins of a step still open at this mint belong to that step, never to "Recovered": payments (in flight here are
  // waited for; their change goes to them), swaps (settled from their record), deposits with counters on record
  // (left out of this scan; each one settles itself as that deposit).
  for (const p of S.pending.filter(p => p.mint === url && p.id !== opts.except)) await reconcile(p, { force: true }).catch(() => {});
  for (const o of S.ops.filter(o => o.mint === url && o.id !== opts.except)) await settleOp(o.id).catch(() => {});
  const keysets = w.keyChain.getKeysets().filter(k => k.unit === 'sat');
  let found = [];
  for (const k of keysets) {
    onStep && onStep(`Scanning ${host(url)} · keyset ${k.id.slice(0, 8)}…`);
    const r = await w.batchRestore(300, undefined, 0, k.id);
    if (r.lastCounterWithSignature != null) await counterSource.advanceToAtLeast(k.id, r.lastCounterWithSignature + 1);
    if (r.proofs && r.proofs.length) {
      const st = await w.checkProofsStates(r.proofs);
      found = found.concat(r.proofs.filter((p, i) => st[i] && st[i].state === 'UNSPENT'));
    }
  }
  // interrupted deposits from before their counters were recorded (issued by the mint, never stored) get what was
  // found first, each up to its amount; their quotes are then done. Only a deposit made on this device before 1.12
  // can be one: any other deposit without counters never asked the mint for its coins here, so what a scan finds
  // isn't its (it was issued to another device holding this wallet).
  const waiting = [];
  for (const q of S.quotes.filter(q => q.mint === url && q.kind === 'bolt11' && legacyQuote(q))) {
    if ((restoreDeposits[url] || new Set()).has(q.quote) || (opts.deposits || []).some(x => x.quote === q.quote)) { waiting.push(q); continue; }
    const st = await inTime(w.checkMintQuoteBolt11(q.quote), 30000).catch(() => null); if (st && st.state === 'ISSUED') waiting.push(q);
  }
  // The counters of anything open at this mint: its coins stay out of what this scan credits. Worked out last, and
  // again for anything that started meanwhile (a payment made during the scan: its change is its own), so that from
  // the last look to the write nothing waits. (Not the step this scan is repairing: its counters turned out to be
  // used already, by another device with the same phrase, so the coins there are that device's, found here like any
  // others.)
  const ex = opts.except, owned = new Set(), looked = new Set(), rkey = c => `${c.id}:${c.start}:${c.n}`;
  const ranges = () => [].concat(S.pending.filter(p => p.mint === url && p.ctr && !p.changeDone && p.id !== ex).map(p => p.ctr), S.ops.filter(o => o.mint === url && o.id !== ex).flatMap(o => o.ctr), S.quotes.filter(q => q.mint === url && q.ctr && q.quote !== ex).map(q => q.ctr));
  for (let i = 0; i < 5; i++) {
    const todo = ranges().filter(c => !looked.has(rkey(c))); if (!todo.length) break;
    for (const c of todo) { looked.add(rkey(c)); const r = await restoreRange(w, url, c.start, c.n, c.id); for (const p of r.proofs || []) owned.add(p.secret); }
  }
  if (ranges().some(c => !looked.has(rkey(c)))) throw new Error("The mint didn't answer. Try again in a moment.");
  // from here to the write, no wait: not what we hold, nor a token we sent that hasn't been claimed, nor coins of a
  // payment in flight, nor anything an open step owns
  const haveNow = () => new Set((S.proofs[url] || []).map(p => p.secret).concat(S.txs.filter(t => t.status === 'pending').flatMap(t => (t.sent || []).map(p => p.secret)), S.pending.flatMap(p => p.proofs.map(x => x.secret)), S.extra && S.extra.mint === url ? S.extra.proofs.map(p => p.secret) : [], [...owned]));   // (nor the Extra Life's coins)
  let fresh = found.filter(p => !haveNow().has(p.secret));
  if (fresh.length) {   // still unspent now (a coin found early may have been spent since), then the last look, with no wait after it
    const st = await inTime(w.checkProofsStates(fresh), 30000); fresh = fresh.filter((p, i) => st[i] && st[i].state === 'UNSPENT');
    if (ranges().some(c => !looked.has(rkey(c)))) throw new Error("The mint didn't answer. Try again in a moment.");
    const have = haveNow(); fresh = fresh.filter(p => !have.has(p.secret));
  }
  let left = sum(fresh);
  for (const id of [...(restoreDeposits[url] || [])]) if (!S.quotes.some(x => x.quote === id && x.mint === url && !x.ctr)) restoreDeposits[url].delete(id);
  for (const q of waiting) {
    if (!S.quotes.some(x => x.quote === q.quote)) continue;
    const credit = Math.min(left, num(q.amount)); left -= credit;
    if (!credit && (q.empty = (q.empty || 0) + 1) < 3) continue;   // nothing found for it this time: it waits (it is never credited 0 at once)
    updTx(q.txId, { status: 'done', amount: credit, ts: Date.now() }); S.quotes = S.quotes.filter(x => x.quote !== q.quote);
    if (restoreDeposits[url]) restoreDeposits[url].delete(q.quote);
  }
  if (fresh.length) { addProofs(url, fresh); if (left) addTx({ type: 'in', method: 'ecash', amount: left, mint: url, note: 'Recovered with recovery phrase' }); }
  save();
  return sum(fresh);
}

/* Same phrase used on another device can leave our counters behind: the mint answers 11003.
   Catch up by rescanning that mint (which also recovers anything new), then retry once. */
/* A mint that answers a request with an error code (NUT-00) did none of it: it signed nothing for that request. */
const isRefusal = e => !!e && (e.name === 'MintOperationError' || (e.status >= 400 && e.status < 500 && typeof e.code === 'number'));
const isDupOutputs = e => e && (e.code === 11003 || /already signed/i.test(String(e.message || '')));
async function withRepair(url, fn, ropts) {
  try { const r = await fn(); opMark(url, true); return r; }
  catch (e) {
    if (!isDupOutputs(e) || flights.has('restore:' + normUrl(url))) { opMark(url, false, e); throw e; }   // (a scan already running here may be waiting on this very step)
    await restoreFromMint(url, null, ropts);
    const r = await fn(); opMark(url, true); return r;
  }
}

/* ---------- one tab at a time ---------- */
let tabLocked = false;
const TAB_ID = Math.random().toString(36).slice(2);
let chan = null;
try {
  chan = new BroadcastChannel('nutcade-wallet');
  chan.onmessage = e => {
    const m = e.data || {};
    if (m.t === 'hello' && !tabLocked) chan.postMessage({ t: 'busy', id: TAB_ID });
    else if (m.t === 'busy' && m.id !== TAB_ID && !tabLocked && !booted) { tabLocked = true; writeGuard.paused = true; render(); }
    else if (m.t === 'takeover' && m.id !== TAB_ID) { tabLocked = true; writeGuard.paused = true; closeSheet(); if (window.Arcade && window.Arcade.playing()) document.querySelector('[data-g=exit]')?.click(); render(); }
  };
  chan.postMessage({ t: 'hello', id: TAB_ID });
} catch (e) { chan = null; }
let booted = false;
setTimeout(() => { booted = true; }, 600);
window.NutPrefs = S.prefs;
window.NutStore = store;

/* ---------- curated mints ---------- */
const CURATED = [
  { url: 'https://mint.minibits.cash/Bitcoin', name: 'Minibits', blurb: 'Run by the Minibits wallet team.' },
  { url: 'https://mint.cubabitcoin.org', name: 'Cuba Bitcoin', blurb: 'Community mint from Cuba Bitcoin.' },
  { url: 'https://8333.space:3338', name: '8333.space', blurb: 'Long-running public Nutshell mint.' },
  { url: 'https://testnut.cashu.space', name: 'Testnut', blurb: 'Test mint. Invoices pay themselves, sats are fake.', test: true },
  { url: 'https://nofees.testnut.cashu.space', name: 'Testnut (no fees)', blurb: 'Test mint with zero fees. Fake sats.', test: true }
];
const RELAYS = ['wss://relay.damus.io', 'wss://nos.lol', 'wss://relay.primal.net', 'wss://relay.nostr.band', 'wss://relay.cashumints.space'];

/* ---------- wallet instances ---------- */
const wallets = {};
async function getWallet(url) {
  if (wallets[url]) return wallets[url];
  const p = (async () => {
    const w = new L.Wallet(url, { unit: 'sat', bip39seed: seedFor(), counterSource });
    await w.loadMint();
    p.ready = w;   // for the few places that need it without waiting (the cost shown on a pay screen)
    return w;
  })();
  wallets[url] = p;
  try { return await p; } catch (e) { delete wallets[url]; throw friendly(e, url); }
}
function friendly(e, url) {
  if (e && e.keep) return e;   // already a sentence in your language (blocked mints, LNURL services)
  const m = String(e && e.message || e);
  if (/didn't answer in time/i.test(m)) {   // a mint request past its time limit: the mint by its name (never a raw " at <address>")
    const u = (m.match(/ at (https?:\/\/\S+)/) || [])[1] || url;
    const name = u ? ((S.mints.find(x => x.url === normUrl(u)) || {}).name || host(u)) : '';
    return new Error(name ? `${name} didn't answer in time. Try again in a moment.` : "The mint didn't answer in time. Try again in a moment.");
  }
  if (/Failed to fetch|NetworkError|Load failed|network/i.test(m)) {
    const inFrame = window.top !== window.self;
    return new Error(inFrame
      ? `Can't reach ${host(url || '')}. This preview blocks connections to mints. Open the NUTCADE file in a normal browser tab to use real sats.`
      : `Can't reach ${host(url || '')}. Check the address and your connection, then try again.`);
  }
  // A mint's own error text ("mint quote already paid") is shown small under a sentence in your language.
  if (e && !e.raw && (typeof e.code === 'number' || typeof e.status === 'number' || /^[a-z]/.test(m))) {
    const say = /quote.*(already|issued)|already (been )?(paid|issued)/i.test(m) ? 'That invoice was already paid.'
      : /already spent|token.*spent|proofs? (are|is) spent/i.test(m) ? 'This ecash was already spent.'
      : /not paid|unpaid/i.test(m) ? "That invoice hasn't been paid yet."
      : /pending/i.test(m) ? 'The mint says this payment is still pending.'
      : /expired/i.test(m) ? 'That request expired. Start again.'
      : /keyset/i.test(m) ? 'The mint changed its keys. Refresh the mint and try again.'
      : /rate.?limit|too many requests/i.test(m) ? 'The mint is busy. Wait a moment and try again.'
      : /insufficient|not enough|balance/i.test(m) ? "There isn't enough to cover this."
      : 'The mint turned this down.';
    const f = new Error(say); f.raw = m; return f;
  }
  return e instanceof Error ? e : new Error(m);
}
function methodsOf(w) {
  const info = w.getMintInfo();
  const pick = n => { try { const s = info.isSupported(n); return s.disabled ? [] : (s.params || []).filter(m => m.unit === 'sat').map(m => ({ method: m.method, min: m.min_amount == null ? null : num(m.min_amount), max: m.max_amount == null ? null : num(m.max_amount), confirmations: m.options && m.options.confirmations })); } catch (e) { return []; } };
  return { mint: pick(4), melt: pick(5) };
}
const supports = (mint, dir, method) => !!(mint && mint.methods && (mint.methods[dir] || []).some(m => m.method === method));
const methodInfo = (mint, dir, method) => mint && mint.methods && (mint.methods[dir] || []).find(m => m.method === method);

async function addMint(url, opts = {}) {
  url = normUrl(url);
  const w = await getWallet(url);
  const info = w.getMintInfo();
  let m = S.mints.find(x => x.url === url);
  const rec = { url, name: info.name || host(url), desc: info.description || '', methods: methodsOf(w) };
  const isNew = !m;
  if (isNew && belowMin(url)) { const e = new Error(`${rec.name} only accepts ${mintMax(url)} coins per request; NUTCADE needs at least ${MIN_REQ}.`); e.keep = true; delete wallets[url]; throw e; }   // (it couldn't take deposits)
  if (m) Object.assign(m, rec); else { S.mints.push(rec); m = rec; }
  if (!S.proofs[url]) S.proofs[url] = [];
  if (!S.active || opts.activate) S.active = url;
  save();
  if (isNew) scheduleMintBackup();
  return m;
}
const activeMint = () => S.mints.find(m => m.url === S.active) || null;
const balanceOf = url => sum(S.proofs[url]);
const totalBalance = () => S.mints.reduce((t, m) => t + balanceOf(m.url), 0);
const pendingOut = () => S.pending.filter(p => !p.paid).reduce((t, p) => t + sum(p.proofs), 0);

function addTx(t) {
  const tx = Object.assign({ id: uid(), ts: Date.now(), note: '', status: 'done', fee: 0 }, t);
  if (price.rate && price.cur && !tx.fx) tx.fx = { cur: price.cur, rate: price.rate };
  if (internalMove) tx.move = true;
  const ru = piggyRoundUp(tx); if (ru) tx.roundup = ru;
  S.txs.unshift(tx);
  save();
  return tx;
}
const txById = id => S.txs.find(t => t.id === id);
function updTx(id, patch) { const t = txById(id); if (t) Object.assign(t, patch); save(); return t; }
function addProofs(url, ps) {
  const cur = S.proofs[url] || [];
  const seen = new Set(cur.map(p => p.secret));
  for (const p of plain(ps)) if (!seen.has(p.secret)) cur.push(p);
  S.proofs[url] = cur;
  save();
}

/* ---------- RECEIVE ---------- */
async function lnMintQuote(amount, note, url = S.active) {
  if (isBlocked(url)) throw blockedErr(url, 'ln');
  const w = await getWallet(url);
  { const e = quoteFitErr(url, amount); if (e) throw e; }   // (one check before every mint quote: a deposit the mint can't issue is refused before anything is paid)
  const q = await w.createMintQuoteBolt11(amount);
  const tx = addTx({ type: 'in', method: 'ln', amount, mint: url, note, status: 'pending', request: q.request, quote: q.quote });
  S.quotes.push({ kind: 'bolt11', quote: q.quote, request: q.request, amount, mint: url, txId: tx.id, expiry: q.expiry || null, rec: 1 });
  save();
  return tx;
}
async function onchainMintQuote(note) {
  const url = S.active; if (isBlocked(url)) throw blockedErr(url, 'ln'); const w = await getWallet(url);
  const k = new Uint8Array(32); crypto.getRandomValues(k);
  const privkey = hex(k), pubkey = hex(L.getPubKeyFromPrivKey(k));
  { const e = quoteFitErr(url, null); if (e) throw e; }
  const q = await w.createMintQuoteOnchain(pubkey);
  const tx = addTx({ type: 'in', method: 'onchain', amount: 0, mint: url, note, status: 'pending', request: q.request, quote: q.quote });
  S.quotes.push({ kind: 'onchain', quote: q.quote, request: q.request, mint: url, txId: tx.id, privkey, expiry: q.expiry || null });
  save();
  return tx;
}
const busyQuotes = new Set();
// one check per deposit at a time (shared by every caller, and locked across tabs), on the freshest copy of the record
function checkQuote(q) { return single('quote:' + q.quote, () => checkQuoteNow(q.quote, q.txId)); }
async function checkQuoteNow(id, txId) {
  await syncIfStale();
  const q = S.quotes.find(x => x.quote === id);
  if (!q) { const t = txById(txId); return t && t.status === 'done' ? 'paid' : 'gone'; }
  busyQuotes.add(q.quote);
  try {
    const w = await getWallet(q.mint);
    if (q.kind === 'bolt11') {
      const r = await w.checkMintQuoteBolt11(q.quote);
      if (q.state !== r.state) { q.state = r.state; save(); }   // a paid invoice is never offered for paying again
      if ((r.state === 'UNPAID' || r.state === 'PAID') && !q.rec) { q.rec = 1; save(); }   // seen not issued yet: if it is issued later, only from counters on its record
      if (r.state === 'PAID') {
        let cfg;
        if (r.pubkey) {   // NUT-20 locked quote (npub.cash can lock payments to your Nostr key)
          const k = npcPrivFor(r.pubkey) || (S.p2pk.find(x => hex(L.getPubKeyFromPrivKey(L.hexToBytes(x.priv))) === String(r.pubkey).toLowerCase()) || {}).priv;
          if (!k) throw new Error("This payment is locked to a key this wallet doesn't have.");
          cfg = { privkey: k };
        }
        // the counters the new coins are signed for are on the deposit's record before the mint is asked
        const onCountersReserved = u => { if (u && u.count > 0) { q.ctr = { id: u.keysetId, start: u.start, n: u.count }; save(); } };
        let proofs;
        try { proofs = await withRepair(q.mint, () => w.mintProofsBolt11(q.amount, r, Object.assign({}, cfg, { onCountersReserved })), { except: q.quote }); }
        catch (e) { if (isRefusal(e) && q.ctr) { delete q.ctr; save(); } throw e; }   // (refused: nothing was signed at those counters for it)
        const held = new Set((S.proofs[q.mint] || []).map(p => p.secret));
        S.proofs[q.mint] = (S.proofs[q.mint] || []).concat(plain(proofs).filter(p => !held.has(p.secret)));
        updTx(q.txId, { status: 'done', ts: Date.now() });
        dropQuote(q); sfx('coin'); refresh();
        document.dispatchEvent(new CustomEvent('nutcade:paid', { detail: q.quote }));
        if (!$('#layer .sheet')) celebrate('in', q.amount);
        toast(`+${money(q.amount)} received`, 'lime');
        return 'paid';
      }
      if (r.state === 'ISSUED') {
        // The mint issued this deposit but we never stored the ecash (an answer lost: reload, closed tab). It is restored
        // from exactly the counters on its record and credited to this deposit. A record from before 1.12 has none: then
        // the mint is scanned, and the scan credits what it finds to waiting deposits first. If the mint can't be asked
        // now, the deposit stays and this is tried again later; it never becomes a separate "Recovered" line.
        // Any other deposit without counters (one from a backup, or one this device never asked the mint for) was
        // issued to another device holding this wallet: it is closed here with nothing, and no coin found by a scan
        // is taken for it.
        let got = 0;
        try {
          if (q.ctr) got = await creditDepositRange(w, q);
          else if (legacyQuote(q)) { await restoreFromMint(q.mint, null, { deposits: [q] }); got = num((txById(q.txId) || {}).amount); }
          else closeDepositEmpty(q);
        } catch (e) { return 'waiting'; }
        if (S.quotes.some(x => x.quote === q.quote)) return 'waiting';
        refresh();
        if (got) { sfx('coin'); toast(`Recovered ${money(got)} from an interrupted deposit`, 'lime'); }
        document.dispatchEvent(new CustomEvent('nutcade:paid', { detail: q.quote }));
        return 'paid';
      }
      if (q.expiry && Date.now() / 1000 > q.expiry) { dropQuote(q); updTx(q.txId, { status: 'expired' }); refresh(); return 'expired'; }
      return 'waiting';
    } else {
      const r = await w.checkMintQuoteOnchain(q.quote);
      const avail = num(r.amount_paid) - num(r.amount_issued);
      if (avail > 0) {
        const t0 = txById(q.txId);
        const { r: proofs, op } = await journaled(q.mint, 'receive', { amount: avail, note: t0 ? t0.note : '', txId: t0 && t0.status === 'pending' ? q.txId : null }, cb => w.mintProofsOnchain(avail, r, q.privkey, { onCountersReserved: cb }));
        const got = sum(proofs);
        addProofs(q.mint, proofs);
        const t = txById(q.txId);
        if (t && t.status === 'pending') updTx(q.txId, { status: 'done', amount: got, ts: Date.now() });
        else addTx({ type: 'in', method: 'onchain', amount: got, mint: q.mint, note: t ? t.note : '', request: q.request, quote: q.quote });
        closeOp(op); save();
        sfx('coin'); refresh(); toast(`+${money(got)} deposited on-chain`, 'lime');
        return 'paid';
      }
      if (q.expiry && Date.now() / 1000 > q.expiry) { dropQuote(q); const t = txById(q.txId); if (t && t.status === 'pending') updTx(q.txId, { status: 'expired' }); refresh(); return 'expired'; }
      return 'waiting';
    }
  } finally { busyQuotes.delete(q.quote); }
}
function dropQuote(q) { S.quotes = S.quotes.filter(x => x.quote !== q.quote); save(); }
// a deposit with no counters on record made on this device before 1.12 (only then could the mint have issued it to
// this record without them); not one from a backup, nor one made or seen waiting by 1.12.1 or later
const legacyQuote = q => !q.ctr && !q.rec && !Object.prototype.hasOwnProperty.call(q, 'impLine');
// issued, but not to this record: closed with what it already had (nothing), never with another step's coins
function closeDepositEmpty(q) {
  const was = txById(q.txId);
  updTx(q.txId, { status: 'done', amount: was && was.status === 'done' ? num(was.amount) : 0, ts: Date.now() });
  S.quotes = S.quotes.filter(x => x.quote !== q.quote); save();
}
// an interrupted deposit with its counters on record: exactly its coins, credited to it, in one write
async function creditDepositRange(w, q) {
  const r = await restoreRange(w, q.mint, q.ctr.start, q.ctr.n, q.ctr.id);
  // the mint signs a deposit's amount exactly; other coins at these counters were signed for another request (by a
  // device holding this wallet): not this deposit's, so it is closed with nothing
  const all = sum(r.proofs || []);
  if (all && q.amount != null && all !== num(q.amount)) { closeDepositEmpty(q); return 0; }
  const held = new Set((S.proofs[q.mint] || []).map(p => p.secret));
  let found = (r.proofs || []).filter(p => !held.has(p.secret)), away = [];
  if (found.length) { const st = await inTime(w.checkProofsStates(found), 30000); away = found.filter((p, i) => st[i] && st[i].state === 'SPENT'); found = found.filter((p, i) => st[i] && st[i].state === 'UNSPENT'); }
  const held2 = new Set((S.proofs[q.mint] || []).map(p => p.secret)); found = found.filter(p => !held2.has(p.secret));
  // (deposit coins already spent: a device holding the same wallet got this deposit and spent it; it was received, and
  // it left again: "already spent elsewhere".)
  const sent = new Set(S.txs.flatMap(t => (t.sent || []).map(p => p.secret))); away = away.filter(p => !held2.has(p.secret) && !sent.has(p.secret));
  if (!found.length && !away.length && (q.empty = (q.empty || 0) + 1) < 3) { save(); return 0; }   // nothing there yet: it waits, it isn't closed at 0
  const was = txById(q.txId), before = was && was.status === 'done' ? num(was.amount) : 0;
  S.proofs[q.mint] = (S.proofs[q.mint] || []).concat(plain(found));
  updTx(q.txId, { status: 'done', amount: before + sum(found) + sum(away), ts: Date.now() }); spentElsewhere(q.mint, sum(away), q.impLine);
  S.quotes = S.quotes.filter(x => x.quote !== q.quote); save();
  return sum(found);
}

function cleanToken(t) { t = String(t || '').trim().replace(/^(web\+)?cashu:(\/\/)?/i, ''); const m = t.match(/cashu[AB][A-Za-z0-9_\-+/=]+/); return m ? m[0] : t; }
function peekToken(t) {
  const meta = L.getTokenMetadata(cleanToken(t));
  return { mint: normUrl(meta.mint), amount: num(meta.amount), unit: meta.unit || 'sat', memo: meta.memo || '' };
}
function receiveToken(token, note, opts = {}) {
  let mint = null; try { mint = normUrl(peekToken(cleanToken(token)).mint); } catch (e) {}
  return mint ? tooManyRetry(mint, () => mintLock(mint, () => receiveTokenNow(token, note, opts))) : receiveTokenNow(token, note, opts);
}
async function receiveTokenNow(token, note, opts = {}) {
  token = cleanToken(token);
  const meta = peekToken(token);
  if (!opts.own && isBlocked(meta.mint)) throw blockedErr(meta.mint);   // your own token coming back is still yours
  if (meta.unit !== 'sat') throw new Error(`This token is in ${meta.unit}. NUTCADE handles sats only.`);
  if (!S.mints.find(m => m.url === meta.mint)) await addMint(meta.mint);
  const w = await getWallet(meta.mint);
  if (belowMin(meta.mint)) throw minErr(meta.mint);   // (no new deposits at a mint below the minimum)
  const sm = smallMint(meta.mint);   // a token with more coins than the mint takes in one request: claimed in parts
  if (sm && !opts.part && !opts.follow) {   // (our own token taken back too)
    let ps = []; try { ps = w.decodeToken(token).proofs || []; } catch (e) {}
    if (ps.length > sm || bitsOf(Math.max(0, sum(ps) - feeOfPs(w, ps))) > sm) {
      const parts = tokenParts(w, ps, sm);
      if (!parts) throw new Error(`${host(meta.mint)} takes at most ${sm} coins per request and charges a fee to claim, so each part of this token gives back its coins less that fee, and for some of its coins that needs more than ${sm} coins back. It can't be claimed there in any parts. Nothing was spent: the token still holds its sats, for when the mint takes more coins per request.`);
      if (parts.length > 1) return receiveInParts(w, meta, token, note, parts, opts.own ? S.txs.find(t => t.token === token && (t.status === 'pending' || t.status === 'claimed')) : null);
    }
  }
  let res;
  // what this claim finishes is on its record too (a token of ours coming back, a gift, a bounty, an Extra Life...),
  // so if its answer is lost, settling it later closes those records the same way
  const own0 = S.txs.find(t => t.token === token && (t.status === 'pending' || t.status === 'claimed'));
  try { const privs = allPrivs(); res = await journaled(meta.mint, 'receive', { amount: meta.amount, note: note || meta.memo, own: own0 && own0.id, follow: opts.follow || null }, (cb, o) => rRecv(o, w, token, Object.assign(privs.length ? { privkey: privs } : {}, { onCountersReserved: cb }))); }
  catch (e) { if (/witness|signature|p2pk|locked|locktime/i.test(e.message || '')) throw new Error("This ecash is locked to someone else's key, so this wallet can't claim it."); throw e; }
  const proofs = res.r, got = sum(proofs);
  addProofs(meta.mint, proofs);
  // mark own sent token as reclaimed if it matches
  const own = S.txs.find(t => t.token === token && (t.status === 'pending' || t.status === 'claimed'));   // our own unclaimed token came back
  if (own) updTx(own.id, { status: 'reclaimed' });
  const tx = addTx({ type: 'in', method: 'ecash', amount: got, fee: inFee(meta.amount, got, own || own0), mint: meta.mint, note: note || meta.memo });
  closeOp(res.op); save();
  return tx;
}
/* A claim settled from its record (its answer was lost) finishes what the claim was for, exactly as the normal path
   does: our own token is marked as back, and the feature's record is closed (Extra Life cashed out and its heir told,
   a bounty won, an heirloom or a treasure claimed, a saved incoming token or a payment request settled). Each is
   idempotent, and it overrides a "someone else got it" a retry may have written meanwhile. */
/* The fee a claim shows: what the mint kept of the token. Our own token coming back (taken back, a gift that came
   back) already carried the fee for its receiver, which its sent line counts: only what the mint kept beyond that
   is a fee here, so a token taken back shows one fee for what it cost, not that fee twice. */
const inFee = (tokenAmount, got, own) => { const f = Math.max(0, num(tokenAmount) - num(got)); return own ? Math.max(0, f - Math.max(0, num(tokenAmount) - num(own.amount))) : f; };
function receiveDone(op, t) {
  const own = op.own && txById(op.own); if (own && own.status !== 'reclaimed') updTx(own.id, { status: 'reclaimed' });
  const f = op.follow || {};
  if (f.k === 'extra-end') extraEnded(f);
  else if (f.k === 'bounty-won') bountyWon(f);
  else if (f.k === 'heir') heirClaimed(f);
  else if (f.k === 'hunt') huntWon(f, t);
  else if (f.k === 'incoming') incomingClaimed(f, t);
  else if (f.k === 'req') reqPaid(f.reqId, t);
}
// a token saved offline that this wallet claimed on another device (its line came in with a backup): the saved one goes
function dropClaimedIncoming() {
  const got = new Set(S.txs.map(t => t.fromIncoming).filter(Boolean)); if (!got.size) return;
  const n = S.txs.length; S.txs = S.txs.filter(t => !(t.incoming && (t.status === 'pending' || t.status === 'failed') && got.has(t.id))); if (S.txs.length !== n) save();
}
function incomingClaimed(f, t) {
  S.txs = S.txs.filter(x => x.id !== f.txId);
  if (t && f.txId) updTx(t.id, { fromIncoming: f.txId });   // (a copy of this wallet still holding the saved token knows it was claimed here)
  if (f.reqId) reqPaid(f.reqId, t);
  save();
}
function reqPaid(reqId, t) {
  if (!reqId || !t) return;
  updTx(t.id, { reqId });
  const r = S.requests.find(x => x.id === reqId); if (r && !r.paid.includes(t.id)) { r.paid.push(t.id); store.set('requests', S.requests); }
}

/* ---------- SEND ---------- */
/* On a mint that charges a fee to spend ecash (NUT-02 input fees), sending the whole balance can't work: the fee
   has to come from somewhere. These turn the library's "Not enough funds available" into a sentence that says so,
   and for ecash, offers the most that can be sent after the fee. */
function maxSendable(w, have) {
  const total = sum(have); if (!total || !have[0].id) return 0;
  const fee = n => { try { return num(w.getFeesForKeyset(n, have[0].id)); } catch (e) { return 0; } };
  const coins = a => { let c = 0; for (let x = a; x > 0; x = Math.floor(x / 2)) c += x % 2; return c; };   // a token of a SAT uses one coin per 1-bit
  const inFee = fee(have.length);   // as if every coin is spent: the most the swap can cost
  for (let a = total - inFee, i = 0; a > 0 && i < 500; a--, i++) {
    let r = 0; for (let j = 0; j < 4; j++) r = fee(coins(a + r));   // the token carries its receiver's fee too
    if (a + r + inFee <= total) return a;
  }
  return 0;
}
function shortOf(e, w, url, want, melt) {
  if (!/not enough (funds|proofs)/i.test(String(e && e.message || ''))) return e;
  const have = S.proofs[url] || [], total = sum(have);
  if (melt) return new Error(`This payment needs ${money(want)} plus the mint's fee to spend ecash, and this mint holds ${money(total)}.`);
  const max = maxSendable(w, have);
  const f = new Error(max > 0 ? `${money(want)} plus the mint's fee is more than this mint holds. The most you can send is ${money(max)}.` : `This mint's fee is more than its balance of ${money(total)}, so nothing can be sent from it.`);
  if (max > 0) f.fix = { act: 'sendMax', a: max, label: $('#layer [data-act=doSendEcash]') ? `Send ${money(max)}` : `Use ${money(max)}` };
  return f;
}
function sendEcash(amount, note, lockTo, url = S.active, opts = {}) { return tooManyRetry(url, () => mintLock(url, () => sendEcashNow(amount, note, lockTo, url, opts))); }
async function sendEcashNow(amount, note, lockTo, url, opts) {
  piggyGuard(amount);
  const w = await getWallet(url);
  if (sum(S.proofs[url] || []) < amount) throw new Error(`Not enough funds. This mint holds ${money(sum(S.proofs[url] || []))}.`);
  const outCfg = lockTo ? { send: { type: 'p2pk', options: Object.assign({ pubkey: lockTo }, opts.locktime ? { locktime: opts.locktime, refundKeys: [myLockPub()] } : {}, opts.hashlock ? { hashlock: opts.hashlock } : {}) }, keep: w.defaultOutputType() } : undefined;
  // the spending limit, with the most this can take: the swap's own numbers, fees included
  if (belowMin(url) && !opts.noBatch) return sendBatched(w, amount, note, lockTo, url, opts, outCfg);   // (a mint that dropped below the minimum: its sats can still leave, in steps)
  const plan = swapPlan(w, S.proofs[url] || [], amount, outCfg && outCfg.send, url);
  if (plan && plan.tooMany) throw manyErr(url, plan.tooMany);
  const hold = limitGate(plan ? plan.spend : feeMax(w, S.proofs[url] || [], amount), { free: opts.noLimit, grant: opts.grant, approved: opts.approved });
  try { return await withPick(w, plan && plan.sel, () => sendEcashSwap(w, amount, note, lockTo, url, opts, outCfg, hold)); }
  finally { hold.release(); }
}
async function sendEcashSwap(w, amount, note, lockTo, url, opts, outCfg, hold) {
  // Sending the most this mint allows after fees: every coin goes into the swap, so nothing is left behind.
  // (The library picks coins at random, and a smaller pick costs a smaller fee and leaves a SAT or two over.)
  // (a snapshot of the coins: the fee is worked out from exactly what went in, whatever else arrives meanwhile)
  let have;
  const attempt = async () => {
    have = [...(S.proofs[url] || [])];
    const all = have.length && amount === maxSendable(w, have) && w._selectProofs;
    const pick = all ? w._selectProofs : null;
    if (all) w._selectProofs = ps => ({ keep: [], send: ps });
    try { return await journaled(url, 'send', { inputs: have, amount, note, locked: !!lockTo, tx: Object.assign({ locked: lockTo || null }, opts.txx || {}), follow: opts.follow || null, lim: limRec(hold) }, (cb, o) => rSend(o, w, amount, have, { includeFees: true, onCountersReserved: cb }, outCfg)); }
    finally { if (all) w._selectProofs = pick; }
  };
  const { r: { keep, send }, op } = await spentRetry(url, attempt).catch(e => { throw shortOf(e, w, url, amount, false); });
  const used = new Set(have.map(p => p.secret));
  S.proofs[url] = (S.proofs[url] || []).filter(p => !used.has(p.secret)).concat(plain(keep));
  const token = L.getEncodedToken({ mint: url, proofs: send, unit: 'sat' });
  // the fee is everything the balance dropped by beyond the amount: the mint's fee for this swap (NUT-02) plus the
  // fee the token carries so the receiver gets the full amount
  const tx = addTx(Object.assign({ type: 'out', method: 'ecash', amount, fee: Math.max(0, sum(have) - sum(keep) - amount), mint: url, note, status: 'pending', token, sent: plain(send), locked: lockTo || null }, opts.txx || {}, hold.id ? { limId: hold.id } : {}));
  closeOp(op); save();
  return tx;
}
/* The most a payment from a mint can take from the balance, worked out before paying: the amount, the Lightning
   fee reserve (unused reserve comes back as change), and the mint's input fees (NUT-02) for getting the ecash
   ready (a swap that may spend every coin at that mint) and for the coins the payment itself spends. Shown on every
   screen that asks you to confirm a payment, and used for Wallet Connect budgets. */
function meltCost(url, amount, reserve) {
  amount = num(amount); reserve = num(reserve);
  const w = (wallets[url] || {}).ready, have = S.proofs[url] || [];
  let mintFee = 0;
  if (w && have.length) {
    const fee = (n, id) => { try { return num(w.getFeesForKeyset(n, id || have[0].id)); } catch (e) { return 0; } };
    const coins = a => { let c = 0; for (let x = a; x > 0; x = Math.floor(x / 2)) c += x % 2; return c; };
    let swap = 0; try { swap = num(w.getFeesForProofs(have)); } catch (e) { swap = fee(have.length); }
    let kid = have[0].id; try { kid = w.keysetId; } catch (e) {}
    let r = 0; for (let j = 0; j < 4; j++) r = fee(coins(amount + reserve + r), kid);
    mintFee = swap + r;
  }
  return { amount, reserve, mintFee, total: amount + reserve + mintFee };
}
const costRows = c => `<dt>Fee reserve</dt><dd>${money(c.reserve)}</dd>${c.mintFee ? `<dt>Mint fee, at most</dt><dd>${money(c.mintFee)}</dd>` : ''}<dt>Total, at most</dt><dd>${money(c.total)}</dd>`;
async function meltQuote(kind, dest, amount) {
  const w = await getWallet(S.active);
  if (kind === 'ln') return w.createMeltQuoteBolt11(dest);
  return w.createMeltQuoteOnchain(dest, amount);
}
async function payMelt(kind, mq, feeIndex, note, dest, url = S.active, extra = {}) {
  const { grant, noLimit, ...txExtra } = extra || {};
  const w = await getWallet(url);
  const c = await tooManyRetry(url, () => mintLock(url, () => payPrep(w, kind, mq, feeIndex, note, dest, url, txExtra, { grant, free: noLimit, auto: !!txExtra.nwc })));
  try {
    if (writeGuard.paused) throw pausedErr();   // (paused in between: the tab in charge settles the prepared ecash)
    return await single('melt:' + c.pend.id, () => meltNow(w, kind, mq, feeIndex, url, c.tx, c.pend, c.spent, c.amount, c.onCountersReserved));
  } finally { c.hold.release(); }
}
async function payPrep(w, kind, mq, feeIndex, note, dest, url, extra, lim = {}) {
  const amount = num(mq.amount);
  const reserve = kind === 'ln' ? num(mq.fee_reserve) : num((mq.fee_options || []).find(f => f.fee_index === feeIndex)?.fee_reserve);
  const need = amount + reserve;
  const have = S.proofs[url] || [];
  // the most this payment can take: the amount, the fee reserve and the mint's fees to spend the ecash
  // (more coins than the mint takes in one request, for the swap or for the payment itself: in steps, NUT-06)
  let plan = swapPlan(w, have, need, undefined, url); const steps = belowMin(url);   // (in steps only from a mint that dropped below the minimum)
  if (plan && plan.tooMany && !steps) throw manyErr(url, plan.tooMany);
  if (steps && kind !== 'ln') throw minErr(url);   // (on-chain: its change could need more outputs than the mint takes; paid only from mints that take enough)   // (the payment spends the swap's sent coins: as many as it asked for)
  const pm = steps ? planMelt(w, url, need) : null; if (steps) plan = null;
  const most = pm ? pm.T + pm.fees : plan ? plan.spend : meltCost(url, amount, reserve).total;
  if (sum(have) < most) throw new Error(`Not enough funds. Need ${money(most)} including fees; this mint holds ${money(sum(have))}.`);
  piggyGuard(need);
  const hold = limitGate(most, lim);
  try { return await withPick(w, plan && plan.sel, () => payPrepSwap(w, kind, mq, note, dest, url, extra, amount, need, hold, !!pm)); }
  catch (e) { hold.release(); throw e; }
}
async function payPrepSwap(w, kind, mq, note, dest, url, extra, amount, need, hold, steps) {
  let inputs;
  const lim = limRec(hold);
  const ready = steps ? () => meltInputsBatched(w, url, need) : () => spentRetry(url, () => { inputs = [...(S.proofs[url] || [])]; return journaled(url, 'swap', { inputs, lim }, (cb, o) => rSend(o, w, need, inputs, { includeFees: true, onCountersReserved: cb })); });
  const got = await ready().catch(e => { throw shortOf(e, w, url, need, true); });
  if (got.inputs) inputs = got.inputs;
  const { r: { keep, send }, op } = got;
  const spent = sum(inputs) - sum(keep);   // what left the balance: the amount, the fee reserve and any swap fee
  // extra (who asked: a Wallet Connect app, a zap) is on the record before anything is sent, so a reload can't lose it
  const tx = addTx(Object.assign({ type: 'out', method: kind, amount, fee: Math.max(0, spent - amount), mint: url, note, status: 'pending', request: dest, quote: mq.quote }, kind === 'ln' && mq.request && mq.request !== dest ? { invoice: String(mq.request) } : {}, extra, hold.id ? { limId: hold.id } : {}));   // (a Lightning address payment keeps the invoice it paid, for its preimage)
  // where the mint's change will be signed (NUT-08 blank outputs, from this wallet's counters): after a reload it is
  // restored from exactly there. The library reports the range it reserved; until then, this is where it will start.
  let ksid = null; try { ksid = w.keysetId; } catch (e) {}
  const over = BigInt(Math.max(0, sum(send) - amount));
  const pend = { id: uid(), mint: url, proofs: plain(send), quote: mq.quote, kind, txId: tx.id, spent, amount, change: 0, ctr: ksid ? { id: ksid, start: S.counters[ksid] || 0, n: Math.max(over <= 1n ? 0 : (over - 1n).toString(2).length, 1) } : null };
  { const sm = mintMax(url), over = sum(send) - amount; if (sm && Math.max(over <= 1 ? 0 : (over - 1).toString(2).length, 1) > sm) { if (kind === 'ln') pend.cap = sm; else { pend.noChange = true; pend.ctr = null; } } }   // (more change outputs than the mint takes: only as many as it takes; it returns the change in those, the most it can, and what it keeps is its fee)
  const onCountersReserved = u => { if (u && u.count > 0) { pend.ctr = { id: u.keysetId, start: u.start, n: u.count }; save(); } };
  const used = new Set(inputs.map(p => p.secret));
  S.proofs[url] = (S.proofs[url] || []).filter(p => !used.has(p.secret)).concat(plain(keep)); S.pending.push(pend); if (op) closeOp(op); save();   // (the payment record takes over the coins from the swap's)
  return { tx, pend, spent, amount, onCountersReserved, hold };
}
async function meltNow(w, kind, mq, feeIndex, url, tx, pend, spent, amount, onCountersReserved) {
  const send = pend.proofs;
  try {
    const mo = Object.assign({ onCountersReserved }, pend.noChange ? { nut08Change: false } : {});
    const capped = async () => { const pr = await w.prepareMelt('bolt11', mq, send, mo); pr.outputData = pr.outputData.slice(0, pend.cap); return w.completeMelt(pr); };
    const res = await withRepair(url, () => kind === 'ln' ? (pend.cap ? capped() : w.meltProofsBolt11(mq, send, mo)) : w.meltProofsOnchain(mq, send, feeIndex, mo), { except: pend.id });
    const change = plain(res.change || []);
    if (change.length) { addProofs(url, change); pend.change = sum(change); }
    const st = res.quote && res.quote.state;
    if (change.length || st === 'PAID') pend.changeDone = true;   // still pending: its change comes later, recovered when it settles
    if (st === 'PAID') {
      S.pending = S.pending.filter(p => p.id !== pend.id);
      settleMelt(pend, 'done', 0); updTx(tx.id, { outpoint: res.quote.outpoint || null, preimage: res.quote.payment_preimage || null });
    } else {
      updTx(tx.id, { status: 'pending', fee: Math.max(0, spent - amount) });   // at most this; change may still come back
    }
    save();
    return txById(tx.id);
  } catch (e) {
    // the mint's answer was lost (a dropped connection): ask the mint how it went before calling it a failure
    const r = await reconcileNow(pend.id, tx.id, {}).catch(() => null);
    if (r === 'paid') return txById(tx.id);
    const f = friendly(e, url), t = txById(tx.id);
    if (t && t.status === 'failed') f.also = t.cost ? `The ecash came back, except ${money(t.cost)} the mint kept as its fee.` : 'Nothing left your wallet.';
    throw f;
  }
}
/* One at a time per record (a payment, a deposit, a mint's restore): every caller in this tab shares the run in
   progress, and where the browser has Web Locks another tab waits for it too. */
const flights = new Map();
/* Web Locks where the browser has them. Where they are missing, or the browser refuses them (some sandboxed or
   opaque-origin pages reject every request), the lock is the one in this tab instead (other tabs are kept out by the
   takeover guard and the generation stamp on every save). Said once in the console. */
let locksOff = false;
async function withLock(name, fn, fallback = fn) {
  if (locksOff || !(navigator.locks && navigator.locks.request)) return fallback();
  let ran = false;
  try { return await navigator.locks.request(name, () => { ran = true; return fn(); }); }
  catch (e) {
    if (ran) throw e;
    locksOff = true; try { console.warn(`NUTCADE: this browser refused Web Locks (${(e && e.name) || e}); using the lock in this tab.`); } catch (x) {}
    return fallback();
  }
}
const tabQueue = new Map();   // one at a time per name, in this tab
function inTab(name, fn) {
  const run = (tabQueue.get(name) || Promise.resolve()).then(fn, fn), tail = run.catch(() => {});
  tabQueue.set(name, tail); tail.then(() => { if (tabQueue.get(name) === tail) tabQueue.delete(name); });
  return run;
}
function single(key, fn) {
  if (flights.has(key)) return flights.get(key);
  const p = withLock('nutcade:' + key, () => fn()).finally(() => flights.delete(key));
  flights.set(key, p);
  return p;
}
/* One money step at a time per mint, in this tab and across tabs (Web Locks): from asking the mint to writing its
   answer down. The step starts from what is saved now (another tab may have just written), and a paused tab starts
   nothing. */
function mintLock(url, fn) {
  const go = async () => { if (writeGuard.paused) throw pausedErr(); await syncIfStale(); return fn(); };
  return withLock('nutcade:mint:' + normUrl(url), go, () => inTab('mint:' + normUrl(url), go));
}
/* opts.force: try a waiting change recovery now (at startup, or when you ask), instead of waiting for its backoff */
function reconcile(pend, opts = {}) { return single('melt:' + pend.id, () => reconcileNow(pend.id, pend.txId, opts)); }
async function reconcileNow(id, txId, opts) {
  await syncIfStale();   // another tab may have settled it already
  const pend = S.pending.find(p => p.id === id);
  if (!pend) { const t = txById(txId); return !t || t.status === 'done' ? 'paid' : t.status === 'failed' ? 'returned' : 'pending'; }   // settled by an earlier run
  if (pend.paid) return finishPaid(pend, opts);   // the payment went through; only its change may still be at the mint
  const w = await getWallet(pend.mint);
  let qs = null;
  try { qs = pend.kind === 'ln' ? await w.checkMeltQuoteBolt11(pend.quote) : await w.checkMeltQuoteOnchain(pend.quote); } catch (e) {}
  if (qs && qs.state === 'PAID') { markPaid(pend, qs); return finishPaid(pend, opts); }
  const states = await w.checkProofsStates(pend.proofs);
  const unspent = pend.proofs.filter((p, i) => states[i] && states[i].state === 'UNSPENT');
  const stillPending = states.some(s => s.state === 'PENDING');
  if (!stillPending) {
    // every coin spent: it was paid, unless the mint says this payment wasn't made (its coins were spent by
    // something else, a device holding this wallet): then nothing was paid and nothing came back
    if (!unspent.length && qs && qs.state === 'UNPAID') { S.pending = S.pending.filter(p => p.id !== pend.id); settleMelt(pend, 'failed', sum(pend.proofs)); spentElsewhere(pend.mint, sum(pend.proofs), pend.impLine); save(); return 'returned'; }
    if (!unspent.length) { markPaid(pend, null); return finishPaid(pend, opts); }
    addProofs(pend.mint, unspent);
    S.pending = S.pending.filter(p => p.id !== pend.id);
    settleMelt(pend, 'failed', sum(unspent));
    save();
    return 'returned';
  }
  return 'pending';
}
/* A melt the mint reports paid is recorded as done right away, with the fee so far (the whole reserve, until the
   change is back). Its pending record stays, with the counter range of its change, until the change has really been
   recovered: a failed attempt (no connection, a 500 or 429, a reload or a closed tab in the middle) is retried with
   backoff on later starts and on the regular check, and the fee is only lowered by what actually came back. */
function markPaid(pend, qs) {
  pend.paid = true; pend.proofs = [];   // spent: no longer "in flight"
  settleMelt(pend, 'done', 0);
  const t = txById(pend.txId);
  updTx(pend.txId, { outpoint: (qs && qs.outpoint) || (t && t.outpoint) || null, preimage: (qs && qs.payment_preimage) || (t && t.preimage) || null, changePending: !!(pend.ctr && !pend.changeDone) });
  save();
}
async function finishPaid(pend, opts = {}) {
  if (pend.ctr && !pend.changeDone) {
    if (!opts.force && pend.nextTry && Date.now() < pend.nextTry) return 'paid';
    try { await recoverChange(pend); }
    catch (e) { pend.tries = (pend.tries || 0) + 1; pend.nextTry = Date.now() + Math.min(30 * 60e3, 15e3 * 2 ** (pend.tries - 1)); save(); return 'paid'; }
  }
  S.pending = S.pending.filter(p => p.id !== pend.id);
  settleMelt(pend, 'done', 0);   // the fee now counts the change that came back
  updTx(pend.txId, { changePending: false });
  save();
  return 'paid';
}
/* A payment's change (unused Lightning fee reserve) normally comes back with the mint's answer. If NUTCADE closed
   before that answer arrived, the change was still signed for this wallet's next counters: restore exactly those,
   keep what is unspent and not already held or sent in a token, so the fee recorded is what the payment really cost. */
// a mint that doesn't answer at all counts as a failed attempt (retried later), so it can't hold up everything else
const inTime = (p, ms) => Promise.race([p, new Promise((_, no) => setTimeout(() => no(new Error("The mint didn't answer in time.")), ms))]);
// Throws when the mint can't be asked (the caller retries later). Idempotent: change already credited to this payment
// (pend.recovered) is never counted twice, and the change and the proofs are saved together.
async function recoverChange(pend) {
  if (!pend.ctr || pend.changeDone) return 0;
  const w = await getWallet(pend.mint);
  const r = await restoreRange(w, pend.mint, pend.ctr.start, pend.ctr.n, pend.ctr.id);
  const mine = new Set(pend.recovered || []), have = new Set((S.proofs[pend.mint] || []).map(p => p.secret));
  const sent = new Set(S.txs.flatMap(t => (t.sent || []).map(p => p.secret)).concat(S.pending.filter(p => p.id !== pend.id).flatMap(p => p.proofs.map(x => x.secret))));
  let found = (r.proofs || []).filter(p => !have.has(p.secret) && !sent.has(p.secret) && !mine.has(p.secret)), spentAway = [];
  // (change the mint signed that is spent already was spent by a device holding the same wallet: it came back, so it
  // isn't fee, and it left again: "already spent elsewhere")
  if (found.length) { const st = await inTime(w.checkProofsStates(found), 30000); spentAway = found.filter((p, i) => st[i] && st[i].state === 'SPENT'); found = found.filter((p, i) => st[i] && st[i].state === 'UNSPENT'); }
  // checked again right before crediting, with no wait in between: what is already held or credited adds nothing
  const held = new Set((S.proofs[pend.mint] || []).map(p => p.secret)), credited = new Set(pend.recovered || []);
  found = found.filter(p => !held.has(p.secret) && !credited.has(p.secret)); spentAway = spentAway.filter(p => !held.has(p.secret) && !credited.has(p.secret));
  if (found.length || spentAway.length) {
    pend.recovered = [...credited, ...found.map(p => p.secret), ...spentAway.map(p => p.secret)]; pend.change = (pend.change || 0) + sum(found) + sum(spentAway);
    spentElsewhere(pend.mint, sum(spentAway), pend.impLine);
    addProofs(pend.mint, found);   // saves the proofs and this record together
  }
  pend.changeDone = true; save();
  return sum(found);
}
/* ---------- the operation journal ----------
   Every swap (making a token, claiming one, getting ecash ready for a payment, any proofs-in / proofs-out call) is
   written down before the mint is asked: the coins of ours it may spend, and, as soon as the library reserves them
   (still before the request leaves), the counters its new coins are signed for. When it completes, the result and
   the end of the record are saved in one write. If the answer never arrives (a reload, a closed or paused tab, a
   dropped connection, a mint that stops answering), the record is settled with the mint later, at the next start,
   takeover or background check: our spent coins are dropped, the new coins are restored from exactly those counters,
   and the history line is written once. Settling is one at a time per record (in this tab and across tabs) and
   idempotent by secret, so nothing is counted twice.
   A swap also writes down every output it asks the mint to sign (amount, keyset, secret, blinding factor and B_),
   including the ones no counter can re-create (ecash locked to a key or to a secret: gifts, bounties, Extra Life),
   and the record is stored (inside the PIN vault when one is set) before the request leaves. NUT-09 restore gives
   back the mint's signature for any B_ it signed, so settling asks for exactly those B_, unblinds them with the
   saved blinding factors (checking the mint's DLEQ proof when it sends one) and gets every coin back: a locked
   token is shown again as the token it was going to be, everything else lands in the balance. A locked step whose
   follow-up data is made just before the swap (a bounty's secret and its challenge, Extra Life's heir and date)
   keeps that data in the same record, so it finishes as that step: a working bounty (the challenge is still sent),
   an Extra Life that is set up or continued. The record, secrets included, is deleted once settled. */
const opsRunning = new Set();
const closeOp = op => { S.ops = S.ops.filter(o => o.id !== op.id); S.opsdone = [op.id].concat((S.opsdone || []).filter(x => x !== op.id)).slice(0, 300); };
async function journaled(url, kind, info, run) {
  const op = { id: uid(), kind, mint: url, inputs: (info.inputs || []).map(p => p.secret), amount: info.amount || 0, note: info.note || '', locked: !!info.locked, extra: !!info.extra, txId: info.txId || null, tx: info.tx || null, follow: info.follow || null, own: info.own || null, created: Date.now(), ctr: [], outs: [] };
  if (info.lim && info.lim.id) op.lim = { id: info.lim.id, a: info.lim.a, at: Date.now() };   // (counts toward the spending limit until it settles)
  S.ops.push(op); save();
  const onCountersReserved = u => { if (u && u.count > 0) { op.ctr.push({ id: u.keysetId, start: u.start, n: u.count }); save(); } };
  opsRunning.add(op.id);
  try {
    return await single('op:' + op.id, async () => {
      for (let i = 0; ; i++) {
        try { const r = await run(onCountersReserved, op); opMark(url, true); return { r, op }; }
        catch (e) {
          if (i === 0 && isDupOutputs(e) && !flights.has('restore:' + normUrl(url))) { op.ctr = []; op.outs = []; save(); await restoreFromMint(url, null, { except: op.id }); continue; }   // (nothing of this attempt was signed)   // counters behind (same phrase elsewhere): catch up, once
          opMark(url, false, e); e.op = op; throw e;
        }
      }
    });
  } catch (e0) {
    let e = e0;
    opsRunning.delete(op.id);
    if (isRefusal(e) && (op.ctr.length || op.outs.length)) { op.refused = 1; save(); }   // the mint refused it: it signed nothing for it
    if (!op.ctr.length && !op.outs.length) { closeOp(op); save(); }   // never reached the mint: nothing to settle
    else setTimeout(() => settleOp(op.id).catch(() => {}), 0);   // asked, and the answer is an error or never came: the mint decides
    if (op.outs.length) {   // the request went out: the mint may have done it, so nothing may act as if it hadn't (no offline fallback)
      if (netErr(e)) { e = new Error("The mint didn't answer. Try again in a moment."); e.op = op; }
      e.asked = true;
    }
    throw e;
  } finally { opsRunning.delete(op.id); }
}
const saveNow = async () => { save(); if (vault.on) await vault.chain; };
const outRec = (o, send) => ({ a: num(String(o.blindedMessage.amount)), id: o.blindedMessage.id, B: o.blindedMessage.B_, r: o.blindingFactor.toString(16), s: hex(o.secret), e: o.ephemeralE || null, send: send ? 1 : 0 });
// a swap with its outputs on record: prepared (counters reserved), every output written down and stored, then asked
async function askRecorded(w, op, prepared, privkey) {
  const p = await prepared;
  // never a request with more items than the mint takes (NUT-06): refused here, before anything is recorded or sent,
  // so the step can be done in pieces that fit instead
  if (op) { const m = mintMax(op.mint), nOut = (p.sendOutputs || []).length + (p.keepOutputs || []).length; if (m && ((p.inputs || []).length > m || nOut > m)) throw Object.assign(new Error(`${host(op.mint)} takes at most ${m} coins per request, and this step would need more. Nothing was sent.`), { tooBig: true }); }
  if (op) {
    if (p.inputs && p.inputs.length) op.inputs = p.inputs.map(x => x.secret);   // exactly the coins this swap spends (they are busy until it settles)
    op.outs = (p.sendOutputs || []).map(o => outRec(o, true)).concat((p.keepOutputs || []).map(o => outRec(o, false))); await saveNow();
  }
  return w.completeSwap(p, privkey);
}
const rSend = (op, w, amount, proofs, cfg, outCfg) => askRecorded(w, op, w.prepareSwapToSend(amount, proofs, cfg, outCfg), cfg && cfg.privkey);
const rRecv = async (op, w, token, cfg) => (await askRecorded(w, op, w.prepareSwapToReceive(token, cfg), cfg && cfg.privkey)).keep;
// the mint's signatures for exactly these recorded outputs (NUT-09), unblinded with the saved blinding factors
let OutputDataClass = null;
async function restoreRecorded(w, outs, url) {
  if (!outs.length) return [];
  if (!OutputDataClass) OutputDataClass = w.createOutputData(L.Amount.from(1), w.getOutputKeyset(), { type: 'random' })[0].constructor;
  const bm = o => ({ amount: L.Amount.from(o.a), id: o.id, B_: o.B });
  const m = mintMax(url || '') || outs.length, res = { outputs: [], signatures: [] };   // (in pieces the mint takes)
  for (let i = 0; i < outs.length; i += m) { const r = await inTime(w.mint.restore({ outputs: outs.slice(i, i + m).map(bm) }), 30000); res.outputs = res.outputs.concat(r.outputs || []); res.signatures = res.signatures.concat(r.signatures || []); }
  await w._ensureKeysetsForSignatures(res.signatures);
  const sig = {}; (res.outputs || []).forEach((x, i) => { sig[x.B_] = res.signatures[i]; });
  const got = []; let n = 0, odd = false;
  for (const o of outs) {
    const g = sig[o.B]; if (!g || g.amount.isZero()) continue;
    if (num(o.a) > 0) { n++; if (num(g.amount) !== num(o.a)) odd = true; }
    const d = new OutputDataClass(bm(o), BigInt('0x' + o.r), L.hexToBytes(o.s), o.e || undefined);
    got.push(Object.assign(d.toProof(g, w.keysetForSignature(g.id)), { _send: o.send }));   // (toProof checks the DLEQ proof when the mint sent one)
  }
  // signed for another amount than this step asked, or only some of its outputs signed: the mint signed these for
  // another request (a device holding this wallet used the same counters), never for this step
  got.foreign = odd || (n > 0 && n < outs.filter(o => num(o.a) > 0).length);
  return got;
}
// value that left this wallet because a device holding the same coins spent it: one line, or added to the line the same
// import already wrote for that mint
function spentElsewhere(url, v, into) {
  if (!(v > 0)) return;
  const l = into && txById(into);
  if (l && l.note === 'Ecash already spent elsewhere' && l.mint === url && l.type === 'out' && l.status === 'done') updTx(l.id, { amount: num(l.amount) + v });
  else addTx({ type: 'out', method: 'ecash', amount: v, mint: url, note: 'Ecash already spent elsewhere', status: 'done', settled: true });
}
async function settleOp(id) {
  for (let i = 0; i < 3; i++) {
    if (!S.ops.some(o => o.id === id)) return 'done';
    const f = flights.get('op:' + id);
    if (opsRunning.has(id) && f) { await f.catch(() => {}); continue; }   // still running in this tab: wait for it, then look again
    return single('op:' + id, () => settleOpNow(id));
  }
  return S.ops.some(o => o.id === id) ? 'open' : 'done';
}
async function settleOpNow(id) {
  await syncIfStale();
  const op = S.ops.find(o => o.id === id); if (!op || opsRunning.has(id)) return 'done';
  if (!op.ctr.length && !(op.outs || []).length) { closeOp(op); save(); return 'done'; }
  const w = await getWallet(op.mint);
  const rec = op.outs || [], recS = new Set(rec.map(outSecret));
  let outs = await restoreRecorded(w, rec, op.mint), foreign = !!outs.foreign || !!op.refused;
  for (const c of op.ctr) { const r = await restoreRange(w, op.mint, c.start, c.n, c.id); if (rec.length && (r.proofs || []).some(p => !recS.has(p.secret))) foreign = true; outs = outs.concat(r.proofs || []); }
  { const seen = new Set(); outs = outs.filter(p => !seen.has(p.secret) && seen.add(p.secret)); }
  // (a deposit's coins come to exactly its amount)
  if (op.kind === 'receive' && !rec.length && op.amount && sum(outs) && sum(outs) !== num(op.amount)) foreign = true;
  /* Only what the mint signed for THIS step is its: never coins at its counters the mint refused it (it answered
     with an error) or signed for another request (a device holding this wallet used the same counters). Those
     count as nothing signed here: a claim or deposit received nothing, and coins of ours it spent were spent by
     something else. (Unspent coins of the wallet's phrase are still found by a restore.) */
  if (foreign) outs = [];
  const unspent = async ps => { if (!ps.length) return []; const st = await inTime(w.checkProofsStates(ps), 30000); return ps.filter((p, i) => st[i] && st[i].state === 'UNSPENT'); };
  const heldNow = () => new Set((S.proofs[op.mint] || []).map(p => p.secret));
  let fresh = await unspent(outs.filter(p => !heldNow().has(p.secret)));
  const mine = (S.proofs[op.mint] || []).filter(p => op.inputs.includes(p.secret));
  let spent = [];
  if (mine.length) { const st = await inTime(w.checkProofsStates(mine), 30000); spent = mine.filter((p, i) => st[i] && st[i].state === 'SPENT'); }
  // (the Extra Life a CONTINUE was renewing: are its coins spent? asked now, before the one write below)
  const xr = op.follow && op.follow.k === 'extra-renew' && S.extra && S.extra.mint === op.mint && S.extra.proofs.some(p => op.inputs.includes(p.secret)) ? S.extra : null;
  let xGone = false; if (xr) { const st = await inTime(w.checkProofsStates(xr.proofs), 30000); xGone = st.length > 0 && st.every(s => s && s.state === 'SPENT'); }
  // one write: spent coins out, new coins in (never one already held), the history line, the record closed
  const held = heldNow(); fresh = fresh.filter(p => !held.has(p.secret));
  // a locked token the step was making is shown again as that token (only its sender can see it); the rest is balance
  let lockedOut = op.kind === 'send' && (op.locked || (op.follow && op.follow.k === 'reqpay')) ? fresh.filter(p => p._send) : [];   // (a request payment: the same coins go to the payee)
  const have = new Set(S.txs.flatMap(t => (t.sent || []).map(p => p.secret)).concat(S.extra ? S.extra.proofs.map(p => p.secret) : []));
  if (lockedOut.some(p => have.has(p.secret))) { fresh = fresh.filter(p => !have.has(p.secret)); lockedOut = []; }   // that token is already here (settled before): never a second line
  if (lockedOut.length) fresh = fresh.filter(p => !p._send);
  for (const p of outs) delete p._send;
  const gone = new Set(spent.map(p => p.secret)), cur = (S.proofs[op.mint] || []).filter(p => held.has(p.secret));
  const removed = sum(cur.filter(p => gone.has(p.secret))), added = sum(fresh);
  /* The mint kept as its fee only what the step's coins had beyond everything it signed for it. What it signed but
     doesn't come in here was spent since by a device holding the same wallet (a backup restored elsewhere): that is
     "already spent elsewhere", never a fee. Outputs already shown here as a token or as the Extra Life have
     their line.
     Nothing signed at all: the step's coins were spent by something else. */
  const signed = sum(outs), inSet = new Set(fresh.map(p => p.secret));
  const fee0 = signed ? Math.max(0, removed - signed) : 0, shown = sum(outs.filter(p => have.has(p.secret)));
  const spentOut = sum(outs.filter(p => !held.has(p.secret) && !inSet.has(p.secret) && !have.has(p.secret)));
  // (what the coins removed here paid for beyond the fee and this step's own line: outputs already shown here first, the rest left elsewhere)
  const rest = r => { if (r > 0) spentElsewhere(op.mint, Math.max(0, r - shown), op.impLine); else if (r < 0) addTx({ type: 'in', method: 'ecash', amount: -r, mint: op.mint, note: 'Recovered with recovery phrase', settled: true }); };
  S.proofs[op.mint] = cur.filter(p => !gone.has(p.secret)).concat(plain(fresh));
  const waitingTx = op.txId && (txById(op.txId) || {}).status === 'pending' ? op.txId : null;   // a deposit waiting for exactly this: it gets it
  // a claim or deposit: the line is what was received (the token less the mint's fee), and what of it was spent since has its own line
  if (op.kind === 'receive' && added + spentOut && waitingTx) { updTx(waitingTx, { status: 'done', amount: added + spentOut, ts: Date.now() }); spentElsewhere(op.mint, spentOut, op.impLine); }
  else if (op.kind === 'receive') { if (added + spentOut) { const t = addTx({ type: 'in', method: 'ecash', amount: added + spentOut, fee: inFee(op.amount, signed, op.own && txById(op.own)), mint: op.mint, note: op.note || '', settled: true }); spentElsewhere(op.mint, spentOut, op.impLine); if (op.extra && S.extra) { S.extra = null; saveExtra(); } receiveDone(op, t); } }
  else if (lockedOut.length) {
    // (a token that carries the receiver's fee on top of its amount: that part is the sender's fee, as when nothing is interrupted)
    const ps = plain(lockedOut), amount = Math.min(op.amount || sum(ps), sum(ps)), fee = fee0 + sum(ps) - amount;
    const f = op.follow || {};
    if (f.k === 'extra-renew' && S.extra && S.extra.mint === op.mint && S.extra.proofs.some(p => op.inputs.includes(p.secret))) {   // Extra Life continued: its new coins and date
      Object.assign(S.extra, { proofs: ps, until: f.until, renewed: Date.now(), amount: Math.min(S.extra.amount, sum(ps)) }); delete S.extra.unlocked; saveExtra();
      if (removed > added) addTx({ type: 'out', method: 'fee', amount: 0, fee: removed - added, mint: op.mint, note: 'Mint fee for keeping Extra Life going', status: 'done', settled: true });
      else if (added > removed) addTx({ type: 'in', method: 'ecash', amount: added - removed, mint: op.mint, note: 'Recovered with recovery phrase', settled: true });
      setTimeout(() => sendHeirCopy().catch(() => {}), 0);
      closeOp(op); save(); return 'settled';
    }
    if (f.k === 'extra' && !S.extra) {   // Extra Life set up as it was going to be
      S.extra = { mint: op.mint, amount, proofs: ps, heir: f.heir, until: f.until, days: f.days, auto: f.auto !== false, created: Date.now(), renewed: Date.now() }; saveExtra();
      addTx({ type: 'out', method: 'ecash', amount, fee, mint: op.mint, note: `Extra Life for ${f.heir.name}`, status: 'done', extraLife: true, settled: true });
      setTimeout(() => sendHeirCopy().catch(() => {}), 0);
    } else {
      const t = addTx(Object.assign({ type: 'out', method: 'ecash', amount, fee, mint: op.mint, note: op.note || '', status: 'pending', token: L.getEncodedToken({ mint: op.mint, proofs: ps, unit: 'sat' }), sent: ps, settled: true }, op.tx || {}));
      if (f.k === 'bounty') bountyRecovered(f, t, Object.prototype.hasOwnProperty.call(op, 'impLine'));   // a working bounty again: its secret is kept, the challenge is sent
      else if (f.k === 'gift' && contactById(f.contact)) setTimeout(() => deliverToContact(contactById(f.contact), txById(t.id)).catch(() => {}), 0);   // and it still goes to the contact
      else if (f.k === 'hunt-make') setTimeout(() => huntFinish(Object.assign({}, f, { txId: t.id })).catch(() => {}), 0);   // the treasure hunt is still set up
      else if (f.k === 'reqpay') setTimeout(() => deliverReqPays().catch(() => {}), 0);   // and the payment still goes to the request
    }
    rest(removed - added - amount - fee);
  }
  else {
    // a CONTINUE whose new Extra Life coins were spent since (continued again, cashed out, or claimed by the heir, on a
    // device holding this wallet): the Extra Life it was renewing is over here. Its sats left the balance when it was set
    // up, so no line for them; past its date it passed to the heir, as when the heir claims it.
    if (xr && xGone && S.extra === xr) { S.extra = null; saveExtra(); if (Date.now() > num((op.follow || {}).until)) extraPassed(xr); }
    if (fee0) addTx({ type: 'out', method: 'fee', amount: 0, fee: fee0, mint: op.mint, note: 'Mint fee for an interrupted step', status: 'done', settled: true });
    rest(removed - added - fee0);
  }
  closeOp(op); save();
  return 'settled';
}
/* Coins the mint says are already spent (spent elsewhere, or by a step that never recorded its result) are dropped
   from the balance with a history line saying so, after any open record at that mint has been settled first. */
async function pruneSpent(url) {
  for (const o of S.ops.filter(o => o.mint === url)) await settleOp(o.id);
  const w = await getWallet(url), ps = S.proofs[url] || []; if (!ps.length) return 0;
  const st = await inTime(w.checkProofsStates(ps), 30000);
  const gone = new Set(ps.filter((p, i) => st[i] && st[i].state === 'SPENT').map(p => p.secret)); if (!gone.size) return 0;
  const removed = sum((S.proofs[url] || []).filter(p => gone.has(p.secret)));
  S.proofs[url] = (S.proofs[url] || []).filter(p => !gone.has(p.secret));
  if (removed) addTx({ type: 'out', method: 'ecash', amount: removed, mint: url, note: 'Ecash already spent elsewhere', status: 'done' });
  save();
  return removed;
}
const isSpentErr = e => /already spent|proofs? (are|is) spent|token.*spent/i.test(String((e && (e.raw || e.message)) || ''));
// a payment that hit "already spent": settle what was left open, drop the spent coins (with a line), and try once more
async function spentRetry(url, fn) {
  try { return await fn(); }
  catch (e) {
    if (!isSpentErr(e)) throw e;
    const dropped = await pruneSpent(url).catch(() => 0);
    try { return await fn(); }
    catch (e2) { if (!isSpentErr(e2)) throw e2; const f = new Error(dropped > 0 ? `Some of this ecash was already spent. NUTCADE removed ${money(dropped)} of spent ecash from your balance (see your notes). Try again with what is left.` : "The mint says some of this ecash was already spent, but it still shows your coins as unspent, so nothing was removed. Try again in a moment."); f.keep = true; throw f; }
  }
}
/* The history always adds up to the balance. A payment that went through records fee = what left the balance -
   amount - change. One that failed moved nothing, so it records no amount moved and no fee; but if getting the
   ecash ready cost a mint fee (a NUT-02 swap fee) that didn't come back, that cost is its own "Mint fee" line,
   linked to the failed payment, which says so. Older pending payments without these numbers keep what they had. */
function settleMelt(pend, status, returned) {
  const t = txById(pend.txId); if (!t) return;
  if (pend.spent == null) { updTx(t.id, { status }); return; }
  const out = pend.spent - returned - (pend.change || 0);   // what this attempt took from the balance in the end
  if (status === 'done') { updTx(t.id, { status, fee: Math.max(0, out - t.amount), change: pend.change || 0 }); return; }   // (change: what came back of the reserve)
  updTx(t.id, { status, fee: 0 });
  if (t.roundup && S.piggy) { S.piggy.saved = Math.max(0, num(S.piggy.saved) - t.roundup); store.set('piggy', S.piggy); updTx(t.id, { roundup: 0 }); }   // nothing was paid, so nothing to round up
  if (out > 0 && !t.costTx) {
    const f = addTx({ type: 'out', method: 'fee', amount: 0, fee: out, mint: pend.mint, note: 'Mint fee for a failed payment', status: 'done', feeFor: t.id });
    updTx(t.id, { costTx: f.id, cost: out });
  }
}
async function checkClaim(tx) {
  const w = await getWallet(tx.mint);
  const st = await w.checkProofsStates(tx.sent);
  const cur = txById(tx.id);
  if (st.every(s => s.state === 'SPENT') && cur && cur.status === 'pending') {
    updTx(tx.id, Object.assign({ status: 'claimed' }, tx.reqPay ? { delivered: true } : {}));   // (a request payment the payee claimed was delivered)
    // an open bounty on it is over too (spent before anyone was sent the secret: taken back on a device holding this wallet)
    for (const c of S.challenges.filter(c => c.dir === 'out')) for (const b of c.bounties || []) if (b.txId === tx.id && b.state === 'open') { b.state = 'claimed'; saveChallenges(); }
    return true;
  }
  return false;
}
/* After an import, what it brought in that holds coins the mint reports spent (spent since on a device holding the same
   wallet) is closed, never shown as holding sats or offered to take back, claim or continue. None of these coins were
   counted in the balance, so no line is added: a token not claimed yet (a gift, bounty, treasure hunt or plain token,
   counted out when it was made) becomes claimed, a copy held as someone's heir has ended, a bounty offered to us is gone. */
// (what couldn't be checked because its mint didn't answer is checked again by the background check until it answers)
async function closeSpentImported({ txs = [], heirlooms = [], chals = [] }) {
  const spentAll = async (u, ps) => { try { const st = await inTime((await getWallet(u)).checkProofsStates(ps), 30000); return ps.length > 0 && st.every(s => s && s.state === 'SPENT'); } catch (e) { return null; } };
  const tokSpent = async tok => { try { const d = await decodeTok(tok); return await spentAll(normUrl(d.mint), d.proofs); } catch (e) { return null; } };
  const later = { heirlooms: [], chals: [] };
  for (const id of txs) { const t = txById(id); if (t && t.status === 'pending' && t.sent && t.sent.length) await checkClaim(t).catch(() => {}); }
  for (const tok of heirlooms) { const h = S.heirlooms.find(x => x.token === tok && x.state === 'waiting'); if (!h) continue; const sp = await tokSpent(h.token); if (sp === null) later.heirlooms.push(tok); else if (sp && h.state === 'waiting') { h.state = 'ended'; saveHeir(); } }
  for (const id of chals) { const c = S.challenges.find(x => x.id === id && x.dir === 'in'), b = c && c.bounty; if (!(b && b.state === 'open')) continue; const sp = await tokSpent(b.token); if (sp === null) later.chals.push(id); else if (sp && b.state === 'open') { b.state = 'gone'; saveChallenges(); } }
  const r = store.get('recheck', { heirlooms: [], chals: [] });
  store.set('recheck', { heirlooms: [...new Set(r.heirlooms.filter(x => !heirlooms.includes(x)).concat(later.heirlooms))], chals: [...new Set(r.chals.filter(x => !chals.includes(x)).concat(later.chals))] });
}
async function recheckImported() {
  const r = store.get('recheck', null);
  if (r && (r.heirlooms.length || r.chals.length)) await single('recheck', () => closeSpentImported({ heirlooms: r.heirlooms, chals: r.chals }));
}
// Remove spent ecash: open steps are settled first, then spent coins are dropped with a history line (the history
// always adds up to the balance)
async function cleanWallet() {
  let removed = 0;
  for (const m of S.mints) { if (!(S.proofs[m.url] || []).length) continue; const before = (S.proofs[m.url] || []).length; await pruneSpent(m.url); removed += Math.max(0, before - (S.proofs[m.url] || []).length); }
  return removed;
}


/* ---------- languages ----------
   The app is written in English; this layer translates what's on screen (text, placeholders, labels, toasts)
   from the dictionaries in i18n.js. Numbers are kept: "Pay {#} SAT" matches "Pay 1,000 SAT".
   Recovery words, codes, amounts, mint names and your own notes are never touched. */
const LANGS = [['auto', 'Automatic'], ['en', 'English'], ['es', 'Español'], ['pt', 'Português (Brasil)'], ['de', 'Deutsch'], ['fr', 'Français']];
const I18N = window.NUTCADE_I18N || {};
let LANG = 'en';
function pickLang() {
  const p = S.prefs.lang || 'auto';
  if (p !== 'auto') return I18N[p] || p === 'en' ? p : 'en';
  const nav = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || 'en']).map(x => String(x).slice(0, 2).toLowerCase());
  for (const x of nav) { if (x === 'en') return 'en'; if (I18N[x]) return x; }
  return 'en';
}
const NUMRE = /\d[\d,.\u00a0\u202f]*/g, NUMEND = /\d(?:[\d,.\u00a0\u202f]*\d)?/g;
function tr(s) {
  if (LANG === 'en' || !s) return s;
  const d = I18N[LANG]; if (!d) return s; if (!d.done) d.done = new Set();
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(s); const core = m[2].replace(/[ \t\r\n]+/g, ' '); if (!core || !/[A-Za-z]/.test(core)) return s;   // (the narrow no-break space French puts inside numbers is kept)
  let out = d.t[core];
  // numbers become {#}; a second try keeps punctuation right after a number ("like 1000." is "like {#}.")
  for (const re of [NUMRE, NUMEND]) { if (out !== undefined) break; const nums = []; const key = core.replace(re, x => { nums.push(x); return '{#}'; }); if (nums.length && d.t[key] !== undefined) { let i = 0; out = d.t[key].replace(/\{#\}/g, () => nums[i++] ?? ''); } }
  if (out === undefined && d.re) for (const [re, rep_] of d.re) { const mm = re.exec(core); if (mm) { const miss = window.__i18nMiss; window.__i18nMiss = null; try { out = rep_.replace(/\$(\d)/g, (_, k) => tr(mm[+k] || '')); } finally { window.__i18nMiss = miss; } break; } }
  if (out === undefined && core.includes('₿')) {   // "₿67 in your piggy bank" uses the "67 SAT in your piggy bank" translation
    const asSat = core.replace(/₿(\d[\d,.\u00a0\u202f]*\d|\d)/g, '$1 SAT'); let t = asSat; if (asSat !== core) { const miss = window.__i18nMiss; window.__i18nMiss = null; try { t = tr(asSat); } finally { window.__i18nMiss = miss; } }
    if (t !== asSat) out = t.replace(/(\d[\d,.\u00a0\u202f]*\d|\d) SAT/g, '₿$1');
  }
  // an amount like "0,15 $US" or "12 CHF" has nothing to translate, so it isn't reported as missing
  if (out === undefined) { if (window.__i18nMiss && !(/\d/.test(core) && core.replace(/[^A-Za-z]/g, '').length <= 3)) { if (!d.vals) d.vals = new Set(Object.values(d.t)); if (!d.vals.has(core) && !d.done.has(core)) window.__i18nMiss.add(core); } return s; }
  if (d.done) d.done.add(out.replace(/[ \t\r\n]+/g, ' ').trim());
  return m[1] + out + m[3];
}
const NOI18N = '.code,.words,textarea,script,style,canvas,.credit-num,.qr,.share-card,[data-noi18n],.tx .note:not(.empty),.mint-pill,.kv dd.tiny,.uname,.tx .ico,.pc-tip';
// what you type in a textarea is never translated, but its placeholder is
const i18nFilter = { acceptNode: n => { if (n.nodeType === 1 && n.matches(NOI18N)) { if (n.tagName === 'TEXTAREA' && !n.hasAttribute('data-noi18n')) trAttrs(n); return NodeFilter.FILTER_REJECT; } return NodeFilter.FILTER_ACCEPT; } };
function trAttrs(el) { for (const a of ['placeholder', 'aria-label', 'title', 'alt']) { const v = el.getAttribute(a); if (v) { const t = tr(v); if (t !== v) el.setAttribute(a, t); } } }
function trNode(root) {
  if (LANG === 'en' || !root) return;
  if (root.nodeType === 3) { const p = root.parentElement; if (p && !p.closest(NOI18N)) { const t = tr(root.nodeValue); if (t !== root.nodeValue) root.nodeValue = t; } return; }
  if (root.nodeType !== 1) return;
  if (root.closest(NOI18N)) { if (root.tagName === 'TEXTAREA' && !root.hasAttribute('data-noi18n')) trAttrs(root); return; }
  trAttrs(root);
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, i18nFilter);
  let n; while ((n = w.nextNode())) { if (n.nodeType === 1) trAttrs(n); else { const t = tr(n.nodeValue); if (t !== n.nodeValue) n.nodeValue = t; } }
}
let i18nObs = null;
function setLang() {
  LANG = pickLang(); document.documentElement.lang = LANG === 'pt' ? 'pt-BR' : LANG;
  if (LANG !== 'en' && !i18nObs && typeof MutationObserver !== 'undefined') {
    i18nObs = new MutationObserver(ms => { if (LANG === 'en') return; for (const m of ms) { if (m.type === 'characterData') trNode(m.target); else m.addedNodes.forEach(trNode); } });
    i18nObs.observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  trNode(document.body);
}

/* ---------- sound ---------- */
const PREF_DEFAULTS = { sound: true, music: true, crt: true, theme: 'neon', btcSymbol: false, fiat: true, currency: 'USD',
  checkSent: true, nostrBackup: true, npc: false, nostrInbox: true, piggy: false, piggyStep: 100 };
for (const k in PREF_DEFAULTS) if (S.prefs[k] === undefined) S.prefs[k] = PREF_DEFAULTS[k];
S.p2pk = store.get('p2pk', []);   // [{pub, priv, created, used}]
S.requests = store.get('requests', []);
S.contacts = store.get('contacts', []);   // [{id, name, ln, nostr, pubkey, relays}]   // payment requests we made: [{id, encoded, amount, memo, created, paid:[txId]}]
const sfx = n => window.NutAudio && window.NutAudio.sfx(n);

/* ---------- logo ---------- */
const GLYPHS = {
  N: ['110011', '111011', '111011', '110111', '110111', '110011', '110011'],
  U: ['110011', '110011', '110011', '110011', '110011', '110011', '011110'],
  T: ['111111', '001100', '001100', '001100', '001100', '001100', '001100'],
  C: ['011111', '110000', '110000', '110000', '110000', '110000', '011111'],
  A: ['011110', '110011', '110011', '111111', '110011', '110011', '110011'],
  D: ['111110', '110011', '110011', '110011', '110011', '110011', '111110'],
  E: ['111111', '110000', '110000', '111110', '110000', '110000', '111111']
};
const ACORN = [
  '....33....',
  '...3333...',
  '.22222222.',
  '2222222222',
  '2121212122',
  '.11111111.',
  '.11411111.',
  '.11411111.',
  '..111111..',
  '...1111...',
  '....11....'
];
function logoSVG(word = 'NUTCADE', withTag = true, mini = false) {
  // mini: one row (acorn beside the word, no stars or tagline) for the compact header on every screen after setup
  const s = 6, gap = 1, cols = word.length * 6 + (word.length - 1) * gap;
  const pad = 4, mascotH = mini ? 2 : ACORN.length + 2, ox = mini ? pad + ACORN[0].length + 3 : pad;
  if (mini) withTag = false;
  const W = cols + ox + pad, H = mini ? ACORN.length + pad * 2 - 2 : mascotH + 7 + pad * 2 + (withTag ? 6 : 0);
  const cells = [];
  [...word].forEach((ch, i) => { const g = GLYPHS[ch]; if (!g) return; g.forEach((row, y) => [...row].forEach((b, x) => { if (b === '1') cells.push([ox + i * 7 + x, pad + mascotH + y - (mini ? 1 : 0)]); })); });
  const rect = (x, y, c, o = 0) => `<rect x="${(x - o) * s}" y="${(y - o) * s}" width="${s + o * 2 * s}" height="${s + o * 2 * s}" fill="${c}"/>`;
  const layer = (dx, dy, c, o = 0) => cells.map(([x, y]) => rect(x + dx, y + dy, c, o)).join('');
  const ax = mini ? pad - 1 : Math.floor(W / 2 - ACORN[0].length / 2), ay = mini ? pad - 2 : pad - 1;
  const ac = { '1': '#b8651f', '2': '#6b3b12', '3': '#3d2208', '4': '#ffd79a' };
  let acorn = '';
  ACORN.forEach((row, y) => [...row].forEach((c, x) => { if (c !== '.') acorn += rect(ax + x + 0.5, ay + y, ac[c]); }));
  let acornOutline = '';
  ACORN.forEach((row, y) => [...row].forEach((c, x) => { if (c !== '.') acornOutline += rect(ax + x + 0.5, ay + y, '#0a0717', 0.5); }));
  const stars = mini ? '' : [[2, 3], [W - 4, 2], [W - 8, 9], [6, 10], [W - 3, 14]].map(([x, y]) => `<g fill="#2de2ff"><rect x="${x * s}" y="${(y - .5) * s}" width="${s}" height="${s * 2}"/><rect x="${(x - .5) * s}" y="${y * s}" width="${s * 2}" height="${s}"/></g>`).join('');
  const tagTop = (pad + mascotH + 7 + 1.6) * s, tagH = 4 * s, tagY = tagTop + tagH / 2;
  return `<svg viewBox="0 0 ${W * s} ${H * s}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="NUTCADE logo" shape-rendering="crispEdges">
<defs><linearGradient id="chrome" x1="0" y1="0" x2="0" y2="1" gradientUnits="objectBoundingBox">
<stop offset="0" stop-color="#fff6c9"/><stop offset=".28" stop-color="#ffd23a"/><stop offset=".28" stop-color="#ff9a1f"/><stop offset=".55" stop-color="#ff3d8b"/>
<stop offset=".55" stop-color="#0a0717"/><stop offset=".575" stop-color="#0a0717"/><stop offset=".575" stop-color="#c13dff"/><stop offset=".78" stop-color="#7a3dff"/><stop offset=".78" stop-color="#0a0717"/><stop offset=".8" stop-color="#0a0717"/><stop offset=".8" stop-color="#2de2ff"/><stop offset="1" stop-color="#2de2ff"/>
</linearGradient></defs>
${stars}
<g>${acornOutline}${acorn}</g>
<g transform="skewX(-8) translate(${Math.round(Math.tan(8 * Math.PI / 180) * (pad + mascotH + 3.5 - (mini ? 1 : 0)) * s)} 0)">
<g>${layer(0, 0, '#0a0717', 1)}</g>
<g>${layer(2, 2, '#ff3d8b')}</g>
<g>${layer(1, 1, '#2de2ff')}</g>
<g>${layer(0, 0, '#0a0717', .5)}</g>
<g fill="url(#chrome)"><rect x="${ox * s}" y="${(pad + mascotH - (mini ? 1 : 0)) * s}" width="${cols * s}" height="${7 * s}" fill="url(#chrome)" mask="url(#letters)"/></g>
<mask id="letters" maskUnits="userSpaceOnUse">${layer(0, 0, '#fff')}</mask>
</g>
${withTag ? `<g class="tagline"><text x="${W * s / 2}" y="${tagY}" dominant-baseline="central" text-anchor="middle" font-family="'Press Start 2P', monospace" font-size="${s * 2.6}" fill="#ffcf3a" stroke="#0a0717" stroke-width="${s * 0.6}" stroke-linejoin="round" paint-order="stroke" textLength="${Math.round((W - 8) * s)}" lengthAdjust="spacingAndGlyphs">INSERT ECASH · PRESS START</text></g>` : ''}
</svg>`;
}
window.NutLogo = logoSVG;
// The full marquee greets new players; every other screen gets a one-row header so the controls fit on a phone.
const marqueeHTML = full => full
  ? `<header class="marquee"><div class="bulbs top">${'<i></i>'.repeat(14)}</div><h1 class="sr">NUTCADE</h1><div class="logo">${logoSVG()}</div><div class="bulbs bot">${'<i></i>'.repeat(14)}</div></header>`
  : `<header class="marquee mini"><div class="bulbs top">${'<i></i>'.repeat(14)}</div><h1 class="sr">NUTCADE</h1><div class="logo">${logoSVG('NUTCADE', false, true)}</div><div class="bulbs bot">${'<i></i>'.repeat(14)}</div></header>`;


/* ---------- QR scanner ---------- */
let scanStream = null, scanRaf = 0;
function stopScan() { cancelAnimationFrame(scanRaf); scanRaf = 0; if (scanStream) { scanStream.getTracks().forEach(t => t.stop()); scanStream = null; } }
/* Decoder: zxing (WebAssembly, loaded from this site only when scanning) with jsQR as fallback. */
let zxReady = null;
function loadZxing() {
  if (zxReady) return zxReady;
  if (location.protocol !== 'https:' && location.protocol !== 'http:') return (zxReady = Promise.resolve(false));
  zxReady = L.prepareZXingModule({
    overrides: { locateFile: (path, prefix) => path.endsWith('.wasm') ? new URL('zxing_reader.wasm', location.href).href : prefix + path },
    fireImmediately: true
  }).then(() => true).catch(() => false);
  return zxReady;
}
const ZX_OPTS = { formats: ['QRCode'], tryHarder: true, maxNumberOfSymbols: 1 };
let scanPass = 0;
function frameData(src, pass) {
  const w0 = src.videoWidth || src.naturalWidth || src.width, h0 = src.videoHeight || src.naturalHeight || src.height;
  if (!w0 || !h0) return null;
  const c = frameData.c || (frameData.c = document.createElement('canvas'));
  const x = c.getContext('2d', { willReadFrequently: true });
  let sx = 0, sy = 0, sw = w0, sh = h0, w, h;
  if (pass === 1) { const side = Math.min(w0, h0) * 0.8; sx = (w0 - side) / 2; sy = (h0 - side) / 2; sw = sh = side; w = h = 1100; }
  else if (pass === 2) { const k = Math.min(2, 1400 / Math.max(w0, h0)); w = Math.round(w0 * k); h = Math.round(h0 * k); }
  else { const k = Math.min(1, 1200 / Math.max(w0, h0)); w = Math.round(w0 * k); h = Math.round(h0 * k); }
  c.width = w; c.height = h; x.imageSmoothingEnabled = pass === 0; x.drawImage(src, sx, sy, sw, sh, 0, 0, w, h);
  return x.getImageData(0, 0, w, h);
}
async function decodeFrame(src, allPasses) {
  const zx = await loadZxing();
  if (zx) {
    const d = frameData(src, 0); if (!d) return null;
    try { const r = await L.readBarcodes(d, ZX_OPTS); if (r[0] && r[0].isValid && r[0].text) return r[0].text; } catch (e) {}
    if (!allPasses) return null;
  }
  // jsQR needs big modules for dense codes, so alternate the whole frame with an enlarged centre crop.
  for (const pass of allPasses ? [0, 1, 2] : [scanPass++ % 3]) {
    const d = frameData(src, pass); if (!d) continue;
    const r = L.jsQR(d.data, d.width, d.height, { inversionAttempts: pass === 0 ? 'attemptBoth' : 'dontInvert' });
    if (r && r.data) return r.data;
  }
  return null;
}
function openScanner(hint) {
  loadZxing();
  openSheet('Scan QR code', `
    <div class="scan-box"><video id="scanVideo" playsinline muted></video><div class="scan-frame" aria-hidden="true"><i></i><i></i><i></i><i></i></div><div class="scan-msg" id="scanMsg">STARTING CAMERA…</div></div>
    <div class="tiny muted" style="text-align:center">${esc(hint || 'Point at an ecash token, Lightning invoice, Lightning address, Bitcoin address or mint.')}</div>
    <div class="btngrid"><label class="btn violet" for="scanFile" style="cursor:pointer">Scan a photo</label><input id="scanFile" type="file" accept="image/*" hidden><button class="btn violet" data-act="scanPaste">Paste instead</button>${nfcBtn('nfcScan', 'Tap NFC')}${window.Chiptune && window.Chiptune.canListen() ? '<button class="btn violet" data-act="ctListen">Listen</button>' : ''}</div>
    <div id="sheetErr"></div>`, () => { startCamera(); return () => { stopScan(); nfcStop(); }; });
}
async function startCamera() {
  const v = $('#scanVideo'), msg = $('#scanMsg');
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { if (msg) msg.textContent = 'NO CAMERA HERE. SCAN A PHOTO OR PASTE.'; return; }
  try {
    scanStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } }, audio: false });
    if (!v || !v.isConnected) { stopScan(); return; }
    v.srcObject = scanStream; await v.play(); if (msg) msg.hidden = true;
    const detector = ('BarcodeDetector' in window) ? await BarcodeDetector.getSupportedFormats().then(f => f.includes('qr_code') ? new BarcodeDetector({ formats: ['qr_code'] }) : null).catch(() => null) : null;
    let busy = false, last = 0, ur = null;
    const tick = async t => {
      if (!scanStream) return;
      scanRaf = requestAnimationFrame(tick);
      if (busy || t - last < (ur ? 90 : 150) || v.readyState < 2) return; busy = true; last = t;
      try {
        let text = null;
        if (detector) { const r = await detector.detect(v); text = r[0] && r[0].rawValue; }
        if (!text) text = await decodeFrame(v);
        if (text && /^ur:/i.test(text) && window.NutUR) {
          // one frame of an animated QR: keep collecting until the whole code is in
          if (!ur) ur = NutUR.decoder();
          if (await ur.receive(text)) { if (navigator.vibrate) try { navigator.vibrate(5); } catch (e) {} }
          if (msg) { msg.hidden = false; msg.textContent = ur.done() ? 'GOT IT' : 'ANIMATED QR · ' + Math.round(ur.progress() * 100) + '%'; }
          if (ur.error()) { ur = null; if (msg) msg.textContent = 'THAT CODE DIDN\'T CHECK OUT. TRY AGAIN.'; }
          text = ur && ur.done() ? ur.text() : null;
        }
        if (text) { stopScan(); sfx('select'); if (navigator.vibrate) try { navigator.vibrate(30); } catch (e) {} handleScan(text); }
      } catch (e) {}
      busy = false;
    };
    scanRaf = requestAnimationFrame(tick);
  } catch (e) {
    if (msg) msg.textContent = /NotAllowed|Permission/i.test(e.name + e.message) ? 'CAMERA BLOCKED. ALLOW IT IN YOUR BROWSER, OR SCAN A PHOTO.' : 'NO CAMERA FOUND. SCAN A PHOTO OR PASTE.';
  }
}
async function scanPhoto(file) {
  try {
    const url = URL.createObjectURL(file); const img = new Image(); img.src = url; await img.decode();
    const text = await decodeFrame(img, true); URL.revokeObjectURL(url);
    if (!text) throw new Error("No QR code found in that picture. Try a sharper, closer photo.");
    const one = await urSingle(text); if (one === false) throw new Error("That's one frame of an animated QR code. Scan it live with the camera instead.");
    stopScan(); handleScan(one || text);
  } catch (e) { showErr(e); }
}
/* Bitcoin addresses are checked, not just pattern-matched: bech32 (BIP173) for SegWit v0 and bech32m (BIP350)
   for v1 and later, base58check for legacy and P2SH, so one wrong or extra letter is caught. Returns the network
   ('main', 'test' or 'regtest') or null. */
const B32 = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';
function b32polymod(v) { const G = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]; let c = 1; for (const x of v) { const b = c >>> 25; c = ((c & 0x1ffffff) << 5) ^ x; for (let i = 0; i < 5; i++) if ((b >>> i) & 1) c ^= G[i]; } return c >>> 0; }
function segwitNet(a) {
  if (a !== a.toLowerCase() && a !== a.toUpperCase()) return null;
  a = a.toLowerCase(); const at = a.lastIndexOf('1'); if (at < 1 || a.length > 90 || a.length - at < 7) return null;
  const hrp = a.slice(0, at), d = [...a.slice(at + 1)].map(c => B32.indexOf(c)); if (d.some(x => x < 0)) return null;
  const net = { bc: 'main', tb: 'test', bcrt: 'regtest' }[hrp]; if (!net) return null;
  const pm = b32polymod([...[...hrp].map(c => c.charCodeAt(0) >> 5), 0, ...[...hrp].map(c => c.charCodeAt(0) & 31), ...d]);
  const ver = d[0]; if (ver > 16 || pm !== (ver === 0 ? 1 : 0x2bc830a3)) return null;
  let acc = 0, bits = 0; const prog = [];
  for (const x of d.slice(1, -6)) { acc = (acc << 5) | x; bits += 5; while (bits >= 8) { bits -= 8; prog.push((acc >> bits) & 255); } }
  if (bits >= 5 || (acc & ((1 << bits) - 1))) return null;
  if (prog.length < 2 || prog.length > 40 || (ver === 0 && prog.length !== 20 && prog.length !== 32)) return null;
  return net;
}
function base58Net(a) {
  const AB = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'; let n = 0n;
  for (const c of a) { const i = AB.indexOf(c); if (i < 0) return null; n = n * 58n + BigInt(i); }
  const bytes = []; while (n > 0n) { bytes.unshift(Number(n & 255n)); n >>= 8n; }
  for (const c of a) { if (c !== '1') break; bytes.unshift(0); }
  if (bytes.length !== 25) return null;
  const body = Uint8Array.from(bytes.slice(0, 21)), sum = L.sha256(L.sha256(body));
  if (bytes.slice(21).some((x, i) => x !== sum[i])) return null;
  return { 0x00: 'main', 0x05: 'main', 0x6f: 'test', 0xc4: 'test' }[bytes[0]] || null;
}
const btcAddr = a => { a = String(a || '').trim(); return /^(bc|tb|bcrt)1/i.test(a) ? segwitNet(a) : /^[123mn][1-9A-HJ-NP-Za-km-z]{24,40}$/.test(a) ? base58Net(a) : null; };
// the network a mint's Lightning invoices are on, when NUTCADE has seen one: lnbc main, lntb test, lnbcrt regtest
function mintNet(url) {
  const r = [...S.txs, ...S.quotes].filter(t => t.mint === url && /^ln(bcrt|tbs?|bc)\d*/i.test(t.request || '')).map(t => t.request.toLowerCase())[0];
  return !r ? null : r.startsWith('lnbcrt') ? 'regtest' : r.startsWith('lntb') ? 'test' : 'main';
}
// throws a reason when the address can't be paid from this mint
function checkBtcAddr(a, url) {
  const net = btcAddr(a);
  if (!net) throw new Error('That Bitcoin address looks wrong. Check it and paste again.');
  const want = mintNet(url);
  // testnet and regtest share the legacy prefixes m, n and 2, so only bech32 tells them apart
  if (want && want !== net && !(want === 'regtest' && net === 'test' && !/^tb1/i.test(a))) throw new Error(want === 'main' ? "That's a test-network address. This mint pays out on the real Bitcoin network."
    : net === 'main' ? "That's a real Bitcoin address, but this mint pays out on a test network." : "That address is for a different test network than this mint's.");
  return net;
}
/* Figure out what a scanned or pasted string is and open the right screen for it. */
function classify(raw) {
  let t = String(raw || '').trim();
  if (/cashu[AB][A-Za-z0-9_\-+/=]{20,}/.test(t)) return { kind: 'token', value: cleanToken(t) };
  { const m = t.match(/creqA[A-Za-z0-9_\-+/=]+|creqb1[02-9ac-hj-np-z]+/i); if (m) return { kind: 'request', value: m[0] }; }
  { const m = t.match(/^(?:nostr:)?((?:npub1|nprofile1)[02-9ac-hj-np-z]+)$/i); if (m && parseNostrAddr(m[1])) return { kind: 'nostr', value: m[1].toLowerCase() }; }
  const low = t.toLowerCase();
  if (low.startsWith('bitcoin:')) {
    const [addr, q] = t.slice(8).split('?');
    const ps = [...new URLSearchParams(q || '')], get = k => ps.filter(x => x[0].toLowerCase() === k).map(x => x[1]);   // QR codes may be all caps
    const ln = get('lightning')[0]; if (ln && /^ln(bc|tb|bcrt)/i.test(ln)) return { kind: 'invoice', value: ln.toLowerCase() };
    if (!btcAddr(addr)) return { kind: 'unknown' };
    // BIP21 amounts are BTC with a decimal point (see parseBtc). One that can't be read, or two amounts, is left out, never guessed.
    const am = get('amount'), sats = am.length === 1 ? parseBtc(am[0]) : null;
    return { kind: 'btc', value: /^(bc|tb|bcrt)1/i.test(addr) ? addr.toLowerCase() : addr, amount: sats, badAmount: am.length && sats == null ? am.join(' ') : null };
  }
  t = t.replace(/^lightning:/i, '');
  if (/^ln(bc|tb|bcrt|tbs)[0-9a-z]{50,}$/i.test(t)) return { kind: 'invoice', value: t.toLowerCase() };
  if (/^lnurl1[0-9a-z]+$/i.test(t)) return { kind: 'lnurl', value: t.toLowerCase() };
  if (/^lnurl[pwc]:\/\/[^\s]+$/i.test(t)) return { kind: 'lnurl', value: t };   // LUD-17
  if (/^https?:\/\/[^\s]+[?&]lightning=lnurl1[0-9a-z]+/i.test(t)) return { kind: 'lnurl', value: t };
  if (/^[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i.test(t)) return { kind: 'lnaddress', value: t.toLowerCase() };
  if (btcAddr(t)) return { kind: 'btc', value: /^(bc|tb|bcrt)1/i.test(t) ? t.toLowerCase() : t, amount: null };
  if (/^https?:\/\/[^\s]+$/i.test(t)) return { kind: 'mint', value: normUrl(t) };
  return { kind: 'unknown' };
}
// a NUTCADE link: a challenge, or a treasure-hunt clue card
function openLink(t) { if (/^hunt=/.test(t)) { onHuntCard(t.slice(5)); return; } if (/^challenge=/.test(t)) { let rec = null; try { const [evPart, rPart] = t.slice(10).split('&r='); rec = onChallenge(JSON.parse(new TextDecoder().decode(unb64url(evPart))), 'link', null, null, rPart || null); } catch (e) {} if (rec && rec.noChallenge) { const g = window.Arcade && window.Arcade.games.find(x => x.id === rec.noChallenge); openSheet('Challenge!', `<div class="notice" id="noChal">No challenges on this cabinet. You can still play it for fun.</div><div class="tiny muted" data-noi18n>${esc(g ? g.name : '')}</div><button class="btn solid gold block" data-act="openCab" data-game="${esc(rec.noChallenge)}">Play</button><button class="btn block" data-act="close">Later</button>`); } else if (rec && rec.dir === 'in') openChallengeIn(rec.id); else if (rec) openChallengeSend(rec.id); else toast("That challenge link isn't valid.", 'gold'); } else handleScan(t); }
// A ur: code that fits in one QR (or was pasted) decodes on its own. Returns the text, false for one frame of a longer code, null if it isn't ur:.
async function urSingle(text) {
  if (!/^ur:/i.test(String(text).trim()) || !window.NutUR) return null;
  const d = NutUR.decoder(); try { await d.receive(String(text).trim()); } catch (e) { return null; }
  return d.done() ? d.text() : false;
}
function handleScan(text) {
  // a NUTCADE link (a challenge or a treasure-hunt clue) scanned with the camera opens like a tapped link
  { const lk = /#((?:challenge|hunt)=[A-Za-z0-9_.&=-]+)/.exec(String(text || '')); if (lk && /^https?:\/\//i.test(String(text).trim())) { if (needSeed()) return; closeSheet(); openLink(lk[1]); return; } }
  if (/^ur:bytes\//i.test(String(text || '').trim())) { urSingle(text).then(t => t ? handleScan(t) : toast("That's one frame of an animated QR code. Scan it live with the camera instead.", 'gold')); return; }
  const c = classify(text);
  if (c.kind === 'token') { closeSheet(); openReceive('ecash'); const box = $('#tokIn'); if (box) { box.value = c.value; box.dispatchEvent(new Event('input', { bubbles: true })); } return; }
  if (c.kind === 'unknown') { closeSheet(); sfx('err'); toast("That QR code isn't something NUTCADE can use.", 'gold'); return; }
  if (c.kind === 'request') { if (needSeed()) return; return openPayRequest(c.value); }
  if (c.kind === 'nostr') { if (needSeed()) return; const k = S.contacts.find(x => x.pubkey === parseNostrAddr(c.value).pubkey); return k ? openPayContact(k.id) : openContactEdit(null, { nostr: c.value }); }
  if (c.kind === 'lnurl') { if (needMint()) return; return openLnurl(c.value); }
  if (needMint()) return;
  if (c.kind === 'invoice') { openSend('ln'); const d = $('#destIn'); if (d) { d.value = c.value; const b = $('[data-act="doMeltQuote"]'); if (b) b.click(); } return; }
  if (c.kind === 'btc') {
    openSend('onchain'); const d = $('#destIn'); if (d) d.value = c.value; if (c.amount && $('#amtIn')) setSats($('#amtIn'), c.amount);
    if (c.badAmount != null) showErr(amtErr("This Bitcoin link's amount can't be read, so it was left out. Type the amount yourself.", 'bip21'));
    return;
  }
  if (c.kind === 'lnaddress') return openPayLnurl(c.value);
  if (c.kind === 'mint') { openMintPicker(); const u = $('#mintUrl'); if (u) { u.value = c.value; u.focus(); } toast('Check the address, then tap Add', 'cyan'); }
}
function lnurlToUrl(v) {
  if (/^(lnurl[pwc]:\/\/|https?:\/\/)/i.test(v)) return lnurlHttp(v);   // LUD-17 schemes and ?lightning= links
  if (v.includes('@')) { const [user, domain] = v.split('@'); return `https://${domain}/.well-known/lnurlp/${encodeURIComponent(user)}`; }
  const d = L.bech32.decode(v, 2000); return new TextDecoder().decode(L.bech32.fromWords(d.words));
}
function openPayLnurl(target) {
  openSheet('Pay', `<div class="tiny muted">To</div><div class="code" style="color:var(--ink)">${esc(target.length > 48 ? target.slice(0, 24) + '…' + target.slice(-12) : target)}</div>
    <div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="1000" autocomplete="off"></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200"></div>
    <button class="btn solid pink block" data-act="lnurlQuote" data-t="${esc(target)}">Get quote</button><div id="sheetErr"></div>`);
}
async function lnurlInvoice(target, sats, comment) {
  const base = await fetch(lnurlToUrl(target)).then(r => { if (!r.ok) throw new Error(`That address didn't answer (${r.status}).`); return r.json(); });
  if (base.status === 'ERROR') throw new Error(base.reason || 'That address returned an error.');
  if (base.tag !== 'payRequest' || !base.callback) throw new Error("That address isn't set up to receive payments.");
  const msat = sats * 1000;
  if (msat < base.minSendable || msat > base.maxSendable) throw new Error(`This address accepts ${money(Math.ceil(base.minSendable / 1000))} to ${money(Math.floor(base.maxSendable / 1000))}.`);
  const u = new URL(base.callback); u.searchParams.set('amount', String(msat));
  if (comment && base.commentAllowed) u.searchParams.set('comment', comment.slice(0, base.commentAllowed));
  const inv = await fetch(u.toString()).then(r => r.json());
  if (inv.status === 'ERROR' || !inv.pr) throw new Error(inv.reason || "Couldn't get an invoice from that address.");
  return inv.pr;
}

/* ---------- payment effects: coin drop on receive, coin launch on send ---------- */
const COIN = ['..yyyy..', '.yYYYYy.', 'yYyyyyYy', 'yYyYYyYy', 'yYyYYyYy', 'yYyyyyYy', '.yYYYYy.', '..yyyy..'];
function celebrate(dir, amount) {
  if (document.querySelector('.cashier')) return;   // the till has its own PAID! screen
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const old = document.getElementById('fxLayer'); if (old) old.remove();
  const layer = document.createElement('div'); layer.id = 'fxLayer'; layer.setAttribute('aria-hidden', 'true');
  const label = document.createElement('div'); label.className = 'fx-label ' + (dir === 'in' ? 'in' : 'out');
  const big = document.createElement('b'); big.textContent = dir === 'in' ? '1UP!' : 'SENT!';
  const amt = document.createElement('span'); amt.textContent = (dir === 'in' ? '+' : '-') + money(amount);
  label.append(big, amt); layer.appendChild(label);
  document.body.appendChild(layer);
  if (reduce) { setTimeout(() => layer.remove(), 1400); return; }
  const cv = document.createElement('canvas'); layer.prepend(cv);
  const dpr = Math.min(2, devicePixelRatio || 1), W = innerWidth, H = innerHeight;
  cv.width = W * dpr; cv.height = H * dpr; const x = cv.getContext('2d'); x.scale(dpr, dpr); x.imageSmoothingEnabled = false;
  const gold = getComputedStyle(document.body).getPropertyValue('--gold').trim() || '#ffcf3a';
  const n = Math.min(26, 8 + Math.round(Math.log10(Math.max(10, num(amount))) * 4));
  const coins = Array.from({ length: n }, (_, i) => dir === 'in'
    ? { x: Math.random() * W, y: -20 - Math.random() * H * 0.5, vx: (Math.random() - .5) * 1.2, vy: 2 + Math.random() * 3, s: 3 + Math.floor(Math.random() * 2), f: Math.random() * 6 }
    : { x: W / 2 + (Math.random() - .5) * 120, y: H * 0.62, vx: (Math.random() - .5) * 6, vy: -9 - Math.random() * 6, s: 3 + Math.floor(Math.random() * 2), f: Math.random() * 6 });
  const t0 = performance.now();
  (function frame(t) {
    const el = t - t0; if (el > 1700 || !layer.isConnected) { layer.remove(); return; }
    x.clearRect(0, 0, W, H);
    for (const c of coins) {
      c.vy += dir === 'in' ? 0.25 : 0.32; c.x += c.vx; c.y += c.vy; c.f += 0.25;
      if (dir === 'in' && c.y > H - 40 && c.vy > 0) { c.vy *= -0.45; c.y = H - 40; }
      const w = Math.max(0.15, Math.abs(Math.cos(c.f))); // spinning coin
      x.save(); x.translate(Math.round(c.x), Math.round(c.y)); x.scale(w, 1); x.globalAlpha = el > 1300 ? (1700 - el) / 400 : 1;
      COIN.forEach((row, ry) => [...row].forEach((ch, rx) => { if (ch === '.') return; x.fillStyle = ch === 'Y' ? '#fff3b0' : gold; x.fillRect((rx - 4) * c.s, (ry - 4) * c.s, c.s, c.s); }));
      x.restore();
    }
    requestAnimationFrame(frame);
  })(t0);
}

/* ---------- QR ---------- */
function qrCanvas(text, mode) {
  try {
    const qr = L.qrcode(0, text.length > 600 ? 'L' : 'M');
    qr.addData(text, mode); qr.make();
    const n = qr.getModuleCount(), sc = 4, q = 2;
    const c = document.createElement('canvas'); c.width = c.height = (n + q * 2) * sc;
    const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, c.width, c.height); x.fillStyle = '#0a0717';
    for (let r = 0; r < n; r++) for (let k = 0; k < n; k++) if (qr.isDark(r, k)) x.fillRect((k + q) * sc, (r + q) * sc, sc, sc);
    return c;
  } catch (e) { return null; }
}
function slimToken(t) {
  const d = L.getDecodedToken(t, Object.keys(S.counters));
  return L.getEncodedToken({ mint: d.mint, unit: d.unit || 'sat', memo: d.memo, proofs: d.proofs.map(p => { const o = Object.assign({}, p); delete o.dleq; return o; }) });
}
// Above this many characters a single QR code gets too dense for most phone cameras, so it plays as an animated QR instead.
const QR_STATIC_MAX = 1000;
function qrBlock(text, label) {
  const id = 'qr' + uid();
  setTimeout(() => {
    const el = document.getElementById(id); if (!el) return;
    // Tokens with many proofs (locked gifts especially) get long. Without the DLEQ proofs, which the receiving wallet
    // doesn't need to claim the ecash, they're about a quarter shorter. The copied text stays the full token.
    let t = text;
    if (/^cashuB/.test(text) && text.length > QR_STATIC_MAX) { try { t = slimToken(text); } catch (e) {} }
    const c = t.length <= QR_STATIC_MAX ? qrCanvas(t) : null;
    if (c) { c.setAttribute('aria-label', tr(label || 'QR code')); el.appendChild(c); return; }
    animatedQR(el, t, label);
  }, 0);
  return `<div class="qr" id="${id}"></div>`;
}
/* A long code plays as a loop of small QR codes (BC-UR, the format cashu.me uses), drawn in uppercase so each frame
   is a compact alphanumeric QR. Any frame order works and missed frames are fine: the scanner keeps collecting. */
function animatedQR(el, text, label) {
  if (!window.NutUR) { el.outerHTML = '<div class="notice cyan">Too long for one QR code. Use Copy or Play as sound instead.</div>'; return; }
  const enc = NutUR.encoder(text, 150); let n = 0;
  el.classList.add('qr-anim'); el.setAttribute('role', 'img'); el.setAttribute('aria-label', tr((label || 'QR code') + ', animated'));
  el.insertAdjacentHTML('afterend', `<div class="tiny muted qr-anim-note" style="text-align:center">Animated QR · ${enc.count} parts · scan with NUTCADE or cashu.me</div>`);
  const step = async () => {
    if (!el.isConnected) return;
    const part = (await enc.next()).toUpperCase();
    const c = qrCanvas(part, 'Alphanumeric') || qrCanvas(part);
    if (c && el.isConnected) { el.replaceChildren(c); el.dataset.part = String(++n); }
    setTimeout(step, 200);
  };
  step();
}

/* ---------- toasts / copy ---------- */
/* A new toast replaces the one on screen (the latest thing you did matters most), for a time that fits its
   length. While a game is open every toast waits until you leave it (the last three, one after another), so
   none lands on the controls, the key hints or a high score; the cashier screen only shows errors. */
let toastT = 0; const toastQ = [];
const toastHeld = () => !!(window.Arcade && window.Arcade.playing && window.Arcade.playing());
const toastMs = (msg, c) => Math.min(c === 'red' ? 5000 : 4000, 1600 + msg.length * 32);
function toast(msg, c = 'lime') {
  msg = tr(String(msg ?? ''));
  if (document.querySelector('.cashier') && c !== 'red') return;   // the till shows its own PAID! screen
  if (toastHeld()) {
    if (!toastQ.some(t => t.msg === msg)) { toastQ.push({ msg, c }); while (toastQ.filter(t => t.c !== 'red').length > 3) toastQ.splice(toastQ.findIndex(t => t.c !== 'red'), 1); }   // errors are never dropped; at most three others wait
    if (!toastT) toastT = setTimeout(nextToast, 1000); return;
  }
  showToast(msg, c);
}
function showToast(msg, c) {
  let el = $('#toast'); if (!el) { el = document.createElement('div'); el.id = 'toast'; el.className = 'toast'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
  clearTimeout(toastT);
  el.style.setProperty('--c', `var(--${c})`); el.textContent = msg; el.hidden = false;
  const ct = document.querySelector('.cashier .cash-top');   // on the till the toast sits just under its top row, however tall a translated button makes it
  el.style.top = ct ? Math.max(4, Math.round(ct.getBoundingClientRect().bottom + 6)) + 'px' : '';
  toastT = setTimeout(() => { el.hidden = true; toastT = toastQ.length ? setTimeout(nextToast, 180) : 0; }, toastMs(msg, c));
}
function nextToast() {   // held toasts, once the game is closed
  toastT = 0;
  if (toastHeld()) { toastT = setTimeout(nextToast, 1000); return; }
  const i = toastQ.findIndex(x => x.c === 'red'); const t = toastQ.splice(i >= 0 ? i : 0, 1)[0]; if (t) showToast(t.msg, t.c);   // errors first
}
// a game opening puts the toast on screen back in line until the game closes
function holdToasts() {
  const el = $('#toast'); if (!el || el.hidden) return;
  if (!toastQ.some(t => t.msg === el.textContent)) toastQ.unshift({ msg: el.textContent, c: (el.style.getPropertyValue('--c').match(/--(\w+)/) || [, 'lime'])[1] });
  el.hidden = true; clearTimeout(toastT); toastT = setTimeout(nextToast, 1000);
}
function clearToasts() { for (let i = toastQ.length - 1; i >= 0; i--) if (toastQ[i].c !== 'red') toastQ.splice(i, 1); clearTimeout(toastT); toastT = 0; const el = $('#toast'); if (el && !(el.style.getPropertyValue('--c') || '').includes('red')) el.hidden = true; if (toastQ.length) toastT = setTimeout(nextToast, 300); }
async function copy(text, el) {
  try { await navigator.clipboard.writeText(text); toast('Copied', 'cyan'); sfx('blip'); }
  catch (e) {
    const box = el && el.closest('.sheet') && el.closest('.sheet').querySelector('.code');
    if (box) { const r = document.createRange(); r.selectNodeContents(box); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }
    toast('Copy blocked here. The text is selected, copy it by hand.', 'gold');
  }
}

/* ---------- sheets ---------- */
let sheetCleanup = null;
/* Amount fields: type sats, or flip to your currency (uses the live price, when Show Bitcoin price is on). */
const canFiat = () => !!(S.prefs.fiat && price.rate && price.cur === S.prefs.currency);
/* ---------- typed amounts ----------
   Every amount or count a person types is read by one of four parsers: parseSat (whole SAT), parseFiat (your
   currency), parseBtc (the amount in a bitcoin: link) and parseCount (people, coins, keys). Each returns the
   exact value or throws a message in your language that says what it couldn't read and shows an example.
   Nothing is guessed and nothing is dropped: a letter, a minus sign, a second decimal mark or a digit group
   that isn't three digits long makes the whole amount unreadable.
   Digit groups: a mark (or a space, or ') counts as grouping only when the first group is 1 to 3 digits and
   doesn't start with 0, and every later group is exactly 3 digits. Anything else with marks in it is refused.
   Your currency: German, Spanish, Portuguese and French use a decimal comma; English uses a decimal point.
   When both marks appear, the last one is the decimal mark and may appear only once (1.234,56 and 1,234.56
   both mean 1234.56). A lone decimal mark of your language is always the decimal mark (1.000 is one in
   English). A lone mark of the other kind is grouping when it fits the grouping rule (1.000 is a thousand in
   German) and otherwise the decimal mark (0.500 in German is a half, 1234.5 in German is 1234.5). */
const MAX_SAT = 2100000000000000;   // 21 million BTC: no amount can be larger than every bitcoin there will ever be
const GAP = /[\s'’   ]/;   // spaces and apostrophes only ever group digits
const SEPS = /[.,\s'’   ]/g;
const AMT_CHARS = /^[0-9.,\s'’   ]+$/;
const decMark = () => (1.5).toLocaleString(numLocale()).replace(/\d/g, '') || '.';
const grpMark = () => { const g = (1234).toLocaleString(numLocale(), { useGrouping: 'always' }).replace(/\d/g, ''); return /^[.,]$/.test(g) ? g : ' '; };
// 1.234.567 or 1 234 567 or 1234567; never 1.23.456, 12..50 or 0.500
const groupsOk = s => { const g = s.split(/[.,\s'’   ]/); return g.length === 1 ? /^\d+$/.test(g[0]) : /^[1-9]\d{0,2}$/.test(g[0]) && g.slice(1).every(x => /^\d{3}$/.test(x)); };
const amtErr = (msg, why) => { const e = new Error(msg); e.amount = why; return e; };
const fiatUnreadable = () => amtErr("That amount can't be read. Type it like this: " + fmtFiatPlain(1234.56), 'unreadable');
const satUnreadable = () => amtErr("That amount can't be read. Type whole SAT, like this: " + fmt(1500), 'unreadable');
const satWhole = () => amtErr('SAT are whole numbers, with no decimals. Type it like this: ' + fmt(1500), 'decimal');
const tooLarge = () => amtErr("That's more than 21 million BTC, more bitcoin than will ever exist. Type a smaller amount.", 'large');
const parseFiat = v => Number(parseFiatText(v));
// the amount as a plain decimal string ("1234.56"), so converting it to SAT can be exact
function parseFiatText(v) {
  const s = String(v ?? '').trim(); if (!s) return '0';
  if (!AMT_CHARS.test(s)) throw fiatUnreadable();
  const dec = decMark(), dot = s.lastIndexOf('.'), comma = s.lastIndexOf(',');
  let point = -1;
  if (dot >= 0 && comma >= 0) point = Math.max(dot, comma);
  else if (dot >= 0 || comma >= 0) {
    const at = Math.max(dot, comma), mark = s[at];
    if (s.indexOf(mark) !== at) point = -1;                       // the same mark twice: grouping (1.234.567)
    else if (mark === dec) point = at;                            // your language's decimal mark
    else point = groupsOk(s) && /^\d{3}$/.test(s.slice(at + 1)) ? -1 : at;   // 1.000 in German is a thousand; 0.500 and 1234.5 are decimals
  }
  const whole = point >= 0 ? s.slice(0, point) : s, frac = point >= 0 ? s.slice(point + 1) : '';
  if (point >= 0 && s.indexOf(s[point]) !== point) throw fiatUnreadable();   // two decimal marks
  if (!/^\d*$/.test(frac) || (whole && !groupsOk(whole))) throw fiatUnreadable();
  // "01.000": a leading zero, then a mark and three digits, could be a mistyped 1.000 (a thousand) or 1.0: refused
  if (point >= 0 && /^0\d/.test(whole) && frac.length === 3) throw fiatUnreadable();
  return (whole.replace(SEPS, '') || '0') + '.' + (frac || '0');
}
function parseSat(v) {
  const s = String(v ?? '').trim(); if (!s) return 0;
  if (!AMT_CHARS.test(s)) throw satUnreadable();
  const punct = s.replace(/[^.,]/g, ''), single = punct.length === 1 && !GAP.test(s);
  // grouping uses spaces or your language's own mark (1,500 in English, 1.500 in German, 1 500 in French);
  // any other mark, or a group that isn't 3 digits, reads as a decimal (1.5, 1,5) or isn't an amount at all
  if ([...punct].some(c => c !== grpMark()) || !groupsOk(s)) throw single ? satWhole() : satUnreadable();
  const n = Number(s.replace(SEPS, ''));
  if (!Number.isSafeInteger(n) || n > MAX_SAT) throw tooLarge();
  return n;
}
// whole-number counts: people at the table, coins in a hunt. msg is the sentence to show when it isn't one.
function parseCount(v, msg) {
  const s = String(v ?? '').trim();
  if (!/^\d{1,9}$/.test(s)) throw amtErr(msg || 'Use a whole number, like 4.', 'count');
  return Number(s);
}
/* bitcoin: links (BIP21) write the amount in BTC with a decimal point: amount = *digit [ "." *digit ]. NUTCADE
   reads digits with an optional point and at most 8 decimals (1 SAT), using string math so nothing is rounded.
   Exponents (1e-3), commas, signs and anything after the digits are not BIP21, so they return null, and so does
   an amount of 0 or above 21 million BTC. The caller then leaves the amount out and says so. */
function parseBtc(v) {
  const m = /^(\d*)(?:\.(\d*))?$/.exec(String(v ?? ''));
  if (!m || !(m[1] || m[2]) || (m[2] || '').length > 8) return null;
  const w = (m[1] || '0').replace(/^0+(?=\d)/, ''); if (w.length > 8) return null;
  const n = Number(w) * 1e8 + Number((m[2] || '').padEnd(8, '0'));
  return n > 0 && n <= MAX_SAT ? n : null;
}
// your currency without grouping, with the language's decimal mark: 12,50 in German, 12.50 in English
const fmtFiatPlain = (x, dp = 2) => Number(x).toLocaleString(numLocale(), { minimumFractionDigits: dp, maximumFractionDigits: dp, useGrouping: false });
/* SAT, from an amount in your currency ("1234.56") at the live rate, in exact decimal arithmetic and rounded half
   up, so a large amount is never a SAT off from floating point. One that rounds to nothing, or is more than
   21 million BTC, is refused. */
function fiatToSats(t, rate = price.rate) {
  const m = /^(\d*)\.?(\d*)$/.exec(String(t)), r = /^(\d+)\.?(\d*)$/.exec(String(rate));
  if (!m || !(rate > 0)) return 0;
  let n;
  if (r) {
    const num = BigInt((m[1] + m[2]) || '0') * 10n ** BigInt(r[2].length + 8), den = BigInt(r[1] + r[2]) * 10n ** BigInt(m[2].length);
    if (num === 0n) return 0;
    const q = (2n * num + den) / (2n * den);
    if (q > BigInt(MAX_SAT)) throw tooLarge();
    n = Number(q);
  } else n = Math.round(Number(t) / rate * 1e8);   // a rate written with an exponent: never seen, but still sane
  if (!(Number(t) > 0)) return 0;
  if (n < 1) throw amtErr("That's less than 1 SAT. Type a larger amount.", 'small');
  if (!Number.isSafeInteger(n) || n > MAX_SAT) throw tooLarge();
  return n;
}
function satsOf(id) {
  const el = typeof id === 'string' ? $('#' + id) : id; if (!el) return 0;
  const v = String(el.value || '').trim(); if (!v) return 0;
  if (el.dataset.cur === 'fiat') {
    // typed in SAT and only the view was switched: the amount is still exactly the SAT typed
    const bk = el._unitBack; if (bk && bk.cur === 'sat' && bk.shown === el.value) return parseSat(bk.typed);
    if (!canFiat()) throw new Error('The exchange rate is not available right now. Switch the amount to SAT.');
    return fiatToSats(parseFiatText(v));
  }
  return parseSat(v);
}
function setSats(el, n) { if (!el) return; el._unitBack = null; el.dataset.cur = 'sat'; el.value = n; const w = el.closest('.amtwrap'); if (w) { const b = w.querySelector('.unitbtn'); if (b) b.textContent = 'SAT'; el.setAttribute('inputmode', 'numeric'); } unitLabel(el); amtConv(el); }
// "Amount (SAT)" becomes "Amount (USD)" when you type in your currency
function unitLabel(el) {
  const lab = el.id && document.querySelector(`label[for="${el.id}"]`); if (!lab) return;
  if (lab.dataset.en === undefined) { if (!/\(SAT\b/.test(lab.textContent)) return; lab.dataset.en = lab.textContent; }
  lab.textContent = tr(lab.dataset.en.replace('(SAT', '(' + (el.dataset.cur === 'fiat' ? S.prefs.currency : 'SAT')));
}
function amtConv(el) {
  const out = el.parentElement && el.parentElement.parentElement && el.parentElement.parentElement.querySelector('.amtconv');
  let t = '', bad = false;
  try {
    const n = satsOf(el);   // throws when the amount can't be read: the field is marked and the hint stays empty
    if (n && canFiat()) t = el.dataset.cur === 'fiat' ? `≈ ${money(n)}` : `≈ ${fiatOf(n)}`;
  } catch (e) { bad = !!e.amount; }
  if (bad) el.setAttribute('aria-invalid', 'true');
  else { el.removeAttribute('aria-invalid'); const er = $('#sheetErr [data-amount]'); if (er) er.remove(); }   // fixed: the old reason goes
  if (out) out.textContent = t;
}
function enhanceAmounts(root) {
  if (!root || !S.prefs.fiat) return;
  root.querySelectorAll('input.amount:not([data-enh])').forEach(el => {
    el.dataset.enh = '1'; el.dataset.cur = 'sat';
    const lab = el.id && root.querySelector(`label[for="${el.id}"]`); if (lab && /\(SAT\b/.test(lab.textContent)) lab.dataset.en = lab.textContent;
    const wrap = document.createElement('div'); wrap.className = 'amtwrap';
    el.parentElement.insertBefore(wrap, el); wrap.appendChild(el);
    wrap.insertAdjacentHTML('beforeend', `<button type="button" class="unitbtn" data-act="amtUnit" aria-label="Switch between sats and ${esc(S.prefs.currency)}">SAT</button>`);
    wrap.insertAdjacentHTML('afterend', '<div class="amtconv tiny muted" aria-live="polite"></div>');
    el.addEventListener('input', () => amtConv(el));
    if (S.prefs.amtFiat && canFiat() && !el.value) toggleUnit(el);
    amtConv(el);
  });
}
// your currency, with enough decimals to show a small amount: 0.68 or 0.0068, never 0.00
const fiatField = x => x >= 0.01 || !(x > 0) ? fmtFiatPlain(x) : Number(x).toLocaleString(numLocale(), { minimumFractionDigits: 2, maximumFractionDigits: Math.min(8, Math.ceil(-Math.log10(x)) + 1), useGrouping: false });
/* SAT ⇄ your currency. Switching back without editing restores exactly what you typed (7 SAT stays 7, not the
   10 that $0.01 would make). An amount that can't be read stays as it is, with the reason, and doesn't switch. */
function toggleUnit(el) {
  if (!canFiat() && el.dataset.cur !== 'fiat') { toast('Turn on Show Bitcoin price in Settings to enter amounts in your currency.', 'gold'); return; }
  let n = 0; try { n = satsOf(el); } catch (e) { showErr(e); return; }
  const toFiat = el.dataset.cur !== 'fiat', typed = el.value, back = el._unitBack;
  let next = n ? (toFiat ? fiatField(n / 1e8 * price.rate) : String(n)) : '';
  if (back && back.cur === (toFiat ? 'fiat' : 'sat') && back.shown === typed) next = back.typed;   // not edited since the last switch
  el._unitBack = { cur: el.dataset.cur, typed, shown: next };
  el.dataset.cur = toFiat ? 'fiat' : 'sat';
  el.setAttribute('inputmode', toFiat ? 'decimal' : 'numeric');
  el.value = next;
  const b = el.parentElement.querySelector('.unitbtn'); if (b) b.textContent = toFiat ? S.prefs.currency : 'SAT';
  unitLabel(el); S.prefs.amtFiat = toFiat; save(); amtConv(el);
}
let sheetOpener = null;   // the control that opened the sheet gets focus back when it closes
function openSheet(title, html, onOpen) {
  const was = document.activeElement;
  closeSheet();
  sheetOpener = was && was !== document.body && !was.closest('#layer') ? was : sheetOpener && sheetOpener.isConnected ? sheetOpener : null;
  const layer = $('#layer');
  layer.innerHTML = `<div class="scrim" data-scrim><div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="sheet-head"><h3>${esc(title)}</h3><button class="x" data-act="close" aria-label="Close">X</button></div><div class="sheet-body" style="display:grid;gap:14px">${html}</div></div></div>`;
  const body = layer.querySelector('.sheet-body');
  enhanceAmounts(body);
  sheetCleanup = onOpen ? onOpen(body) : null; fitNums(body);
  const f = layer.querySelector('input:not([type=file]),textarea'); if (!matchMedia('(pointer:coarse)').matches) { if (f) f.focus(); else { const sh = layer.querySelector('.sheet'); sh.tabIndex = -1; sh.focus({ preventScroll: true }); } }
  return body;
}
function fitNums(root) {
  (root || document).querySelectorAll('.credit-num,.cash-amt,.cash-charge').forEach(el => {
    if (el.dataset.fs === undefined) el.dataset.fs = el.style.fontSize || '';
    const min = el.classList.contains('cash-charge') ? 9 : 14;   // the CHARGE label stays one readable line
    let fs = parseFloat(getComputedStyle(el).fontSize), i = 0;
    while (el.scrollWidth > el.clientWidth + 1 && fs > min && i++ < 30) { fs = Math.max(min, fs - (min < 14 ? 0.5 : 1.5)); el.style.fontSize = fs + 'px'; }
  });
}
function closeSheet() {
  if (typeof sheetCleanup === 'function') sheetCleanup(); sheetCleanup = null;
  const had = !!$('#layer').firstChild, inLayer = document.activeElement && document.activeElement.closest('#layer');
  $('#layer').innerHTML = '';
  // the screen may have been redrawn while the sheet was open: then find the same button again
  let back = sheetOpener;
  if (back && !back.isConnected && back.dataset && back.dataset.act) back = [...document.querySelectorAll(`#app [data-act="${back.dataset.act}"]`)].find(x => !back.dataset.id || x.dataset.id === back.dataset.id) || null;
  if (had && back && back.isConnected && (inLayer || document.activeElement === document.body)) { try { back.focus({ preventScroll: true }); } catch (e) {} }
}
const FOCUSABLE = 'button:not([disabled]),[href],input:not([type=hidden]):not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
function setBody(html, onOpen) {
  const b = $('#layer .sheet-body'); if (!b) return; if (typeof sheetCleanup === 'function') sheetCleanup();
  const sheet = b.closest('.sheet'), a = document.activeElement, lost = !a || a === document.body || a === sheet || !sheet.contains(a) || b.contains(a);
  b.innerHTML = html; enhanceAmounts(b); sheetCleanup = onOpen ? onOpen(b) : null; fitNums(b);
  // the body was replaced (a lookup finished): the first field gets the focus, as when a sheet opens
  if (lost && !matchMedia('(pointer:coarse)').matches) { const f = b.querySelector('input:not([type=file]):not([type=checkbox]):not([type=radio]),textarea'); if (f) f.focus({ preventScroll: true }); else { sheet.tabIndex = -1; sheet.focus({ preventScroll: true }); } }
}
const busyHTML = msg => `<div class="row" style="justify-content:center;padding:24px 0"><span class="spinner">${esc(msg)}</span></div>`;
const errHTML = e => `<div class="notice red"${e && e.amount ? ' data-amount' : ''}>${esc(e && e.message || e)}${e && e.also ? `<div>${esc(e.also)}</div>` : ''}${e && e.raw ? `<div class="tiny muted raw" data-noi18n>${esc(e.raw)}</div>` : ''}${e && e.fix ? `<button class="btn sm gold" style="margin-top:8px" data-act="${esc(e.fix.act)}"${e.fix.a != null ? ` data-a="${esc(e.fix.a)}"` : ''}${e.fix.id ? ` data-id="${esc(e.fix.id)}"` : ''}>${esc(e.fix.label)}</button>` : ''}</div>`;

/* ---------- views ---------- */
let tab = 'wallet';
let histFilter = 'all', histQuery = '', histTag = '';
const tagsOf = note => [...new Set((String(note || '').match(/#[\p{L}\p{N}_-]{1,24}/gu) || []).map(x => x.slice(1).toLowerCase()))];
const ICONS = {
  wallet: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M1 4h12v2h2v7H1z" opacity=".35"/><path d="M1 3h11v1H2v8h12V7h-3v3h4V6h-1V4h1v9H1z"/><rect x="11" y="8" width="2" height="1"/></svg>',
  arcade: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 1h8v2h1v5h-1v7H4V8H3V3h1z" opacity=".35"/><path d="M4 1h8v1H4zM3 2h1v6H3zm9 0h1v6h-1zM5 3h6v4H5zm-1 5h8v1H4zm0 1h1v6H4zm7 0h1v6h-1zM6 11h1v1H6zm3 0h2v2H9z"/></svg>',
  history: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M3 1h10v14H3z" opacity=".35"/><path d="M3 1h10v14H3V1zm1 1v12h8V2zm1 2h6v1H5zm0 3h6v1H5zm0 3h4v1H5z"/></svg>',
  mints: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M2 6h12v8H2z" opacity=".35"/><path d="M8 1l7 4v1H1V5zm0 1.2L3.5 5h9zM2 7h2v6H2zm5 0h2v6H7zm5 0h2v6h-2zM1 14h14v1H1z"/></svg>',
  settings: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M5 4h6v8H5z" opacity=".35"/><path d="M7 1h2v2h2v1h1v1h1v2h2v2h-2v2h-1v1h-1v1H9v2H7v-2H5v-1H4v-1H3V9H1V7h2V5h1V4h1V3h2zm0 4v1H6v4h1v1h2v-1h1V6H9V5z"/></svg>'
};
const TABS = [['wallet', 'WALLET'], ['arcade', 'ARCADE'], ['history', 'NOTES'], ['mints', 'MINTS'], ['settings', 'SETTINGS']];

function render() {
  const app = $('#app');
  app.className = S.prefs.crt ? 'crt' : '';
  document.body.className = 'theme-' + (S.prefs.theme || 'neon');
  if (S.prefs.fiat && S.seed) fetchPrice();
  let body = '';
  if (tabLocked) {
    npcSocketStop(); liveSync(); dmStop(); nwcStop();
    app.innerHTML = `<div class="wrap">${marqueeHTML(false)}
      <section class="screen"><div class="panel hot"><span class="h2" style="color:var(--pink)">Open in another tab</span>
      <p style="margin:0">NUTCADE is already open in another tab or window. Running two copies at once can make them overwrite each other's ecash, so this one is paused.</p>
      <button class="btn solid gold block" data-act="takeover">Use NUTCADE here instead</button></div></section></div>`;
    return;
  }
  if (vault.on && !vault.open) {
    app.innerHTML = `<div class="wrap lockwrap${raw.get('vault', {}).bio ? ' bio' : ''}" style="padding-bottom:calc(32px + env(safe-area-inset-bottom,0px))">
      ${marqueeHTML(false)}
      ${viewLock()}</div>`;
    if (window.NutAudio) window.NutAudio.stopMusic();
    if (window.PriceChart) window.PriceChart.disconnect();
    return;
  }
  if (needsGate()) {
    const gv = viewGate();
    app.innerHTML = `<div class="wrap" style="padding-bottom:calc(32px + env(safe-area-inset-bottom,0px))">
      ${marqueeHTML(gate.step === 'welcome')}
      ${storageOk ? '' : '<div class="notice red" style="margin-top:14px">This browser is blocking storage, so your wallet would vanish on reload. Open NUTCADE in a normal browser tab.</div>'}
      ${gv}</div>`;
    if (window.NutAudio) window.NutAudio.stopMusic();
    return;
  }
  if (tab === 'wallet') body = viewWallet();
  else if (tab === 'arcade') body = `<section class="screen" id="arcadeScreen"></section>`;
  else if (tab === 'history') body = viewHistory();
  else if (tab === 'mints') body = viewMints();
  else body = viewSettings();
  // a redraw replaces every button: the one with keyboard focus gets it back afterwards, or focus would fall to
  // the page (a background refresh just after a sheet closed used to drop focus that had just been returned)
  const fa = document.activeElement, fsel = fa && fa !== document.body && app.contains(fa) && fa.dataset && fa.dataset.act
    ? ['act', 'id', 'tab', 'm', 'url', 'game'].filter(k => fa.dataset[k] != null).map(k => `[data-${k}="${CSS.escape(fa.dataset[k])}"]`).join('') : null;
  app.innerHTML = `<div class="wrap">
    ${marqueeHTML(false)}
    ${storageOk ? '' : '<div class="notice red" style="margin-top:14px">This browser is blocking storage, so ecash you receive here would vanish on reload. Open NUTCADE in a normal browser tab before adding funds.</div>'}
    ${body}
  </div>
  <nav class="tabbar" aria-label="Sections"><div class="in">${TABS.map(([k, l]) => `<button class="tab" data-act="tab" data-tab="${k}" ${tab === k ? 'aria-current="page"' : ''}>${ICONS[k]}<span>${l}</span></button>`).join('')}</div></nav>`;
  if (tab === 'arcade' && window.Arcade) { window.Arcade.mountList($('#arcadeScreen')); const cp = challengePanel(); if (cp) $('#arcadeScreen').insertAdjacentHTML('beforeend', cp); if (window.Trophies) window.Trophies.mount($('#arcadeScreen')); }
  if (tab === 'mints' && S.mints.some(m => !health[m.url] || Date.now() - health[m.url].at > 5 * 60e3)) setTimeout(checkHealth, 0);
  if (window.Trophies) setTimeout(() => window.Trophies.checkWallet(), 0);
  setTimeout(liveSync, 0);
  setTimeout(dmListen, 0);
  setTimeout(nwcListen, 0);
  netBanner();
  if (pendingLink && S.seed && S.seed.backedUp) { const t = pendingLink; pendingLink = null; setTimeout(() => openLink(t), 300); }
  if (S.prefs.npc) npcSocketStart();
  if (window.NutAudio && !(window.Arcade && window.Arcade.playing())) { if (tab === 'arcade') window.NutAudio.music('title'); else window.NutAudio.stopMusic(); }
  if (tab === 'wallet' && window.Arcade) { const el = $('#topScore'); if (el) el.innerHTML = window.Arcade.topLine(); }
  if (window.PriceChart) { if (tab === 'wallet') window.PriceChart.mount($('#priceMount')); else window.PriceChart.disconnect(); }
  fitNums(app);
  if (fsel && (document.activeElement === document.body || !document.activeElement)) { const el = app.querySelector(fsel); if (el) el.focus({ preventScroll: true }); }
}
window.addEventListener('resize', () => { clearTimeout(fitNums.t); fitNums.t = setTimeout(() => { document.querySelectorAll('.credit-num,.cash-amt,.cash-charge').forEach(el => { el.style.fontSize = el.dataset.fs || ''; }); fitNums(); }, 150); });
function refresh() { if ($('#layer .sheet')) { /* keep sheet */ } const y = window.scrollY; render(); window.scrollTo(0, y); }

function txRow(t) {
  const sign = t.type === 'in' ? '+' : '-';   // the pixel font's hyphen sits mid-height; its − glyph falls back to the baseline
  const method = { ln: 'LN', ecash: 'ECASH', onchain: 'ON-CHAIN', fee: 'FEE' }[t.method];
  const moved = !(t.status === 'failed' || t.status === 'expired');   // a failed or expired payment moved nothing: its amount is struck through
  const stat = (t.status !== 'done' ? `<span class="chip ${t.status === 'pending' ? 'pending' : t.status === 'claimed' || t.status === 'reclaimed' ? 'claimed' : 'failed'}">${esc(t.status.toUpperCase())}</span>` : '') + (t.lockUntil && t.status === 'pending' ? '<span class="chip ecash">LOCKED</span>' : '') + (t.move ? '<span class="chip claimed">MOVE</span>' : '') + (t.cashier ? '<span class="chip ln">SALE</span>' : '') + (t.nwc ? '<span class="chip ecash">NWC</span>' : '') + (t.zap ? '<span class="chip claimed">ZAP</span>' : '') + (t.refused && t.status === 'pending' && isBlocked(t.mint) ? '<span class="chip failed">BLOCKED</span>' : '');
  const amt = t.method === 'onchain' && t.type === 'in' && !t.amount ? 'WAIT' : t.method === 'fee' ? '-' + fmt(t.fee) : (moved ? sign : '') + fmt(t.amount);
  const wide = amt.length > 11;   // a huge amount gets its own line under the note instead of squeezing the chips
  return `<button class="tx ${t.type}" data-act="tx" data-id="${t.id}"><span class="ico" aria-hidden="true">${t.type === 'in' ? '↓' : '↑'}</span>
    <span class="mid"><div class="note ${t.note ? '' : 'empty'}">${esc(noteText(t.note) || 'Add a note…')}</div>
    <div class="meta"><span class="chip ${t.method === 'ecash' ? 'ecash' : 'ln'}">${method}</span>${stat}<span${Date.now() - t.ts >= 604800e3 ? ' data-noi18n' : ''}>${timeAgo(t.ts)}</span></div></span>
    <span class="amt${wide ? ' wide' : ''}${moved ? '' : ' void'}">${amt}</span></button>`;
}
function timeAgo(ts) {
  const d = (Date.now() - ts) / 1000;
  if (d < 60) return 'just now'; if (d < 3600) return Math.floor(d / 60) + 'm ago'; if (d < 86400) return Math.floor(d / 3600) + 'h ago';
  if (d < 604800) return Math.floor(d / 86400) + 'd ago';
  return fmtDate(ts);
}
// Every date in the app reads the same way, in the app's language: "Nov 20, 2026" (with the time where it matters).
const dateLocale = () => ({ en: 'en-US', pt: 'pt-BR' })[LANG] || LANG;
function fmtDate(ms, withTime) {
  const d = new Date(ms); if (isNaN(d)) return '';
  try { return d.toLocaleDateString(dateLocale(), { month: 'short', day: 'numeric', year: 'numeric' }) + (withTime ? ', ' + d.toLocaleTimeString(dateLocale(), { hour: 'numeric', minute: '2-digit' }) : ''); }
  catch (e) { return d.toDateString(); }
}
// Notes NUTCADE writes itself (not ones you typed) are shown in your language.
const AUTO_NOTE = /^(Sats for the duress PIN wallet$|Back from the duress PIN's wallet$|Mint fee for splitting a payment into smaller requests$|Recovered with recovery phrase|Restored from another phrase|Restored from backup$|Lightning address|Lightning payment|Tip to NUTCADE|Reclaimed: |Gift came back|Moved (from|to) |Sale(: | #cashier)|Swap to |Bounty (for|from) |Extra Life( |$)|Treasure hunt(: |$)|Loaded score card|Swapped from |Gift( for |$)|Payment request$|Mint fee for a failed payment$|Mint fee for (moving ecash under your phrase|an interrupted step|keeping Extra Life going)$|Ecash already spent elsewhere$|Payment request couldn't be delivered: the sats came back$|To |Zap to |Wallet Connect: |LNURL voucher$)|\((part \d+ of \d+|cancelled at the till)\)$/;
function noteText(n) {
  if (!n || !AUTO_NOTE.test(n)) return n;
  const m = /^(.*) \((part \d+ of \d+|cancelled at the till)\)$/.exec(n);   // your own words before the suffix stay as you typed them
  return m ? noteText(m[1]) + ' (' + tr(m[2]) + ')' : tr(n);
}
const TX_STATUS = { pending: 'Pending', done: 'Complete', failed: 'Failed', claimed: 'Claimed', reclaimed: 'Reclaimed', expired: 'Expired' };

/* ---------- first-run gate: create + back up before entering ---------- */
let gate = { step: 'welcome', picks: null };
const needsGate = () => !S.seed || !S.seed.backedUp || gate.step === 'done';
function pickWords() { const p = []; while (p.length < 3) { const i = Math.floor(Math.random() * 12); if (!p.includes(i)) p.push(i); } return p.sort((a, b) => a - b); }
const stepDots = n => `<div class="steps" aria-label="Step ${n} of 3">${[1, 2, 3].map(i => `<i class="${i <= n ? 'on' : ''}"></i>`).join('')}<span>STEP ${n}/3</span></div>`;
function viewGate() {
  if (S.seed && !S.seed.backedUp && gate.step === 'welcome') gate.step = 'show';
  const legacy = totalBalance() > 0;
  if (gate.step === 'welcome') return `<section class="screen">
    <div class="panel hot gate">
      ${stepDots(1)}
      <h2 class="gate-h">WELCOME, PLAYER 1</h2>
      <ul class="gate-list">
        <li><b>A Bitcoin wallet.</b> NUTCADE holds sats as Cashu ecash: fast, private, and sent like a text.</li>
        <li><b>Your keys, your sats.</b> A 12-word recovery phrase is the only way to get your sats back if this device is lost.</li>
        <li><b>An arcade.</b> Eight cabinets of free play once you're in.</li>
      </ul>
      ${legacy ? `<div class="notice">You already hold ${money(totalBalance())} here from before recovery phrases. Creating your phrase moves that ecash under it so it's protected too.</div>` : ''}
      <label class="ack" for="ack"><input id="ack" type="checkbox" data-gatecheck="ack"><span>I understand NUTCADE is new, experimental software, that mints hold the Bitcoin behind my ecash, and that my 12 words are the only way to recover my sats.</span></label>
      <button class="btn solid gold block" data-act="gateCreate" data-needs="ack" disabled>Create a new wallet</button>
      <button class="btn block" data-act="gateRestore" data-needs="ack" disabled>Restore from recovery phrase</button>
    </div></section>`;
  const words = S.seed.mnemonic.split(' ');
  if (gate.step === 'show') return `<section class="screen">
    <div class="panel hot gate">
      ${stepDots(2)}
      <h2 class="gate-h">WRITE DOWN YOUR 12 WORDS</h2>
      <div class="notice red">Anyone with these words can take your sats. Write them on paper, in order, and keep them offline. Never type them into a website, take a screenshot, or send them to anyone, including NUTCADE support.</div>
      ${phraseGrid(words)}
      <div class="tiny muted">Later, also note the mints you use next to your words. Restoring scans those mints.</div>
      <label class="ack" for="wrote"><input id="wrote" type="checkbox" data-gatecheck="wrote"><span>I wrote down all 12 words, in order, on paper.</span></label>
      <button class="btn solid gold block" data-act="gateToConfirm" data-needs="wrote" disabled>Continue</button>
    </div></section>`;
  if (gate.step === 'confirm') {
    if (!gate.picks) gate.picks = pickWords();
    return `<section class="screen">
    <div class="panel hot gate">
      ${stepDots(3)}
      <h2 class="gate-h">CHECK YOUR BACKUP</h2>
      <p style="margin:0">Type these words from your paper, not from memory.</p>
      ${gate.picks.map(i => `<div class="field"><label for="cw${i}">Word #${i + 1}</label><input id="cw${i}" class="inp" data-cw="${i}" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false"></div>`).join('')}
      <div id="gateErr"></div>
      <button class="btn solid gold block" data-act="gateConfirm">Confirm backup</button>
      <button class="linkbtn" data-act="gateBack" style="justify-self:center">Back to my words</button>
    </div></section>`;
  }
  return `<section class="screen">
    <div class="panel hot gate" style="text-align:center;justify-items:center">
      <h2 class="gate-h" style="color:var(--lime)">PLAYER 1 READY!</h2>
      <p style="margin:0">Your wallet is created and backed up. ${gate.msg ? esc(gate.msg) : ''}</p>
      ${gate.busy ? `<span class="spinner">${esc(gate.busy)}</span>` : `${vault.on ? '' : `<div class="notice cyan" style="text-align:left">Recommended: set a PIN so nobody who picks up this device can open your wallet. It also encrypts your phrase and ecash here.</div><button class="btn block violet" data-act="pinSet">Set a PIN</button>`}<button class="btn solid gold block" data-act="gateStart">Press start</button>`}
    </div></section>`;
}
function phraseGrid(words) {
  return `<ol class="words" aria-label="${tr('Recovery phrase')}">${words.map((w, i) => `<li><span>${i + 1}</span>${esc(w)}</li>`).join('')}</ol>`;
}
function openShowPhrase(fresh) {
  const words = S.seed.mnemonic.split(' ');
  openSheet(fresh ? 'Your recovery phrase' : 'Recovery phrase', `
    <div class="notice red">Anyone with these 12 words can take your sats. Write them on paper in this order and keep them offline. Never type them into a website or send them to anyone, including NUTCADE support.</div>
    ${phraseGrid(words)}
    ${S.mints.length ? `<div class="field"><label>Also write down your mints</label><div class="code" style="color:var(--ink);font-size:14px">${S.mints.map(m => esc(m.url)).join('<br>')}</div><div class="tiny muted">Restoring scans the mints you list, so keep this list with your words.</div></div>` : '<div class="tiny muted">When you add mints, note their addresses next to your words. Restoring scans the mints you list.</div>'}
    <button class="btn block" data-act="close">Done</button>`);
}
function openConfirmPhrase() {
  const words = S.seed.mnemonic.split(' ');
  const pick = []; while (pick.length < 3) { const i = Math.floor(Math.random() * 12); if (!pick.includes(i)) pick.push(i); } pick.sort((a, b) => a - b);
  openSheet('Check your words', `
    <p style="margin:0">Type these words from your paper to make sure you copied them correctly.</p>
    ${pick.map(i => `<div class="field"><label for="cw${i}">Word #${i + 1}</label><input id="cw${i}" class="inp" data-cw="${i}" autocomplete="off" autocapitalize="off" spellcheck="false"></div>`).join('')}
    <button class="btn solid gold block" data-act="seedConfirm">Confirm</button>
    <button class="linkbtn" data-act="seedShow" style="justify-self:center">Show the words again</button>
    <div id="sheetErr"></div>`);
}
function openRestore() {
  const curated = CURATED.filter(c => !c.test);
  const urls = [...new Set(S.mints.map(m => m.url).concat(curated.map(c => c.url)))];
  openSheet('Restore wallet', `
    ${S.seed ? `<div class="notice">This replaces your current wallet with the one from these 12 words.${totalBalance() ? ` The ${money(totalBalance())} here moves into the restored wallet, so nothing is lost.` : ''} Write down your current words first if you might want this wallet back.</div>` : '<div class="th">Use the 12 words from a previous NUTCADE or another Cashu wallet like cashu.me.</div>'}
    <div class="field"><label for="phraseIn">Your 12 words</label><textarea id="phraseIn" class="inp" placeholder="word1 word2 word3 …" autocomplete="off" autocapitalize="off" spellcheck="false" data-input="phrase"></textarea><div id="phraseOk" class="tiny muted">Separate words with spaces.</div></div>
    <div class="field"><div class="row between"><label>Mints to scan</label><button class="btn sm violet" data-act="findMints">Find my mints on Nostr</button></div><div id="nostrMints" class="tiny muted"></div><div class="txs" id="rmList">${urls.map((u, i) => `<label class="toggle" for="rm${i}" style="font-size:19px"><span style="overflow-wrap:anywhere;min-width:0" data-noi18n>${esc(host(u))}</span><input id="rm${i}" type="checkbox" data-rmint="${esc(u)}" ${S.mints.find(m => m.url === u) ? 'checked' : ''}></label>`).join('')}</div></div>
    <div class="field"><label for="rmExtra">Other mint addresses (one per line)</label><textarea id="rmExtra" class="inp" data-noi18n placeholder="https://mint.example.com" autocomplete="off" autocapitalize="off" spellcheck="false"></textarea></div>
    <button class="btn solid gold block" data-act="doRestorePhrase">Restore</button>
    <div id="restoreLog" class="tiny muted"></div><div id="sheetErr"></div>`);
}

function viewWallet() {
  const m = activeMint();
  const nag = S.seed && !S.seed.backedUp ? `<div class="notice red row between" style="flex-wrap:wrap"><span>Your recovery phrase isn't backed up yet.</span><button class="btn sm red" data-act="seedShow">Back up now</button></div>` : '';
  const legacy = S.seed && !S.seed.secured && totalBalance() > 0 && S.seed.backedUp ? `<div class="notice row between" style="flex-wrap:wrap"><span>${money(totalBalance())} here isn't covered by your phrase yet.</span><button class="btn sm gold" data-act="secureAll">Protect it</button></div>` : '';
  if (!m) return `<section class="screen">${nag}${legacy}
    <div class="credits" style="text-align:center;justify-items:center"><div class="label">Credits</div><div class="credit-num">0<small>${unitTag()}</small></div>
    <div class="spinner" style="font-size:11px">INSERT MINT TO START</div></div>
    <div class="panel"><p style="margin:0">NUTCADE holds Bitcoin as Cashu ecash. A mint issues the ecash, so pick one first. Try a test mint if you want to play with fake sats.</p>
    <button class="btn solid gold block" data-act="pickMint">Choose a mint</button>
    <button class="btn block lime" data-act="recvMethod" data-m="ecash">Someone sent me ecash</button></div>
    <div id="priceMount"></div>
    <div class="panel"><div class="row between"><span class="h2">Arcade</span><button class="btn sm violet" data-act="tab" data-tab="arcade">Play</button></div><div id="topScore" class="tiny muted"></div></div>
    <button class="linkbtn tiny" style="justify-self:center;color:var(--pink)" data-act="support">${HEART}<span>Support NUTCADE</span></button>
  </section>`;
  const bal = balanceOf(m.url), tot = totalBalance(), po = pendingOut();
  const recent = S.txs.slice(0, 4);
  return `<section class="screen">${nag}${legacy}
    <div class="credits">
      <div class="row between"><span class="label">Credits</span><span class="row" style="gap:10px">${tot !== bal ? `<span class="tiny muted">All mints ${money(tot)}</span>` : ''}${vault.on ? '<button class="lockbtn" data-act="lockNow" aria-label="Lock wallet" title="Lock wallet"><svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M5 7V5a3 3 0 0 1 6 0v2h1v8H4V7zm1 0h4V5a2 2 0 0 0-4 0zm1 3v3h2v-3z"/></svg></button>' : ''}</span></div>
      <div class="credit-num" aria-live="polite">${S.prefs.btcSymbol ? '₿' : ''}${fmt(bal)}<small>${unitTag()}</small></div>
      ${fiatOf(bal) ? `<div class="tiny muted fiat" data-sats="${bal}">≈ ${fiatOf(bal)}</div>` : ''}
      ${piggySaved() ? `<div class="tiny piggy-line">${pigSVG('tiny')}<span>${money(piggySaved())} in your piggy bank · ${money(Math.max(0, tot - piggySaved()))} to spend</span></div>` : ''}
      <button class="mint-pill" data-act="pickMint" aria-label="${tr('Change mint')}"><span class="dot"></span><span>${esc(m.name)}</span><span class="muted">▾</span></button>
      ${po ? `<div class="tiny" style="color:var(--violet)">${money(po)} in flight. <button class="linkbtn" data-act="reconcileAll">Check now</button></div>` : ''}
    </div>
    <div class="pushes">
      <button class="push recv" data-act="receive"><span class="cap" aria-hidden="true">↓</span><span class="t">RECEIVE</span></button>
      <button class="push send" data-act="send"><span class="cap" aria-hidden="true">↑</span><span class="t">SEND</span></button>
    </div>
    <div class="scanrow"><button class="btn violet scan-btn" data-act="scan"><svg class="ico-scan" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M1 1h5v1H2v4H1zm9 0h5v5h-1V2h-4zM1 10h1v4h4v1H1zm13 0h1v5h-5v-1h4zM4 4h3v3H4zm5 0h3v3H9zM4 9h3v3H4zm5 0h1v1H9zm2 0h1v1h-1zm-2 2h1v1H9zm2 1h1v1h-1z"/></svg>Scan QR code</button>${window.Chiptune && window.Chiptune.canListen() ? '<button class="btn violet" data-act="ctListen" aria-label="Listen for a code sent as sound"><svg class="ico-scan" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M6 1h4v8H6zM4 6h1v3a3 3 0 0 0 6 0V6h1v3a4 4 0 0 1-3.5 4V15h-1v-2A4 4 0 0 1 4 9z"/></svg>Listen</button>' : ''}</div>
    <div class="toolrow"><button class="btn sm gold" data-act="cashier">Cashier mode</button><button class="btn sm pink" data-act="splitOpen">Split a bill</button>${S.extra ? '' : '<button class="btn sm lime" data-act="extraOpen">Extra Life</button>'}<button class="btn sm violet" data-act="huntNew">Treasure hunt</button></div>
    ${importsPanel()}${splitPanels()}${piggyPanel()}${extraPanel()}${huntsPanel()}
    <div id="priceMount"></div>
    <div class="panel">
      <div class="row between"><span class="h2">Recent</span>${S.txs.length ? '<button class="linkbtn" data-act="tab" data-tab="history">All notes</button>' : ''}</div>
      ${recent.length ? `<div class="txs">${recent.map(txRow).join('')}</div>` : `<div class="empty-state"><b>NO PLAYS YET</b>Receive some sats and every transaction shows up here with room for a note.</div>`}
    </div>
    <div class="panel"><div class="row between"><span class="h2">Arcade</span><button class="btn sm violet" data-act="tab" data-tab="arcade">Play</button></div><div id="topScore" class="tiny muted"></div></div>
    <button class="linkbtn tiny" style="justify-self:center;color:var(--pink)" data-act="support">${HEART}<span>Support NUTCADE</span></button>
  </section>`;
}

function viewHistory() {
  const q = histQuery.toLowerCase();
  // an amount typed the way the language writes it (25.000, 25 000, 25,000) matches 25000
  const qAmt = /^[\d\s.,\u00a0\u202f'’]+$/.test(q) ? q.replace(/[^\d]/g, '') : q;
  const list = S.txs.filter(t => (histFilter === 'all' || t.type === histFilter) && (!histTag || tagsOf(t.note).includes(histTag)) && (!q || (t.note || '').toLowerCase().includes(q) || (noteText(t.note) || '').toLowerCase().includes(q) || (qAmt && String(t.amount).includes(qAmt))));
  const noted = S.txs.filter(t => t.note).length;
  const counts = {}; S.txs.forEach(t => tagsOf(t.note).forEach(g => { counts[g] = (counts[g] || 0) + 1; }));
  const tags = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 14);
  return `<section class="screen">
    <div class="row between"><div style="display:grid;gap:4px"><h2 class="h2">Notes</h2><span class="tiny muted">${noted}/${S.txs.length} noted</span></div>${S.txs.length ? '<button class="btn sm" data-act="csv">Export CSV</button>' : ''}</div>
    <div class="field"><label for="hq">Search notes</label><input id="hq" class="inp" type="search" placeholder="pizza, rent, Satoshi…" value="${esc(histQuery)}" data-input="hq" autocomplete="off"></div>
    <div class="seg three" role="group" aria-label="Filter">${[['all', 'ALL'], ['in', 'IN'], ['out', 'OUT']].map(([k, l]) => `<button data-act="hf" data-f="${k}" aria-pressed="${histFilter === k}">${l}</button>`).join('')}</div>
    ${tags.length ? `<div class="tagrow" role="group" aria-label="Tags">${tags.map(([g, n]) => `<button class="tag" data-noi18n data-act="htag" data-tag="${esc(g)}" aria-pressed="${histTag === g}">#${esc(g)} <span>${n}</span></button>`).join('')}</div>` : `<div class="tiny muted">Tip: add #tags to notes, like #food or #rent, to group them.</div>`}
    <div class="txs" id="txList">${list.length ? list.map(txRow).join('') : `<div class="empty-state"><b>${S.txs.length ? 'NO MATCH' : 'GAME OVER?'}</b>${S.txs.length ? 'No transaction matches that search.' : 'Not yet. Your first transaction will land here.'}</div>`}</div>
  </section>`;
}

function viewMints() {
  return `<section class="screen">
    <div class="row between"><h2 class="h2">Your mints</h2><button class="btn sm gold" data-act="pickMint">Add mint</button></div>
    ${healthPanel()}
    ${S.mints.length ? `<div class="txs">${S.mints.map(m => `<div class="panel ${m.url === S.active ? 'hot' : ''}" style="gap:8px">
      <div class="row between" style="align-items:flex-start"><div style="min-width:0"><div class="uname" style="font-family:var(--f-display);font-size:11px;line-height:1.5;color:var(--gold)">${esc(m.name)}</div><div class="tiny muted" data-noi18n style="overflow-wrap:anywhere">${esc(host(m.url))}</div></div>
      <div style="font-family:var(--f-display);font-size:12px;white-space:nowrap">${fmt(balanceOf(m.url))}</div></div>
      <div class="row between" style="gap:8px">${mintHealthLine(m)}${reportChip(m.url)}</div>
      <div class="row" style="flex-wrap:wrap;gap:6px">${methodChips(m)}</div>
      ${blockedNotice(m.url)}${minNotice(m.url)}
      <div class="row" style="flex-wrap:wrap">${m.url === S.active ? '<span class="chip ecash">ACTIVE</span>' : `<button class="btn sm lime" data-act="useMint" data-url="${esc(m.url)}">Use</button>`}${isBlocked(m.url) ? '<span class="chip failed">BLOCKED</span>' : ''}
      <button class="btn sm" data-act="refreshMint" data-url="${esc(m.url)}">Refresh</button>
      ${isBlocked(m.url) ? `<button class="btn sm gold" data-act="unblockMint" data-url="${esc(m.url)}">Unblock</button>` : `<button class="btn sm" data-act="blockMint" data-url="${esc(m.url)}">Block</button>`}
      <button class="btn sm red" data-act="removeMint" data-url="${esc(m.url)}">Remove</button></div></div>`).join('')}</div>`
      : `<div class="empty-state"><b>NO MINTS</b>Add a mint to start holding ecash.</div>`}
    <div class="tiny muted" style="text-align:center">Mint settings, backup and privacy live in the Settings tab.</div>
  </section>`;
}
/* ---------- PIN lock, passkey unlock, auto-lock ---------- */
const pinUI = { mode: null, value: '', first: '', old: '' };
const PIN_MIN = 6, PIN_MAX = 12;
function hydrateFromVault() {
  const d = vault.data;
  // keys that joined the vault in a later version (the Extra Life, treasure hunts) move in from plain storage
  loadWalletState();
  S.limits = d.limits || null;
  S.hunts = d.hunts || []; S.found = d.found || {}; S.imports = d.imports || [];
  S.seed = d.seed || null; S.proofs = d.proofs || {}; S.pending = d.pending || []; S.quotes = d.quotes || []; S.txs = d.txs || []; S.p2pk = d.p2pk || []; S.requests = d.requests || []; S.contacts = d.contacts || []; S.nwc = d.nwc || []; S.ops = d.ops || []; S.extra = d.extra || null;
  seedBytes = null; raw.del('pinfails'); requestPersist(); mergeMintSpellings();
  nwcSince = Math.floor(Date.now() / 1000);   // Wallet Connect requests sent while it was locked are refused, not paid now
}
const HEART = '<svg class="ico-heart" viewBox="0 0 7 6" fill="currentColor" aria-hidden="true" shape-rendering="crispEdges"><path d="M1 0h2v1h1V0h2v1h1v2H6v1H5v1H4v1H3V5H2V4H1V3H0V1h1z"/></svg>';
// A drawn backspace key: the pixel font has no ⌫, and the fallback glyph is tiny.
const DEL_ICON = '<svg class="ico-del" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" shape-rendering="crispEdges"><path fill-rule="evenodd" d="M5 3h10v10H5L1 8zm1 1L2.5 8 6 12h8V4z"/><path d="M7 5h1v1H7zm1 1h1v1H8zm1 1h1v1H9zm1 1h1v1h-1zm1 1h1v1h-1zm0-4h1v1h-1zm-1 1h1v1h-1zM8 8h1v1H8zM7 9h1v1H7z"/></svg>';
// Six faint boxes that fill as you type; past six, a box is added per digit up to the 12-digit maximum.
// The next box to fill has a cyan border that never disappears (a PIN is 6 to 12 digits).
const digitsLabel = n => tr(n === 1 ? '1 digit entered' : `${n} digits entered`);   // singular and plural, also for screen readers
const pinDots = n => Array.from({ length: Math.max(PIN_MIN, Math.min(PIN_MAX, n + 1)) }, (_, i) => `<i class="${i < n ? 'on' : i === n ? 'cur' : ''}"></i>`).join('');
function padHTML(title, sub, opts = {}) {
  const n = pinUI.value.length;
  return `<div class="pinpad" data-pinpad="${pinUI.mode}">
    <div class="pin-title">${esc(title)}</div>${sub ? `<div class="th${opts.warn ? ' warn' : ''}" style="text-align:center">${esc(sub)}</div>` : ''}
    <div class="pin-dots" aria-label="${esc(digitsLabel(n))}">${pinDots(n)}</div>
    <div id="pinErr" class="pin-err" role="alert"></div>
    <div class="pin-keys">${['1', '2', '3', '4', '5', '6', '7', '8', '9', 'del', '0', 'ok'].map(k => `<button type="button" class="pin-k ${k === 'ok' ? 'ok' : ''}" data-act="pinKey" data-k="${k}" aria-label="${k === 'del' ? 'Delete' : k === 'ok' ? 'Enter' : k}">${k === 'del' ? DEL_ICON : k === 'ok' ? 'OK' : k}</button>`).join('')}</div>
    ${opts.extra || ''}</div>`;
}
function viewLock() {
  const rec = raw.get('vault', {}); const f = pinFails(); const wait = Math.max(0, Math.ceil((f.until - Date.now()) / 1000));
  if (pinUI.mode !== 'unlock') { pinUI.mode = 'unlock'; pinUI.value = ''; }
  return `<section class="screen"><div class="panel hot gate" style="justify-items:center">
    ${padHTML('ENTER PIN', wait ? `Too many wrong tries. Wait ${wait}s.` : 'Your wallet is locked.', { warn: !!wait, extra:
      `${rec.bio ? `<button class="btn block violet" data-act="bioUnlock">Unlock with Face ID / fingerprint</button>` : ''}
       <button class="linkbtn" data-act="forgotPin" style="justify-self:center">Forgot PIN?</button>` })}
  </div></section>`;
}
function openPinSheet(mode, title, sub) {
  pinUI.mode = mode; pinUI.value = '';
  openSheet(title, padHTML(sub.title, sub.text) + '<div id="sheetErr"></div>');
}
function refreshPad() {
  const pad = document.querySelector('[data-pinpad]'); if (!pad) return;
  const n = pinUI.value.length;
  pad.querySelector('.pin-dots').innerHTML = pinDots(n);
  pad.querySelector('.pin-dots').setAttribute('aria-label', digitsLabel(n));
}
function pinError(msg) { sfx('err'); const e = $('#pinErr'); if (e) { e.textContent = msg; } const d = document.querySelector('.pin-dots'); if (d) { d.classList.remove('shake'); void d.offsetWidth; d.classList.add('shake'); } pinUI.value = ''; refreshPad(); }
const nextPad = mode => { pinUI.mode = mode; pinUI.value = ''; };
async function pinSubmit() {
  const v = pinUI.value, m = pinUI.mode;
  if (v.length < PIN_MIN) return pinError(`Use at least ${PIN_MIN} digits.`);
  const busy = msg => { const e = $('#pinErr'); if (e) { e.textContent = msg; e.classList.add('busy'); } };
  try {
    if (m === 'unlock') {
      const f = pinFails(); if (f.until > Date.now()) return pinError(`Wait ${Math.ceil((f.until - Date.now()) / 1000)}s before trying again.`);
      busy('CHECKING…');
      const k = await pinToKeys(v);
      if (!k) { const f2 = notePinFail(); return pinError(f2.until > Date.now() ? `Wrong PIN. Wait ${Math.ceil((f2.until - Date.now()) / 1000)}s.` : (5 - f2.n === 1 ? 'Wrong PIN. 1 try before a wait.' : `Wrong PIN. ${Math.max(0, 5 - f2.n)} tries before a wait.`)); }
      await openPart(k.dek, k.decoy); hydrateFromVault(); pinUI.mode = null; sfx('start'); render(); armAutoLock();
      setTimeout(() => backgroundTick(true).then(() => { if (!$('#layer .sheet') && tab !== 'arcade') refresh(); }), 300);
      return;
    }
    if (m === 'limitOK' || m === 'limitSave' || /^duress/.test(m)) return pinMore(m, v, busy);
    if (m === 'set') { pinUI.first = v; nextPad('setConfirm'); setBody(padHTML('CONFIRM PIN', 'Type the same PIN again.') + '<div id="sheetErr"></div>'); return; }
    if (m === 'setConfirm') {
      if (v !== pinUI.first) { nextPad('set'); setBody(padHTML('CHOOSE A PIN', "Those didn't match. Start again.") + '<div id="sheetErr"></div>'); return; }
      busy('ENCRYPTING…'); await createVault(v); pinUI.first = '';
      sfx('levelup'); armAutoLock();
      setBody(`<div style="text-align:center;display:grid;gap:12px"><div style="font-family:var(--f-display);font-size:15px;color:var(--lime)">WALLET LOCKED DOWN!</div>
        <p style="margin:0">Your phrase, ecash and notes are now encrypted on this device. You'll enter your PIN when NUTCADE opens.</p>
        ${await bioSupported() ? '<button class="btn block violet" data-act="bioEnable">Also unlock with Face ID / fingerprint</button>' : ''}
        <button class="btn solid gold block" data-act="close">Done</button></div>`);
      refresh(); return;
    }
    if (m === 'changeOld') { busy('CHECKING…'); if (!(await pinToDek(v))) { notePinFail(); return pinError('That PIN is wrong.'); } pinUI.old = v; nextPad('changeNew');   // (the allowance is checked once the new PIN is typed twice: the same step as every refusal of a new PIN)
      setBody(padHTML('NEW PIN', `Choose a new PIN (${PIN_MIN} to ${PIN_MAX} digits).`) + '<div id="sheetErr"></div>'); return; }
    if (m === 'changeNew') { pinUI.first = v; nextPad('changeConfirm'); setBody(padHTML('CONFIRM NEW PIN', 'Enter it again.') + '<div id="sheetErr"></div>'); return; }
    if (m === 'changeConfirm') {
      if (v !== pinUI.first) { nextPad('changeNew'); setBody(padHTML('NEW PIN', "Those didn't match. Start again.") + '<div id="sheetErr"></div>'); return; }
      busy('ENCRYPTING…'); pinChangeCheck(); await changePin(pinUI.old, v); pinChangeUse(); pinUI.old = pinUI.first = ''; sfx('coin'); closeSheet(); toast('PIN changed', 'lime'); return;
    }
    if (m === 'remove') { busy('CHECKING…'); if (!(await pinToDek(v))) { notePinFail(); return pinError('That PIN is wrong.'); } pinChangeCheck(); if (vault.decoy) throw pinChangeRefuse(); await removeVault(v); pinChangeUse(); sfx('blip'); closeSheet(); refresh(); toast('PIN removed. Your wallet is no longer encrypted.', 'gold'); return; }
    if (m === 'bioVerify') { busy('CHECKING…'); const dek = await pinToDek(v); if (!dek) { notePinFail(); return pinError('That PIN is wrong.'); } pinChangeCheck(); if (vault.decoy) throw pinChangeRefuse(); pinChangeUse(); await enableBio(); closeSheet(); refresh(); toast('Face ID / fingerprint unlock is on', 'lime'); return; }
  } catch (e) { pinError(e.message || 'Something went wrong.'); }
}

/* Passkey (WebAuthn PRF) unlock: the authenticator returns a secret only after Face ID / fingerprint,
   and that secret wraps the same data key the PIN wraps. */
async function bioSupported() {
  try { return !!(window.PublicKeyCredential && await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()); } catch (e) { return false; }
}
async function prfSecret(credId, prfSalt) {
  const a = await navigator.credentials.get({ publicKey: { challenge: rnd(32), allowCredentials: [{ type: 'public-key', id: credId }], userVerification: 'required', timeout: 60000, extensions: { prf: { eval: { first: prfSalt } } } } });
  const r = a.getClientExtensionResults().prf; if (!r || !r.results || !r.results.first) throw new Error("This device's passkeys can't unlock NUTCADE. Use your PIN.");
  return new Uint8Array(r.results.first);
}
async function enableBio() {
  if (!vault.dek) throw new Error('Unlock the wallet first.');
  const prfSalt = rnd(32);
  const cred = await navigator.credentials.create({ publicKey: {
    rp: { name: 'NUTCADE', id: location.hostname }, user: { id: rnd(16), name: 'NUTCADE wallet', displayName: 'NUTCADE wallet' },
    challenge: rnd(32), pubKeyCredParams: [{ type: 'public-key', alg: -7 }, { type: 'public-key', alg: -257 }],
    authenticatorSelection: { authenticatorAttachment: 'platform', userVerification: 'required', residentKey: 'preferred' },
    timeout: 60000, extensions: { prf: { eval: { first: prfSalt } } } } });
  const ext = cred.getClientExtensionResults().prf;
  if (!ext || ext.enabled === false) throw new Error("This device's passkeys can't unlock NUTCADE. Your PIN still works.");
  const credId = new Uint8Array(cred.rawId);
  const secret = ext.results && ext.results.first ? new Uint8Array(ext.results.first) : await prfSecret(credId, prfSalt);
  const kek = await kekFromSecret(secret);
  const rec = raw.get('vault'); rec.bio = { credId: b64e(credId), prfSalt: b64e(prfSalt), wrap: await wrapDek(vault.dek, kek) }; raw.set('vault', rec);
}
async function bioToDek() {
  const rec = raw.get('vault'); const b = rec.bio;
  const secret = await prfSecret(b64d(b.credId), b64d(b.prfSalt));
  return unwrapDek(b.wrap, await kekFromSecret(secret));
}

/* Auto-lock: reload (which clears every secret from memory) after inactivity or time in the background. */
let lastActive = Date.now(), hiddenAt = 0, autoLockTimer = 0;
const lockAfterMs = () => (S.prefs.lockAfter ?? 5) * 60e3;
async function lockNow() { try { await vault.chain; } catch (e) {} location.reload(); }
function armAutoLock() {
  clearInterval(autoLockTimer);
  if (!vault.on || !vault.open || !lockAfterMs()) return;
  autoLockTimer = setInterval(() => { if (Date.now() - lastActive > lockAfterMs() && !(window.Arcade && window.Arcade.playing())) lockNow(); }, 15000);
}
['pointerdown', 'keydown', 'touchstart', 'wheel'].forEach(ev => window.addEventListener(ev, () => { lastActive = Date.now(); }, { passive: true }));
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { hiddenAt = Date.now(); return; }
  if (vault.on && vault.open && hiddenAt && lockAfterMs() && Date.now() - hiddenAt > lockAfterMs()) lockNow();
});

/* ---------- settings ---------- */
const APP_VERSION = '1.13.1';
const CURRENCIES = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'CHF', 'JPY', 'BRL', 'MXN', 'INR', 'ZAR', 'NGN', 'ARS', 'SEK'];
const THEMES = [['neon', 'Neon arcade'], ['amber', 'Amber CRT'], ['phosphor', 'Green phosphor']];
const SECTIONS = [['set-security', 'Security'], ['set-backup', 'Backup'], ['set-contacts', 'Contacts'], ['set-lnaddr', 'Lightning address'], ['set-nwc', 'Wallet Connect'], ['set-look', 'Look & sound'], ['set-privacy', 'Privacy'], ['set-piggy', 'Piggy bank'], ['set-tools', 'Wallet tools'], ['set-about', 'About']];
const toggle = (k, label, help) => `<label class="toggle set" for="p_${k}"><span><span class="tl">${label}</span>${help ? `<span class="th">${help}</span>` : ''}</span><input id="p_${k}" type="checkbox" data-act="pref" data-k="${k}" ${S.prefs[k] ? 'checked' : ''}></label>`;
function viewSettings() {
  const inflight = S.pending.length;   // (a paid payment still waiting for its change counts: Check stuck payments retries it)
  return `<section class="screen settings">
    <h2 class="h2">Settings</h2>
    <nav class="set-index" aria-label="Settings sections">${SECTIONS.map(([id, l]) => `<button class="chip ecash" data-act="jump" data-id="${id}">${l}</button>`).join('')}</nav>

    <div class="panel" id="set-security"><span class="h2">Security</span>
      <div class="row between tiny"><span>PIN lock &amp; encryption</span><span style="color:${vault.on ? 'var(--lime)' : 'var(--gold)'}">${vault.on ? 'ON' : 'OFF'}</span></div>
      ${vault.on ? `<div class="row between tiny"><span>Face ID / fingerprint</span><span style="color:${raw.get('vault', {}).bio ? 'var(--lime)' : 'var(--dim)'}">${raw.get('vault', {}).bio ? 'ON' : 'OFF'}</span></div>` : ''}
      <p class="th" style="margin:0">${vault.on ? 'Your phrase, ecash and notes are encrypted on this device and unlock with your PIN.' : 'Set a PIN so nobody who picks up this device can open your wallet. It also encrypts your phrase, ecash and notes here.'}</p>
      ${vault.on ? `<div class="row wrap"><button class="btn sm" data-act="pinChange">Change PIN</button>${raw.get('vault', {}).bio ? '<button class="btn sm" data-act="bioDisable">Turn off Face ID</button>' : '<button class="btn sm violet" data-act="bioStart" data-bio>Use Face ID / fingerprint</button>'}<button class="btn sm gold" data-act="lockNow">Lock now</button><button class="btn sm red" data-act="pinRemove">Remove PIN</button></div>
      <div class="field"><label for="p_lockAfter">Lock automatically after</label><select id="p_lockAfter" class="inp" data-act="prefSelect" data-k="lockAfter">${[[1, '1 minute'], [5, '5 minutes'], [15, '15 minutes'], [60, '1 hour'], [0, 'Never']].map(([v, l]) => `<option value="${v}" ${(S.prefs.lockAfter ?? 5) == v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>`
      : `<button class="btn sm gold" data-act="pinSet">Set a PIN</button>`}
      ${duressPanel()}
      <div class="sub">Spending limit</div>
      ${limitPanel()}
    </div>

    <div class="panel" id="set-backup"><span class="h2">Backup</span>
      <div class="row between tiny"><span>Recovery phrase backed up</span><span style="color:${S.seed && S.seed.backedUp ? 'var(--lime)' : 'var(--red)'}">${S.seed && S.seed.backedUp ? 'YES' : 'NOT YET'}</span></div>
      <div class="row between tiny"><span>Protected from browser clean-up</span><span style="color:${persisted ? 'var(--lime)' : 'var(--gold)'}">${persisted ? 'YES' : persisted === false ? 'NOT GRANTED' : 'CHECKING'}</span></div>
      ${persisted ? '' : '<div class="th">On iPhone, add NUTCADE to your home screen so Safari keeps its data.</div>'}
      <div class="row wrap"><button class="btn sm gold" data-act="seedShow">Show recovery phrase</button><button class="btn sm violet" data-act="findLost">Find lost ecash</button><button class="btn sm" data-act="sweepOpen">Restore ecash from another phrase</button></div>
      <div class="sub">Mint list on Nostr</div>
      ${toggle('nostrBackup', 'Back up my mint list to Nostr', 'Saves the list of mints you use, encrypted with a key from your 12 words, so restoring finds them for you. Works with cashu.me.')}
      ${S.prefs.nostrBackup ? `<div class="row between tiny"><span>Last backup</span><span style="color:${S.prefs.mintBackupAt ? 'var(--lime)' : 'var(--gold)'}">${mintBackupState === 'saving' ? 'SAVING…' : S.prefs.mintBackupAt ? timeAgo(S.prefs.mintBackupAt * 1000).toUpperCase() : mintBackupState === 'failed' ? 'RELAYS DIDN\'T ANSWER' : 'NOT YET'}</span></div><button class="btn sm" data-act="mintBackupNow">Back up now</button>` : ''}
      <div class="sub">Backup file</div>
      <p class="th" style="margin:0">Your phrase, ecash, notes and history in one file. Anyone with it can spend your sats.</p>
      <div class="row wrap"><button class="btn sm gold" data-act="backupDownload">Download backup</button><button class="btn sm" data-act="restore">Import backup</button></div>
      <div class="sub">Restore a wallet</div>
      <p class="th" style="margin:0">Moving from another wallet? Use the 12 words from a previous NUTCADE or another Cashu wallet like cashu.me. Any sats in this wallet move into the restored one.</p>
      <button class="btn sm gold" data-act="seedRestore">Restore wallet from 12 words</button>
      <div class="sub">Reset wallet</div>
      <p class="th" style="margin:0">Start over: deletes this wallet from this browser, then takes you back to the start screen to create a new wallet or restore one.</p>
      <button class="btn sm red" data-act="resetAsk">Reset wallet</button>
    </div>

    <div class="panel" id="set-contacts"><span class="h2">Contacts</span>
      <div class="row between tiny"><span>Saved contacts</span><span style="color:var(--ink)">${S.contacts.length}</span></div>
      <p class="th" style="margin:0">Pay people by name, with their Lightning address or by sending ecash over Nostr.</p>
      <button class="btn sm gold" data-act="contactsOpen">Open contacts</button>
    </div>

    <div class="panel" id="set-lnaddr"><span class="h2">Lightning address</span>
      ${S.prefs.npc ? `<div class="code addr">${esc(npcAddress())}</div>
      <div class="row between tiny"><span>Payments go to</span><span style="color:var(--ink)" data-noi18n>${esc((S.mints.find(m => m.url === S.prefs.npcMint) || {}).name || host(S.prefs.npcMint || ''))}</span></div>
      <div class="row wrap"><button class="btn sm gold" data-act="lnAddr">Manage</button><button class="btn sm" data-act="copy" data-text="${esc(npcAddress())}">Copy</button></div>`
      : `<p class="th" style="margin:0">A permanent address like name@npub.cash that anyone can pay from any Lightning wallet. It's free, uses npub.cash, and is the same address cashu.me gives these 12 words.</p><button class="btn sm gold" data-act="lnAddr">Set it up</button>`}
    </div>

    ${nwcPanel()}

    <div class="panel" id="set-look"><span class="h2">Look &amp; sound</span>
      <div class="field"><label>Cabinet theme</label><div class="seg three" role="group" aria-label="Theme">${THEMES.map(([k, l]) => `<button data-act="setTheme" data-t="${k}" aria-pressed="${S.prefs.theme === k}">${l.split(' ')[0].toUpperCase()}</button>`).join('')}</div></div>
      <div class="field"><label for="p_lang">Language</label><select id="p_lang" class="inp" data-act="prefSelect" data-k="lang">${LANGS.map(([k, l]) => `<option value="${k}" ${(S.prefs.lang || 'auto') === k ? 'selected' : ''} data-noi18n>${l}</option>`).join('')}</select></div>
      ${toggle('sound', 'Sound effects', '')}
      ${toggle('music', 'Arcade music', '')}
      ${toggle('crt', 'CRT scanlines', '')}
      ${toggle('btcSymbol', 'Show amounts as ₿', '₿1,000 instead of 1,000 SAT.')}
    </div>

    <div class="panel" id="set-privacy"><span class="h2">Privacy</span>
      ${toggle('fiat', 'Show Bitcoin price', 'Fetches the exchange rate from coinbase.com to show your balance in money.')}
      <div class="field"><label for="p_currency">Currency</label><select id="p_currency" class="inp" data-act="prefSelect" data-k="currency" ${S.prefs.fiat ? '' : 'disabled'}>${CURRENCIES.map(c => `<option data-noi18n ${c === S.prefs.currency ? 'selected' : ''}>${c}</option>`).join('')}</select></div>
      ${toggle('checkSent', 'Check if sent ecash was claimed', 'Asks your mints in the background. Turn off to contact them less.')}
      ${toggle('nostrInbox', 'Receive ecash sent over Nostr', 'Listens on Nostr relays for ecash friends send to your ecash address. Requests you made still arrive for 30 days when this is off.')}
    </div>

    <div class="panel" id="set-piggy"><span class="h2">Piggy bank</span>
      ${toggle('piggy', 'Round up my payments', 'Each payment rounds up and the difference is set aside in your piggy bank. The sats stay in your wallet; NUTCADE makes you wait through a countdown before you spend them.')}
      ${S.prefs.piggy ? `<div class="field"><label for="p_piggyStep">Round up to the nearest</label><select id="p_piggyStep" class="inp" data-act="prefSelect" data-k="piggyStep">${[10, 100, 1000].map(v => `<option value="${v}" ${(+S.prefs.piggyStep || 100) === v ? 'selected' : ''}>${fmt(v)} SAT</option>`).join('')}</select></div>
      <div class="row between tiny"><span>Saved so far</span><span style="color:var(--gold)">${money(piggySaved())}</span></div>${piggySaved() ? '<button class="btn sm" data-act="piggyEmpty">Empty piggy bank</button>' : ''}` : ''}
    </div>

    <div class="panel" id="set-tools"><span class="h2">Wallet tools</span>
      <p class="th" style="margin:0">Use these if your balance looks wrong or a payment seems stuck.</p>
      <div class="row wrap"><button class="btn sm gold" data-act="cashier">Cashier mode</button><button class="btn sm" data-act="tillOpen">Today's till</button>${S.mints.some(m => canMoveFrom(m.url)) ? '<button class="btn sm" data-act="moveOpen">Move sats between mints</button>' : ''}<button class="btn sm lime" data-act="extraOpen">Extra Life</button></div>
      <div class="row wrap"><button class="btn sm violet" data-act="clean">Remove spent ecash</button><button class="btn sm" data-act="reconcileAll">Check stuck payments${inflight ? ` (${inflight})` : ''}</button></div>
    </div>

    <div class="panel" id="set-about"><span class="h2">About</span>
      <dl class="kv"><dt>Version</dt><dd>${APP_VERSION}</dd><dt>Works with</dt><dd>Any Cashu wallet</dd></dl>
      <div class="row wrap"><a class="btn sm" href="https://github.com/Random21m/nutcade" target="_blank" rel="noopener">Source on GitHub</a><a class="btn sm" href="https://cashu.space" target="_blank" rel="noopener">What is Cashu?</a><a class="btn sm" href="https://github.com/Random21m/nutcade/issues/new?template=bug.yml" target="_blank" rel="noopener">Report a problem</a></div>
      <p class="th" style="margin:0">Reports are public on GitHub. Never paste your 12 words, your PIN or a token into one.</p>
      <div class="sub" style="color:var(--pink)">Support NUTCADE</div>
      <p class="th" style="margin:0">Free and open source. Tips over Lightning are optional and keep the cabinets lit.</p>
      <button class="btn sm pink" data-act="support">Donate</button>
    </div>
  </section>`;
}

/* fiat price (cashu.me uses the same Coinbase endpoint) */
let price = { rate: null, at: 0, cur: null };
async function fetchPrice(force) {
  if (!S.prefs.fiat) return;
  if (!force && price.cur === S.prefs.currency && Date.now() - price.at < 5 * 60e3) return;
  try {
    const j = await fetch('https://api.coinbase.com/v2/exchange-rates?currency=BTC').then(r => r.json());
    const rate = parseFloat(j.data.rates[S.prefs.currency]);
    if (rate > 0) { price = { rate, at: Date.now(), cur: S.prefs.currency }; if (!$('#layer .sheet') && tab === 'wallet') refresh(); }
  } catch (e) {}
}
const fiatOf = sats => (S.prefs.fiat && price.rate && price.cur === S.prefs.currency) ? (sats / 1e8 * price.rate).toLocaleString(numLocale(), { style: 'currency', currency: S.prefs.currency }) : null;

/* P2PK keys */
function newP2PK() {
  const k = new Uint8Array(32); crypto.getRandomValues(k);
  const pub = hex(L.getPubKeyFromPrivKey(k));
  S.p2pk.push({ pub, priv: hex(k), created: Date.now() });
  if (!store.set('p2pk', S.p2pk)) throw new Error("This browser won't save data.");
  return pub;
}
const p2pkPrivs = () => S.p2pk.map(k => k.priv);
const validPub = s => /^0[23][0-9a-f]{64}$/i.test(String(s || '').trim());

/* ---------- Nostr keys from the recovery phrase (same derivation as cashu.me) ----------
   Lightning address (npub.cash): the first 32 bytes of the BIP39 seed.
   Mint-list backup (NUT-27): sha256(seed || "cashu-mint-backup"), encrypted to itself with NIP-44. */
const nostrKey = () => seedFor().slice(0, 32);
function backupKeyFrom(seed) { const tag = new TextEncoder().encode('cashu-mint-backup'); const b = new Uint8Array(seed.length + tag.length); b.set(seed); b.set(tag, seed.length); return L.sha256(b); }
const BACKUP_RELAYS = ['wss://relay.damus.io', 'wss://nos.lol', 'wss://relay.primal.net'];   // cashu.me's defaults, so either app finds the other's backup
const relays = () => (S.prefs.relays && S.prefs.relays.length) ? S.prefs.relays : BACKUP_RELAYS;

function relayPublish(ev, timeout = 7000, list = relays()) {
  if (writeGuard.paused) return Promise.resolve(0);   // a paused tab sends nothing (the tab in charge does)
  return new Promise(res => {
    let ok = 0, left = 0; const socks = []; let fin = false;
    const end = () => { if (fin) return; fin = true; socks.forEach(s => { try { s.close(); } catch (e) {} }); res(ok); };
    for (const r of list) {
      let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
      socks.push(ws); left++;
      const drop = () => { if (ws._done) return; ws._done = true; if (--left <= 0) end(); };
      ws.onopen = () => ws.send(JSON.stringify(['EVENT', ev]));
      ws.onmessage = m => { let d; try { d = JSON.parse(m.data); } catch (e) { return; } if (d[0] === 'OK' && d[1] === ev.id) { if (d[2]) ok++; try { ws.close(); } catch (e) {} drop(); } };
      ws.onerror = drop; ws.onclose = drop;
    }
    if (!left) end();
    setTimeout(end, timeout);
  });
}
function relayQuery(filter, timeout = 7000, list = relays()) {
  return new Promise(res => {
    const out = new Map(); let left = 0; const socks = []; let fin = false;
    const end = () => { if (fin) return; fin = true; socks.forEach(s => { try { s.close(); } catch (e) {} }); res([...out.values()]); };
    for (const r of list) {
      let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
      socks.push(ws); left++;
      const drop = () => { if (ws._done) return; ws._done = true; if (--left <= 0) end(); };
      ws.onopen = () => ws.send(JSON.stringify(['REQ', 'nc', filter]));
      ws.onmessage = m => { let d; try { d = JSON.parse(m.data); } catch (e) { return; } if (d[0] === 'EVENT' && d[2] && d[2].id) out.set(d[2].id, d[2]); else if (d[0] === 'EOSE' || d[0] === 'CLOSED') { try { ws.close(); } catch (e) {} drop(); } };
      ws.onerror = drop; ws.onclose = drop;
    }
    if (!left) end();
    setTimeout(end, timeout);
  });
}

/* Mint-list backup (NUT-27): kind 30078, d=mint-list, NIP-44 content {mints, timestamp}. */
let mintBackupT = 0, mintBackupState = null, mintBackupTry = 0;
function scheduleMintBackup(delay = 1500) {
  if (!S.prefs.nostrBackup || !S.seed || !S.mints.length) return;
  clearTimeout(mintBackupT); mintBackupT = setTimeout(() => backupMints().catch(() => {}), delay);
}
async function backupMints() {
  const mints = S.mints.map(m => m.url); if (!mints.length) return 0;
  const sk = backupKeyFrom(seedFor()), pk = L.nostrPub(sk);
  const ck = L.nip44.v2.utils.getConversationKey(sk, pk);
  const ts = Math.max(Math.floor(Date.now() / 1000), (S.prefs.mintBackupAt || 0) + 1);
  const content = L.nip44.v2.encrypt(JSON.stringify({ mints, timestamp: ts }), ck);
  const ev = L.finalizeEvent({ kind: 30078, created_at: ts, tags: [['d', 'mint-list'], ['client', 'nutcade']], content }, sk);
  mintBackupState = 'saving'; mintBackupTry = Date.now();
  const ok = await relayPublish(ev);
  mintBackupState = ok ? 'ok' : 'failed';
  if (ok) { S.prefs.mintBackupAt = ts; S.prefs.mintBackupList = mints.join(' '); save(); }
  return ok;
}
async function findMintBackups(mnemonic) {
  const sk = backupKeyFrom(L.mnemonicToSeedSync(mnemonic)), pk = L.nostrPub(sk);
  const ck = L.nip44.v2.utils.getConversationKey(sk, pk);
  const evs = await relayQuery({ kinds: [30078], authors: [pk], '#d': ['mint-list'], limit: 10 });
  const found = new Map();
  for (const e of evs) {
    if (e.pubkey !== pk || !L.verifyEvent(e)) continue;
    try {
      const d = JSON.parse(L.nip44.v2.decrypt(e.content, ck));
      for (const u of d.mints || []) if (typeof u === 'string' && /^https?:\/\/[^\s]+$/i.test(u)) { const k = normUrl(u); found.set(k, Math.max(found.get(k) || 0, d.timestamp || e.created_at)); }
    } catch (x) {}
  }
  return [...found.entries()].sort((a, b) => b[1] - a[1]).map(([u]) => u);
}

/* ---------- your own Lightning address (npub.cash v2) ---------- */
const npcBase = () => String(S.prefs.npcHost || 'https://npub.cash').replace(/\/+$/, '');
const npcPub = () => L.nostrPub(nostrKey());
const npcAddress = () => (S.prefs.npcName || L.npubEncode(npcPub())) + '@' + new URL(npcBase()).host;
function nip98(url, method) {
  const ev = L.finalizeEvent({ kind: 27235, created_at: Math.floor(Date.now() / 1000), tags: [['u', url], ['method', method]], content: '' }, nostrKey());
  return 'Nostr ' + btoa(JSON.stringify(ev));
}
async function npc(path, opts = {}, authPath) {
  const method = opts.method || 'GET';
  const headers = { authorization: nip98(npcBase() + (authPath || path), method) };
  if (opts.body) headers['content-type'] = 'application/json';
  let r;
  try { r = await fetch(npcBase() + path, { method, headers, body: opts.body ? JSON.stringify(opts.body) : undefined }); }
  catch (e) { throw new Error(`Can't reach ${new URL(npcBase()).host}. Check your connection and try again.`); }
  let j = null; try { j = await r.json(); } catch (e) {}
  if (!r.ok || !j || j.error) throw new Error((j && typeof j.message === 'string' && j.message) || `${new URL(npcBase()).host} answered ${r.status}.`);
  return j;
}
function npcPrivFor(pub) {
  const sk = nostrKey(); const x = npcPub(); pub = String(pub || '').toLowerCase();
  return (pub === '02' + x || pub === '03' + x || pub === hex(L.getPubKeyFromPrivKey(sk))) ? hex(sk) : null;
}
async function npcConnect(wantMint) {
  const u = (await npc('/api/v2/user/info')).data.user;
  let mint = u.mintUrl ? normUrl(u.mintUrl) : '';
  const want = wantMint ? normUrl(wantMint) : (S.mints.find(m => m.url === mint) ? mint : (activeMint() && supports(activeMint(), 'mint', 'bolt11') ? S.active : mint));
  if (want) { await getWallet(want).catch(() => {}); if (belowMin(want)) throw minErr(want); }   // (the Lightning address's payments are deposits there)
  if (want && want !== mint) {
    if (!S.mints.find(m => m.url === want)) await addMint(want);
    const d = await npc('/api/v2/user/mint', { method: 'PATCH', body: { mint_url: want } });
    mint = normUrl(d.data.user.mintUrl || want);
  }
  if (mint && !S.mints.find(m => m.url === mint)) await addMint(mint);
  S.prefs.npc = true; S.prefs.npcName = u.name || ''; S.prefs.npcMint = mint; save();
  npcSocketStart();
  return mint;
}
function npcOff() { S.prefs.npc = false; save(); npcSocketStop(); }
let npcBusy = null;
function npcSync() {
  if (!S.prefs.npc || !S.seed || tabLocked || (vault.on && !vault.open)) return Promise.resolve(0);
  if (npcBusy) return npcBusy;
  npcBusy = (async () => {
    let added = 0, offset = 0, total = 0, latest = S.prefs.npcSince || 0; const seen = new Set();
    do {
      const qs = new URLSearchParams({ limit: '50', offset: String(offset) });
      if (S.prefs.npcSince) qs.set('since', String(Math.max(0, S.prefs.npcSince - 1)));
      const j = await npc('/api/v2/wallet/quotes?' + qs, {}, '/api/v2/wallet/quotes');
      const page = (j.data && j.data.quotes) || [];
      total = (j.metadata && j.metadata.total) || 0;
      for (const q of page) {
        const key = q.mintUrl + '|' + q.quoteId; if (seen.has(key)) continue; seen.add(key);
        if (q.state !== 'PAID') continue;
        latest = Math.max(latest, q.paidAt || q.createdAt || 0);
        if (S.txs.some(t => t.quote === q.quoteId) || S.quotes.some(x => x.quote === q.quoteId)) continue;
        const mint = normUrl(q.mintUrl), amount = num(q.amount);
        if (!amount) continue;
        if (!S.mints.find(m => m.url === mint)) await addMint(mint);
        const tx = addTx({ type: 'in', method: 'ln', amount, mint, note: 'Lightning address', status: 'pending', request: q.request, quote: q.quoteId, ts: (q.paidAt || q.createdAt || Date.now() / 1000) * 1000 });
        S.quotes.push({ kind: 'bolt11', quote: q.quoteId, request: q.request, amount, mint, txId: tx.id, expiry: null, npc: true });
        save(); added++;
      }
      offset += page.length;
      if (!page.length) break;
    } while (offset < total);
    if (latest > (S.prefs.npcSince || 0)) { S.prefs.npcSince = latest; save(); }
    for (const q of S.quotes.filter(x => x.npc)) await checkQuote(q).catch(() => {});
    return added;
  })().finally(() => { npcBusy = null; });
  return npcBusy;
}
/* npub.cash pushes "a quote changed" over a websocket after a NIP-98 challenge, then we sync. */
let npcWs = null, npcWsTry = 0, npcWsTimer = 0;
function npcSocketStart() {
  if (!S.prefs.npc || !S.seed || tabLocked || typeof WebSocket === 'undefined') return;
  if (npcWs && (npcWs.readyState === 0 || npcWs.readyState === 1)) return;
  const wsUrl = npcBase().replace(/^http/, 'ws') + '/api/v2/ws/quote';
  let ws; try { ws = new WebSocket(wsUrl); } catch (e) { return; }
  npcWs = ws;
  ws.onmessage = ev => {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.type === 'challenge') {
      const p = m.payload && typeof m.payload === 'object' ? m.payload : null;
      const authUrl = p ? p.url : wsUrl, method = (p && p.method) || 'GET';
      try { const a = new URL(authUrl), b = new URL(wsUrl); if (!['https:', 'wss:', 'http:', 'ws:'].includes(a.protocol) || a.host !== b.host || a.pathname !== b.pathname) throw 0; }
      catch (e) { ws.close(); return; }
      ws.send(JSON.stringify(p ? { type: 'challenge-response', payload: nip98(authUrl, method) } : { type: 'auth', token: nip98(authUrl, method) }));
    } else if (m.type === 'ok' || m.type === 'challenge-success') { npcWsTry = 0; npcSync().then(n => { if (n) refresh(); }).catch(() => {}); }
    else if (m.type === 'update') npcSync().then(n => { if (n) refresh(); }).catch(() => {});
    else if (m.type === 'error') ws.close();
  };
  ws.onclose = () => { if (npcWs !== ws) return; npcWs = null; if (!S.prefs.npc) return; clearTimeout(npcWsTimer); npcWsTimer = setTimeout(npcSocketStart, Math.min(60e3, 1000 * 2 ** npcWsTry++) * (0.75 + Math.random() / 2)); };
}
function npcSocketStop() { clearTimeout(npcWsTimer); const w = npcWs; npcWs = null; if (w) try { w.close(1000); } catch (e) {} }

/* ---------- instant updates from mints (NUT-17 websockets); the 30-second check stays as the fallback ---------- */
const live = new Map();
const reclaiming = new Set();   // our own tokens we're taking back, so a live SPENT isn't reported as claimed   // key -> canceller | 'none' | null (connecting)
async function liveWatch(key, url, cmd, subscribe) {
  if (live.has(key)) return;
  live.set(key, null);
  try {
    const w = await getWallet(url);
    const sup = w.getMintInfo().isSupported(17);
    if (!sup || !sup.supported || !(sup.params || []).some(p => p.unit === 'sat' && (p.commands || []).includes(cmd))) { live.set(key, 'none'); return; }
    const cancel = await subscribe(w);
    if (live.get(key) === null) live.set(key, cancel); else { try { cancel(); } catch (e) {} }
  } catch (e) { live.delete(key); }
}
function liveDrop(key) { const c = live.get(key); live.delete(key); if (typeof c === 'function') try { c(); } catch (e) {} }
function liveSync() {
  if (!S.seed || tabLocked || (vault.on && !vault.open)) { for (const k of [...live.keys()]) liveDrop(k); return; }
  const want = new Set();
  for (const q of S.quotes.filter(q => q.kind === 'bolt11')) {
    const k = 'mq:' + q.quote; want.add(k);
    liveWatch(k, q.mint, 'bolt11_mint_quote', w => w.on.mintQuotePaid(q.quote, () => checkQuote(q).catch(() => {}), () => liveDrop(k)));
  }
  for (const p of S.pending.filter(p => p.kind === 'ln' && !p.paid)) {
    const k = 'melt:' + p.quote; want.add(k);
    liveWatch(k, p.mint, 'bolt11_melt_quote', w => w.on.meltQuotePaid(p.quote, () => reconcile(p).then(r => { if (r === 'paid') { refresh(); toast('Payment confirmed', 'lime'); } }).catch(() => {}), () => liveDrop(k)));
  }
  if (S.prefs.checkSent) for (const t of S.txs.filter(t => t.status === 'pending' && t.method === 'ecash' && t.sent).slice(0, 10)) {
    const k = 'tok:' + t.id; want.add(k);
    const spent = new Set();
    liveWatch(k, t.mint, 'proof_state', w => w.on.proofStateUpdates(t.sent, ps => {
      if (ps.state !== 'SPENT') return;
      spent.add(ps.proof.secret);
      if (spent.size < t.sent.length) return;
      // The mint pushed SPENT for every proof in the token: it has been claimed (or reclaimed by us, which wins).
      const cur = txById(t.id);
      if (cur && cur.status === 'pending' && !reclaiming.has(t.id)) { updTx(t.id, { status: 'claimed' }); refresh(); toast(`Your ${money(t.amount)} token was claimed`, 'lime'); }
    }, () => liveDrop(k)));
  }
  for (const k of [...live.keys()]) if (!want.has(k)) liveDrop(k);
}


/* ---------- multinut: one Lightning invoice paid from several mints (NUT-15) ---------- */
async function mppMints() {
  const out = [];
  for (const m of S.mints) {
    const bal = balanceOf(m.url); if (bal <= 0) continue;
    try {
      const w = await getWallet(m.url);
      const s = w.getMintInfo().isSupported(15);
      if (s && s.supported && (s.params || []).some(p => p.method === 'bolt11' && p.unit === 'sat')) out.push({ url: m.url, name: m.name, bal, w });
    } catch (e) {}
  }
  return out;
}
async function planMultinut(invoice, amount, onStep) {
  const cands = (await mppMints()).sort((a, b) => b.bal - a.bal);
  if (cands.length < 2) throw new Error('Paying from several mints needs at least two mints with sats that support multi-path payments (NUT-15).');
  // leave room for each mint's Lightning fee reserve and input fees
  const room = c => Math.max(0, Math.floor((c.bal - 2) / 1.02) - 2);
  if (cands.reduce((t, c) => t + room(c), 0) < amount) throw new Error(`Your mints that support this hold ${money(cands.reduce((t, c) => t + c.bal, 0))}, not enough for ${money(amount)} plus fees.`);
  let left = amount; const parts = [];
  for (const c of cands) { if (!left) break; const a = Math.min(room(c), left); if (a > 0) { parts.push({ c, amount: a }); left -= a; } }
  for (let round = 0; round < 4; round++) {
    let deficit = 0;
    for (const p of parts) {
      if (p.mq && num(p.mq.amount) === p.amount) continue;
      onStep && onStep(`Asking ${p.c.name} for ${money(p.amount)}…`);
      p.mq = await p.c.w.createMultiPathMeltQuote(invoice, p.amount * 1000);
      const inFee = num(p.c.w.getFeesForProofs(S.proofs[p.c.url] || []));
      p.need = num(p.mq.amount) + num(p.mq.fee_reserve);
      const over = p.need + Math.min(inFee, 3) - p.c.bal;
      if (over > 0) { const cut = Math.min(p.amount - 1, over); p.amount -= cut; deficit += cut; }
    }
    if (!deficit) break;
    for (const p of parts) { const slack = room(p.c) - p.amount - 2; if (slack > 0 && deficit) { const add = Math.min(slack, deficit); p.amount += add; deficit -= add; } }
    for (const c of cands) { if (!deficit) break; if (!parts.some(p => p.c === c)) { const a = Math.min(room(c), deficit); if (a > 0) { parts.push({ c, amount: a }); deficit -= a; } } }
    if (deficit) throw new Error("Couldn't fit the fees into your mints' balances. Try a smaller payment.");
  }
  if (parts.reduce((t, p) => t + num(p.mq.amount), 0) !== amount) throw new Error("The mints' quotes didn't add up to the invoice. Nothing was sent.");
  return parts.filter(p => p.amount > 0);
}
function openMultinut(invoice, amount, dest, note) {
  openSheet('Pay from several mints', busyHTML('PLANNING'), body => {
    let alive = true;
    planMultinut(invoice, amount, t => { const s = body.querySelector('.spinner'); if (s) s.textContent = t.toUpperCase(); }).then(parts => {
      if (!alive) return;
      const fees = parts.reduce((t, p) => t + num(p.mq.fee_reserve), 0), mintFees = parts.reduce((t, p) => t + meltCost(p.c.url, p.mq.amount, p.mq.fee_reserve).mintFee, 0);
      setBody(`<p style="margin:0">NUTCADE will pay this ${money(amount)} invoice in ${parts.length} parts at once. The payment only completes if every part goes through; if one fails, all the sats come back.</p>
        <div class="txs">${parts.map((p, i) => `<div class="tx out" data-part="${i}"><span class="ico" aria-hidden="true">${i + 1}</span><span class="mid"><div class="note">${esc(p.c.name)}</div><div class="meta"><span>Fee reserve ${money(p.mq.fee_reserve)}</span><span>Holds ${money(p.c.bal)}</span></div></span><span class="amt">${fmt(p.mq.amount)}</span></div>`).join('')}</div>
        <dl class="kv"><dt>Pay</dt><dd>${money(amount)}</dd>${costRows({ reserve: fees, mintFee: mintFees, total: amount + fees + mintFees })}<dt>To</dt><dd class="tiny">${esc(dest.length > 40 ? dest.slice(0, 18) + '…' + dest.slice(-14) : dest)}</dd></dl>
        <div class="tiny muted">Unused fee reserve comes back as change.</div>
        <button class="btn solid pink block" id="mppPay">Pay ${money(amount)}</button><div id="sheetErr"></div>`, b2 => {
        b2.querySelector('#mppPay').onclick = e => run(e.currentTarget, 'PAYING', async () => {
          const n = parts.length;
          const grant = limitGrant(amount + fees + mintFees);   // the spending limit counts the whole payment, not each part
          let res; try { res = await Promise.allSettled(parts.map((p, i) => payMelt('ln', p.mq, 0, `${note || 'Lightning payment'} (part ${i + 1} of ${n})`, dest, p.c.url, { grant }))); } finally { grant.release(); }
          const txs = res.map(r => r.status === 'fulfilled' ? r.value : null);
          refresh();
          if (txs.every(t => t && t.status === 'done')) return showDone('out', amount, `Lightning · ${n} mints`);
          for (const p of [...S.pending]) if (parts.some(x => x.mq.quote === p.quote)) await reconcile(p).catch(() => {});
          const st = parts.map(p => (S.txs.find(t => t.quote === p.mq.quote) || {}).status);
          refresh();
          if (st.every(s => s === 'done')) return showDone('out', amount, `Lightning · ${n} mints`);
          if (st.some(s => s === 'pending')) setBody(`<div class="notice">The payment is in flight. NUTCADE will settle each part when the mints confirm. Check the parts in your notes.</div><button class="btn block gold" data-act="close">OK</button>`);
          else if (st.some(s => s === 'done')) {   // (some parts were paid and some came back: the words match what was booked)
            const paid = parts.filter((p, i) => st[i] === 'done'), kept = parts.reduce((t, p) => t + num((S.txs.find(x => x.quote === p.mq.quote) || {}).cost), 0);
            setBody(`<div class="notice red">Only part of this payment went through: ${money(paid.reduce((t, p) => t + num(p.mq.amount), 0))} was paid. The other parts came back to your wallet${kept ? `, except ${money(kept)} the mints kept as fees` : ''}. Check with the payee: the invoice may not count as paid.</div><button class="btn block gold" data-act="close">OK</button>`);
          }
          else {
            const kept = parts.reduce((t, p) => t + num((S.txs.find(x => x.quote === p.mq.quote) || {}).cost), 0);   // swap fees that didn't come back
            setBody(`<div class="notice red">${kept ? `The payment didn't go through. The parts that were sent came back to your wallet, except ${money(kept)} the mints kept as fees.` : "The payment didn't go through, so the parts that were sent came back to your wallet."}</div><button class="btn block gold" data-act="close">OK</button>`);
          }
        });
        return null;
      });
    }).catch(e => { if (alive) setBody(`${errHTML(friendly(e, S.active))}<button class="btn block" data-act="close">Close</button>`); });
    return () => { alive = false; };
  });
}

/* ---------- payment requests (NUT-18) ---------- */
// Requests are received as NIP-17 gift-wrapped DMs to the same Nostr key cashu.me uses (first 32 bytes of the seed).
function newRequest(amount, memo, onlyMine) {
  const pub = L.nostrPub(nostrKey());
  const id = hex(rnd(4));
  const transport = [{ type: 'nostr', target: L.nprofileEncode({ pubkey: pub, relays: relays() }), tags: [['n', '17']] }];
  const pr = new L.PaymentRequest(transport, id, amount || undefined, 'sat', onlyMine && S.mints.length ? S.mints.map(m => m.url) : undefined, memo || undefined);
  const r = { id, encoded: pr.toEncodedRequest(), amount: amount || 0, memo: memo || '', created: Date.now(), paid: [] };
  S.requests.unshift(r); S.requests = S.requests.slice(0, 30); store.set('requests', S.requests);
  dmListen();
  return r;
}
let dmSocks = [], dmRetry = 0, dmNext = 0;
const dmWanted = () => !!(S.seed && S.seed.backedUp && !tabLocked && !(vault.on && !vault.open) && (S.prefs.nostrInbox || S.requests.some(r => Date.now() - r.created < 30 * 86400e3)));
function dmListen() {
  if (!dmWanted()) { dmStop(); return; }
  if (dmSocks.some(s => s.readyState <= 1) || Date.now() < dmNext) return;
  const pub = L.nostrPub(nostrKey());
  // gift wraps carry randomized timestamps up to two days in the past
  const since = Math.floor(Math.min(Date.now(), S.prefs.dmSince || Math.min(...S.requests.map(r => r.created))) / 1000) - 2 * 86400;
  dmSocks = [];
  for (const r of relays()) {
    let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
    dmSocks.push(ws);
    ws.onopen = () => ws.send(JSON.stringify(['REQ', 'ncdm', { kinds: [1059], '#p': [pub], since }]));
    ws.onmessage = m => { let d; try { d = JSON.parse(m.data); } catch (e) { return; } if (d[0] === 'EVENT' && d[2]) onGiftWrap(d[2]); else if (d[0] === 'EOSE') { dmRetry = 0; } };
    ws.onclose = () => { if (dmSocks.includes(ws) && dmSocks.every(s => s.readyState >= 2)) { const d = Math.min(120e3, 3000 * 2 ** dmRetry++); dmNext = Date.now() + d; setTimeout(dmListen, d + 50); } };
  }
}
function dmStop() { const s = dmSocks; dmSocks = []; s.forEach(w => { try { w.close(); } catch (e) {} }); }
const seenWraps = new Set(raw.get('dmseen', []));
let wrapChain = Promise.resolve();
function onGiftWrap(ev) {
  if (!ev || ev.kind !== 1059 || seenWraps.has(ev.id)) return;
  seenWraps.add(ev.id); raw.set('dmseen', [...seenWraps].slice(-400));
  wrapChain = wrapChain.then(async () => {
    let rumor; try { if (!L.verifyEvent(ev)) return; rumor = L.nip59.unwrapEvent(ev, nostrKey()); } catch (e) { return; }
    let p; try { p = JSON.parse(rumor.content); } catch (e) { return; }
    if (p && p.t === 'nutcade-challenge' && p.ev) { onChallenge(p.ev, 'nostr', p.bounty, rumor.pubkey, typeof p.replay === 'string' ? p.replay : null); return; }
    if (p && p.t === 'nutcade-result' && p.ev) { await onResult(p.ev, typeof p.replay === 'string' ? p.replay : null); return; }
    if (p && p.t === 'nutcade-bounty' && p.re && typeof p.pre === 'string') { const rec = S.challenges.find(x => x.id === p.re && x.dir === 'in'); if (rec) await claimBounty(rec, p.pre, rumor.pubkey); return; }
    if (p && (p.t === 'nutcade-extralife' || p.t === 'nutcade-extralife-end')) { await onExtraLife(p, rumor.pubkey); return; }
    if (p && Array.isArray(p.proofs) && p.proofs.length && typeof p.mint === 'string') await receivePayload(p, rumor.pubkey);
  }).catch(() => {});
}
async function receivePayload(p, from) {
  if ((p.unit || 'sat') !== 'sat') return;
  const mint = normUrl(p.mint);
  const proofs = p.proofs.map(x => Object.assign({}, x, { amount: num(x.amount) }));
  const token = L.getEncodedToken({ mint, proofs, unit: 'sat' });
  if (S.txs.some(t => t.token === token || t.incoming === token)) return;
  const req = S.requests.find(r => r.id && r.id === p.id);
  const who = from && S.contacts.find(c => c.pubkey === from);
  const note = req ? (req.memo ? `Request: ${req.memo}` : 'Payment request') : who ? `From ${who.name}${p.memo ? ': ' + String(p.memo).slice(0, 120) : ''}` : (p.memo ? String(p.memo).slice(0, 120) : 'Ecash over Nostr');
  S.prefs.dmSince = Date.now(); save();
  if (isBlocked(mint)) {   // refused, and said so: it waits in your notes in case you unblock the mint
    addTx({ type: 'in', method: 'ecash', amount: sum(proofs), mint, note, status: 'pending', incoming: token, reqId: p.id || null, refused: true });
    sfx('err'); refresh();
    toast(`Refused ${money(sum(proofs))} from ${mintName(mint)}: you blocked that mint. It waits in your notes if you unblock it.`, 'gold');
    return;
  }
  if (!S.mints.find(m => m.url === mint)) {
    if (!req && !who) return;   // ecash from an unknown mint is only kept when it answers one of our requests or comes from a contact
    addTx({ type: 'in', method: 'ecash', amount: sum(proofs), mint, note, status: 'pending', incoming: token, reqId: p.id || null });
    sfx('blip'); refresh();
    toast(`${money(sum(proofs))} arrived from ${host(mint)}, a mint you don't use yet. Open it in your notes to claim it.`, 'gold');
    return;
  }
  try {
    const tx = await receiveToken(token, note, req ? { follow: { k: 'req', reqId: req.id } } : {});
    updTx(tx.id, { reqId: p.id || null });
    if (req) reqPaid(req.id, tx);
    sfx('coin'); refresh();
    if (!$('#layer .sheet')) celebrate('in', tx.amount);
    toast(`+${money(tx.amount)} received${req ? ' for your request' : ''}`, 'lime');
    document.dispatchEvent(new CustomEvent('nutcade:request', { detail: { id: p.id, amount: tx.amount } }));
  } catch (e) { /* already claimed or not valid: nothing to add */ }
}
function decodeRequest(enc) {
  let pr; try { pr = L.decodePaymentRequest(String(enc).trim().replace(/^cashu:/i, '')); } catch (e) { throw new Error("That payment request can't be read."); }
  return pr;
}
async function deliverPayment(pr, payload, wrap) {
  const tr = (pr.transport || []).find(t => t.type === 'nostr') || (pr.transport || []).find(t => t.type === 'post');
  if (!tr) return false;
  if (tr.type === 'post') {
    let r; try { r = await fetch(tr.target, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); }
    catch (e) { throw new Error("Couldn't reach the requester's server."); }
    if (!r.ok) throw new Error(`The requester's server answered ${r.status}.`);
    return true;
  }
  const d = L.nip19decode(tr.target);
  const to = d.type === 'nprofile' ? d.data.pubkey : d.type === 'npub' ? d.data : null;
  if (!to) throw new Error("This request's Nostr address can't be read.");
  const theirs = (d.type === 'nprofile' && d.data.relays) || [];
  const list = [...new Set(theirs.filter(u => /^wss?:\/\//.test(u)).concat(relays()))].slice(0, 8);
  // A fresh one-time key signs the message, so the payment isn't linked to your Nostr identity.
  const ev = wrap || L.nip17.wrapEvent(rnd(32), { publicKey: to }, JSON.stringify(payload));
  const ok = await relayPublish(ev, 8000, list);
  if (!ok) throw new Error('No Nostr relay accepted the payment.');
  return true;
}
/* A payment to a payment request is made once (one swap, its record in the journal) and its line keeps the request,
   so that if the app stops before the payee has it (a reload, a closed tab, a swap whose answer was lost), the SAME
   coins are delivered once the wallet is back: the Nostr message is made once and kept, so sending it again is the
   same message (relays and the payee see it once). If the payee already has the coins (spent), the line is closed;
   if it can't be delivered after several tries, the coins come back with a line that says so. */
const reqPayload = (pr, url, proofs) => Object.assign({ id: pr.id, mint: url, unit: 'sat', proofs }, pr.description ? { memo: pr.description } : {});
function reqWrap(pr, payload) {
  const tr = (pr.transport || []).find(t => t.type === 'nostr'); if (!tr) return null;
  try { const d = L.nip19decode(tr.target); const to = d.type === 'nprofile' ? d.data.pubkey : d.type === 'npub' ? d.data : null; return to ? L.nip17.wrapEvent(rnd(32), { publicKey: to }, JSON.stringify(payload)) : null; } catch (e) { return null; }
}
async function payRequest(pr, amount, url, note, enc) {
  const lock = pr.nut10 && pr.nut10.kind === 'P2PK' && validPub(pr.nut10.data) ? pr.nut10.data : null;
  const rq = enc && (pr.transport || []).length ? { reqPay: { req: enc } } : {};
  const tx = await sendEcash(amount, note, lock, url, rq.reqPay ? { txx: rq, follow: { k: 'reqpay' } } : {});
  const payload = reqPayload(pr, url, tx.sent), wrap = rq.reqPay ? reqWrap(pr, payload) : null;
  if (wrap) { updTx(tx.id, { reqPay: Object.assign({}, rq.reqPay, { ev: wrap }) }); await saveNow(); }   // (kept before it is sent)
  let sent = false, why = '';
  try { sent = await deliverPayment(pr, payload, wrap); } catch (e) { why = e.message; }
  if (sent) updTx(tx.id, { delivered: true });
  else if (rq.reqPay) updTx(tx.id, { reqPay: Object.assign({}, txById(tx.id).reqPay, { shown: 1 }) });   // (you were shown the token: it is yours to pass on)
  return { tx, sent, why };
}
const REQ_TRIES = 6;
async function deliverReqPays() {
  for (const t0 of S.txs.filter(t => t.reqPay && !t.reqPay.shown && !t.delivered && t.status === 'pending' && t.sent && t.sent.length)) {
    if (t0.reqPay.next && Date.now() < t0.reqPay.next) continue;
    await single('reqpay:' + t0.id, async () => {
      await syncIfStale();
      const t = txById(t0.id); if (!t || !t.reqPay || t.reqPay.shown || t.delivered || t.status !== 'pending') return;
      // the payee already has it: closed, never sent again
      const w = await getWallet(t.mint); const st = await inTime(w.checkProofsStates(t.sent), 30000);
      if (st.length && st.every(x => x && x.state === 'SPENT')) { updTx(t.id, { delivered: true, status: 'claimed' }); return; }
      let pr = null; try { pr = decodeRequest(t.reqPay.req); } catch (e) {}
      let ok = false; const ev = t.reqPay.ev || (pr ? reqWrap(pr, reqPayload(pr, t.mint, t.sent)) : null);
      if (pr && ev && !t.reqPay.ev) { updTx(t.id, { reqPay: Object.assign({}, t.reqPay, { ev }) }); await saveNow(); }
      if (pr) { try { ok = await deliverPayment(pr, reqPayload(pr, t.mint, t.sent), ev); } catch (e) { ok = false; } }
      if (ok) { updTx(t.id, { delivered: true }); return; }
      const tries = (t.reqPay.tries || 0) + 1;
      if (tries < REQ_TRIES && pr) { updTx(t.id, { reqPay: Object.assign({}, t.reqPay, { tries, next: Date.now() + Math.min(30 * 60e3, 30e3 * 2 ** (tries - 1)) }) }); return; }
      // it can't be delivered: the coins come back, with a line saying so
      updTx(t.id, { reqPay: Object.assign({}, t.reqPay, { shown: 1 }) });
      await receiveToken(t.token, "Payment request couldn't be delivered: the sats came back", { own: true }).catch(() => {});
      refresh();
    });
  }
}

/* ---------- NFC (Web NFC: Chrome on Android) ---------- */
const nfcOK = () => typeof window !== 'undefined' && 'NDEFReader' in window;
let nfcAbort = null;
function nfcStop() { if (nfcAbort) { try { nfcAbort.abort(); } catch (e) {} nfcAbort = null; } }
function nfcText(message) {
  for (const rec of message.records || []) {
    if (rec.recordType === 'mime' && /octet-stream/.test(rec.mediaType || '')) {
      const u = new Uint8Array(rec.data.buffer, rec.data.byteOffset, rec.data.byteLength);
      if (String.fromCharCode(...u.slice(0, 4)) === 'craw') return L.getEncodedToken(L.getDecodedTokenBinary(u, Object.keys(S.counters)));
    }
    if (['text', 'url', 'absolute-url'].includes(rec.recordType)) {
      const s = new TextDecoder(rec.encoding || 'utf-8').decode(rec.data);
      const m = s.match(/cashu[AB][A-Za-z0-9_\-+/=]{20,}|creqA[A-Za-z0-9_\-+/=]+|creqb1[02-9ac-hj-np-z]+|ln(bc|tb|bcrt)[0-9a-z]{50,}|lnurl1[0-9a-z]+/i);
      return m ? m[0] : s;
    }
  }
  return '';
}
async function nfcRead(onText, onState) {
  nfcStop();
  const r = new NDEFReader(); const ac = new AbortController(); nfcAbort = ac;
  r.onreading = ev => { if (nfcAbort !== ac) return; nfcStop(); let t = ''; try { t = nfcText(ev.message); } catch (e) {} onText(t); };
  r.onreadingerror = () => onState && onState("COULDN'T READ THAT TAG. HOLD IT STILL.");
  await r.scan({ signal: ac.signal });
}
async function nfcWrite(text) {
  nfcStop();
  const w = new NDEFReader(); const ac = new AbortController(); nfcAbort = ac;
  let rec = { recordType: 'text', data: text, lang: 'en' };
  if (/^cashuB/.test(text) && text.length > 460) {   // small cards (NTAG215 ≈ 500 bytes): use the compact binary form cashu.me also reads
    try { rec = { recordType: 'mime', mediaType: 'application/octet-stream', data: L.getEncodedTokenBinary(L.getDecodedToken(text, Object.keys(S.counters))) }; } catch (e) {}
  }
  try { await w.write({ records: [rec] }, { overwrite: true, signal: ac.signal }); }
  finally { if (nfcAbort === ac) nfcAbort = null; }
}
const nfcBtn = (act, label, extra = '', cls = 'btn violet') => nfcOK() ? `<button class="${cls}" data-act="${act}" ${extra}><svg class="ico-scan" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3 2h1v12H3zm2 2h1v8H5zm5-2h1v12h-1zm2 2h1v8h-1zM7 3h2v1h1v2H9V5H7zm0 5h2v1h1v2H9v-1H7z"/></svg>${label}</button>` : '';


/* ---------- contacts ---------- */
function parseNostrAddr(v) {
  v = String(v || '').trim().replace(/^nostr:/i, '');
  if (!v) return null;
  try { const d = L.nip19decode(v); if (d.type === 'npub') return { pubkey: d.data, relays: [] }; if (d.type === 'nprofile') return { pubkey: d.data.pubkey, relays: (d.data.relays || []).filter(u => /^wss?:\/\//.test(u)).slice(0, 5) }; } catch (e) {}
  if (/^[0-9a-f]{64}$/i.test(v)) return { pubkey: v.toLowerCase(), relays: [] };
  return null;
}
const myEcashAddress = () => L.nprofileEncode({ pubkey: L.nostrPub(nostrKey()), relays: relays().slice(0, 3) });
function saveContact(c) {
  const name = String(c.name || '').trim().slice(0, 40);
  if (!name) throw new Error('Give the contact a name.');
  const ln = String(c.ln || '').trim().toLowerCase();
  if (ln && !/^[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}$/.test(ln) && !/^lnurl1[0-9a-z]+$/.test(ln)) throw new Error("That Lightning address doesn't look right. It should look like name@wallet.com.");
  let nostr = null;
  if (String(c.nostr || '').trim()) { nostr = parseNostrAddr(c.nostr); if (!nostr) throw new Error("That Nostr address can't be read. Paste an npub or nprofile."); }
  if (!ln && !nostr) throw new Error('Add a Lightning address, a Nostr address, or both.');
  // one contact per person: the same Lightning or Nostr address can't be saved twice
  const twin = S.contacts.find(x => x.id !== c.id && ((ln && x.ln === ln) || (nostr && x.pubkey === nostr.pubkey)));
  if (twin) { const e = new Error(`${twin.name} already has ${ln && twin.ln === ln ? 'this Lightning address' : 'this Nostr address'}. Edit that contact instead.`); e.fix = { act: 'contactEdit', id: twin.id, label: 'Edit that contact' }; throw e; }
  const rec = { id: c.id || uid(), name, ln, nostr: nostr ? String(c.nostr).trim().replace(/^nostr:/i, '') : '', pubkey: nostr ? nostr.pubkey : '', relays: nostr ? nostr.relays : [], created: c.created || Date.now() };
  const i = S.contacts.findIndex(x => x.id === rec.id);
  if (i >= 0) S.contacts[i] = rec; else S.contacts.push(rec);
  S.contacts.sort((a, b) => a.name.localeCompare(b.name));
  store.set('contacts', S.contacts);
  return rec;
}
const contactById = id => S.contacts.find(c => c.id === id);
async function sendToContactNostr(c, amount, note) {
  const tx = await sendEcash(amount, note, null);
  const payload = { mint: S.active, unit: 'sat', proofs: tx.sent, memo: note || undefined };
  const list = [...new Set((c.relays || []).concat(relays()))].slice(0, 8);
  const ev = L.nip17.wrapEvent(rnd(32), { publicKey: c.pubkey }, JSON.stringify(payload));
  const ok = await relayPublish(ev, 8000, list);
  updTx(tx.id, { contactId: c.id, contactName: c.name, delivered: !!ok });
  return { tx, ok };
}
function contactChips() {
  if (!S.contacts.length) return '';
  return `<div class="field"><label>To a contact</label><div class="tagrow">${S.contacts.slice(0, 12).map(c => `<button class="tag" data-noi18n data-act="payContact" data-id="${c.id}">${esc(c.name)}</button>`).join('')}<button class="tag" data-act="contactsOpen">Manage</button></div></div>`;
}
function openContacts() {
  if (needSeed()) return;
  openSheet('Contacts', `
    <p style="margin:0">Save the people you pay. A contact can have a Lightning address, a Nostr address for sending ecash (npub or nprofile), or both. Contacts stay on this device${vault.on ? ', encrypted with your PIN' : ''}.</p>
    ${S.contacts.length ? `<div class="txs">${S.contacts.map(c => `<div class="tx in contact"><span class="ico" aria-hidden="true">${esc(c.name.slice(0, 1).toUpperCase())}</span><span class="mid"><div class="note" data-noi18n>${esc(c.name)}</div><div class="meta">${c.ln ? `<span class="chip ln">LN</span>` : ''}${c.pubkey ? '<span class="chip ecash">NOSTR</span>' : ''}<span class="addr" data-noi18n>${esc(c.ln || (c.nostr.slice(0, 16) + '…')).replace(/([@.])/g, '$1<wbr>')}</span></div></span><span class="row cbtns"><button class="btn sm pink" data-act="payContact" data-id="${c.id}">Pay</button><button class="btn sm" data-act="contactEdit" data-id="${c.id}">Edit</button></span></div>`).join('')}</div>` : '<div class="empty-state"><b>NO CONTACTS</b>Add someone you pay often.</div>'}
    <button class="btn solid gold block" data-act="contactEdit">Add a contact</button>
    <div class="sub">Your ecash address</div>
    <p class="th" style="margin:0">Give this to friends so they can send you ecash over Nostr from NUTCADE or cashu.me.</p>
    <div class="code">${esc(myEcashAddress())}</div>
    <div class="btngrid"><button class="btn violet" data-act="copy" data-text="${esc(myEcashAddress())}">Copy</button><button class="btn violet" data-act="myAddrQR">Show QR</button></div>`);
}
function openContactEdit(id, prefill = {}) {
  const c = id ? contactById(id) : Object.assign({ name: '', ln: '', nostr: '' }, prefill);
  openSheet(id ? 'Edit contact' : 'Add a contact', `
    <div class="field"><label for="cName">Name</label><input id="cName" class="inp" data-noi18n maxlength="40" value="${esc(c.name)}" placeholder="Alex" autocomplete="off"></div>
    <div class="field"><label for="cLn">Lightning address (optional)</label><input id="cLn" class="inp" data-noi18n value="${esc(c.ln)}" placeholder="alex@wallet.com" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
    <div class="field"><label for="cNostr">Nostr address for ecash (optional)</label><input id="cNostr" class="inp" value="${esc(c.nostr)}" placeholder="npub1… or nprofile1…" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
    <button class="btn solid gold block" data-act="contactSave" data-id="${id || ''}">Save</button>
    ${id ? `<button class="btn block red" data-act="contactDel" data-id="${id}">Delete contact</button>` : prefill.nostr ? `<button class="btn block" data-act="zapOpen" data-pk="${esc(prefill.nostr)}">Zap them without saving</button>` : ''}<div id="sheetErr"></div>`);
}
function openPayContact(id) {
  const c = contactById(id); if (!c) return;
  if (needMint()) return;
  const m = activeMint();
  const canLn = c.ln && supports(m, 'melt', 'bolt11');
  openSheet(`Pay ${c.name}`, `
    <div class="tiny muted">From <b style="color:var(--ink)" data-noi18n>${esc(m.name)}</b> · ${money(balanceOf(m.url))} available</div>
    <div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="1000" autocomplete="off"></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="Lunch"></div>
    ${c.pubkey ? `<button class="btn solid pink block" data-act="contactEcash" data-id="${c.id}">Send ecash over Nostr</button><button class="btn block" data-act="zapContact" data-id="${c.id}">Zap <span data-noi18n>${esc(c.name)}</span></button>` : ''}
    ${canLn ? `<button class="btn ${c.pubkey ? '' : 'solid pink'} block" data-act="contactLn" data-id="${c.id}">Pay ${esc(c.ln)}</button>` : c.ln ? `<div class="tiny muted">${esc(m.name)} can't pay Lightning. Pick another mint to pay ${esc(c.ln)}.</div>` : ''}
    <div id="sheetErr"></div>`);
}

/* ---------- ecash inbox over Nostr (NIP-17), like cashu.me ---------- */
// dmWanted also covers contacts sending to your ecash address; turn it off in Settings → Privacy.

/* ---------- offline ---------- */
const isOffline = () => typeof navigator !== 'undefined' && navigator.onLine === false;
const netErr = e => /Can't reach|Failed to fetch|NetworkError|Load failed|network/i.test(String(e && e.message || e));
// Exact-match selection: proofs are powers of two, so taking the largest that fits finds an exact set whenever one exists.
function pickExact(proofs, amount) {
  const sorted = proofs.slice().sort((a, b) => num(b.amount) - num(a.amount));
  const out = []; let left = amount;
  for (const p of sorted) { const a = num(p.amount); if (a <= left) { out.push(p); left -= a; if (!left) break; } }
  return left === 0 ? out : null;
}
function offlineAmounts(proofs, amount) {
  const all = new Set([0]); for (const p of proofs) { for (const v of [...all]) all.add(v + num(p.amount)); if (all.size > 4000) break; }
  const vals = [...all].filter(v => v > 0).sort((a, b) => a - b);
  const below = vals.filter(v => v < amount).pop(), above = vals.find(v => v > amount);
  return [below, above].filter(Boolean);
}
function sendOffline(amount, note, url = S.active) {
  piggyGuard(amount);
  const hold = limitGate(amount); hold.release();   // (nothing in between: the coins and the line are written right here)
  const busy = new Set(S.ops.filter(o => o.mint === url).flatMap(o => o.inputs));   // coins a step still in flight may have spent
  const have = (S.proofs[url] || []).filter(p => !busy.has(p.secret));
  const pick = pickExact(have, amount);
  if (!pick) { const near = offlineAmounts(have, amount); throw new Error(`Offline, NUTCADE can only send amounts made of the exact coins you hold.${near.length ? ` Try ${near.map(money).join(' or ')}.` : ''}`); }
  const ids = new Set(pick.map(p => p.secret));
  S.proofs[url] = (S.proofs[url] || []).filter(p => !ids.has(p.secret));
  const token = L.getEncodedToken({ mint: url, proofs: pick, unit: 'sat' });
  save();
  return addTx(Object.assign({ type: 'out', method: 'ecash', amount, mint: url, note, status: 'pending', token, sent: plain(pick), offline: true }, hold.id ? { limId: hold.id } : {}));
}
function holdIncoming(token, note) {
  const meta = peekToken(token);
  if (S.txs.some(t => t.incoming === cleanToken(token))) throw new Error('This token is already saved and waiting.');
  return addTx({ type: 'in', method: 'ecash', amount: meta.amount, mint: meta.mint, note: note || meta.memo || '', status: 'pending', incoming: cleanToken(token), offline: true });
}
let claimingSaved = null;
function claimSaved() { if (!claimingSaved) claimingSaved = claimSavedNow().finally(() => { claimingSaved = null; }); return claimingSaved; }   // one at a time
async function claimSavedNow() {
  if (isOffline()) return 0;
  let n = 0;
  for (const t of S.txs.filter(t => t.status === 'pending' && t.incoming && t.offline && S.mints.find(m => m.url === t.mint))) {
    try { const nt = await receiveToken(t.incoming, t.note, { follow: { k: 'incoming', txId: t.id, reqId: t.reqId || null } }); incomingClaimed({ txId: t.id, reqId: t.reqId || null }, nt); n += nt.amount; }
    catch (e) {
      if (netErr(e) || e.blocked) continue;
      if (S.txs.some(x => x.fromIncoming === t.id)) { S.txs = S.txs.filter(x => x.id !== t.id); save(); continue; }   // claimed by this wallet (another device): its line is here already
      updTx(t.id, { status: 'failed', note: (t.note ? t.note + ' · ' : '') + 'already claimed by someone else' });
    }
  }
  dropClaimedIncoming();
  if (n) { sfx('coin'); refresh(); toast(`Back online: claimed ${money(n)} you saved offline`, 'lime'); }
  return n;
}
function netBanner() {
  let b = document.getElementById('netBanner');
  if (!isOffline()) { if (b) b.remove(); document.body.classList.remove('offline'); return; }
  if (!b) { b = document.createElement('div'); b.id = 'netBanner'; b.className = 'netbanner'; b.setAttribute('role', 'status'); document.body.appendChild(b); }
  b.textContent = "OFFLINE · You can still send exact amounts and save tokens to claim later";
  // push the page down by the banner's height, so it never sits on the header
  document.body.classList.add('offline'); requestAnimationFrame(() => { if (b.isConnected) document.body.style.setProperty('--netb', b.offsetHeight + 'px'); });
}
window.addEventListener('offline', () => { netBanner(); });
window.addEventListener('online', () => { netBanner(); claimSaved().catch(() => {}); backgroundTick().then(() => refresh()).catch(() => {}); });

/* Sweep ecash found under a different phrase into this wallet. */
async function sweepPhrase(phrase, urls, onStep) {
  const otherSeed = L.mnemonicToSeedSync(phrase);
  let total = 0; const fails = [];
  for (const url of urls) {
    try {
      if (!S.mints.find(m => m.url === url)) await addMint(url);
      const other = new L.Wallet(url, { unit: 'sat', bip39seed: otherSeed });
      await other.loadMint();
      let found = [];
      for (const k of other.keyChain.getKeysets().filter(k => k.unit === 'sat')) {
        onStep && onStep(`Scanning ${host(url)} · keyset ${k.id.slice(0, 8)}…`);
        const r = await other.batchRestore(300, undefined, 0, k.id);
        if (r.proofs && r.proofs.length) {
          const st = await other.checkProofsStates(r.proofs);
          found = found.concat(r.proofs.filter((p, i) => st[i] && st[i].state === 'UNSPENT'));
        }
      }
      if (found.length) total += await mintLock(url, async () => {
        const w = await getWallet(url);
        const { r: mine, op } = await journaled(url, 'receive', { amount: sum(found), note: 'Restored from another phrase' }, (cb, o) => rRecv(o, w, found, { onCountersReserved: cb }));
        addProofs(url, mine);
        addTx({ type: 'in', method: 'ecash', amount: sum(mine), fee: Math.max(0, sum(found) - sum(mine)), mint: url, note: 'Restored from another phrase' });
        closeOp(op); save();
        return sum(mine);
      });
    } catch (e) { fails.push(host(url)); }
  }
  return { total, fails };
}

/* Receive swap: claim at the foreign mint, then pay ourselves over Lightning into the active mint. */
async function swapIn(token, note) {
  token = cleanToken(token);
  const meta = peekToken(token);
  if (isBlocked(meta.mint)) throw blockedErr(meta.mint);
  const dest = activeMint();
  if (!dest || !supports(dest, 'mint', 'bolt11')) throw new Error('Your active mint must accept Lightning deposits to swap into it.');
  if (!S.mints.find(m => m.url === meta.mint)) await addMint(meta.mint);
  const fw = await getWallet(meta.mint), dw = await getWallet(dest.url);
  await mintLock(meta.mint, async () => {
  const { r: got, op } = await journaled(meta.mint, 'receive', { amount: meta.amount, note: note || `Swapped from ${host(meta.mint)}` }, (cb, o) => rRecv(o, fw, token, Object.assign(S.p2pk.length ? { privkey: p2pkPrivs() } : {}, { onCountersReserved: cb })));
  addProofs(meta.mint, got); closeOp(op); save();
  });
  const total = sum(S.proofs[meta.mint]);
  let amt = total - Math.max(2, Math.ceil(total * 0.02)), mq, melt, need;
  for (let i = 0; i < 4; i++) {
    if (amt < 1) throw new Error('This token is too small to cover Lightning fees for a swap. Claim it at its own mint instead.');
    { const e = quoteFitErr(dest.url, amt); if (e) { e.message += ` The token's ${money(total)} are in your balance at ${(S.mints.find(m => m.url === meta.mint) || {}).name || host(meta.mint)}.`; throw e; } }
    mq = await dw.createMintQuoteBolt11(amt);
    melt = await fw.createMeltQuoteBolt11(mq.request);
    const inFee = num(fw.getFeesForProofs(S.proofs[meta.mint]));
    need = num(melt.amount) + num(melt.fee_reserve) + inFee;
    if (need <= total) break;
    amt -= (need - total); mq = null;
  }
  if (!mq) throw new Error("Couldn't fit the swap fees into this token. Claim it at its own mint instead.");
  const tx = addTx({ type: 'in', method: 'ln', amount: amt, mint: dest.url, note: note || `Swapped from ${host(meta.mint)}`, status: 'pending', request: mq.request, quote: mq.quote });
  S.quotes.push({ kind: 'bolt11', quote: mq.quote, request: mq.request, amount: amt, mint: dest.url, txId: tx.id }); save();
  const prevActive = S.active; S.active = meta.mint;
  try { await payMelt('ln', melt, 0, `Swap to ${dest.name}`, mq.request, S.active, { noLimit: true }); }
  finally { S.active = prevActive; save(); }
  const q = S.quotes.find(x => x.quote === mq.quote);
  for (let i = 0; i < 20 && q; i++) { const r = await checkQuote(q).catch(() => 'waiting'); if (r === 'paid') break; await sleep(1000); }
  return { amt, from: meta.mint, to: dest.url };
}

function methodChips(m) {
  const has = (d, k) => supports(m, d, k);
  const c = [];
  if (has('mint', 'bolt11') || has('melt', 'bolt11')) c.push('<span class="chip ln">LIGHTNING</span>');
  if (has('mint', 'onchain') || has('melt', 'onchain')) c.push('<span class="chip ln" style="color:var(--lime)">ON-CHAIN</span>');
  c.push('<span class="chip ecash">ECASH</span>');
  return c.join('');
}

/* ---------- mint picker ---------- */
function openMintPicker() {
  const known = new Set(S.mints.map(m => m.url));
  const card = (u, name, blurb, extra = '') => `<div class="panel" style="gap:8px;background:var(--panel-2)" data-probe="${esc(u)}">
    <div class="row between" style="align-items:flex-start"><div style="min-width:0"><div class="row" style="gap:8px"><span class="dot off"></span><span class="uname" style="font-family:var(--f-display);font-size:10px;line-height:1.5;color:var(--gold)" data-name>${esc(name)}</span></div>
    <div class="tiny muted" data-noi18n style="overflow-wrap:anywhere">${esc(host(u))}</div></div>
    ${known.has(u) ? '<span class="chip ecash">ADDED</span>' : `<button class="btn sm lime" data-act="addMint" data-url="${esc(u)}">Add</button>`}</div>
    <div class="tiny">${esc(blurb)}</div><div class="row" style="gap:6px;flex-wrap:wrap" data-chips>${extra}</div></div>`;
  openSheet('Choose a mint', `
    <div class="notice cyan">A mint holds the Bitcoin behind your ecash. Only add mints you trust, and spread larger amounts across several.</div>
    ${S.mints.length ? `<div class="field"><label>Your mints</label><div class="txs">${S.mints.map(m => `<button class="tx in" data-act="useMint" data-url="${esc(m.url)}"><span class="ico">${m.url === S.active ? '★' : '·'}</span><span class="mid"><div class="note">${esc(m.name)}</div><div class="meta">${esc(host(m.url))}</div></span><span class="amt">${fmt(balanceOf(m.url))}</span></button>`).join('')}</div></div>` : ''}
    <div class="field"><label for="mintUrl">Mint address</label><div class="row inrow"><input id="mintUrl" class="inp" data-noi18n placeholder="https://mint.example.com" autocomplete="off" autocapitalize="off" spellcheck="false"><button class="btn solid gold" data-act="addMintUrl">Add</button></div></div>
    <div id="mintErr"></div>
    <div class="field"><label>Popular mints</label><div class="txs">${CURATED.map(c => card(c.url, c.name, c.blurb, c.test ? '<span class="chip failed">TEST SATS</span>' : '')).join('')}</div></div>
    <div class="field"><label>Discovered on Nostr</label><div id="nostrList" class="txs"><button class="btn block violet" data-act="discover">Find mints people recommend</button></div></div>`,
    body => { probeAll(body); return null; });
}
async function probeCard(el) {
  const u = el.dataset.probe; if (el.dataset.done) return; el.dataset.done = '1';
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 7000);
    const r = await fetch(u + '/v1/info', { signal: ctl.signal }); clearTimeout(t);
    const info = await r.json();
    el.querySelector('.dot').className = 'dot';
    if (info.name) el.querySelector('[data-name]').textContent = info.name;
    const n = info.nuts || {};
    const meth = d => ((n[d] && n[d].methods) || []).filter(m => m.unit === 'sat').map(m => m.method);
    const chips = [];
    if (meth('4').includes('bolt11') || meth('5').includes('bolt11')) chips.push('<span class="chip ln">LIGHTNING</span>');
    if (meth('4').includes('onchain') || meth('5').includes('onchain')) chips.push('<span class="chip ln" style="color:var(--lime)">ON-CHAIN</span>');
    el.querySelector('[data-chips]').insertAdjacentHTML('afterbegin', chips.join(''));
  } catch (e) {
    el.querySelector('[data-chips]').insertAdjacentHTML('afterbegin', '<span class="chip claimed">OFFLINE</span>');
  }
}
function probeAll(root) { root.querySelectorAll('[data-probe]').forEach(probeCard); }

function discoverMints(onUpdate) {
  const recs = new Map(); // url -> {pubs:Set, reviews:[]}
  const seenIds = new Set();
  const socks = []; let finished = false;
  const done = () => { if (finished) return; finished = true; socks.forEach(s => { try { s.close(); } catch (e) {} }); onUpdate(recs, true); };
  let open = 0;
  for (const r of RELAYS) {
    let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
    socks.push(ws); open++;
    ws.onopen = () => { ws.send(JSON.stringify(['REQ', 'nc1', { kinds: [38000], '#k': ['38172'], limit: 600 }])); ws.send(JSON.stringify(['REQ', 'nc2', { kinds: [38172], limit: 300 }])); };
    let eose = 0;
    ws.onmessage = ev => {
      let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m[0] === 'EVENT') {
        const e = m[2]; if (!e || seenIds.has(e.id)) return; seenIds.add(e.id);
        const urls = (e.tags || []).filter(t => t[0] === 'u' && /^https?:\/\//.test(t[1] || '')).map(t => normUrl(t[1]));
        for (const u of urls) {
          if (!recs.has(u)) recs.set(u, { pubs: new Set(), reviews: [], announced: false });
          const rec = recs.get(u);
          if (e.kind === 38000) { rec.pubs.add(e.pubkey); if (e.content && e.content.length < 280) rec.reviews.push(e.content); }
          else rec.announced = true;
        }
        onUpdate(recs, false);
      } else if (m[0] === 'EOSE') { if (++eose >= 2) { try { ws.close(); } catch (e) {} if (--open <= 0) done(); } }
    };
    ws.onerror = () => { if (--open <= 0) done(); };
  }
  if (!socks.length) done();
  setTimeout(done, 8000);
  return () => { finished = true; socks.forEach(s => { try { s.close(); } catch (e) {} }); };
}
function renderDiscovered(recs, final) {
  const el = $('#nostrList'); if (!el) return;
  const known = new Set(S.mints.map(m => m.url)); const curated = new Set(CURATED.map(c => c.url));
  const rows = [...recs.entries()].filter(([u, r]) => r.pubs.size > 0 && !curated.has(u)).sort((a, b) => b[1].pubs.size - a[1].pubs.size).slice(0, 25);
  if (!rows.length) { el.innerHTML = final ? '<div class="empty-state">No recommendations came back from Nostr relays. Add a mint by address instead.</div>' : busyHTML('LISTENING TO RELAYS'); return; }
  el.innerHTML = (final ? '' : busyHTML('LISTENING TO RELAYS')) + rows.map(([u, r]) => `<div class="panel" style="gap:8px;background:var(--panel-2)" data-probe="${esc(u)}">
    <div class="row between" style="align-items:flex-start"><div style="min-width:0"><div class="row" style="gap:8px"><span class="dot off"></span><span style="font-family:var(--f-display);font-size:10px;color:var(--gold)" data-name>${esc(host(u))}</span></div>
    <div class="tiny muted" data-noi18n style="overflow-wrap:anywhere">${esc(host(u))}</div></div>
    ${known.has(u) ? '<span class="chip ecash">ADDED</span>' : `<button class="btn sm lime" data-act="addMint" data-url="${esc(u)}">Add</button>`}</div>
    <div class="tiny" style="color:var(--pink)">★ ${r.pubs.size} recommendation${r.pubs.size === 1 ? '' : 's'}</div>
    ${r.reviews[0] ? `<div class="tiny muted">"${esc(r.reviews[0].slice(0, 140))}"</div>` : ''}<div class="row" style="gap:6px;flex-wrap:wrap" data-chips></div></div>`).join('');
  if (final) probeAll(el);
}

/* ---------- receive / send sheets ---------- */
function needSeed() { if (!S.seed) { closeSheet(); tab = 'wallet'; render(); toast('Set up your recovery phrase first', 'gold'); return true; } return false; }
function needMint() { if (!S.seed) { closeSheet(); tab = 'wallet'; render(); toast('Set up your recovery phrase first', 'gold'); return true; } if (!activeMint()) { openMintPicker(); return true; } return false; }
function methodSeg(dir, cur) {
  const m = activeMint();
  const opts = [['ecash', 'ECASH'], ['ln', 'LIGHTNING'], ['onchain', 'ON-CHAIN']];
  return `<div class="seg three" role="group" aria-label="Method">${opts.map(([k, l]) => `<button data-act="${dir}Method" data-m="${k}" aria-pressed="${cur === k}">${l}</button>`).join('')}</div>`;
}
function openReceive(method = 'ln') {
  if (method === 'ecash' ? needSeed() : needMint()) return;
  const m = activeMint();
  if (!m && method !== 'ecash') return openMintPicker();
  let inner = '';
  if (method === 'ecash') inner = `
    <div class="field"><div class="row between"><label for="tokIn">Paste ecash token</label><button class="btn sm violet" data-act="scan" data-hint="Point at an ecash token."><svg class="ico-scan" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M1 1h5v1H2v4H1zm9 0h5v5h-1V2h-4zM1 10h1v4h4v1H1zm13 0h1v5h-5v-1h4zM4 4h3v3H4zm5 0h3v3H9zM4 9h3v3H4zm5 0h1v1H9zm2 0h1v1h-1zm-2 2h1v1H9zm2 1h1v1h-1z"/></svg>Scan</button></div><textarea id="tokIn" class="inp" placeholder="cashuB…" autocomplete="off" spellcheck="false" data-input="tokPeek"></textarea></div>
    <div id="tokPeek"></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="Lunch money from Sam"></div>
    <button class="btn solid lime block" data-act="doReceiveToken">Claim ecash</button>
    ${window.Chiptune && window.Chiptune.canListen() ? '<button class="btn block violet" data-act="ctListen">Listen for a token sent as sound</button>' : ''}
    ${S.seed ? '<button class="btn block" data-act="reqOpen">Request a payment</button><button class="btn block" data-act="splitOpen">Split a bill</button><button class="linkbtn tiny" data-act="myAddrQR" style="justify-self:start">Show my ecash address (for contacts)</button>' : ''}`;
  else if (method === 'ln') inner = supports(m, 'mint', 'bolt11') ? `
    ${S.prefs.npc ? `<div class="panel lnaddr"><div class="row between"><span class="label">Your Lightning address</span><button class="linkbtn tiny" data-act="lnAddr">Manage</button></div><div class="code addr">${esc(npcAddress())}</div><div class="row"><button class="btn sm" data-act="copy" data-text="${esc(npcAddress())}">Copy</button><button class="btn sm violet" data-act="lnAddrQR">Show QR</button></div><div class="tiny muted">Payments to it land here whenever NUTCADE is open. Or make a one-time invoice below.</div></div>`
      : `<button class="linkbtn tiny" data-act="lnAddr" style="justify-self:start">＠ Get your own Lightning address</button>`}
    <div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="2100" autocomplete="off"></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="Arcade fund"></div>
    <button class="btn solid lime block" data-act="doLnInvoice">Create invoice</button>` : notSupported('Lightning deposits');
  else inner = supports(m, 'mint', 'onchain') ? `
    <div class="notice">On-chain deposits need ${esc(methodInfo(m, 'mint', 'onchain')?.confirmations || 'a few')} confirmation(s). NUTCADE watches the address while it's open.${minMax(methodInfo(m, 'mint', 'onchain'))}</div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="Savings top-up"></div>
    <button class="btn solid lime block" data-act="doOnchainAddr">Get Bitcoin address</button>` : notSupported('On-chain deposits');
  openSheet('Receive', `${methodSeg('recv', method)}${m && method !== 'ecash' ? `<div class="tiny muted">Into <b style="color:var(--ink)" data-noi18n>${esc(m.name)}</b></div>${blockedNotice(m.url)}` : ''}${inner}<div id="sheetErr"></div>`);
}
function minMax(mi) { if (!mi) return ''; const a = []; if (mi.min) a.push(`min ${fmt(mi.min)}`); if (mi.max) a.push(`max ${fmt(mi.max)}`); return a.length ? ` <span>Limits: ${a.join(', ')} SAT.</span>` : ''; }   // its own sentence, so it's translated on its own
function notSupported(what) { return `<div class="notice red">${what} aren't offered by ${esc(activeMint().name)}. Pick a mint that lists them in the mint picker.</div><button class="btn block gold" data-act="pickMint">Open mint picker</button>`; }

function openSend(method = 'ecash') {
  if (needMint()) return;
  const m = activeMint(); let inner = '';
  if (method === 'ecash') inner = `
    <div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="500" autocomplete="off"></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="High score bet with Alex"></div>
    ${giftFields()}
    <button class="btn solid pink block" data-act="doSendEcash">Create token</button>
    <button class="linkbtn tiny" data-act="reqPayOpen" style="justify-self:start">Pay a payment request instead</button>`;
  else if (method === 'ln') inner = supports(m, 'melt', 'bolt11') ? `
    <div class="field"><div class="row between"><label for="destIn">Invoice or Lightning address</label><button class="btn sm violet" data-act="scan" data-hint="Point at a Lightning invoice or address."><svg class="ico-scan" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M1 1h5v1H2v4H1zm9 0h5v5h-1V2h-4zM1 10h1v4h4v1H1zm13 0h1v5h-5v-1h4zM4 4h3v3H4zm5 0h3v3H9zM4 9h3v3H4zm5 0h1v1H9zm2 0h1v1h-1zm-2 2h1v1H9zm2 1h1v1h-1z"/></svg>Scan</button></div><textarea id="destIn" class="inp" placeholder="lnbc… or name@domain.com" autocomplete="off" spellcheck="false"></textarea></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="Coffee"></div>
    <button class="btn solid pink block" data-act="doMeltQuote" data-k="ln">Get quote</button>` : notSupported('Lightning payments');
  else inner = supports(m, 'melt', 'onchain') ? `
    <div class="field"><div class="row between"><label for="destIn">Bitcoin address</label><button class="btn sm violet" data-act="scan" data-hint="Point at a Bitcoin address."><svg class="ico-scan" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M1 1h5v1H2v4H1zm9 0h5v5h-1V2h-4zM1 10h1v4h4v1H1zm13 0h1v5h-5v-1h4zM4 4h3v3H4zm5 0h3v3H9zM4 9h3v3H4zm5 0h1v1H9zm2 0h1v1h-1zm-2 2h1v1H9zm2 1h1v1h-1z"/></svg>Scan</button></div><input id="destIn" class="inp" placeholder="bc1q…" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
    <div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="50000" autocomplete="off"></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="Move to cold storage"></div>
    <button class="btn solid pink block" data-act="doMeltQuote" data-k="onchain">Get fee options</button>${minMax(methodInfo(m, 'melt', 'onchain')) ? `<div class="tiny muted">${minMax(methodInfo(m, 'melt', 'onchain'))}</div>` : ''}` : notSupported('On-chain withdrawals');
  openSheet('Send', `${contactChips()}${methodSeg('send', method)}<div class="tiny muted">From <b style="color:var(--ink)" data-noi18n>${esc(m.name)}</b> · ${money(balanceOf(m.url))} available</div>${inner}<div id="sheetErr"></div>`);
}
const val = id => ($('#' + id) || {}).value || '';
const amt = () => { const n = satsOf('amtIn'); if (!n || n <= 0) throw new Error('Enter an amount in sats, like 1000.'); return n; };
function showErr(e) { sfx('err'); const el = $('#sheetErr'); if (el) el.innerHTML = errHTML(e); else toast(e.message || String(e), 'red'); }
async function run(btn, label, fn) {
  const old = btn ? btn.innerHTML : ''; if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner">${label}</span>`; }
  // (a step that moved sats and then failed, say a treasure hunt no relay took: the screen behind is redrawn at once)
  const was = () => S.txs.length + ':' + totalBalance() + ':' + (S.txs[0] || {}).id, before = was();
  try { return await fn(); } catch (e) { if (e && e.piggy) { piggyBreak(e.piggy, () => run(btn, label, fn)); return; } if (e && e.limit) { limitAsk(e, () => run(btn, label, fn)); return; } showErr(friendly(e, S.active)); if (was() !== before) refresh(); }
  finally { if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = old; } }
}

const PAID_COLLECTING = 'This invoice is already paid. NUTCADE is collecting the ecash from the mint, and it shows here as soon as it is in.';
const quotePaid = q => !q || q.state === 'PAID' || q.state === 'ISSUED';   // no quote left, or the mint says paid: never offer it for paying
function showInvoice(tx) {
  const q = S.quotes.find(x => x.quote === tx.quote), st = (txById(tx.id) || {}).status;
  if (st === 'expired') { setBody(`<div class="notice">This invoice has expired. Nothing was received.</div><button class="btn solid gold block" data-act="close">OK</button>`); return; }
  if (quotePaid(q) || st !== 'pending') {
    setBody(`<div class="notice">${PAID_COLLECTING}</div><div class="row" style="justify-content:center"><span class="spinner" id="payState">COLLECTING</span></div>`, () => {
      if (!q) return null; let alive = true;
      (async () => { while (alive) { const r = await checkQuote(q).catch(() => null); if (r === 'paid') { if (alive) showDone('in', (txById(tx.id) || tx).amount, 'Lightning'); return; } await sleep(3000); } })();
      return () => { alive = false; };
    });
    return;
  }
  setBody(`<div class="label" style="text-align:center">Pay this invoice</div>
    <div class="credit-num" style="text-align:center;font-size:26px">${fmt(tx.amount)}<small>${unitTag()}</small></div>
    ${qrBlock('lightning:' + tx.request.toUpperCase(), 'Lightning invoice QR')}
    <div class="code">${esc(tx.request)}</div>
    <div class="row"><button class="btn block" data-act="copy" data-text="${esc(tx.request)}">Copy invoice</button></div>
    <div class="row" style="justify-content:center"><span class="spinner" id="payState">WAITING FOR PAYMENT</span></div>`, () => {
    if (!q) return null;
    let alive = true;
    const onPaid = e => { if (e.detail === q.quote && alive) { alive = false; showDone('in', tx.amount, 'Lightning'); } };
    document.addEventListener('nutcade:paid', onPaid);
    liveSync();
    (async () => { while (alive) { try { const r = await checkQuote(q); if (r === 'paid') { if (alive) { alive = false; showDone('in', tx.amount, 'Lightning'); } return; } if (r === 'expired') { const s = $('#payState'); if (s) s.textContent = 'INVOICE EXPIRED'; return; } } catch (e) { } await sleep(3000); } })();
    return () => { alive = false; document.removeEventListener('nutcade:paid', onPaid); };
  });
}
function showAddress(tx) {
  const q = S.quotes.find(x => x.quote === tx.quote);
  setBody(`<div class="label" style="text-align:center">Send Bitcoin to</div>
    ${qrBlock('bitcoin:' + tx.request, 'Bitcoin address QR')}
    <div class="code">${esc(tx.request)}</div>
    <button class="btn block" data-act="copy" data-text="${esc(tx.request)}">Copy address</button>
    <div class="notice">Ecash appears after the deposit confirms. You can close this; NUTCADE keeps checking while it's open.</div>
    <div class="row" style="justify-content:center"><span class="spinner" id="payState">WATCHING THE CHAIN</span></div>`, () => {
    if (!q) return null; let alive = true;
    (async () => { while (alive) { try { const r = await checkQuote(q); if (r === 'paid') { if (alive) showDone('in', txById(tx.id).amount, 'On-chain'); return; } } catch (e) { } await sleep(15000); } })();
    return () => { alive = false; };
  });
}
function showToken(tx, sentTo) {
  setBody(`<div class="label" style="text-align:center">${tx.lockUntil ? 'Locked gift' : 'Ecash token'}</div>
    <div class="credit-num" style="text-align:center;font-size:26px">${fmt(tx.amount)}<small>${unitTag()}</small></div>
    ${qrBlock(tx.token, 'Ecash token QR')}
    <div class="code">${esc(tx.token)}</div>
    <button class="btn solid pink block" data-act="copy" data-text="${esc(tx.token)}">Copy token</button>
    ${nfcOK() ? `<button class="btn block violet" data-act="nfcWrite" data-text="${esc(tx.token)}">Write to NFC card</button>` : ''}
    ${ctBtn(tx.token, 'Play as sound', 'btn block violet')}
    ${tx.lockUntil ? `<div class="notice cyan">Only ${esc(tx.giftTo || 'the person you picked')} can claim this. ${sentTo ? 'It was also sent to them over Nostr. ' : ''}If they haven't by ${fmtDay(tx.lockUntil)}, NUTCADE takes it back for you.</div>`
    : '<div class="notice cyan">Anyone holding this token can claim it. It stays in your notes until they do, and you can reclaim it if they never claim it.</div>'}`);
}
let lastContact = null;
function showDone(dir, amount, how, extra = '') {
  sfx('start'); celebrate(dir, amount);
  setBody(`<div style="text-align:center;display:grid;gap:14px;padding:10px 0">
    <div style="font-family:var(--f-display);font-size:18px;color:${dir === 'in' ? 'var(--lime)' : 'var(--pink)'}">${dir === 'in' ? '1UP!' : 'SENT!'}</div>
    <div class="credit-num" style="font-size:30px">${dir === 'in' ? '+' : '-'}${fmt(amount)}<small>${unitTag()}</small></div>
    <div class="muted">${esc(how)}</div>
    ${extra}<button class="btn solid gold block" data-act="close">Continue</button></div>`);
  refresh();
}
function showMeltQuote(kind, mq, dest, note) {
  const amount = num(mq.amount);
  const head = $('#layer .sheet-head h3'); if (head) { head.textContent = tr('Pay'); head.closest('.sheet').setAttribute('aria-label', tr('Pay')); }
  const opts = kind === 'onchain' ? (mq.fee_options || []) : [];
  const worst = kind === 'ln' ? costShown(S.active, amount, mq.fee_reserve) : meltCost(S.active, amount, Math.max(0, ...(mq.fee_options || []).map(o => num(o.fee_reserve))));
  const feeRow = kind === 'ln' ? costRows(worst) : worst.mintFee ? `<dt>Mint fee, at most</dt><dd>${money(worst.mintFee)}</dd>` : '';
  setBody(`<dl class="kv"><dt>Pay</dt><dd>${money(amount)}</dd>${feeRow}<dt>To</dt><dd class="tiny">${esc(dest.length > 40 ? dest.slice(0, 18) + '…' + dest.slice(-14) : dest)}</dd>${note ? `<dt>Note</dt><dd ${AUTO_NOTE.test(note) ? '' : 'data-noi18n'}>${esc(note)}</dd>` : ''}</dl>
    ${opts.length ? `<div class="field"><label>Fee speed</label><div class="txs">${opts.map((o, i) => `<label class="tx out" style="cursor:pointer"><span class="ico"><input type="radio" name="fee" value="${o.fee_index}" ${i === 0 ? 'checked' : ''} style="accent-color:var(--pink)"></span><span class="mid"><div class="note">${esc(tr(`~${o.estimated_blocks} block${o.estimated_blocks === 1 ? '' : 's'}`))}</div><div class="meta">≈ ${Math.round(o.estimated_blocks * 10)} min</div></span><span class="amt">${fmt(o.fee_reserve)}</span></label>`).join('')}</div></div>` : ''}
    ${kind === 'ln' ? changeNote(S.active) : ''}
    ${kind === 'ln' && balanceOf(S.active) < worst.total ? `<div class="notice">${esc((activeMint() || {}).name || 'This mint')} holds ${money(balanceOf(S.active))}, not enough on its own.${S.mints.filter(m => balanceOf(m.url) > 0).length > 1 ? ' You can split the payment across your mints.' : ''}</div>` : ''}
    <button class="btn solid pink block" id="payBtn">Pay ${money(amount)}</button>
    ${kind === 'ln' && S.mints.filter(m => balanceOf(m.url) > 0).length > 1 ? `<button class="btn block violet" id="mppBtn">Pay from several mints</button>` : ''}<div id="sheetErr"></div>`, body => {
    const mb = body.querySelector('#mppBtn'); if (mb) mb.onclick = () => openMultinut(mq.request, amount, dest, note);
    body.querySelector('#payBtn').onclick = e => run(e.currentTarget, 'PAYING', async () => {
      const fi = kind === 'onchain' ? parseInt((body.querySelector('input[name=fee]:checked') || {}).value || '0', 10) : 0;
      const zx = zapByQuote.get(mq.quote);
      const tx = await payMelt(kind, mq, fi, note, dest, S.active, zx || {});
      const isAddr = kind === 'ln' && /^[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i.test(dest);
      const ct = isAddr && (S.contacts.find(c => c.ln === dest.toLowerCase()) || null);
      if (ct) updTx(tx.id, { contactId: ct.id, contactName: ct.name });
      lastContact = null;
      const save = isAddr && !ct ? `<button class="btn block violet" data-act="contactFrom" data-ln="${esc(dest.toLowerCase())}">Save ${esc(dest)} as a contact</button>` : '';
      if (tx.status === 'done') showDone('out', amount, kind === 'ln' ? (zx ? note : ct ? `Lightning to ${ct.name}` : 'Lightning') : 'On-chain' + (tx.outpoint ? ' · ' + tx.outpoint.slice(0, 12) + '…' : ''), save);
      else { setBody(`<div class="notice">Payment is in flight. NUTCADE will settle it when the mint confirms. Check the transaction in your notes.</div><button class="btn block gold" data-act="close">OK</button>`); refresh(); }
    });
    return null;
  });
}

function openTx(id) {
  const t = txById(id); if (!t) return;
  const method = { ln: 'Lightning', ecash: 'Ecash', onchain: 'On-chain', fee: 'Mint fee' }[t.method];
  const mint = S.mints.find(m => m.url === t.mint);
  const moved = !(t.status === 'failed' || t.status === 'expired'), head = t.method === 'fee' ? t.fee : t.amount;
  let extra = '';
  if (t.status === 'failed' && t.type === 'out') extra = `<div class="notice">${t.cost ? `This payment didn't go through. The ecash came back, except ${money(t.cost)} the mint kept as its fee for getting it ready.` : "This payment didn't go through. Nothing left your wallet."}</div>`;
  else if (t.method === 'fee') extra = `<div class="notice">The mint kept this fee when a payment didn't go through. The rest of the ecash came back to your wallet.</div>`;
  else if (t.status === 'pending' && t.incoming && isBlocked(t.mint)) extra = `${errHTML(blockedErr(t.mint))}<div class="tiny muted">This ecash waits here. Unblock the mint to claim it.</div>`;
  else if (t.status === 'pending' && t.incoming && t.refused) extra = `<div class="notice">This ecash was refused while its mint was blocked. The mint is unblocked now, so you can claim it.</div><button class="btn block lime" data-act="claimIncoming" data-id="${t.id}">Claim now</button>`;
  else if (t.status === 'pending' && t.incoming && t.offline) extra = `<div class="notice">Saved while offline. NUTCADE claims it automatically when the mint can be reached.</div><button class="btn block lime" data-act="claimIncoming" data-id="${t.id}">Claim now</button>`;
  else if (t.status === 'pending' && t.incoming) extra = `<div class="notice">This ecash came from ${esc(host(t.mint))}, a mint you don't use yet. Claiming adds that mint and trusts it with ${money(t.amount)}.</div><button class="btn block lime" data-act="claimIncoming" data-id="${t.id}">Trust mint &amp; claim</button>`;
  else if (t.status === 'pending' && t.method === 'ecash' && t.token) extra = `${t.lockUntil ? `<div class="notice cyan">Locked to ${esc(t.giftTo || 'one person')}. ${Date.now() < t.lockUntil ? `If they haven't claimed it by ${fmtDay(t.lockUntil)}, it comes back to you automatically.` : 'The lock has run out, so you can take it back.'}</div>` : ''}${qrBlock(t.token, 'Ecash token QR')}<div class="code">${esc(t.token)}</div>
    <div class="row" style="flex-wrap:wrap"><button class="btn sm pink" data-act="copy" data-text="${esc(t.token)}">Copy token</button>${nfcOK() ? `<button class="btn sm violet" data-act="nfcWrite" data-text="${esc(t.token)}">Write to NFC</button>` : ''}${ctBtn(t.token)}<button class="btn sm" data-act="checkClaim" data-id="${t.id}">Check claimed</button>${t.lockUntil ? (Date.now() < t.lockUntil ? `<button class="btn sm" disabled>Back on ${fmtDay(t.lockUntil)}</button>` : `<button class="btn sm gold" data-act="giftTake" data-id="${t.id}">Take it back</button>`) : `<button class="btn sm gold" data-act="reclaim" data-id="${t.id}">Reclaim</button>`}</div>`;
  else if (t.status === 'pending' && t.type === 'in' && t.method === 'ln') extra = quotePaid(S.quotes.find(x => x.quote === t.quote)) ? `<div class="notice">${PAID_COLLECTING}</div>` : `<button class="btn block lime" data-act="resumeInvoice" data-id="${t.id}">Show invoice</button>`;
  else if (t.status === 'pending' && t.type === 'in' && t.method === 'onchain') extra = `<div class="row" style="flex-wrap:wrap"><button class="btn sm lime" data-act="resumeAddr" data-id="${t.id}">Show address</button><button class="btn sm red" data-act="stopWatch" data-id="${t.id}">Stop watching</button></div>`;
  else if (t.status === 'pending' && t.type === 'out') extra = `<button class="btn block violet" data-act="reconcileTx" data-id="${t.id}">Check payment</button>`;
  else if (t.changePending && t.type === 'out') extra = `<div class="notice">This payment went through. Its change (the unused fee reserve) hasn't come back from the mint yet, so the fee shown is the most it can be. NUTCADE keeps trying, and the fee drops when the change is back.</div><button class="btn block violet" data-act="reconcileTx" data-id="${t.id}">Try now</button>`;
  openSheet(t.method === 'fee' ? 'Mint fee' : t.type === 'in' ? 'Received' : 'Sent', `
    <div class="credit-num${moved ? '' : ' void'}" style="font-size:28px;color:${t.type === 'in' ? 'var(--lime)' : 'var(--pink)'}">${moved ? (t.type === 'in' ? '+' : '-') : ''}${head ? fmt(head) : '…'}<small>${unitTag()}</small></div>
    <div class="field"><label for="noteEdit">Note</label><textarea id="noteEdit" class="inp" maxlength="500" placeholder="What was this for?">${esc(noteText(t.note))}</textarea></div>
    <button class="btn solid gold block" data-act="saveNote" data-id="${t.id}">Save note</button>
    <dl class="kv"><dt>Method</dt><dd>${method}</dd><dt>Status</dt><dd>${esc(TX_STATUS[t.status] || t.status)}</dd>${t.fee && t.method !== 'fee' ? `<dt>Fee</dt><dd>${money(t.fee)}</dd>` : ''}
    <dt>Mint</dt><dd data-noi18n>${esc(mint ? mint.name : host(t.mint))}</dd><dt>When</dt><dd data-noi18n>${fmtDate(t.ts, true)}</dd>
    ${t.outpoint ? `<dt>Tx</dt><dd class="tiny">${esc(t.outpoint)}</dd>` : ''}${t.nwcName ? `<dt>App</dt><dd data-noi18n>${esc(t.nwcName)}</dd>` : ''}${t.lnurlw ? `<dt>Voucher</dt><dd data-noi18n>${esc(t.lnurlw)}</dd>` : ''}${t.roundup ? `<dt>Round-up</dt><dd>+${money(t.roundup)} to piggy bank</dd>` : ''}${t.lockUntil ? `<dt>Locked to</dt><dd ${t.giftTo && !t.hunt ? 'data-noi18n' : ''}>${esc(t.giftTo || 'one person')}</dd>` : ''}${t.type === 'out' && t.method !== 'ecash' && t.request ? `<dt>To</dt><dd class="tiny">${esc(t.request.slice(0, 24))}…</dd>` : ''}</dl>
    ${extra}<div id="sheetErr"></div>`);
}


/* ---------- payment request sheets ---------- */
function openRequest() {
  if (needSeed()) return;
  const recent = S.requests.slice(0, 5);
  openSheet('Request a payment', `
    <p style="margin:0">Make a payment request that any Cashu wallet (like cashu.me) can pay. The ecash comes straight to this wallet over Nostr, even if you're not looking at this screen.</p>
    <div class="field"><label for="amtIn">Amount (SAT, optional)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="Any amount" autocomplete="off"></div>
    <div class="field"><label for="memoIn">What it's for (the payer sees this)</label><input id="memoIn" class="inp" maxlength="120" placeholder="Pizza night"></div>
    ${S.mints.length ? `<label class="toggle" for="onlyMine"><span><span class="tl">Only from my mints</span><span class="th">The payer must use one of the mints you use, so you never get ecash from a mint you don't trust.</span></span><input id="onlyMine" type="checkbox" checked></label>` : ''}
    <button class="btn solid lime block" data-act="reqCreate">Create request</button>
    <button class="btn block pink" data-act="splitOpen">Split a bill with friends instead</button>
    ${recent.length ? `<div class="sub">Recent requests</div><div class="txs">${recent.map(r => `<button class="tx in" data-act="reqShow" data-id="${r.id}"><span class="ico" aria-hidden="true">?</span><span class="mid"><div class="note ${r.memo ? '' : 'empty'}">${esc(r.memo || 'No description')}</div><div class="meta"><span>${timeAgo(r.created)}</span>${r.paid.length ? `<span class="chip claimed">PAID ×${r.paid.length}</span>` : ''}</div></span><span class="amt">${r.amount ? fmt(r.amount) : esc(tr('ANY'))}</span></button>`).join('')}</div>` : ''}
    <div id="sheetErr"></div>`);
}
function showRequest(r) {
  const paidBefore = r.paid.length;
  openSheet('Payment request', `
    <div class="label" style="text-align:center">${r.memo ? `<span data-noi18n>${esc(r.memo)}</span>` : 'Pay me'}</div>
    <div class="credit-num" style="text-align:center;font-size:26px">${r.amount ? fmt(r.amount) : esc(tr('ANY'))}<small>${unitTag()}</small></div>
    ${qrBlock(r.encoded, 'Payment request QR')}
    <div class="code">${esc(r.encoded)}</div>
    <button class="btn solid lime block" data-act="copy" data-text="${esc(r.encoded)}">Copy request</button>${nfcBtn('nfcWrite', 'Write to NFC card', `data-text="${esc(r.encoded)}"`, 'btn block violet')}${ctBtn(r.encoded, 'Play as sound', 'btn block violet')}
    <div class="row" style="justify-content:center"><span class="spinner" id="payState">WAITING FOR PAYMENT</span></div>
    <div class="tiny muted">Payments arrive over Nostr while NUTCADE is open, and the ones sent while it's closed arrive the next time you open it (for 30 days).</div>`, () => {
    dmListen();
    const on = e => { if (e.detail && e.detail.id === r.id) showDone('in', e.detail.amount, 'Payment request'); };
    document.addEventListener('nutcade:request', on);
    return () => document.removeEventListener('nutcade:request', on);
  });
}
function openPayRequest(enc) {
  let pr; try { pr = decodeRequest(enc); } catch (e) { closeSheet(); sfx('err'); toast(e.message, 'red'); return; }
  const amount = pr.amount ? num(pr.amount) : 0;
  const allowed = pr.mints && pr.mints.length ? pr.mints.map(normUrl) : null;
  const usable = S.mints.filter(m => (!allowed || allowed.includes(m.url)) && balanceOf(m.url) > 0);
  const tr = (pr.transport || []).find(t => t.type === 'nostr' || t.type === 'post');
  const pick = usable.find(m => m.url === S.active) || usable.slice().sort((a, b) => balanceOf(b.url) - balanceOf(a.url))[0];
  let body = `<div class="label">${pr.description ? `<span data-noi18n>${esc(pr.description)}</span>` : 'Payment request'}</div>
    ${amount ? `<div class="credit-num" style="font-size:26px">${fmt(amount)}<small>${unitTag()}</small></div>` : `<div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="1000" autocomplete="off"></div>`}`;
  if (pr.unit && pr.unit !== 'sat') body += `<div class="notice red">This request asks for ${esc(pr.unit)}. NUTCADE pays in sats only.</div>`;
  else if (allowed && allowed.every(isBlocked)) body += errHTML(blockedErr(allowed[0], 'request'));
  else if (!usable.length) body += `<div class="notice red">${allowed ? `This request only accepts ecash from ${allowed.map(u => esc(host(u))).join(', ')}, and you don't hold any there.` : "You don't have any sats to pay with yet."}</div>${allowed ? `<button class="btn block gold" data-act="addMint" data-url="${esc(allowed[0])}">Add ${esc(host(allowed[0]))}</button>` : ''}`;
  else body += `<div class="field"><label for="reqMint">Pay from</label><select id="reqMint" class="inp">${usable.map(m => `<option value="${esc(m.url)}" ${m === pick ? 'selected' : ''}>${esc(m.name)} · ${fmt(balanceOf(m.url))}</option>`).join('')}</select></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" value="${esc(pr.description || '')}"></div>
    ${tr ? `<div class="tiny muted">Sent ${tr.type === 'nostr' ? 'privately over Nostr' : 'to ' + esc(host(tr.target))}${pr.nut10 && pr.nut10.kind === 'P2PK' ? ', locked to the requester\'s key' : ''}.</div>` : '<div class="notice">This request has no delivery address, so NUTCADE will make a token for you to send yourself.</div>'}
    <button class="btn solid pink block" data-act="payReq" data-req="${esc(enc)}">Pay</button>`;
  openSheet('Pay request', body + '<div id="sheetErr"></div>');
}

/* ---------- Lightning address sheet ---------- */
function openLnAddr() {
  if (needSeed()) return;
  const lnMints = S.mints.filter(m => supports(m, 'mint', 'bolt11'));
  const cur = S.prefs.npc ? S.prefs.npcMint : (activeMint() && supports(activeMint(), 'mint', 'bolt11') ? S.active : (lnMints[0] || {}).url);
  const pick = lnMints.length ? `<div class="field"><label for="npcMint">Mint that receives the payments</label><select id="npcMint" class="inp">${lnMints.map(m => `<option data-noi18n value="${esc(m.url)}" ${m.url === cur ? 'selected' : ''}>${esc(m.name)}</option>`).join('')}</select></div>` : '';
  if (!S.prefs.npc) return openSheet('Lightning address', `
    <p style="margin:0">Get a permanent Lightning address that anyone can pay from any Lightning wallet, like an email address for sats.</p>
    <div class="code addr">${esc(npcAddress())}</div>
    <ul class="gate-list">
      <li><b>How it works.</b> npub.cash, a free service from the Cashu community, turns each payment into ecash at your mint. NUTCADE claims it whenever it's open.</li>
      <li><b>Your key.</b> The address comes from your 12 words, so restoring them (here or in cashu.me) brings it back.</li>
      <li><b>Privacy.</b> npub.cash sees the amounts and times of payments to this address, but not the rest of your wallet.</li>
    </ul>
    ${pick || '<div class="notice">Add a mint that takes Lightning deposits first.</div>'}
    ${lnMints.length ? '<button class="btn solid gold block" data-act="lnAddrOn">Turn on my Lightning address</button>' : '<button class="btn block gold" data-act="pickMint">Add a mint</button>'}<div id="sheetErr"></div>`);
  const name = (S.mints.find(m => m.url === S.prefs.npcMint) || {}).name || host(S.prefs.npcMint || '');
  const waiting = S.quotes.filter(q => q.npc).length;
  openSheet('Lightning address', `
    ${qrBlock('lightning:' + npcAddress(), 'Lightning address QR')}
    <div class="code addr">${esc(npcAddress())}</div>
    <button class="btn solid gold block" data-act="copy" data-text="${esc(npcAddress())}">Copy address</button>
    <dl class="kv"><dt>Mint</dt><dd data-noi18n>${esc(name)}</dd><dt>Checked</dt><dd>${npcWs && npcWs.readyState === 1 ? 'Live' : 'Every 30 s'}</dd>${waiting ? `<dt>Claiming</dt><dd>${waiting} payment${waiting === 1 ? '' : 's'}</dd>` : ''}</dl>
    ${pick}${lnMints.length > 1 ? '<button class="btn block" data-act="lnAddrMint">Use this mint</button>' : ''}
    <div class="btngrid"><button class="btn violet" data-act="lnAddrSync">Check for payments</button><button class="btn red" data-act="lnAddrOff">Turn off</button></div>
    <div class="tiny muted">Turning it off only stops this device checking. Payments sent meanwhile wait at npub.cash and arrive when you turn it back on.</div><div id="sheetErr"></div>`);
}

/* ---------- support / donations ---------- */
const DONATE = { address: 'keywest@strike.me', lnurl: 'LNURL1DP68GURN8GHJ7UM5WF5KKEFWD4JJ7TNHV4KXCTTTDEHHWM30D3H82UNVWQHKKETEWAJHXAQ6MZ0AF' };
function openSupport() {
  const m = activeMint();
  const canTip = m && supports(m, 'melt', 'bolt11');
  openSheet('Support NUTCADE', `
    <p style="margin:0">NUTCADE is free and open source, and it stays that way. If you enjoy it and want to support its development, you can send a few sats over Lightning. It's entirely optional and changes nothing about how the wallet or the arcade work.</p>
    <div class="panel" style="background:var(--panel-2)">
      <span class="h2" style="color:var(--pink)">Tip from this wallet</span>
      ${canTip ? `<div class="seg three" role="group" aria-label="Tip amount">${[21, 210, 2100].map(a => `<button data-act="tipPreset" data-a="${a}" aria-pressed="${a === 210}">${fmt(a)}</button>`).join('')}</div>
      <div class="field"><label for="tipAmt">Amount (SAT)</label><input id="tipAmt" class="inp amount" inputmode="numeric" value="210" autocomplete="off"></div>
      <button class="btn solid pink block" data-act="tipQuote">${HEART}<span>Tip from ${esc(m.name)}</span></button>
      <div class="tiny muted">You'll see the fee and confirm before anything is sent. ${money(balanceOf(m.url))} available.</div>`
      : `<div class="tiny muted">${m ? `${esc(m.name)} can't pay Lightning, so use the address below from another wallet.` : 'Add a mint and some sats to tip from NUTCADE, or use the address below from any Lightning wallet.'}</div>`}
    </div>
    <div class="field"><label>Lightning address</label><div class="row"><div class="code" style="flex:1;font-size:16px">${DONATE.address}</div><button class="btn sm" data-act="copy" data-text="${DONATE.address}">Copy</button></div></div>
    ${qrBlock('lightning:' + DONATE.lnurl, 'QR code for the Lightning address ' + DONATE.address)}
    <div class="field"><label>Same thing as a payment code (LNURL)</label><div class="code">${DONATE.lnurl}</div><button class="btn sm" data-act="copy" data-text="${DONATE.lnurl}">Copy LNURL</button></div>
    <div class="notice">Be wary of any other "NUTCADE donation" address. The same address and code are in the project README on GitHub. Never send your backup or seed words to anyone, for any reason.</div>
    <div id="sheetErr"></div>`);
}
async function lnAddressInvoice(address, sats, comment) {
  const [user, domain] = address.split('@');
  const base = await fetch(`https://${domain}/.well-known/lnurlp/${encodeURIComponent(user)}`).then(r => { if (!r.ok) throw new Error(`The Lightning address didn't answer (${r.status}).`); return r.json(); });
  if (base.status === 'ERROR') throw new Error(base.reason || 'The Lightning address returned an error.');
  if (base.tag !== 'payRequest' || !base.callback) throw new Error("That Lightning address isn't set up for payments.");
  const msat = sats * 1000;
  if (msat < base.minSendable || msat > base.maxSendable) throw new Error(`Tips must be between ${fmt(Math.ceil(base.minSendable / 1000))} and ${money(Math.floor(base.maxSendable / 1000))}.`);
  const u = new URL(base.callback); u.searchParams.set('amount', String(msat));
  if (comment && base.commentAllowed) u.searchParams.set('comment', comment.slice(0, base.commentAllowed));
  const inv = await fetch(u.toString()).then(r => r.json());
  if (inv.status === 'ERROR' || !inv.pr) throw new Error(inv.reason || "Couldn't get an invoice from the Lightning address.");
  return inv.pr;
}

/*@@app_r4.js@@*/
/*@@app_r5.js@@*/
/*@@app_r6.js@@*/
/*@@app_r7.js@@*/
/*@@app_r8.js@@*/
/*@@app_daily.js@@*/

/* ---------- actions ---------- */
/* Importing a backup never puts a coin into the balance, or a line into the history, without the mint's word: every
   coin in it is checked first (NUT-07), and only the unspent ones not already held are added. The history then gets
   one line per mint for what the backup changed, so it adds up to the balance: "Restored from backup" for coins the
   wallet didn't have, "Ecash already spent elsewhere" for coins the backup's own history counts that are gone since.
   An open step in it is settled here only if this wallet hasn't settled it already (by record, and by its coins).
   A mint that can't be asked right now doesn't hold up the others: its part of the backup (coins, history lines,
   open steps) waits aside, stored like any other secret, shown as "Waiting to check with <mint>", and is checked
   again by the background check and the Check now button; it comes in, the same way, once the mint answers. */
const ledgerOf = (txs, u) => txs.reduce((s, t) => t.mint !== u || t.status === 'failed' || t.status === 'expired' ? s : t.type === 'in' ? s + (t.status === 'done' || t.status === 'claimed' ? num(t.amount) : 0) : s - num(t.amount) - num(t.fee), 0);
const outSecret = o => { try { return new TextDecoder().decode(L.hexToBytes(o.s)); } catch (e) { return ''; } };
function opSettledHere(o) {
  if ((S.opsdone || []).includes(o.id)) return true;
  const mine = new Set([].concat(Object.values(S.proofs).flat().map(p => p.secret), S.txs.flatMap(t => (t.sent || []).map(p => p.secret)), S.extra ? S.extra.proofs.map(p => p.secret) : []));
  return (o.outs || []).some(x => mine.has(outSecret(x)));
}
const uniqBy = (a, k) => { const seen = new Set(); return (a || []).filter(x => x && x[k] && !seen.has(x[k]) && seen.add(x[k])); };
// coins this wallet already has at a mint: in the balance, in payments in flight, in tokens not yet claimed, in the Extra Life
const heldHere = u => new Set((S.proofs[u] || []).map(p => p.secret).concat(S.pending.flatMap(p => p.proofs.map(x => x.secret)), S.txs.filter(t => t.status === 'pending').flatMap(t => (t.sent || []).map(p => p.secret)), S.extra ? S.extra.proofs.map(p => p.secret) : []));
// a backup's open deposit is new here only if this wallet isn't watching it already and its line is still waiting (a
// Lightning deposit) or open (an on-chain address, which can be paid more than once): never one claimed or closed here
const newQuote = q => !!q && (q.kind === 'bolt11' || q.kind === 'onchain') && typeof q.quote === 'string' && !S.quotes.some(x => x.quote === q.quote) && (t => !!t && (t.status === 'pending' || (q.kind === 'onchain' && t.status === 'done')))(txById(q.txId)) && !S.txs.some(t => t.quote === q.quote && t.id !== q.txId);
S.imports = store.get('imports', []);   // parts of an imported backup waiting for their mint to answer: [{ id, mint, proofs, txs, pending, ops, extra, at }]
const saveImports = () => store.set('imports', S.imports);
const freshOps = ops => (ops || []).filter(o => o && o.id && typeof o.mint === 'string' && !S.ops.find(x => x.id === o.id)).map(o => Object.assign({ inputs: [], ctr: [], outs: [] }, o, { mint: normUrl(o.mint), impLine: null })).filter(o => !opSettledHere(o));
// a mint's part of a backup, checked at the mint: [unspent coins (and the coins of steps to settle here)] or null if it can't be asked
async function checkImport(u, proofs, ops) {
  const opIn = new Set(ops.flatMap(o => o.inputs));
  if (!proofs.length) return [];
  try { const w = await getWallet(u); const st = await inTime(w.checkProofsStates(proofs), 30000); return proofs.filter((p, i) => opIn.has(p.secret) || (st[i] && st[i].state === 'UNSPENT')); }
  catch (e) { return null; }
}
// a mint's part of a backup, written in one go: history lines it doesn't have, coins not held, one line, its open steps
function applyImport(u, coins, txs, pending, ops, quotes) {
  const ids = new Set(S.txs.map(t => t.id)), newTxs = uniqBy(txs, 'id').filter(t => !ids.has(t.id));   // (each line once, however often the backup holds it)
  for (const t of newTxs) S.txs.push(t);
  dropClaimedIncoming();
  S.txs.sort((a, b) => b.ts - a.ts);
  const newPend = uniqBy(pending, 'id').filter(p => !S.pending.find(x => x.id === p.id) && !ids.has(p.txId)).map(p => Object.assign({}, p, { impLine: null }));   // (one whose payment this wallet already has was settled here)
  for (const p of newPend) S.pending.push(p);
  const held = heldHere(u);
  const inc = coins.filter(p => !held.has(p.secret));
  if (inc.length) addProofs(u, inc);
  const diff = sum(inc) - ledgerOf(newTxs, u);
  let line = null;
  if (diff > 0) addTx({ type: 'in', method: 'ecash', amount: diff, mint: u, note: 'Restored from backup' });
  else if (diff < 0) line = addTx({ type: 'out', method: 'ecash', amount: -diff, mint: u, note: 'Ecash already spent elsewhere', status: 'done' });
  const fresh = uniqBy(ops, 'id').filter(o => !S.ops.find(x => x.id === o.id) && !opSettledHere(o));
  for (const o of fresh) S.ops.push(o);
  // a deposit the backup was still waiting for (paid or not) comes back with its line, unless this wallet has it already
  const newQ = uniqBy(quotes || [], 'quote').filter(q => newQuote(q)).map(q => Object.assign({}, q, { mint: u, impLine: null }));
  for (const q of newQ) S.quotes.push(q);
  // what these steps and deposits find spent since (on the device the backup came from) joins this import's line
  if (line) for (const r of [].concat(fresh, newPend, newQ)) r.impLine = line.id;
  return { ops: fresh, quotes: newQ, pending: newPend, txs: newTxs.filter(t => t.status === 'pending' && t.sent && t.sent.length).map(t => t.id) };
}
// the steps, deposits and payments a backup brought in are settled, checked and asked about right away (each the usual
// single-flight way: one at a time, idempotent), not only at the next background check
function settleImported({ ops, quotes, pending, txs = [], heirlooms = [], chals = [] }) {
  if (ops.length || quotes.length || pending.length || txs.length || heirlooms.length || chals.length) setTimeout(async () => {
    for (const o of ops) { if (!S.mints.find(m => m.url === o.mint)) await addMint(o.mint).catch(() => {}); await settleOp(o.id).catch(() => {}); }
    for (const q of quotes) { if (!S.mints.find(m => m.url === q.mint)) await addMint(q.mint).catch(() => {}); await checkQuote(q).catch(() => {}); }
    for (const p of pending) await reconcile(p, { force: true }).catch(() => {});
    await closeSpentImported({ txs, heirlooms, chals }).catch(() => {});
    refresh();
  }, 0);
}
// the backup's Extra Life comes in when its coins are unspent, or when one of the steps coming in with it is the
// CONTINUE that spent them (that step then finishes it here, with its new coins and date)
const renewOf = (x, ops) => !!x && Array.isArray(x.proofs) && ops.some(o => o.follow && o.follow.k === 'extra-renew' && x.proofs.some(p => (o.inputs || []).includes(p.secret)));
async function extraIfUnspent(x) {
  if (!x || !Array.isArray(x.proofs) || !x.proofs.length) return { ok: false };
  try { const w = await getWallet(normUrl(x.mint)); const st = await inTime(w.checkProofsStates(x.proofs), 30000); return { ok: st.every(y => y && y.state === 'UNSPENT'), asked: true }; } catch (e) { return { ok: false, asked: false }; }
}
async function importBackup(d) {
  if (d.seed && (!S.seed || (S.seed.mnemonic !== d.seed && totalBalance() === 0))) setSeed(d.seed, true);
  for (const k in d.counters || {}) counterSource.advanceToAtLeast(k, d.counters[k]);
  for (const k of d.p2pk || []) if (!S.p2pk.find(x => x.pub === k.pub)) S.p2pk.push(k); store.set('p2pk', S.p2pk);
  for (const m of d.mints || []) if (m && m.url && !S.mints.find(x => x.url === normUrl(m.url))) S.mints.push(Object.assign({}, m, { url: normUrl(m.url) }));
  // per mint: its coins, history lines, payments in flight and open steps (a backup's own waiting parts included)
  const part = {}, P = u => part[u] || (part[u] = { proofs: [], txs: [], pending: [], ops: [], quotes: [] });
  for (const [u0, ps] of Object.entries(d.proofs || {})) P(normUrl(u0)).proofs.push(...(Array.isArray(ps) ? ps : []));
  for (const t of d.txs || []) if (t && t.id) P(normUrl(t.mint || '')).txs.push(Object.assign({}, t, t.mint ? { mint: normUrl(t.mint) } : {}));
  for (const p of d.pending || []) if (p && p.id && p.mint) P(normUrl(p.mint)).pending.push(p);
  for (const o of d.ops || []) if (o && o.mint) P(normUrl(o.mint)).ops.push(o);
  for (const x of Array.isArray(d.quotes) ? d.quotes : []) if (x && typeof x.mint === 'string') P(normUrl(x.mint)).quotes.push(x);
  for (const r of Array.isArray(d.imports) ? d.imports : []) if (r && r.mint) { const q = P(normUrl(r.mint)); q.proofs.push(...(r.proofs || [])); q.txs.push(...(r.txs || []).map(t => Object.assign({}, t, { mint: normUrl(r.mint) }))); q.pending.push(...(r.pending || [])); q.ops.push(...(r.ops || [])); q.quotes.push(...(r.quotes || [])); }
  const checked = {}, waiting = [];
  for (const [u, q] of Object.entries(part)) {
    // each coin, line, payment, step and deposit once (a backup's waiting parts repeat what it holds itself)
    q.proofs = uniqBy(q.proofs, 'secret').map(p => Object.assign({}, p, { amount: num(p.amount) }));
    q.txs = uniqBy(q.txs, 'id'); q.pending = uniqBy(q.pending, 'id'); q.quotes = uniqBy(q.quotes, 'quote');
    q.ops = freshOps(uniqBy(q.ops, 'id'));
    const coins = u ? await checkImport(u, q.proofs, q.ops) : [];
    if (coins) checked[u] = coins; else waiting.push(u);
  }
  let extra = null, extraLater = null;
  // (the backup's Extra Life, or the one waiting aside in it for its mint: a backup made while waiting has it there)
  const dx = d.extra || ((Array.isArray(d.imports) ? d.imports : []).find(r => r && r.extra && Array.isArray(r.extra.proofs)) || {}).extra || null;
  if (dx && !S.extra) {
    const xu = normUrl(dx.mint || '');
    if (renewOf(dx, (part[xu] || { ops: [] }).ops)) { if (waiting.includes(xu)) extraLater = dx; else extra = dx; }
    else { const r = await extraIfUnspent(dx); if (r.ok) extra = dx; else if (!r.asked) extraLater = dx; }
  }
  await syncIfStale();
  const settle = { ops: [], quotes: [], pending: [], txs: [], heirlooms: [], chals: [] };
  for (const u of Object.keys(checked)) { const q = part[u], r = applyImport(u, checked[u], q.txs, q.pending, q.ops, q.quotes); settle.ops.push(...r.ops); settle.quotes.push(...r.quotes); settle.pending.push(...r.pending); settle.txs.push(...r.txs); }
  // a part that waits aside holds only what this wallet doesn't have yet (nothing at all: nothing waits), and a mint
  // has one waiting part: a second import while it is still down joins it (a new record, so a check already under way
  // for the old one finds it gone and leaves it), each coin, line and step once
  const late = [];
  for (const u of waiting) {
    const q = part[u], held = heldHere(u), ids = new Set(S.txs.map(t => t.id)), x = extraLater && normUrl(extraLater.mint) === u ? extraLater : null;
    const rec = { proofs: q.proofs.filter(p => !held.has(p.secret)), txs: q.txs.filter(t => !ids.has(t.id)), pending: q.pending.filter(p => !S.pending.find(y => y.id === p.id) && !ids.has(p.txId)), ops: q.ops, quotes: q.quotes.filter(y => !S.quotes.some(z => z.quote === y.quote)), extra: x };
    const old = S.imports.find(r => r.mint === u);
    if (old) for (const k of ['proofs', 'txs', 'pending', 'ops', 'quotes']) rec[k] = uniqBy((old[k] || []).concat(rec[k]), { proofs: 'secret', quotes: 'quote' }[k] || 'id');
    if (old && !rec.extra) rec.extra = old.extra || null;
    if (!rec.proofs.length && !rec.txs.length && !rec.pending.length && !rec.ops.length && !rec.quotes.length && !rec.extra) continue;
    S.imports = S.imports.filter(r => r.mint !== u); S.imports.push(Object.assign({ id: uid(), mint: u, at: Date.now() }, rec)); late.push(u);
  }
  if (waiting.length) saveImports();
  for (const r of Array.isArray(d.requests) ? d.requests : []) if (r && r.id && !S.requests.find(x => x.id === r.id)) S.requests.push(r);   // payment requests still open: their payments are still listened for
  if (Array.isArray(d.requests) && d.requests.length) { S.requests.sort((a, b) => (b.created || 0) - (a.created || 0)); S.requests = S.requests.slice(0, 30); store.set('requests', S.requests); }
  // Extra Life (only if its coins are still there), the copies we hold as an heir, and challenges (bounty secrets live there)
  if (extra) { S.extra = Object.assign({}, extra, { mint: normUrl(extra.mint) }); saveExtra(); }
  for (const h of d.heirlooms || []) if (h && h.token && !S.heirlooms.find(x => x.token === h.token)) { S.heirlooms.push(h); if (h.state === 'waiting') settle.heirlooms.push(h.token); } saveHeir();
  // (a bounty whose challenge the backup's device hadn't sent yet is sent from here only as the very message it kept)
  for (const c of d.challenges || []) if (c && !S.challenges.find(x => x.id === c.id && x.dir === c.dir)) { for (const x of c.bounties || []) if (x && x.unsent && !x.wrap) delete x.unsent; S.challenges.push(c); if (c.dir === 'in' && c.bounty) settle.chals.push(c.id); } saveChallenges();
  for (const h of d.hunts || []) if (!S.hunts.find(x => x.pub === h.pub)) S.hunts.push(h); saveHunts();
  for (const k in d.found || {}) if (!S.found[k]) S.found[k] = d.found[k]; saveFound();
  for (const x of Array.isArray(d.blocked) ? d.blocked : []) if (x && typeof x.url === 'string' && /^https?:/i.test(x.url) && !isBlocked(x.url)) S.blocked.push({ url: normUrl(x.url), name: String(x.name || host(x.url)).slice(0, 60), at: +x.at || Date.now() }); saveBlocked();
  if (!S.active && S.mints[0]) S.active = S.mints[0].url;
  save();
  settleImported(settle);
  return late;
}
// the parts waiting for their mint: checked again (background check, Check now); in once the mint answers, never dropped
async function retryImports(url) {
  let done = 0;
  for (const rec of S.imports.filter(r => !url || r.mint === url)) {
    const ops = freshOps(rec.ops), coins = await checkImport(rec.mint, rec.proofs || [], ops);
    if (!coins) continue;
    const ex = rec.extra && !S.extra ? (renewOf(rec.extra, ops) ? { ok: true, asked: true } : await extraIfUnspent(rec.extra)) : null;
    if (ex && !ex.asked) continue;
    await mintLock(rec.mint, async () => {
      if (!S.imports.find(x => x.id === rec.id)) return;
      const settle = applyImport(rec.mint, coins, rec.txs || [], rec.pending || [], ops, rec.quotes || []);
      if (ex && ex.ok && !S.extra) { S.extra = Object.assign({}, rec.extra, { mint: normUrl(rec.extra.mint) }); saveExtra(); }
      S.imports = S.imports.filter(x => x.id !== rec.id); saveImports(); save();
      settleImported(settle); done++;
    });
  }
  return done;
}
function importsPanel() {
  if (!S.imports.length) return '';
  return S.imports.map(r => `<div class="panel imports-panel"><span class="mid"><span class="h2">Waiting to check with <span data-noi18n>${esc((S.mints.find(m => m.url === r.mint) || {}).name || host(r.mint))}</span></span>
    <span class="tiny">${money(sum(r.proofs || []))} from a backup</span><span class="tiny muted">It comes in once the mint answers and confirms it is unspent.</span></span>
    <button class="btn sm" data-act="importsRetry">Check now</button></div>`).join('');
}
/* The backup holds everything that can spend (it is kept private, like the phrase it contains), including the open
   journal records: a step whose answer hasn't come yet (a gift, a bounty, Extra Life, a hunt...) keeps its saved
   outputs and secrets, so the wallet restored from this backup settles it there. Settling is by secret at the mint, so
   the same step settled on both devices gives the same coins, never two sets. */
const backupData = () => JSON.stringify({ app: 'nutcade', v: 2, at: new Date().toISOString(), seed: S.seed ? S.seed.mnemonic : null, counters: S.counters, mints: S.mints, proofs: S.proofs, pending: S.pending, txs: S.txs, p2pk: S.p2pk, extra: S.extra, heirlooms: S.heirlooms, challenges: S.challenges, hunts: S.hunts, found: S.found, blocked: S.blocked, ops: S.ops.filter(o => o.ctr.length || (o.outs || []).length), imports: S.imports, quotes: S.quotes, requests: S.requests }, null, 1);
const A = {
  close: () => closeSheet(),
  tab: b => { if (tab === 'history' && b.dataset.tab !== 'history') { histFilter = 'all'; histQuery = ''; histTag = ''; } tab = b.dataset.tab; closeSheet(); render(); window.scrollTo(0, 0); sfx('blip'); },
  pickMint: () => openMintPicker(),
  receive: () => { sfx('blip'); openReceive(supports(activeMint(), 'mint', 'bolt11') ? 'ln' : 'ecash'); },
  send: () => { sfx('select'); openSend('ecash'); },
  recvMethod: b => openReceive(b.dataset.m),
  sendMethod: b => openSend(b.dataset.m),
  copy: b => copy(b.dataset.text, b),
  hf: b => { histFilter = b.dataset.f; render(); },
  htag: b => { histTag = histTag === b.dataset.tag ? '' : b.dataset.tag; render(); },
  amtUnit: b => { const el = b.parentElement.querySelector('input'); if (el) { toggleUnit(el); el.focus(); } },
  csv: () => exportCsv(S.txs, `nutcade-transactions-${new Date().toISOString().slice(0, 10)}.csv`),
  tx: b => openTx(b.dataset.id),
  addMint: b => run(b, 'ADDING', async () => { if (isBlocked(b.dataset.url)) throw blockedErr(b.dataset.url, 'add'); const m = await addMint(b.dataset.url, { activate: true }); sfx('coin'); toast(`${m.name} added`, 'lime'); closeSheet(); render(); }),
  addMintUrl: b => run(b, 'ADDING', async () => { const u = val('mintUrl'); if (!u.trim()) throw new Error('Type a mint address first.'); if (isBlocked(normUrl(u))) throw blockedErr(normUrl(u), 'add'); const m = await addMint(u, { activate: true }); sfx('coin'); toast(`${m.name} added`, 'lime'); closeSheet(); render(); }),
  useMint: b => { S.active = b.dataset.url; save(); closeSheet(); render(); toast('Mint switched', 'cyan'); },
  refreshMint: b => run(b, '…', async () => { delete wallets[b.dataset.url]; await addMint(b.dataset.url); render(); toast('Mint info refreshed', 'cyan'); }),
  removeMint: b => {
    const u = b.dataset.url, bal = balanceOf(u);
    if (bal > 0) { toast(`Send or move the ${money(bal)} out of this mint before removing it.`, 'red'); sfx('err'); return; }
    openSheet('Remove mint', `<p style="margin:0">Remove ${esc(host(u))} from NUTCADE? Its transaction notes stay.</p><button class="btn solid red block" data-act="confirmRemove" data-url="${esc(u)}">Remove</button>`);
  },
  confirmRemove: b => { const u = b.dataset.url; S.mints = S.mints.filter(m => m.url !== u); delete S.proofs[u]; if (S.active === u) S.active = S.mints[0] ? S.mints[0].url : null; save(); scheduleMintBackup(); closeSheet(); render(); },
  discover: b => {
    const el = $('#nostrList'); el.innerHTML = busyHTML('LISTENING TO RELAYS');
    const stop = discoverMints(renderDiscovered);
    const prev = sheetCleanup; sheetCleanup = () => { stop(); if (prev) prev(); };
  },
  doLnInvoice: b => run(b, 'ASKING MINT', async () => { const tx = await lnMintQuote(amt(), val('noteIn').trim()); showInvoice(tx); }),
  doOnchainAddr: b => run(b, 'ASKING MINT', async () => { const tx = await onchainMintQuote(val('noteIn').trim()); showAddress(tx); }),
  doReceiveToken: b => run(b, 'CLAIMING', async () => {
    const tok = val('tokIn'); if (!tok.trim()) throw new Error('Paste a cashu token first.');
    let meta; try { meta = peekToken(tok); } catch (e) { throw new Error("That doesn't look like a Cashu token. It should start with cashuA or cashuB."); }
    if (isBlocked(meta.mint)) throw blockedErr(meta.mint);
    if (!S.mints.find(m => m.url === meta.mint) && !b.dataset.trust) {
      setTrust(meta); return;
    }
    if (isOffline()) { holdIncoming(tok, val('noteIn').trim()); sfx('blip'); refresh(); setBody(`<div class="notice">You're offline, so this token is saved and will be claimed automatically when you're back online. Until then it isn't yours yet: the sender could still spend it.</div><button class="btn solid gold block" data-act="close">OK</button>`); return; }
    let tx; try { tx = await receiveToken(tok, val('noteIn').trim()); }
    catch (e) { if (!netErr(e) || e.asked) throw e; holdIncoming(tok, val('noteIn').trim()); refresh(); setBody(`<div class="notice">The mint can't be reached right now, so the token is saved and will be claimed automatically when it can. Until then it isn't yours yet.</div><button class="btn solid gold block" data-act="close">OK</button>`); return; }
    sfx('coin'); showDone('in', tx.amount, 'Ecash');
  }),
  doSendEcash: b => run(b, 'MINTING TOKEN', async () => { const a = amt(), note = val('noteIn').trim(); let tx;
    if (($('#giftOn') || {}).checked) {
      if (isOffline()) throw new Error("Locking ecash needs the mint, and you're offline. Turn off the lock or try again online.");
      const c = contactById(val('giftTo')); const pub = c ? '02' + c.pubkey : lockPubFrom(val('giftKey'));
      if (!pub) throw new Error("That key can't be read. Paste their npub, or a Cashu public key starting with 02 or 03.");
      if (pub === myLockPub()) throw new Error("That's your own key. Lock it to someone else, or turn off the lock.");
      const days = +((document.querySelector('[data-act=giftDays][aria-pressed=true]') || {}).dataset || {}).days || 7;
      tx = await sendGift(a, note || (c ? `Gift for ${c.name}` : 'Gift'), { pubkey: pub, seconds: days * 86400, name: c ? c.name : '', contactId: c ? c.id : null });
      let sent = false; if (c) sent = await deliverToContact(c, tx).catch(() => false);
      sfx('coin'); refresh(); showToken(txById(tx.id), sent); return;
    }
    if (isOffline()) tx = sendOffline(a, note);
    else { try { tx = await sendEcash(a, note, null); } catch (e) { if (!netErr(e) || e.asked) throw e; tx = sendOffline(a, note); } } sfx('coin'); refresh(); showToken(tx); }),
  doMeltQuote: b => run(b, 'QUOTING', async () => {
    const k = b.dataset.k; let dest = val('destIn').trim().replace(/^(lightning|bitcoin):/i, '').split('?')[0];
    const note = val('noteIn').trim();
    if (k === 'ln') { const raw0 = val('destIn').trim(), cz = classify(raw0); if (cz.kind === 'nostr') { const t = parseNostrAddr(cz.value); const ct = S.contacts.find(x => x.pubkey === t.pubkey); openZap({ pubkey: t.pubkey, relays: t.relays, name: ct ? ct.name : '' }); return; } if (cz.kind === 'lnurl') { openLnurl(cz.value); return; } const c = classify(dest); if (c.kind === 'lnaddress' || c.kind === 'lnurl') { const n = val('noteIn').trim(); openPayLnurl(c.value); if (n && $('#noteIn')) $('#noteIn').value = n; return; }
      if (!/^ln(bc|tb|bcrt|tbs)[0-9a-z]{50,}$/i.test(dest)) throw new Error("That isn't a complete Lightning invoice. Copy the whole invoice (it starts with lnbc) and paste again."); dest = dest.toLowerCase(); let mq; try { mq = await meltQuote('ln', dest); } catch (e) { if (/bech32|checksum|decode|invalid invoice|parse/i.test(e.message)) throw new Error("That Lightning invoice isn't valid. Check you copied all of it."); throw e; } showMeltQuote('ln', mq, dest, note); }
    else { checkBtcAddr(dest, S.active); const a = amt(); const mq = await meltQuote('onchain', dest, a); showMeltQuote('onchain', mq, dest, note); }
  }),
  saveNote: b => { updTx(b.dataset.id, { note: val('noteEdit').trim() }); sfx('coin'); toast('Note saved', 'gold'); closeSheet(); refresh(); },
  checkClaim: b => run(b, '…', async () => { const t = txById(b.dataset.id); const c = await checkClaim(t); toast(c ? 'Claimed by the receiver' : 'Not claimed yet', c ? 'lime' : 'gold'); if (c) { closeSheet(); refresh(); } }),
  reclaim: b => run(b, 'RECLAIMING', async () => { const t = txById(b.dataset.id); reclaiming.add(t.id); try { await receiveToken(t.token, 'Reclaimed: ' + (t.note || 'ecash token'), { own: true }); } finally { setTimeout(() => reclaiming.delete(t.id), 5000); } updTx(t.id, { status: 'reclaimed' }); sfx('coin'); toast('Token reclaimed', 'lime'); closeSheet(); refresh(); }),
  resumeInvoice: b => { const t = txById(b.dataset.id); showInvoice(t); },
  resumeAddr: b => { const t = txById(b.dataset.id); showAddress(t); },
  stopWatch: b => { const t = txById(b.dataset.id); S.quotes = S.quotes.filter(q => q.quote !== t.quote); updTx(t.id, { status: 'expired' }); closeSheet(); refresh(); },
  reconcileTx: b => run(b, 'CHECKING', async () => { const t = txById(b.dataset.id); const p = S.pending.find(x => x.txId === t.id); if (!p) { toast('Nothing pending for this one', 'cyan'); return; } const r = await reconcile(p, { force: true }); const cp = (txById(t.id) || {}).changePending; toast(cp ? "Paid. Its change hasn't come back yet; NUTCADE keeps trying." : { paid: 'Payment confirmed', returned: 'Payment failed. Sats returned.', pending: 'Still in flight' }[r], r === 'pending' || cp ? 'gold' : 'lime'); closeSheet(); refresh(); }),
  reconcileAll: b => run(b, '…', async () => { for (const p of [...S.pending]) await reconcile(p, { force: true }).catch(() => {}); refresh(); }),
  pref: b => { S.prefs[b.dataset.k] = b.checked; save(); if (!S.prefs.sound || !S.prefs.music) window.NutAudio && window.NutAudio.stopMusic(); if (b.dataset.k === 'fiat' && b.checked) fetchPrice(true); if (b.dataset.k === 'nostrBackup' && b.checked) { S.prefs.mintBackupList = ''; scheduleMintBackup(0); } refresh(); sfx('blip'); },
  backup: () => {
    const data = backupData();
    openSheet('Backup', `<div class="notice red">This contains your recovery phrase and spendable ecash. Keep it private.</div><div class="code" style="max-height:200px">${esc(data)}</div><button class="btn solid gold block" data-act="copy" data-text="${esc(data)}">Copy backup</button>`);
  },
  restore: () => openSheet('Import backup', `<div class="field"><span class="flabel">Backup file</span><div class="row filepick"><label class="btn sm violet"><span>Choose a file</span><input id="restoreFile" type="file" accept=".json,application/json"></label><span id="restoreFileName" class="tiny muted">No file chosen</span></div></div><div class="field"><label for="restoreIn">Or paste the backup text</label><textarea id="restoreIn" class="inp" spellcheck="false"></textarea></div><button class="btn solid gold block" data-act="doRestore">Restore</button><div id="sheetErr"></div>`),
  doRestore: b => run(b, 'CHECKING', async () => {
    let d; try { d = JSON.parse(val('restoreIn')); } catch (e) { throw new Error("That isn't valid backup text."); }
    if (!d || d.app !== 'nutcade') throw new Error('Not a NUTCADE backup.');
    const waiting = await importBackup(d);
    closeSheet(); render();
    toast(waiting.length ? `Backup restored. Waiting to check with ${waiting.map(u => (S.mints.find(m => m.url === u) || {}).name || host(u)).join(', ')}.` : 'Backup restored.', waiting.length ? 'gold' : 'lime');
  }),
  importsRetry: b => run(b, 'CHECKING', async () => {
    const n = await retryImports(); refresh();
    toast(S.imports.length ? `Waiting to check with ${S.imports.map(r => (S.mints.find(m => m.url === r.mint) || {}).name || host(r.mint)).join(', ')}.` : 'Backup restored.', S.imports.length ? 'gold' : 'lime');
  }),
  takeover: () => { try { chan && chan.postMessage({ t: 'takeover', id: TAB_ID }); } catch (e) {} location.reload(); },
  seedCreate: b => run(b, 'ROLLING', async () => { setSeed(newMnemonic(), false); if (totalBalance() === 0) { S.seed.secured = true; store.set('seed', S.seed); } sfx('start'); render(); openShowPhrase(true); }),
  seedShow: () => { if (!S.seed) return; openShowPhrase(!S.seed.backedUp); },
  gateCreate: b => run(b, 'ROLLING', async () => { setSeed(newMnemonic(), false); if (totalBalance() === 0) { S.seed.secured = true; store.set('seed', S.seed); } gate = { step: 'show' }; sfx('start'); render(); window.scrollTo(0, 0); }),
  gateRestore: () => openRestore(),
  gateToConfirm: () => { gate = { step: 'confirm', picks: pickWords() }; sfx('select'); render(); window.scrollTo(0, 0); const f = document.querySelector('[data-cw]'); if (f && !matchMedia('(pointer:coarse)').matches) f.focus(); },
  gateBack: () => { gate = { step: 'show' }; render(); window.scrollTo(0, 0); },
  gateConfirm: async b => {
    const words = S.seed.mnemonic.split(' ');
    const bad = [...document.querySelectorAll('[data-cw]')].filter(i => cleanPhrase(i.value) !== words[+i.dataset.cw]);
    if (bad.length) { sfx('err'); $('#gateErr').innerHTML = errHTML(`Word #${+bad[0].dataset.cw + 1} doesn't match. Check your paper, or go back to your words.`); bad[0].focus(); return; }
    S.seed.backedUp = true; store.set('seed', S.seed); sfx('levelup');
    gate = { step: 'done' };
    if (!S.seed.secured && totalBalance() > 0) {
      gate.busy = 'PROTECTING YOUR ECASH'; render();
      try { const fee = await secureAll(); gate.msg = `Your existing ecash is now protected by your phrase${fee ? ` (mint fee ${money(fee)})` : ''}.`; }
      catch (e) { gate.msg = 'Some older ecash could not be moved yet. Use "Protect it" on the wallet screen to try again.'; }
      gate.busy = null;
    }
    render(); window.scrollTo(0, 0);
  },
  gateStart: () => { gate = { step: 'welcome' }; tab = 'wallet'; sfx('start'); render(); window.scrollTo(0, 0); if (!S.mints.length) openMintPicker(); },
  seedConfirmStart: () => openConfirmPhrase(),
  seedConfirm: b => run(b, 'CHECKING', async () => {
    const words = S.seed.mnemonic.split(' ');
    const bad = [...document.querySelectorAll('[data-cw]')].filter(i => cleanPhrase(i.value) !== words[+i.dataset.cw]);
    if (bad.length) throw new Error(`Word #${+bad[0].dataset.cw + 1} doesn't match. Check your paper, or show the words again.`);
    S.seed.backedUp = true; store.set('seed', S.seed); sfx('levelup');
    if (!S.seed.secured && totalBalance() > 0) {
      setBody(busyHTML('PROTECTING YOUR ECASH'));
      try { const fee = await secureAll(); setBody(`<div class="notice cyan">Backed up. Your existing ecash now sits under your phrase too${fee ? ` (mint fee ${money(fee)})` : ''}.</div><button class="btn solid gold block" data-act="close">Continue</button>`); }
      catch (e) { setBody(`<div class="notice cyan">Backed up.</div>${errHTML(friendly(e, S.active))}<div class="tiny muted">Your older ecash is still in the wallet. Use "Protect it" on the wallet screen to try again.</div><button class="btn solid gold block" data-act="close">Continue</button>`); }
    } else { setBody(`<div style="text-align:center;display:grid;gap:12px"><div style="font-family:var(--f-display);font-size:16px;color:var(--lime)">PHRASE SAVED!</div><p style="margin:0">Your sats can now be recovered from these 12 words.</p><button class="btn solid gold block" data-act="close">Continue</button></div>`); }
    render();
  }),
  secureAll: b => run(b, 'PROTECTING', async () => { const fee = await secureAll(); render(); toast(`Your ecash is now covered by your phrase${fee ? ` (fee ${money(fee)})` : ''}`, 'lime'); }),
  seedRestore: () => openRestore(),
  doRestorePhrase: b => run(b, 'RESTORING', async () => {
    const phrase = cleanPhrase(val('phraseIn'));
    if (!validPhrase(phrase)) throw new Error("That phrase isn't valid. Check each word's spelling and that you have all 12, in order.");
    const urls = [...document.querySelectorAll('[data-rmint]')].filter(i => i.checked).map(i => i.dataset.rmint)
      .concat(val('rmExtra').split(/\s+/).map(s => s.trim()).filter(Boolean).map(normUrl));
    const list = [...new Set(urls)];
    if (!list.length) throw new Error('Pick at least one mint to scan.');
    const log = $('#restoreLog'); const line = t => { if (log) log.innerHTML = esc(t); };
    const same = S.seed && S.seed.mnemonic === phrase;
    const hadBalance = totalBalance() > 0;
    if (!same) setSeed(phrase, true); else { S.seed.backedUp = true; store.set('seed', S.seed); }
    if (!same && hadBalance) { line('Moving your current ecash under the restored phrase…'); await secureAll(); }
    else if (!same) { S.seed.secured = true; store.set('seed', S.seed); }
    let total = 0; const fails = [];
    for (const u of list) {
      try { total += await restoreFromMint(u, line); } catch (e) { fails.push(host(u)); }
    }
    if (!S.active && S.mints[0]) S.active = S.mints[0].url; save();
    sfx(total ? 'levelup' : 'blip'); render();
    setBody(`<div style="text-align:center;display:grid;gap:12px">
      <div style="font-family:var(--f-display);font-size:16px;color:${total ? 'var(--lime)' : 'var(--gold)'}">${total ? 'CONTINUE!' : 'SCAN COMPLETE'}</div>
      <div class="credit-num" style="font-size:28px">${fmt(total)}<small>${unitTag()}</small></div>
      <p style="margin:0">${total ? 'Recovered and back in your wallet.' : 'No unspent ecash was found on those mints for this phrase.'}</p>
      ${fails.length ? `<div class="notice red">Couldn't reach: ${fails.map(esc).join(', ')}. Try those again later from Mints → Find lost ecash.</div>` : ''}
      <button class="btn solid gold block" data-act="close">Continue</button></div>`);
  }),
  findLost: b => run(b, 'SCANNING', async () => {
    if (!S.mints.length) throw new Error('Add the mints you used first, then scan.');
    let total = 0, fails = 0;
    for (const m of S.mints) { try { total += await restoreFromMint(m.url, t => { b.innerHTML = '<span class="spinner">SCANNING</span>'; }); } catch (e) { fails++; } }
    render(); toast(total ? `Found ${money(total)}` : fails ? `Nothing found; ${fails} mint(s) didn't answer` : 'No lost ecash found', total ? 'lime' : 'cyan'); if (total) sfx('coin');
  }),
  support: () => { sfx('select'); openSupport(); },
  pinKey: b => {
    const k = b.dataset.k; lastActive = Date.now();
    if (k === 'del') pinUI.value = pinUI.value.slice(0, -1);
    else if (k === 'ok') return pinSubmit();
    else if (pinUI.value.length < PIN_MAX) { pinUI.value += k; sfx('tick'); }
    const e = $('#pinErr'); if (e && !e.classList.contains('busy')) e.textContent = '';
    refreshPad();
  },
  pinSet: () => openPinSheet('set', 'Set a PIN', { title: 'CHOOSE A PIN', text: `${PIN_MIN} to ${PIN_MAX} digits. You'll need it each time NUTCADE opens. If you forget it, you can restore with your 12 words.` }),
  pinChange: () => openPinSheet('changeOld', 'Change PIN', { title: 'CURRENT PIN', text: 'Enter your current PIN.' }),
  pinRemove: () => openPinSheet('remove', 'Remove PIN', { title: 'ENTER PIN', text: 'Removing the PIN stores your wallet unencrypted on this device again.' }),
  bioStart: () => openPinSheet('bioVerify', 'Face ID / fingerprint', { title: 'ENTER PIN', text: 'Confirm your PIN, then your device will ask for Face ID or your fingerprint.' }),
  bioEnable: b => run(b, 'WAITING', async () => { await enableBio(); closeSheet(); refresh(); toast('Face ID / fingerprint unlock is on', 'lime'); }),
  bioDisable: () => { const rec = raw.get('vault'); delete rec.bio; raw.set('vault', rec); refresh(); toast('Face ID / fingerprint unlock is off. Use your PIN.', 'gold'); },
  // (Face ID / fingerprint opens the real wallet only)
  bioUnlock: async b => {
    try { b.disabled = true; const dek = await bioToDek(); await openPart(dek, false); hydrateFromVault(); pinUI.mode = null; sfx('start'); render(); armAutoLock(); setTimeout(() => backgroundTick(true).then(() => { if (!$('#layer .sheet') && tab !== 'arcade') refresh(); }), 300); }
    catch (e) { b.disabled = false; pinError(/NotAllowed|abort/i.test(e.name + e.message) ? 'Face ID / fingerprint was cancelled. Use your PIN.' : (e.message || "Couldn't unlock. Use your PIN.")); }
  },
  lockNow: () => { sfx('blip'); lockNow(); },
  forgotPin: () => openSheet('Forgot PIN', `<p style="margin:0">Your PIN can't be recovered: it's the key to the encrypted wallet on this device. You can reset the wallet here and restore it with your 12 words and mint list.</p>
    <div class="notice red">Without your 12 words, resetting loses your sats for good.</div>
    <div class="field"><label for="confirmWord">Type RESET to delete the locked wallet</label><input id="confirmWord" class="inp" autocomplete="off" autocapitalize="characters"></div>
    <button class="btn solid red block" data-act="doReset">Reset and restore with 12 words</button><div id="sheetErr"></div>`),
  scan: b => { sfx('select'); openScanner(b.dataset.hint); },
  scanPaste: async () => {
    let t = '';
    try { t = await navigator.clipboard.readText(); } catch (e) {}
    if (!t) { stopScan(); openSheet('Paste', `<div class="field"><label for="pasteIn">Paste here</label><textarea id="pasteIn" class="inp" autocomplete="off" spellcheck="false"></textarea></div><button class="btn solid gold block" data-act="pasteGo">Continue</button>`); return; }
    stopScan(); handleScan(t);
  },
  pasteGo: () => handleScan(val('pasteIn')),
  lnurlQuote: b => run(b, 'ASKING', async () => {
    const sats = amt(); const note = val('noteIn').trim();
    let pr; try { pr = await lnurlInvoice(b.dataset.t, sats, ''); } catch (e) { throw new Error(/fetch|network|load failed/i.test(e.message) ? "Couldn't reach that Lightning address. Check it and try again." : e.message); }
    const mq = await meltQuote('ln', pr);
    if (num(mq.amount) !== sats) throw new Error(`The invoice asked for ${money(num(mq.amount))} instead of ${money(sats)}. Nothing was sent.`);
    showMeltQuote('ln', mq, b.dataset.t, note);
  }),
  jump: b => { const el = document.getElementById(b.dataset.id); if (el) el.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }); },
  setTheme: b => { S.prefs.theme = b.dataset.t; save(); refresh(); sfx('select'); },
  backupDownload: () => {
    const data = backupData();
    try {
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([data], { type: 'application/json' }));
      a.download = `nutcade-backup-${new Date().toISOString().slice(0, 10)}.json`; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000); toast('Backup file downloaded. Keep it private.', 'lime');
    } catch (e) { A.backup(); }
  },
  sweepOpen: () => {
    const urls = [...new Set(S.mints.map(m => m.url).concat(CURATED.filter(c => !c.test).map(c => c.url)))];
    openSheet('Restore ecash', `<p style="margin:0">Enter the other phrase. NUTCADE scans the mints you pick and moves any ecash it finds into this wallet, under your current phrase.</p>
      <div class="field"><label for="phraseIn">Other 12 words</label><textarea id="phraseIn" class="inp" autocomplete="off" autocapitalize="off" spellcheck="false" data-input="phrase"></textarea><div id="phraseOk" class="tiny muted">Separate words with spaces.</div></div>
      <div class="field"><label>Mints to scan</label><div class="txs">${urls.map((u, i) => `<label class="toggle" for="sm${i}" style="font-size:19px"><span style="overflow-wrap:anywhere;min-width:0">${esc(host(u))}</span><input id="sm${i}" type="checkbox" data-rmint="${esc(u)}" ${S.mints.find(m => m.url === u) ? 'checked' : ''}></label>`).join('')}</div></div>
      <div class="field"><label for="rmExtra">Other mint addresses (one per line)</label><textarea id="rmExtra" class="inp" data-noi18n autocomplete="off" autocapitalize="off" spellcheck="false"></textarea></div>
      <button class="btn solid gold block" data-act="doSweep">Scan and restore</button><div id="restoreLog" class="tiny muted"></div><div id="sheetErr"></div>`);
  },
  doSweep: b => run(b, 'SCANNING', async () => {
    const phrase = cleanPhrase(val('phraseIn'));
    if (!validPhrase(phrase)) throw new Error("That phrase isn't valid. Check each word's spelling and that you have all 12, in order.");
    if (S.seed && phrase === S.seed.mnemonic) throw new Error('That is your current phrase. Use Find lost ecash instead.');
    const urls = [...new Set([...document.querySelectorAll('[data-rmint]')].filter(i => i.checked).map(i => i.dataset.rmint).concat(val('rmExtra').split(/\s+/).filter(Boolean).map(normUrl)))];
    if (!urls.length) throw new Error('Pick at least one mint to scan.');
    const log = $('#restoreLog');
    const { total, fails } = await sweepPhrase(phrase, urls, t => { if (log) log.textContent = t; });
    sfx(total ? 'levelup' : 'blip'); refresh();
    setBody(`<div style="text-align:center;display:grid;gap:12px"><div style="font-family:var(--f-display);font-size:16px;color:${total ? 'var(--lime)' : 'var(--gold)'}">${total ? 'BONUS ROUND!' : 'SCAN COMPLETE'}</div>
      <div class="credit-num" style="font-size:28px">${fmt(total)}<small>${unitTag()}</small></div><p style="margin:0">${total ? 'Moved into this wallet.' : 'No unspent ecash was found for that phrase.'}</p>
      ${fails.length ? `<div class="notice red">Couldn't reach: ${fails.map(esc).join(', ')}.</div>` : ''}<button class="btn solid gold block" data-act="close">Continue</button></div>`);
  }),
  p2pkNew: b => run(b, '…', async () => { newP2PK(); sfx('coin'); refresh(); toast('New P2PK key created', 'lime'); }),
  p2pkShow: b => { const k = S.p2pk[+b.dataset.i]; openSheet('Your P2PK key', `<p style="margin:0">Share this public key. Ecash locked to it can only be claimed by this wallet.</p>${qrBlock(k.pub, 'P2PK public key QR')}<div class="code">${esc(k.pub)}</div><button class="btn solid gold block" data-act="copy" data-text="${esc(k.pub)}">Copy key</button>`); },
  exportToken: () => {
    const m = activeMint(); const ps = S.proofs[m.url] || [];
    if (!ps.length) { toast('Nothing to export on this mint', 'gold'); return; }
    const tok = L.getEncodedToken({ mint: m.url, proofs: ps, unit: 'sat' });
    openSheet('Export ecash', `<div class="notice red">This token holds your entire ${esc(m.name)} balance (${money(sum(ps))}). Anyone who has it can spend it. After you claim it in another wallet, use Remove spent ecash here.</div>
      <div class="code" style="max-height:160px">${esc(tok)}</div><button class="btn solid gold block" data-act="copy" data-text="${esc(tok)}">Copy token</button>`);
  },
  ctrBump: b => { counterSource.advanceToAtLeast(b.dataset.id, (S.counters[b.dataset.id] || 0) + 10); refresh(); },
  newSeedAsk: () => openSheet('New recovery phrase', `<p style="margin:0">NUTCADE will create a new 12-word phrase, show it for you to write down, then move your ${money(totalBalance())} under it. The mint may charge a small fee for the move.</p>
    <div class="field"><label for="confirmWord">Type NEW to continue</label><input id="confirmWord" class="inp" autocomplete="off" autocapitalize="characters"></div>
    <button class="btn solid red block" data-act="doNewSeed">Create new phrase</button><div id="sheetErr"></div>`),
  doNewSeed: () => {
    if (val('confirmWord').trim().toUpperCase() !== 'NEW') { showErr(new Error('Type NEW to confirm.')); return; }
    setSeed(newMnemonic(), false); S.seed.secured = totalBalance() === 0; store.set('seed', S.seed);
    closeSheet(); gate = { step: 'show' }; render(); window.scrollTo(0, 0);
  },
  resetAsk: () => openSheet('Reset wallet', `<div class="notice red">This deletes your recovery phrase, ecash, notes and history from this browser, then returns you to the start screen to create a new wallet or restore one. ${totalBalance() ? `If you don't have your 12 words and mint list, your ${money(totalBalance())} is lost forever.` : 'Your wallet is empty.'}</div>
    ${S.mints.length ? `<div class="th">Your mints, to write down with your words:</div><div class="code" style="color:var(--ink)">${S.mints.map(m => esc(m.url)).join('<br>')}</div>` : ''}
    <div class="field"><label for="confirmWord">Type RESET to confirm</label><input id="confirmWord" class="inp" autocomplete="off" autocapitalize="characters"></div>
    <button class="btn solid red block" data-act="doReset">Reset wallet</button><div id="sheetErr"></div>`),
  doReset: () => {
    if (val('confirmWord').trim().toUpperCase() !== 'RESET') { showErr(new Error('Type RESET to confirm.')); return; }
    if (vault.on && vault.open && vault.decoy) { resetPart().then(() => location.reload(), e => showErr(e)); return; }   // (the duress PIN's wallet is emptied; the real wallet is never touched)
    // the vault is closed first, so nothing written below can land in it (or bring it back); then every record of the
    // wallet goes, with the PIN, its tries and changes, and only the device's own settings and arcade tables stay
    vault.on = false; vault.open = false; vault.decoy = false; vault.dek = null; vault.data = {};
    try { for (const k of Object.keys(localStorage)) { if (!k.startsWith('nutcade:')) continue; const n = k.slice(8); if (n === 'prefs' || (devKey(n) && !/^(vault|pinfails|pinchg|gen)$/.test(n))) continue; localStorage.removeItem(k); } } catch (e) {}
    try { npcSocketStop(); dmStop(); for (const k of ['npc', 'npcSince', 'npcName', 'npcMint', 'mintBackupAt', 'mintBackupList', 'dmSince']) delete S.prefs[k]; store.set('prefs', S.prefs); } catch (e) {}
    location.reload();
  },
  swapToken: b => run(b, 'SWAPPING', async () => {
    const r = await swapIn(val('tokIn'), val('noteIn').trim());
    sfx('coin'); refresh();
    setBody(`<div style="text-align:center;display:grid;gap:12px"><div style="font-family:var(--f-display);font-size:16px;color:var(--lime)">SWAPPED!</div><div class="credit-num" style="font-size:28px">+${fmt(r.amt)}<small>${unitTag()}</small></div>
      <p style="margin:0">Claimed at ${esc(host(r.from))} and moved into ${esc((S.mints.find(m => m.url === r.to) || {}).name || host(r.to))} over Lightning.</p><button class="btn solid gold block" data-act="close">Continue</button></div>`);
  }),
  sendMax: b => { const i = $('#amtIn'); if (i) setSats(i, b.dataset.a); const er = $('#sheetErr'); if (er) er.innerHTML = ''; const go = $('#layer [data-act=doSendEcash]'); if (go) go.click(); },
  tipPreset: b => { const i = $('#tipAmt'); if (i) setSats(i, b.dataset.a); b.parentElement.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); sfx('blip'); },
  tipQuote: b => run(b, 'ASKING', async () => {
    const sats = satsOf('tipAmt');
    if (!sats || sats < 1) throw new Error('Enter a tip amount in sats, like 210.');
    if (balanceOf(S.active) < sats) throw new Error(`Not enough funds. This mint holds ${money(balanceOf(S.active))}.`);
    let pr;
    try { pr = await lnAddressInvoice(DONATE.address, sats, 'Tip from NUTCADE'); }
    catch (e) { throw new Error(/fetch|network|load failed/i.test(e.message) ? "Couldn't reach the Lightning address from here. Copy the address into another wallet instead." : e.message); }
    const mq = await meltQuote('ln', pr);
    if (num(mq.amount) !== sats) throw new Error(`The invoice asked for ${money(num(mq.amount))} instead of ${fmt(sats)}. Nothing was sent.`);
    showMeltQuote('ln', mq, DONATE.address, 'Tip to NUTCADE ♥');
  }),
  findMints: b => run(b, 'ASKING RELAYS', async () => {
    const phrase = cleanPhrase(val('phraseIn'));
    if (!validPhrase(phrase)) throw new Error('Enter your 12 words first, then search.');
    const found = await findMintBackups(phrase);
    const info = $('#nostrMints'), list = $('#rmList'); if (!list) return;
    if (!found.length) { if (info) info.innerHTML = 'No mint-list backup was found on Nostr for these words. Tick the mints you used below.'; return; }
    for (const u of found) {
      const box = [...list.querySelectorAll('[data-rmint]')].find(i => i.dataset.rmint === u);
      if (box) box.checked = true;
      else { const i = list.querySelectorAll('[data-rmint]').length; list.insertAdjacentHTML('afterbegin', `<label class="toggle" for="rmn${i}" style="font-size:19px"><span style="overflow-wrap:anywhere;min-width:0" data-noi18n>${esc(host(u))}</span><input id="rmn${i}" type="checkbox" data-rmint="${esc(u)}" checked></label>`); }
    }
    if (info) info.innerHTML = `<span style="color:var(--lime)">Found ${found.length} mint${found.length === 1 ? '' : 's'} in your Nostr backup and ticked ${found.length === 1 ? 'it' : 'them'}.</span>`;
    sfx('coin');
  }),
  mintBackupNow: b => run(b, 'SAVING', async () => { const n = await backupMints(); refresh(); if (!n) throw new Error("No Nostr relay accepted the backup. Check your connection and try again."); toast(`Mint list backed up to ${n} relay${n === 1 ? '' : 's'}`, 'lime'); }),
  contactsOpen: () => { sfx('select'); openContacts(); },
  contactEdit: b => openContactEdit(b.dataset.id || null),
  contactSave: b => run(b, 'SAVING', async () => { const c = saveContact({ id: b.dataset.id || null, name: val('cName'), ln: val('cLn'), nostr: val('cNostr'), created: (contactById(b.dataset.id) || {}).created }); sfx('coin'); toast(`${c.name} saved`, 'lime'); openContacts(); refresh(); }),
  contactDel: b => { S.contacts = S.contacts.filter(c => c.id !== b.dataset.id); store.set('contacts', S.contacts); toast('Contact deleted', 'gold'); openContacts(); refresh(); },
  contactFrom: b => openContactEdit(null, { ln: b.dataset.ln || '' }),
  payContact: b => openPayContact(b.dataset.id),
  contactEcash: b => run(b, 'SENDING', async () => {
    const c = contactById(b.dataset.id); const a = amt(); const note = val('noteIn').trim() || `To ${c.name}`;
    if (isOffline()) throw new Error("You're offline. Sending over Nostr needs a connection. Make a token from Send → Ecash instead.");
    const { tx, ok } = await sendToContactNostr(c, a, note); sfx('coin'); refresh();
    if (ok) return showDone('out', a, `Ecash to ${c.name}`);
    setBody(`<div class="notice red">The ecash was made but no Nostr relay accepted it. It's safe in this token: send it another way, or reclaim it from your notes.</div>${qrBlock(tx.token, 'Ecash token QR')}<button class="btn solid pink block" data-act="copy" data-text="${esc(tx.token)}">Copy token</button><button class="btn block" data-act="close">Close</button>`);
  }),
  contactLn: b => run(b, 'ASKING', async () => {
    const c = contactById(b.dataset.id); const sats = amt(); const note = val('noteIn').trim() || `To ${c.name}`;
    let pr; try { pr = await lnurlInvoice(c.ln, sats, ''); } catch (e) { throw new Error(/fetch|network|load failed/i.test(e.message) ? `Couldn't reach ${c.ln}. Check the address and your connection.` : e.message); }
    const mq = await meltQuote('ln', pr);
    if (num(mq.amount) !== sats) throw new Error(`The invoice asked for ${money(num(mq.amount))} instead of ${money(sats)}. Nothing was sent.`);
    lastContact = c; showMeltQuote('ln', mq, c.ln, note);
  }),
  myAddrQR: () => openSheet('Your ecash address', `<p style="margin:0">Friends can send you ecash over Nostr with this, from NUTCADE or cashu.me. It comes from your 12 words.</p>${qrBlock('nostr:' + myEcashAddress(), 'Ecash address QR')}<div class="code">${esc(myEcashAddress())}</div><button class="btn solid gold block" data-act="copy" data-text="${esc(myEcashAddress())}">Copy address</button>${S.prefs.nostrInbox ? '' : '<div class="notice">Receiving ecash over Nostr is off in Settings → Privacy.</div>'}`),
  reqOpen: () => { sfx('select'); openRequest(); },
  reqCreate: b => run(b, 'CREATING', async () => {
    const a = satsOf('amtIn');
    if (!a && val('amtIn').trim()) throw amtErr('Leave the amount empty to accept any amount, or type more than 0.', 'zero');
    const r = newRequest(a, val('memoIn').trim(), !!($('#onlyMine') || {}).checked); sfx('coin'); showRequest(r);
  }),
  reqShow: b => { const r = S.requests.find(x => x.id === b.dataset.id); if (r) showRequest(r); },
  reqPayOpen: () => openSheet('Pay a payment request', `<div class="field"><label for="pasteIn">Paste the request (starts with creqA)</label><textarea id="pasteIn" class="inp" autocomplete="off" spellcheck="false"></textarea></div><button class="btn solid gold block" data-act="pasteGo">Continue</button><div class="btngrid"><button class="btn violet" data-act="scan" data-hint="Point at a payment request.">Scan</button>${nfcBtn('nfcScan', 'Tap NFC')}</div><div id="sheetErr"></div>`, () => nfcStop),
  payReq: b => run(b, 'PAYING', async () => {
    const pr = decodeRequest(b.dataset.req);
    const a = pr.amount ? num(pr.amount) : amt();
    const url = val('reqMint'); if (!url) throw new Error('Pick a mint to pay from.');
    if (balanceOf(url) < a) throw new Error(`Not enough funds. That mint holds ${money(balanceOf(url))}.`);
    const { tx, sent, why } = await payRequest(pr, a, url, val('noteIn').trim() || pr.description || 'Payment request', b.dataset.req);
    sfx('coin'); refresh();
    if (sent) return showDone('out', a, 'Payment request');
    if (!(pr.transport || []).length) return showToken(tx);
    setBody(`<div class="notice red">The ecash was made but couldn't be delivered${why ? ': ' + esc(why) : ''}. It's safe in this token: send it another way, or reclaim it from your notes.</div>${qrBlock(tx.token, 'Ecash token QR')}<button class="btn solid pink block" data-act="copy" data-text="${esc(tx.token)}">Copy token</button><button class="btn block" data-act="close">Close</button>`);
  }),
  claimIncoming: b => run(b, 'CLAIMING', async () => {
    const t = txById(b.dataset.id); if (!t || !t.incoming) return;
    const nt = await receiveToken(t.incoming, t.note, { follow: { k: 'incoming', txId: t.id, reqId: t.reqId || null } });
    incomingClaimed({ txId: t.id, reqId: t.reqId || null }, nt);
    sfx('coin'); showDone('in', nt.amount, 'Ecash');
  }),
  nfcScan: async b => {
    const msg = $('#scanMsg'); stopScan();
    if (msg) msg.textContent = 'HOLD AN NFC CARD TO THE BACK OF YOUR PHONE';
    else { const e = $('#sheetErr'); if (e) e.innerHTML = '<div class="notice cyan">Hold an NFC card to the back of your phone.</div>'; }
    try { await nfcRead(t => { sfx('blip'); if (!t) { toast("That card doesn't hold anything NUTCADE can use.", 'gold'); return; } handleScan(t); }, m => { if ($('#scanMsg')) $('#scanMsg').textContent = m; }); }
    catch (e) { showErr(new Error(/NotAllowed|denied/i.test(e.name + e.message) ? 'NFC permission was declined. Allow NFC for this site in Chrome settings.' : /NotSupported|NotReadable/i.test(e.name) ? 'NFC is turned off or not available. Turn on NFC in your phone settings.' : (e.message || "NFC didn't start."))); }
  },
  nfcWrite: b => {
    const text = b.dataset.text; sfx('select');
    const old = b.innerHTML; b.disabled = true; b.innerHTML = '<span class="spinner">TAP A CARD</span>';
    toast('Hold an NFC card to the back of your phone', 'cyan');
    nfcWrite(text).then(() => { sfx('coin'); toast('Written to the card', 'lime'); })
      .catch(e => { if (e.name === 'AbortError') return; sfx('err'); toast(/NotAllowed/i.test(e.name) ? 'NFC permission was declined.' : /NetworkError|NotSupported|capacity|too large/i.test(e.name + e.message) ? "Couldn't write: the card may be too small for this. Try a bigger card (NTAG216)." : (e.message || "Couldn't write to the card."), 'red'); })
      .finally(() => { if (b.isConnected) { b.disabled = false; b.innerHTML = old; } });
  },
  lnAddr: () => openLnAddr(),
  lnAddrQR: () => openSheet('Lightning address', `${qrBlock('lightning:' + npcAddress(), 'Lightning address QR')}<div class="code addr">${esc(npcAddress())}</div><button class="btn solid gold block" data-act="copy" data-text="${esc(npcAddress())}">Copy address</button><button class="btn block" data-act="close">Done</button>`),
  lnAddrOn: b => run(b, 'CONNECTING', async () => { const m = val('npcMint'); await npcConnect(m || null); sfx('levelup'); refresh(); openLnAddr(); toast('Your Lightning address is ready', 'lime'); npcSync().catch(() => {}); }),
  lnAddrMint: b => run(b, 'SAVING', async () => { await npcConnect(val('npcMint')); refresh(); openLnAddr(); toast('Payments now go to ' + ((S.mints.find(m => m.url === S.prefs.npcMint) || {}).name || host(S.prefs.npcMint)), 'lime'); }),
  lnAddrSync: b => run(b, 'CHECKING', async () => { const n = await npcSync(); refresh(); toast(n ? `${n} payment${n === 1 ? '' : 's'} found` : 'No new payments', n ? 'lime' : 'cyan'); }),
  lnAddrOff: () => { npcOff(); refresh(); closeSheet(); toast('Lightning address turned off here. Payments wait at npub.cash until you turn it back on.', 'gold'); },
  clean: b => run(b, 'CHECKING', async () => { const n = await cleanWallet(); render(); toast(n ? `Removed ${n} spent proof${n === 1 ? '' : 's'}` : 'All proofs are good', 'lime'); })
};
/*@@app_r4_actions.js@@*/
/*@@app_r5_actions.js@@*/
/*@@app_r6_actions.js@@*/
/*@@app_r7_actions.js@@*/
/*@@app_r8_actions.js@@*/
function setTrust(meta) {
  const el = $('#tokPeek'); const dest = activeMint();
  const canSwap = dest && supports(dest, 'mint', 'bolt11') && dest.url !== meta.mint;
  el.innerHTML = `<div class="notice">This token is from ${esc(host(meta.mint))}, a mint you haven't added. Claiming adds it and trusts it with ${money(meta.amount)}.${canSwap ? ` Or swap it into ${esc(dest.name)} over Lightning (small fee).` : ''}</div>`;
  const btn = $('[data-act="doReceiveToken"]'); btn.dataset.trust = '1'; btn.textContent = 'Trust mint & claim';
  if (canSwap && !$('[data-act="swapToken"]')) btn.insertAdjacentHTML('afterend', `<button class="btn block violet" data-act="swapToken">Swap into ${esc(dest.name)}</button>`);
}

document.addEventListener('click', e => {
  if (e.target.matches('[data-scrim]')) { closeSheet(); return; }
  const b = e.target.closest('[data-act]'); if (!b) return;
  if (b.type === 'checkbox') return;
  const f = A[b.dataset.act]; if (f) { e.preventDefault(); f(b, e); }
});
document.addEventListener('change', e => {
  const b = e.target.closest('[data-act="pref"]'); if (b) A.pref(b);
  if (e.target.id === 'scanFile' && e.target.files[0]) scanPhoto(e.target.files[0]);
  if (e.target.id === 'restoreFile' && e.target.files[0]) { const nm = $('#restoreFileName'); if (nm) { nm.textContent = e.target.files[0].name; nm.setAttribute('data-noi18n', ''); } e.target.files[0].text().then(t => { const box = $('#restoreIn'); if (box) box.value = t; }).catch(() => {}); }
  const sel = e.target.closest('[data-act="prefSelect"]'); if (sel) { S.prefs[sel.dataset.k] = sel.dataset.k === 'lockAfter' ? +sel.value : sel.value; save(); if (sel.dataset.k === 'lockAfter') { armAutoLock(); return; } if (sel.dataset.k === 'lang') { setLang(); refresh(); return; } if (sel.dataset.k === 'piggyStep') { S.prefs.piggyStep = +sel.value; save(); refresh(); return; } price = { rate: null, at: 0, cur: null }; fetchPrice(true); }
  if (e.target.id === 'nwcPer') { const f = $('#nwcAmtF'); if (f) f.hidden = e.target.value === 'none'; }
  if (e.target.id === 'giftOn') { const box = $('#giftBox'); if (box) box.hidden = !e.target.checked; sfx('blip'); }
  if (e.target.id === 'giftTo') { const f = $('#giftKeyF'); if (f) f.hidden = !!e.target.value; }
  const g = e.target.dataset && e.target.dataset.gatecheck;
  if (g) document.querySelectorAll(`[data-needs="${g}"]`).forEach(x => { x.disabled = !e.target.checked; });
});
document.addEventListener('input', e => {
  const k = e.target.dataset && e.target.dataset.input;
  if (k === 'hq') { histQuery = e.target.value; const list = $('#txList'); const pos = e.target.selectionStart; render(); const i = $('#hq'); if (i) { i.focus(); try { i.setSelectionRange(pos, pos); } catch (x) {} } }
  if (k === 'phrase') {
    const el = $('#phraseOk'); const n = cleanPhrase(e.target.value).split(' ').filter(Boolean).length;
    if (el) el.innerHTML = validPhrase(e.target.value) ? '<span style="color:var(--lime)">Valid 12-word phrase</span>' : `${n} of 12 words${n >= 12 ? ' · checksum doesn\'t match, check spelling and order' : ''}`;
  }
  if (k === 'tokPeek') {
    const el = $('#tokPeek'); const v = e.target.value.trim(); if (!v) { el.innerHTML = ''; return; }
    try { const m = peekToken(v); el.innerHTML = (isBlocked(m.mint) ? errHTML(blockedErr(m.mint)) : '') + `<dl class="kv"><dt>Amount</dt><dd style="color:var(--gold)">${money(m.amount)}</dd><dt>Mint</dt><dd data-noi18n>${esc(host(m.mint))}</dd>${m.memo ? `<dt>Memo</dt><dd data-noi18n>${esc(m.memo)}</dd>` : ''}</dl>`; }
    catch (x) { el.innerHTML = '<div class="tiny muted">Waiting for a valid cashu token…</div>'; }
  }
});
document.addEventListener('keydown', e => {
  const sheet = $('#layer .sheet'), trap = sheet || cash.el;
  if (trap && e.key === 'Tab') {   // keep keyboard focus inside the open sheet, or the till
    const f = [...trap.querySelectorAll(FOCUSABLE)].filter(x => x.getClientRects().length && getComputedStyle(x).visibility !== 'hidden');
    if (f.length) {
      const i = f.indexOf(document.activeElement);
      if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); return; }
      if (!e.shiftKey && (i === -1 || i === f.length - 1)) { e.preventDefault(); f[0].focus(); return; }
    }
  }
  // Enter in a sheet's field presses the sheet's main button (the first solid one after the field)
  if (sheet && e.key === 'Enter' && e.target.matches && e.target.matches('input:not([type=checkbox]):not([type=radio]):not([type=file])') && sheet.contains(e.target)
      && e.target.id !== 'mintUrl' && e.target.dataset.cw === undefined && !e.target.closest('[data-pinpad]')) {
    const btns = [...sheet.querySelectorAll('.btn.solid:not([disabled]), button.solid:not([disabled])')].filter(b => b.getClientRects().length);
    const after = btns.find(b => e.target.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) || btns[0];
    if (after) { e.preventDefault(); after.click(); return; }
  }
  if (document.querySelector('[data-pinpad]') && !e.target.matches('input,textarea,select')) {
    const k = /^[0-9]$/.test(e.key) ? e.key : e.key === 'Backspace' ? 'del' : e.key === 'Enter' ? 'ok' : null;
    if (k) { e.preventDefault(); const b = document.querySelector(`[data-pinpad] [data-k="${k}"]`); if (b) A.pinKey(b); return; }
  } if (e.key === 'Enter' && e.target.dataset && e.target.dataset.cw !== undefined && $('[data-act=gateConfirm]')) { e.preventDefault(); A.gateConfirm($('[data-act=gateConfirm]')); } if (e.key === 'Escape' && $('#layer .sheet')) closeSheet(); if (e.key === 'Enter' && e.target.id === 'mintUrl') A.addMintUrl($('[data-act="addMintUrl"]')); });

/* ---------- background checks ---------- */
// one background check at a time: the timer, coming back online and opening the app can all ask for one, and two at
// once could claim the same thing twice (the second then wrongly finding it "already spent")
let tickRun = null, tickAt = 0;
function backgroundTick(startup) {
  if (tickRun && Date.now() - tickAt < 120e3) return tickRun;   // (one stuck for 2 minutes is left behind)
  tickAt = Date.now();
  const me = tickRun = tickBody(startup).finally(() => { if (tickRun === me) tickRun = null; });
  return me;
}
// Each mint's work runs on its own (and every mint request has a time limit), so a mint that never answers can't hold
// up the other mints or the other checks (gift refunds, Extra Life, heir claims, bounties, "was my token claimed").
async function mintTick(url, startup) {
  const now = Date.now(), maxAge = 14 * 86400000;
  // (each step has a time limit of its own too: one that joins a check already in flight, say one stuck on a mint
  // from the last round, is left behind after it, and the rest of this mint's work goes on)
  const step = p => inTime(p, STEP_MS);
  if (S.imports.some(r => r.mint === url)) await step(retryImports(url)).catch(() => {});   // a backup's part waiting for this mint
  for (const o of S.ops.filter(o => o.mint === url)) {   // steps whose answer never came: settled with backoff (at once at a start)
    if (!startup && o.nextTry && now < o.nextTry) continue;
    try { await step(settleOp(o.id)); } catch (e) { o.tries = (o.tries || 0) + 1; o.nextTry = Date.now() + Math.min(30 * 60e3, 15e3 * 2 ** (o.tries - 1)); save(); }
  }
  for (const q of S.quotes.filter(q => q.mint === url && (q.kind === 'onchain' || now - (txById(q.txId)?.ts || 0) < maxAge))) await step(checkQuote(q)).catch(() => {});
  for (const p of S.pending.filter(p => p.mint === url)) await step(reconcile(p, { force: !!startup })).catch(() => {});
  await step(fetchPreimages(url)).catch(() => {});
  if (S.prefs.checkSent) for (const t of S.txs.filter(t => t.mint === url && t.status === 'pending' && t.method === 'ecash' && t.sent).slice(0, 10)) await step(checkClaim(t)).catch(() => {});
}
/* A payment settled from its coins' state (the mint's quote check failed at that moment) has no preimage yet: it is
   asked for later, a few times, so Wallet Connect apps and the details can show it. */
async function fetchPreimages(url) {
  const w = await getWallet(url);
  for (const t of S.txs.filter(t => t.mint === url && t.type === 'out' && t.method === 'ln' && t.status === 'done' && !t.preimage && t.quote && (t.preTries || 0) < 6 && Date.now() - t.ts < 7 * 86400e3).slice(0, 5)) {
    let qs = null; try { qs = await w.checkMeltQuoteBolt11(t.quote); } catch (e) {}
    updTx(t.id, qs && qs.payment_preimage ? { preimage: qs.payment_preimage } : { preTries: (t.preTries || 0) + 1 });
  }
}
async function tickBody(startup) {
  if (!S.seed || tabLocked) return;
  const urls = [...new Set(S.mints.map(m => m.url).concat(S.quotes.map(q => q.mint), S.pending.map(p => p.mint), S.ops.map(o => o.mint), S.imports.map(r => r.mint)))];
  await Promise.all([
    ...urls.map(u => mintTick(u, startup).catch(() => {})),
    (async () => { if (S.prefs.npc) await npcSync().catch(() => {}); })(),
    claimSaved().catch(() => {}),
    refundExpiredGifts().catch(() => {}),
    (async () => { await extraTick().catch(() => {}); await claimHeirlooms().catch(() => {}); })(),
    retryBounties().catch(() => {}),
    retryHunts().catch(() => {}),
    deliverReqPays().catch(() => {}),
    recheckImported().catch(() => {})
  ]);
  if (S.prefs.nostrBackup && S.mints.length && S.prefs.mintBackupList !== S.mints.map(m => m.url).join(' ') && Date.now() - mintBackupTry > 10 * 60e3) scheduleMintBackup(startup ? 4000 : 0);
}
let tickCount = 0;
setInterval(() => { if (document.hidden || tabLocked || $('#layer .sheet')) return; tickCount++; backgroundTick().then(() => { if (!$('#layer .sheet') && tab !== 'arcade') refresh(); }); }, 30000);
// A Lightning invoice made in the last half hour is checked every 8 s while NUTCADE is open, in case the mint's
// live update was missed (for example while the connection dropped), so a paid invoice never waits for the 30 s tick.
setInterval(() => {
  if (document.hidden || tabLocked || (vault.on && !vault.open) || !S.seed) return;
  const fresh = S.quotes.filter(q => q.kind === 'bolt11' && Date.now() - (txById(q.txId)?.ts || 0) < 30 * 60e3);
  for (const q of fresh) checkQuote(q).then(r => { if (r === 'paid' && !$('#layer .sheet') && tab !== 'arcade') refresh(); }).catch(() => {});
}, 8000);

function livePrice(v, cur) {
  if (cur !== S.prefs.currency) return;
  const had = price.rate; price = { rate: v, at: Date.now(), cur };
  const f = $('.credits .fiat'); if (f) f.textContent = '≈ ' + fiatOf(+f.dataset.sats);
  else if (!had && tab === 'wallet' && !$('#layer .sheet')) refresh();
}
/* A link like …/#token=cashuB… (from an NFC card or a shared link) opens the token once the wallet is unlocked. */
let pendingLink = null;
function readHashLink() { try { const h = decodeURIComponent(location.hash || ''); const m = h.match(/(cashu[AB][A-Za-z0-9_\-+/=]{20,}|creqA[A-Za-z0-9_\-+/=]+|challenge=[A-Za-z0-9_-]{40,}(?:&r=r[01]\.[A-Za-z0-9_-]+)?|hunt=[0-9a-f]{64}\.\d{1,2}\.\d{1,2}\.\d{1,2}\.[A-Za-z0-9_-]{40,46})/); if (m) { pendingLink = m[1]; history.replaceState(null, '', location.pathname + location.search); return true; } } catch (e) {} return false; }
readHashLink();
window.addEventListener('hashchange', () => { if (readHashLink()) refresh(); });   // a link opened while NUTCADE is already open
window.Nutcade = { loadCard, render, refresh, S, toast, parseSat, parseFiat, parseBtc, parseCount, btcAddr, fiatToSats, holdToasts, tr, fmtDate, fmtEn, locale: () => numLocale(), logoSVG, sfx, openSheet, closeSheet, esc, fmt, livePrice, celebrate, classify, handleScan, vault, live, startChallenge, challengeDone, sendResult, canChallenge: () => !!(S.seed && S.seed.backedUp), soundBytes, soundText, health, piggySaved, r7: { decodeBolt11, meltCost, meltCostNow: async (u, a, r) => { await getWallet(u); return meltCost(u, a, r); }, sharedX: (sk, pub) => hex(SECP.sharedX(sk, pub)), isBlocked, nwcLive, nwcListen, wdUsed, nwcSince: () => nwcSince }, r8: { spentDay: () => limitUsed(), limitLeft: () => limitLeft(), sendEcash: (a, n, l, u) => sendEcash(a, n, l, u || S.active), newRequest: (a, m) => newRequest(a, m), backupData: () => backupData(), mintMax: u => mintMax(u), moveQuote: (f, t, a) => moveQuote(f, t, a) } };
setLang();
/* Offline: a service worker keeps a copy of the app (network first, so updates still arrive right away). */
try { if ('serviceWorker' in navigator && window.top === window.self && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) navigator.serviceWorker.register('sw.js').catch(() => {}); } catch (e) {}
if (!vault.on) mergeMintSpellings();   // with a PIN, this runs when the vault opens (hydrateFromVault)
render();
if (S.mints.length && !(vault.on && !vault.open)) setTimeout(() => backgroundTick(true).then(() => { if (!$('#layer .sheet') && tab !== 'arcade') refresh(); }), 1200);
})();
