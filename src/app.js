/* NUTCADE wallet core + UI */
(function(){
'use strict';
const L = window.CashuLib;
const $ = (s, r=document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = a => a == null ? 0 : (typeof a === 'object' && typeof a.toNumber === 'function') ? a.toNumber() : Number(a) || 0;
const sum = ps => (ps || []).reduce((t, p) => t + num(p.amount), 0);
const fmt = n => Math.round(num(n)).toLocaleString('en-US');
const unitTag = () => (window.NutPrefs && window.NutPrefs.btcSymbol) ? '' : 'SAT';
const money = n => (window.NutPrefs && window.NutPrefs.btcSymbol) ? '₿' + fmt(n) : fmt(n) + ' SAT';
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
const normUrl = u => { u = String(u || '').trim(); if (!/^https?:\/\//i.test(u)) u = 'https://' + u; return u.replace(/\/+$/, ''); };
const host = u => { try { const x = new URL(u); return x.host + (x.pathname === '/' ? '' : x.pathname); } catch (e) { return u; } };
const plain = ps => (ps || []).map(p => { const o = {}; for (const k in p) o[k] = p[k]; o.amount = num(p.amount); return o; });
const hex = b => Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ---------- storage ---------- */
/* Storage. When a PIN is set, the sensitive keys live only inside an encrypted vault:
   AES-GCM with a random data key, which is wrapped by a PIN-derived key (PBKDF2) and,
   optionally, by a passkey PRF secret (Face ID / fingerprint). */
const raw = {
  get(k, d) { try { const v = localStorage.getItem('nutcade:' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('nutcade:' + k, JSON.stringify(v)); return true; } catch (e) { return false; } },
  del(k) { try { localStorage.removeItem('nutcade:' + k); } catch (e) {} }
};
const VAULT_KEYS = ['seed', 'proofs', 'pending', 'quotes', 'txs', 'p2pk', 'requests', 'contacts'];
const vault = { on: raw.get('vault', null) != null, open: false, data: {}, dek: null, chain: Promise.resolve(), queued: false };
const store = {
  get(k, d) { if (vault.on && VAULT_KEYS.includes(k)) return vault.open && vault.data[k] !== undefined ? vault.data[k] : d; return raw.get(k, d); },
  set(k, v) { if (vault.on && VAULT_KEYS.includes(k)) { if (!vault.open) return false; vault.data[k] = v; queueVaultWrite(); return true; } return raw.set(k, v); }
};
const b64e = u8 => btoa(String.fromCharCode(...new Uint8Array(u8)));
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
  const rec = raw.get('vault', {}); rec.data = { iv: b64e(iv), ct: b64e(ct) };
  if (!raw.set('vault', rec)) throw new Error("This browser won't save data.");
}
function queueVaultWrite() {
  if (vault.queued) return; vault.queued = true;
  vault.chain = vault.chain.then(() => { vault.queued = false; return sealData(); }).catch(() => { vault.queued = false; });
}
async function openVault(dek) {
  const rec = raw.get('vault');
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(rec.data.iv) }, dek, b64d(rec.data.ct));
  vault.data = JSON.parse(new TextDecoder().decode(pt)); vault.dek = dek; vault.open = true;
}
async function createVault(pin) {
  const dek = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']);
  const salt = rnd(16), kek = await kekFromPin(pin, salt, PBKDF2_ITER);
  vault.data = {}; for (const k of VAULT_KEYS) vault.data[k] = S[k] !== undefined ? S[k] : null;
  vault.dek = dek;
  if (!raw.set('vault', { v: 1, kdf: { alg: 'PBKDF2-SHA256', iter: PBKDF2_ITER, salt: b64e(salt) }, pin: await wrapDek(dek, kek) })) throw new Error("This browser won't save data.");
  await sealData();
  // prove it decrypts before deleting the plain copies
  const check = await unwrapDek(raw.get('vault').pin, kek); const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(raw.get('vault').data.iv) }, check, b64d(raw.get('vault').data.ct));
  if (JSON.parse(new TextDecoder().decode(pt)).seed?.mnemonic !== S.seed?.mnemonic) throw new Error('Encryption check failed. Your wallet was not changed.');
  vault.on = true; vault.open = true;
  for (const k of VAULT_KEYS) raw.del(k);
}
async function pinToDek(pin) {
  const rec = raw.get('vault');
  const kek = await kekFromPin(pin, b64d(rec.kdf.salt), rec.kdf.iter);
  try { return await unwrapDek(rec.pin, kek); } catch (e) { return null; }
}
async function changePin(oldPin, newPin) {
  const dek = await pinToDek(oldPin); if (!dek) throw new Error('Current PIN is wrong.');
  const salt = rnd(16), kek = await kekFromPin(newPin, salt, PBKDF2_ITER);
  const rec = raw.get('vault'); rec.kdf = { alg: 'PBKDF2-SHA256', iter: PBKDF2_ITER, salt: b64e(salt) }; rec.pin = await wrapDek(dek, kek);
  raw.set('vault', rec);
}
async function removeVault(pin) {
  const dek = await pinToDek(pin); if (!dek) throw new Error('PIN is wrong.');
  await vault.chain;
  for (const k of VAULT_KEYS) if (vault.data[k] != null) raw.set(k, vault.data[k]);
  raw.del('vault'); vault.on = false; vault.open = false; vault.dek = null; vault.data = {};
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
S.counters = store.get('counters', {});  // keysetId -> next counter (NUT-13)
let storageOk = store.set('probe', 1);
function save() {
  for (const k of ['mints', 'active', 'proofs', 'pending', 'txs', 'quotes', 'prefs']) storageOk = store.set(k, S[k]) && storageOk;
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
const counterSource = {
  async reserve(id, n) { const start = S.counters[id] || 0; if (n > 0) { S.counters[id] = start + n; persistCounters(); } return { start, count: n }; },
  async reserveAt(id, start, count) { const cur = S.counters[id] || 0; if (start < cur) throw new Error('Counter range already used.'); S.counters[id] = start + count; persistCounters(); return { start, count }; },
  async advanceToAtLeast(id, minNext) { if ((S.counters[id] || 0) < minNext) { S.counters[id] = minNext; persistCounters(); } },
  async snapshot() { return Object.assign({}, S.counters); },
  async setNext(id, next) { S.counters[id] = next; persistCounters(); }
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
async function secureMint(url) {
  const ps = S.proofs[url] || []; if (!ps.length) return 0;
  const w = await getWallet(url);
  const fresh = await withRepair(url, () => w.receive(ps));
  S.proofs[url] = plain(fresh); save();
  return sum(ps) - sum(fresh);
}
async function secureAll(onStep) {
  let fees = 0;
  for (const m of S.mints) { if (!(S.proofs[m.url] || []).length) continue; onStep && onStep(m); fees += await secureMint(m.url); }
  S.seed.secured = true; store.set('seed', S.seed);
  return fees;
}
async function restoreFromMint(url, onStep) {
  if (!S.mints.find(m => m.url === url)) await addMint(url);
  const w = await getWallet(url);
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
  const have = new Set((S.proofs[url] || []).map(p => p.secret));
  const fresh = found.filter(p => !have.has(p.secret));
  if (fresh.length) { addProofs(url, fresh); addTx({ type: 'in', method: 'ecash', amount: sum(fresh), mint: url, note: 'Recovered with recovery phrase' }); }
  return sum(fresh);
}

/* Same phrase used on another device can leave our counters behind: the mint answers 11003.
   Catch up by rescanning that mint (which also recovers anything new), then retry once. */
const isDupOutputs = e => e && (e.code === 11003 || /already signed/i.test(String(e.message || '')));
async function withRepair(url, fn) {
  try { const r = await fn(); opMark(url, true); return r; }
  catch (e) {
    if (!isDupOutputs(e)) { opMark(url, false, e); throw e; }
    await restoreFromMint(url);
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
    else if (m.t === 'busy' && m.id !== TAB_ID && !tabLocked && !booted) { tabLocked = true; render(); }
    else if (m.t === 'takeover' && m.id !== TAB_ID) { tabLocked = true; closeSheet(); if (window.Arcade && window.Arcade.playing()) document.querySelector('[data-g=exit]')?.click(); render(); }
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
  { url: 'https://mint.coinos.io', name: 'Coinos', blurb: 'Mint from the Coinos web wallet.' },
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
    return w;
  })();
  wallets[url] = p;
  try { return await p; } catch (e) { delete wallets[url]; throw friendly(e, url); }
}
function friendly(e, url) {
  const m = String(e && e.message || e);
  if (/Failed to fetch|NetworkError|Load failed|network/i.test(m)) {
    const inFrame = window.top !== window.self;
    return new Error(inFrame
      ? `Can't reach ${host(url || '')}. This preview blocks connections to mints. Open the NUTCADE file in a normal browser tab to use real sats.`
      : `Can't reach ${host(url || '')}. Check the address and your connection, then try again.`);
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
const pendingOut = () => S.pending.reduce((t, p) => t + sum(p.proofs), 0);

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
async function lnMintQuote(amount, note) {
  const url = S.active; const w = await getWallet(url);
  const q = await w.createMintQuoteBolt11(amount);
  const tx = addTx({ type: 'in', method: 'ln', amount, mint: url, note, status: 'pending', request: q.request, quote: q.quote });
  S.quotes.push({ kind: 'bolt11', quote: q.quote, request: q.request, amount, mint: url, txId: tx.id, expiry: q.expiry || null });
  save();
  return tx;
}
async function onchainMintQuote(note) {
  const url = S.active; const w = await getWallet(url);
  const k = new Uint8Array(32); crypto.getRandomValues(k);
  const privkey = hex(k), pubkey = hex(L.getPubKeyFromPrivKey(k));
  const q = await w.createMintQuoteOnchain(pubkey);
  const tx = addTx({ type: 'in', method: 'onchain', amount: 0, mint: url, note, status: 'pending', request: q.request, quote: q.quote });
  S.quotes.push({ kind: 'onchain', quote: q.quote, request: q.request, mint: url, txId: tx.id, privkey, expiry: q.expiry || null });
  save();
  return tx;
}
const busyQuotes = new Set();
async function checkQuote(q) {
  if (busyQuotes.has(q.quote)) return 'busy';
  if (!S.quotes.some(x => x.quote === q.quote)) { const t = txById(q.txId); return t && t.status === 'done' ? 'paid' : 'gone'; }
  busyQuotes.add(q.quote);
  try {
    const w = await getWallet(q.mint);
    if (q.kind === 'bolt11') {
      const r = await w.checkMintQuoteBolt11(q.quote);
      if (r.state === 'PAID') {
        let cfg;
        if (r.pubkey) {   // NUT-20 locked quote (npub.cash can lock payments to your Nostr key)
          const k = npcPrivFor(r.pubkey) || (S.p2pk.find(x => hex(L.getPubKeyFromPrivKey(L.hexToBytes(x.priv))) === String(r.pubkey).toLowerCase()) || {}).priv;
          if (!k) throw new Error("This payment is locked to a key this wallet doesn't have.");
          cfg = { privkey: k };
        }
        const proofs = await withRepair(q.mint, () => w.mintProofsBolt11(q.amount, r, cfg));
        addProofs(q.mint, proofs);
        updTx(q.txId, { status: 'done', ts: Date.now() });
        dropQuote(q); sfx('coin'); refresh();
        document.dispatchEvent(new CustomEvent('nutcade:paid', { detail: q.quote }));
        if (!$('#layer .sheet')) celebrate('in', q.amount);
        toast(`+${money(q.amount)} received`, 'lime');
        return 'paid';
      }
      if (r.state === 'ISSUED') {
        // The mint issued this deposit but we never stored the ecash (app closed mid-request). Recover it from the phrase.
        const got = await restoreFromMint(q.mint).catch(() => 0);
        dropQuote(q); updTx(q.txId, { status: 'done' }); refresh();
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
        const proofs = await withRepair(q.mint, () => w.mintProofsOnchain(avail, r, q.privkey));
        const got = sum(proofs);
        addProofs(q.mint, proofs);
        const t = txById(q.txId);
        if (t && t.status === 'pending') updTx(q.txId, { status: 'done', amount: got, ts: Date.now() });
        else addTx({ type: 'in', method: 'onchain', amount: got, mint: q.mint, note: t ? t.note : '', request: q.request, quote: q.quote });
        sfx('coin'); refresh(); toast(`+${money(got)} deposited on-chain`, 'lime');
        return 'paid';
      }
      if (q.expiry && Date.now() / 1000 > q.expiry) { dropQuote(q); const t = txById(q.txId); if (t && t.status === 'pending') updTx(q.txId, { status: 'expired' }); refresh(); return 'expired'; }
      return 'waiting';
    }
  } finally { busyQuotes.delete(q.quote); }
}
function dropQuote(q) { S.quotes = S.quotes.filter(x => x.quote !== q.quote); save(); }

function cleanToken(t) { t = String(t || '').trim().replace(/^(web\+)?cashu:(\/\/)?/i, ''); const m = t.match(/cashu[AB][A-Za-z0-9_\-+/=]+/); return m ? m[0] : t; }
function peekToken(t) {
  const meta = L.getTokenMetadata(cleanToken(t));
  return { mint: normUrl(meta.mint), amount: num(meta.amount), unit: meta.unit || 'sat', memo: meta.memo || '' };
}
async function receiveToken(token, note) {
  token = cleanToken(token);
  const meta = peekToken(token);
  if (meta.unit !== 'sat') throw new Error(`This token is in ${meta.unit}. NUTCADE handles sats only.`);
  if (!S.mints.find(m => m.url === meta.mint)) await addMint(meta.mint);
  const w = await getWallet(meta.mint);
  let proofs;
  try { const privs = allPrivs(); proofs = await withRepair(meta.mint, () => w.receive(token, privs.length ? { privkey: privs } : undefined)); }
  catch (e) { if (/witness|signature|p2pk|locked|locktime/i.test(e.message || '')) throw new Error("This ecash is locked to someone else's key, so this wallet can't claim it."); throw e; }
  addProofs(meta.mint, proofs);
  const got = sum(proofs);
  // mark own sent token as reclaimed if it matches
  const own = S.txs.find(t => t.token === token && (t.status === 'pending' || t.status === 'claimed'));   // our own unclaimed token came back
  if (own) updTx(own.id, { status: 'reclaimed' });
  return addTx({ type: 'in', method: 'ecash', amount: got, fee: Math.max(0, meta.amount - got), mint: meta.mint, note: note || meta.memo });
}

/* ---------- SEND ---------- */
async function sendEcash(amount, note, lockTo, url = S.active, opts = {}) {
  piggyGuard(amount);
  const w = await getWallet(url);
  const have = S.proofs[url] || [];
  if (sum(have) < amount) throw new Error(`Not enough credits. This mint holds ${money(sum(have))}.`);
  const outCfg = lockTo ? { send: { type: 'p2pk', options: Object.assign({ pubkey: lockTo }, opts.locktime ? { locktime: opts.locktime, refundKeys: [myLockPub()] } : {}, opts.hashlock ? { hashlock: opts.hashlock } : {}) }, keep: w.defaultOutputType() } : undefined;
  const { keep, send } = await withRepair(url, () => w.send(amount, have, { includeFees: true }, outCfg));
  S.proofs[url] = plain(keep);
  const token = L.getEncodedToken({ mint: url, proofs: send, unit: 'sat' });
  save();
  return addTx({ type: 'out', method: 'ecash', amount, fee: Math.max(0, sum(send) - amount), mint: url, note, status: 'pending', token, sent: plain(send), locked: lockTo || null });
}
async function meltQuote(kind, dest, amount) {
  const w = await getWallet(S.active);
  if (kind === 'ln') return w.createMeltQuoteBolt11(dest);
  return w.createMeltQuoteOnchain(dest, amount);
}
async function payMelt(kind, mq, feeIndex, note, dest, url = S.active) {
  const w = await getWallet(url);
  const amount = num(mq.amount);
  const reserve = kind === 'ln' ? num(mq.fee_reserve) : num((mq.fee_options || []).find(f => f.fee_index === feeIndex)?.fee_reserve);
  const need = amount + reserve;
  const have = S.proofs[url] || [];
  if (sum(have) < need) throw new Error(`Not enough credits. Need ${money(need)} including fees, this mint holds ${fmt(sum(have))}.`);
  piggyGuard(need);
  const { keep, send } = await withRepair(url, () => w.send(need, have, { includeFees: true }));
  const tx = addTx({ type: 'out', method: kind, amount, mint: url, note, status: 'pending', request: dest, quote: mq.quote });
  const pend = { id: uid(), mint: url, proofs: plain(send), quote: mq.quote, kind, txId: tx.id };
  S.proofs[url] = plain(keep); S.pending.push(pend); save();
  try {
    const res = await withRepair(url, () => kind === 'ln' ? w.meltProofsBolt11(mq, send) : w.meltProofsOnchain(mq, send, feeIndex));
    const change = plain(res.change || []);
    if (change.length) addProofs(url, change);
    const st = res.quote && res.quote.state;
    if (st === 'PAID') {
      S.pending = S.pending.filter(p => p.id !== pend.id);
      updTx(tx.id, { status: 'done', fee: Math.max(0, sum(send) - amount - sum(change)), outpoint: res.quote.outpoint || null, preimage: res.quote.payment_preimage || null });
    } else {
      updTx(tx.id, { status: 'pending', fee: reserve });
    }
    save();
    return txById(tx.id);
  } catch (e) {
    await reconcile(pend).catch(() => {});
    throw friendly(e, url);
  }
}
async function reconcile(pend) {
  const w = await getWallet(pend.mint);
  let qs = null;
  try { qs = pend.kind === 'ln' ? await w.checkMeltQuoteBolt11(pend.quote) : await w.checkMeltQuoteOnchain(pend.quote); } catch (e) {}
  if (qs && qs.state === 'PAID') {
    S.pending = S.pending.filter(p => p.id !== pend.id);
    updTx(pend.txId, { status: 'done', outpoint: qs.outpoint || null });
    return 'paid';
  }
  const states = await w.checkProofsStates(pend.proofs);
  const unspent = pend.proofs.filter((p, i) => states[i] && states[i].state === 'UNSPENT');
  const stillPending = states.some(s => s.state === 'PENDING');
  if (!stillPending) {
    if (unspent.length) addProofs(pend.mint, unspent);
    S.pending = S.pending.filter(p => p.id !== pend.id);
    const allSpent = unspent.length === 0;
    updTx(pend.txId, { status: allSpent ? 'done' : 'failed' });
    save();
    return allSpent ? 'paid' : 'returned';
  }
  return 'pending';
}
async function checkClaim(tx) {
  const w = await getWallet(tx.mint);
  const st = await w.checkProofsStates(tx.sent);
  const cur = txById(tx.id);
  if (st.every(s => s.state === 'SPENT') && cur && cur.status === 'pending') { updTx(tx.id, { status: 'claimed' }); return true; }
  return false;
}
async function cleanWallet() {
  let removed = 0;
  for (const m of S.mints) {
    const ps = S.proofs[m.url] || []; if (!ps.length) continue;
    const w = await getWallet(m.url);
    const st = await w.checkProofsStates(ps);
    const keep = ps.filter((p, i) => !st[i] || st[i].state !== 'SPENT');
    removed += ps.length - keep.length;
    S.proofs[m.url] = keep;
  }
  save();
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
const NUMRE = /\d[\d,.]*/g;
function tr(s) {
  if (LANG === 'en' || !s) return s;
  const d = I18N[LANG]; if (!d) return s; if (!d.done) d.done = new Set();
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(s); const core = m[2].replace(/\s+/g, ' '); if (!core || !/[A-Za-z]/.test(core)) return s;
  let out = d.t[core];
  if (out === undefined) { const nums = []; const key = core.replace(NUMRE, x => { nums.push(x); return '{#}'; }); if (nums.length && d.t[key] !== undefined) { let i = 0; out = d.t[key].replace(/\{#\}/g, () => nums[i++] ?? ''); } }
  if (out === undefined && d.re) for (const [re, rep_] of d.re) { const mm = re.exec(core); if (mm) { out = rep_.replace(/\$(\d)/g, (_, k) => tr(mm[+k] || '')); break; } }
  if (out === undefined) { if (window.__i18nMiss) { if (!d.vals) d.vals = new Set(Object.values(d.t)); if (!d.vals.has(core) && !d.done.has(core)) window.__i18nMiss.add(core); } return s; }
  if (d.done) d.done.add(out.replace(/\s+/g, ' ').trim());
  return m[1] + out + m[3];
}
const NOI18N = '.code,.words,textarea,script,style,canvas,.credit-num,.qr,.share-card,[data-noi18n],.tx .note:not(.empty),.mint-pill,.kv dd.tiny';
const i18nFilter = { acceptNode: n => n.nodeType === 1 && n.matches(NOI18N) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT };
function trAttrs(el) { for (const a of ['placeholder', 'aria-label', 'title', 'alt']) { const v = el.getAttribute(a); if (v) { const t = tr(v); if (t !== v) el.setAttribute(a, t); } } }
function trNode(root) {
  if (LANG === 'en' || !root) return;
  if (root.nodeType === 3) { const p = root.parentElement; if (p && !p.closest(NOI18N)) { const t = tr(root.nodeValue); if (t !== root.nodeValue) root.nodeValue = t; } return; }
  if (root.nodeType !== 1 || root.closest(NOI18N)) return;
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
function logoSVG(word = 'NUTCADE', withTag = true) {
  const s = 6, gap = 1, cols = word.length * 6 + (word.length - 1) * gap;
  const pad = 4, mascotH = ACORN.length + 2;
  const W = cols + pad * 2, H = mascotH + 7 + pad * 2 + (withTag ? 6 : 0);
  const cells = [];
  [...word].forEach((ch, i) => { const g = GLYPHS[ch]; if (!g) return; g.forEach((row, y) => [...row].forEach((b, x) => { if (b === '1') cells.push([pad + i * 7 + x, pad + mascotH + y]); })); });
  const rect = (x, y, c, o = 0) => `<rect x="${(x - o) * s}" y="${(y - o) * s}" width="${s + o * 2 * s}" height="${s + o * 2 * s}" fill="${c}"/>`;
  const layer = (dx, dy, c, o = 0) => cells.map(([x, y]) => rect(x + dx, y + dy, c, o)).join('');
  const ax = Math.floor(W / 2 - ACORN[0].length / 2), ay = pad - 1;
  const ac = { '1': '#b8651f', '2': '#6b3b12', '3': '#3d2208', '4': '#ffd79a' };
  let acorn = '';
  ACORN.forEach((row, y) => [...row].forEach((c, x) => { if (c !== '.') acorn += rect(ax + x + 0.5, ay + y, ac[c]); }));
  let acornOutline = '';
  ACORN.forEach((row, y) => [...row].forEach((c, x) => { if (c !== '.') acornOutline += rect(ax + x + 0.5, ay + y, '#0a0717', 0.5); }));
  const stars = [[2, 3], [W - 4, 2], [W - 8, 9], [6, 10], [W - 3, 14]].map(([x, y]) => `<g fill="#2de2ff"><rect x="${x * s}" y="${(y - .5) * s}" width="${s}" height="${s * 2}"/><rect x="${(x - .5) * s}" y="${y * s}" width="${s * 2}" height="${s}"/></g>`).join('');
  const tagTop = (pad + mascotH + 7 + 1.6) * s, tagH = 4 * s, tagY = tagTop + tagH / 2;
  return `<svg viewBox="0 0 ${W * s} ${H * s}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="NUTCADE logo" shape-rendering="crispEdges">
<defs><linearGradient id="chrome" x1="0" y1="0" x2="0" y2="1" gradientUnits="objectBoundingBox">
<stop offset="0" stop-color="#fff6c9"/><stop offset=".28" stop-color="#ffd23a"/><stop offset=".28" stop-color="#ff9a1f"/><stop offset=".55" stop-color="#ff3d8b"/>
<stop offset=".55" stop-color="#0a0717"/><stop offset=".575" stop-color="#0a0717"/><stop offset=".575" stop-color="#c13dff"/><stop offset=".78" stop-color="#7a3dff"/><stop offset=".78" stop-color="#0a0717"/><stop offset=".8" stop-color="#0a0717"/><stop offset=".8" stop-color="#2de2ff"/><stop offset="1" stop-color="#2de2ff"/>
</linearGradient></defs>
${stars}
<g>${acornOutline}${acorn}</g>
<g transform="skewX(-8) translate(${Math.round(Math.tan(8 * Math.PI / 180) * (pad + mascotH + 3.5) * s)} 0)">
<g>${layer(0, 0, '#0a0717', 1)}</g>
<g>${layer(2, 2, '#ff3d8b')}</g>
<g>${layer(1, 1, '#2de2ff')}</g>
<g>${layer(0, 0, '#0a0717', .5)}</g>
<g fill="url(#chrome)"><rect x="${pad * s}" y="${(pad + mascotH) * s}" width="${cols * s}" height="${7 * s}" fill="url(#chrome)" mask="url(#letters)"/></g>
<mask id="letters" maskUnits="userSpaceOnUse">${layer(0, 0, '#fff')}</mask>
</g>
${withTag ? `<g class="tagline"><text x="${W * s / 2}" y="${tagY}" dominant-baseline="central" text-anchor="middle" font-family="'Press Start 2P', monospace" font-size="${s * 2.6}" fill="#ffcf3a" stroke="#0a0717" stroke-width="${s * 0.6}" stroke-linejoin="round" paint-order="stroke" textLength="${Math.round((W - 8) * s)}" lengthAdjust="spacingAndGlyphs">INSERT ECASH · PRESS START</text></g>` : ''}
</svg>`;
}
window.NutLogo = logoSVG;


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
    <div class="row wrap"><label class="btn sm" for="scanFile" style="cursor:pointer">Scan a photo</label><input id="scanFile" type="file" accept="image/*" hidden><button class="btn sm" data-act="scanPaste">Paste instead</button>${nfcBtn('nfcScan', 'Tap NFC')}${window.Chiptune && window.Chiptune.canListen() ? '<button class="btn sm violet" data-act="ctListen">Listen</button>' : ''}</div>
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
/* Figure out what a scanned or pasted string is and open the right screen for it. */
function classify(raw) {
  let t = String(raw || '').trim();
  if (/cashu[AB][A-Za-z0-9_\-+/=]{20,}/.test(t)) return { kind: 'token', value: cleanToken(t) };
  { const m = t.match(/creqA[A-Za-z0-9_\-+/=]+|creqb1[02-9ac-hj-np-z]+/i); if (m) return { kind: 'request', value: m[0] }; }
  { const m = t.match(/^(?:nostr:)?((?:npub1|nprofile1)[02-9ac-hj-np-z]+)$/i); if (m && parseNostrAddr(m[1])) return { kind: 'nostr', value: m[1].toLowerCase() }; }
  const low = t.toLowerCase();
  if (low.startsWith('bitcoin:')) {
    const [addr, q] = t.slice(8).split('?'); const p = new URLSearchParams(q || '');
    const ln = p.get('lightning'); if (ln && /^ln(bc|tb|bcrt)/i.test(ln)) return { kind: 'invoice', value: ln.toLowerCase() };
    const btc = parseFloat(p.get('amount') || ''); return { kind: 'btc', value: addr, amount: btc > 0 ? Math.round(btc * 1e8) : null };
  }
  t = t.replace(/^lightning:/i, '');
  if (/^ln(bc|tb|bcrt|tbs)[0-9a-z]{50,}$/i.test(t)) return { kind: 'invoice', value: t.toLowerCase() };
  if (/^lnurl1[0-9a-z]+$/i.test(t)) return { kind: 'lnurl', value: t.toLowerCase() };
  if (/^[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i.test(t)) return { kind: 'lnaddress', value: t.toLowerCase() };
  if (/^(bc1|tb1|bcrt1)[a-z0-9]{20,90}$/i.test(t) || /^[13mn2][a-km-zA-HJ-NP-Z1-9]{25,39}$/.test(t)) return { kind: 'btc', value: t, amount: null };
  if (/^https?:\/\/[^\s]+$/i.test(t)) return { kind: 'mint', value: normUrl(t) };
  return { kind: 'unknown' };
}
// A ur: code that fits in one QR (or was pasted) decodes on its own. Returns the text, false for one frame of a longer code, null if it isn't ur:.
async function urSingle(text) {
  if (!/^ur:/i.test(String(text).trim()) || !window.NutUR) return null;
  const d = NutUR.decoder(); try { await d.receive(String(text).trim()); } catch (e) { return null; }
  return d.done() ? d.text() : false;
}
function handleScan(text) {
  if (/^ur:bytes\//i.test(String(text || '').trim())) { urSingle(text).then(t => t ? handleScan(t) : toast("That's one frame of an animated QR code. Scan it live with the camera instead.", 'gold')); return; }
  const c = classify(text);
  if (c.kind === 'token') { closeSheet(); openReceive('ecash'); const box = $('#tokIn'); if (box) { box.value = c.value; box.dispatchEvent(new Event('input', { bubbles: true })); } return; }
  if (c.kind === 'unknown') { closeSheet(); sfx('err'); toast("That QR code isn't something NUTCADE can use.", 'gold'); return; }
  if (c.kind === 'request') { if (needSeed()) return; return openPayRequest(c.value); }
  if (c.kind === 'nostr') { if (needSeed()) return; const k = S.contacts.find(x => x.pubkey === parseNostrAddr(c.value).pubkey); return k ? openPayContact(k.id) : openContactEdit(null, { nostr: c.value }); }
  if (needMint()) return;
  if (c.kind === 'invoice') { openSend('ln'); const d = $('#destIn'); if (d) { d.value = c.value; const b = $('[data-act="doMeltQuote"]'); if (b) b.click(); } return; }
  if (c.kind === 'btc') { openSend('onchain'); const d = $('#destIn'); if (d) d.value = c.value; if (c.amount && $('#amtIn')) setSats($('#amtIn'), c.amount); return; }
  if (c.kind === 'lnaddress' || c.kind === 'lnurl') return openPayLnurl(c.value);
  if (c.kind === 'mint') { openMintPicker(); const u = $('#mintUrl'); if (u) { u.value = c.value; u.focus(); } toast('Check the address, then tap Add', 'cyan'); }
}
function lnurlToUrl(v) {
  if (v.includes('@')) { const [user, domain] = v.split('@'); return `https://${domain}/.well-known/lnurlp/${encodeURIComponent(user)}`; }
  const d = L.bech32.decode(v, 2000); return new TextDecoder().decode(L.bech32.fromWords(d.words));
}
function openPayLnurl(target) {
  openSheet('Pay', `<div class="tiny muted">To</div><div class="code" style="color:var(--ink)">${esc(target.length > 48 ? target.slice(0, 24) + '…' + target.slice(-12) : target)}</div>
    <div class="field"><label for="amtIn">Amount (sat)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="1000" autocomplete="off"></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200"></div>
    <button class="btn solid pink block" data-act="lnurlQuote" data-t="${esc(target)}">Get quote</button><div id="sheetErr"></div>`);
}
async function lnurlInvoice(target, sats, comment) {
  const base = await fetch(lnurlToUrl(target)).then(r => { if (!r.ok) throw new Error(`That address didn't answer (${r.status}).`); return r.json(); });
  if (base.status === 'ERROR') throw new Error(base.reason || 'That address returned an error.');
  if (base.tag !== 'payRequest' || !base.callback) throw new Error("That address isn't set up to receive payments.");
  const msat = sats * 1000;
  if (msat < base.minSendable || msat > base.maxSendable) throw new Error(`This address accepts ${fmt(Math.ceil(base.minSendable / 1000))} to ${fmt(Math.floor(base.maxSendable / 1000))} sats.`);
  const u = new URL(base.callback); u.searchParams.set('amount', String(msat));
  if (comment && base.commentAllowed) u.searchParams.set('comment', comment.slice(0, base.commentAllowed));
  const inv = await fetch(u.toString()).then(r => r.json());
  if (inv.status === 'ERROR' || !inv.pr) throw new Error(inv.reason || "Couldn't get an invoice from that address.");
  return inv.pr;
}

/* ---------- payment effects: coin drop on receive, coin launch on send ---------- */
const COIN = ['..yyyy..', '.yYYYYy.', 'yYyyyyYy', 'yYyYYyYy', 'yYyYYyYy', 'yYyyyyYy', '.yYYYYy.', '..yyyy..'];
function celebrate(dir, amount) {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const old = document.getElementById('fxLayer'); if (old) old.remove();
  const layer = document.createElement('div'); layer.id = 'fxLayer'; layer.setAttribute('aria-hidden', 'true');
  const label = document.createElement('div'); label.className = 'fx-label ' + (dir === 'in' ? 'in' : 'out');
  const big = document.createElement('b'); big.textContent = dir === 'in' ? '1UP!' : 'SENT!';
  const amt = document.createElement('span'); amt.textContent = (dir === 'in' ? '+' : '−') + money(amount);
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
    if (c) { c.setAttribute('aria-label', label || 'QR code'); el.appendChild(c); return; }
    animatedQR(el, t, label);
  }, 0);
  return `<div class="qr" id="${id}"></div>`;
}
/* A long code plays as a loop of small QR codes (BC-UR, the format cashu.me uses), drawn in uppercase so each frame
   is a compact alphanumeric QR. Any frame order works and missed frames are fine: the scanner keeps collecting. */
function animatedQR(el, text, label) {
  if (!window.NutUR) { el.outerHTML = '<div class="notice cyan">Too long for one QR code. Use Copy or Play as sound instead.</div>'; return; }
  const enc = NutUR.encoder(text, 150); let n = 0;
  el.classList.add('qr-anim'); el.setAttribute('role', 'img'); el.setAttribute('aria-label', (label || 'QR code') + ', animated');
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
let toastT;
function toast(msg, c = 'lime') {
  let el = $('#toast'); if (!el) { el = document.createElement('div'); el.id = 'toast'; el.className = 'toast'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
  el.style.setProperty('--c', `var(--${c})`); el.textContent = tr(msg); el.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => { el.hidden = true; }, 3200);
}
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
function satsOf(id) {
  const el = typeof id === 'string' ? $('#' + id) : id; if (!el) return 0;
  const v = String(el.value || '').trim(); if (!v) return 0;
  if (el.dataset.cur === 'fiat') {
    if (!canFiat()) throw new Error('The exchange rate is not available right now. Switch the amount to SAT.');
    const f = parseFloat(v.replace(/[^0-9.,]/g, '').replace(/,(?=\d{1,2}$)/, '.').replace(/,/g, ''));
    return f > 0 ? Math.round(f / price.rate * 1e8) : 0;
  }
  return parseInt(v.replace(/[^0-9]/g, ''), 10) || 0;
}
function setSats(el, n) { if (!el) return; el.dataset.cur = 'sat'; el.value = n; const w = el.closest('.amtwrap'); if (w) { const b = w.querySelector('.unitbtn'); if (b) b.textContent = 'SAT'; el.setAttribute('inputmode', 'numeric'); } amtConv(el); }
function amtConv(el) {
  const out = el.parentElement && el.parentElement.parentElement && el.parentElement.parentElement.querySelector('.amtconv'); if (!out) return;
  let t = '';
  try {
    if (el.value && canFiat()) {
      if (el.dataset.cur === 'fiat') { const n = satsOf(el); t = n ? `≈ ${money(n)}` : ''; }
      else { const n = satsOf(el); t = n ? `≈ ${fiatOf(n)}` : ''; }
    }
  } catch (e) {}
  out.textContent = t;
}
function enhanceAmounts(root) {
  if (!root || !S.prefs.fiat) return;
  root.querySelectorAll('input.amount:not([data-enh])').forEach(el => {
    el.dataset.enh = '1'; el.dataset.cur = 'sat';
    const wrap = document.createElement('div'); wrap.className = 'amtwrap';
    el.parentElement.insertBefore(wrap, el); wrap.appendChild(el);
    wrap.insertAdjacentHTML('beforeend', `<button type="button" class="unitbtn" data-act="amtUnit" aria-label="Switch between sats and ${esc(S.prefs.currency)}">SAT</button>`);
    wrap.insertAdjacentHTML('afterend', '<div class="amtconv tiny muted" aria-live="polite"></div>');
    el.addEventListener('input', () => amtConv(el));
    if (S.prefs.amtFiat && canFiat() && !el.value) toggleUnit(el);
    amtConv(el);
  });
}
function toggleUnit(el) {
  if (!canFiat() && el.dataset.cur !== 'fiat') { toast('Turn on Show Bitcoin price in Settings to enter amounts in your currency.', 'gold'); return; }
  let n = 0; try { n = satsOf(el); } catch (e) {}
  const toFiat = el.dataset.cur !== 'fiat';
  el.dataset.cur = toFiat ? 'fiat' : 'sat';
  el.setAttribute('inputmode', toFiat ? 'decimal' : 'numeric');
  el.value = n ? (toFiat ? (n / 1e8 * price.rate).toFixed(2) : String(n)) : '';
  const b = el.parentElement.querySelector('.unitbtn'); if (b) b.textContent = toFiat ? S.prefs.currency : 'SAT';
  S.prefs.amtFiat = toFiat; save(); amtConv(el);
}
function openSheet(title, html, onOpen) {
  closeSheet();
  const layer = $('#layer');
  layer.innerHTML = `<div class="scrim" data-scrim><div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="sheet-head"><h3>${esc(title)}</h3><button class="x" data-act="close" aria-label="Close">X</button></div><div class="sheet-body" style="display:grid;gap:14px">${html}</div></div></div>`;
  const body = layer.querySelector('.sheet-body');
  enhanceAmounts(body);
  sheetCleanup = onOpen ? onOpen(body) : null;
  const f = layer.querySelector('input,textarea'); if (f && !matchMedia('(pointer:coarse)').matches) f.focus();
  return body;
}
function closeSheet() { if (typeof sheetCleanup === 'function') sheetCleanup(); sheetCleanup = null; $('#layer').innerHTML = ''; }
function setBody(html, onOpen) { const b = $('#layer .sheet-body'); if (!b) return; if (typeof sheetCleanup === 'function') sheetCleanup(); b.innerHTML = html; enhanceAmounts(b); sheetCleanup = onOpen ? onOpen(b) : null; }
const busyHTML = msg => `<div class="row" style="justify-content:center;padding:24px 0"><span class="spinner">${esc(msg)}</span></div>`;
const errHTML = e => `<div class="notice red">${esc(e && e.message || e)}</div>`;

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
    npcSocketStop(); liveSync(); dmStop();
    app.innerHTML = `<div class="wrap"><header class="marquee"><div class="bulbs top">${'<i></i>'.repeat(14)}</div><h1 class="sr">NUTCADE</h1><div class="logo">${logoSVG()}</div><div class="bulbs bot">${'<i></i>'.repeat(14)}</div></header>
      <section class="screen"><div class="panel hot"><span class="h2" style="color:var(--pink)">Open in another tab</span>
      <p style="margin:0">NUTCADE is already open in another tab or window. Running two copies at once can make them overwrite each other's ecash, so this one is paused.</p>
      <button class="btn solid gold block" data-act="takeover">Use NUTCADE here instead</button></div></section></div>`;
    return;
  }
  if (vault.on && !vault.open) {
    app.innerHTML = `<div class="wrap" style="padding-bottom:calc(32px + env(safe-area-inset-bottom,0px))">
      <header class="marquee"><div class="bulbs top">${'<i></i>'.repeat(14)}</div><h1 class="sr">NUTCADE</h1><div class="logo">${logoSVG()}</div><div class="bulbs bot">${'<i></i>'.repeat(14)}</div></header>
      ${viewLock()}</div>`;
    if (window.NutAudio) window.NutAudio.stopMusic();
    if (window.PriceChart) window.PriceChart.disconnect();
    return;
  }
  if (needsGate()) {
    app.innerHTML = `<div class="wrap" style="padding-bottom:calc(32px + env(safe-area-inset-bottom,0px))">
      <header class="marquee"><div class="bulbs top">${'<i></i>'.repeat(14)}</div><h1 class="sr">NUTCADE</h1><div class="logo">${logoSVG()}</div><div class="bulbs bot">${'<i></i>'.repeat(14)}</div></header>
      ${storageOk ? '' : '<div class="notice red" style="margin-top:14px">This browser is blocking storage, so your wallet would vanish on reload. Open NUTCADE in a normal browser tab.</div>'}
      ${viewGate()}</div>`;
    if (window.NutAudio) window.NutAudio.stopMusic();
    return;
  }
  if (tab === 'wallet') body = viewWallet();
  else if (tab === 'arcade') body = `<section class="screen" id="arcadeScreen"></section>`;
  else if (tab === 'history') body = viewHistory();
  else if (tab === 'mints') body = viewMints();
  else body = viewSettings();
  app.innerHTML = `<div class="wrap">
    <header class="marquee"><div class="bulbs top">${'<i></i>'.repeat(14)}</div><h1 class="sr">NUTCADE</h1><div class="logo">${logoSVG()}</div><div class="bulbs bot">${'<i></i>'.repeat(14)}</div></header>
    ${storageOk ? '' : '<div class="notice red" style="margin-top:14px">This browser is blocking storage, so ecash you receive here would vanish on reload. Open NUTCADE in a normal browser tab before adding funds.</div>'}
    ${body}
  </div>
  <nav class="tabbar" aria-label="Sections"><div class="in">${TABS.map(([k, l]) => `<button class="tab" data-act="tab" data-tab="${k}" ${tab === k ? 'aria-current="page"' : ''}>${ICONS[k]}<span>${l}</span></button>`).join('')}</div></nav>`;
  if (tab === 'arcade' && window.Arcade) { window.Arcade.mountList($('#arcadeScreen')); const cp = challengePanel(); if (cp) $('#arcadeScreen').insertAdjacentHTML('beforeend', cp); if (window.Trophies) window.Trophies.mount($('#arcadeScreen')); }
  if (tab === 'mints' && S.mints.some(m => !health[m.url] || Date.now() - health[m.url].at > 5 * 60e3)) setTimeout(checkHealth, 0);
  if (window.Trophies) setTimeout(() => window.Trophies.checkWallet(), 0);
  setTimeout(liveSync, 0);
  setTimeout(dmListen, 0);
  netBanner();
  if (pendingLink && S.seed && S.seed.backedUp) { const t = pendingLink; pendingLink = null; setTimeout(() => { if (/^challenge=/.test(t)) { let rec = null; try { rec = onChallenge(JSON.parse(new TextDecoder().decode(unb64url(t.slice(10)))), 'link'); } catch (e) {} if (rec && rec.dir === 'in') openChallengeIn(rec.id); else if (rec) openChallengeSend(rec.id); else toast("That challenge link isn't valid.", 'gold'); } else handleScan(t); }, 300); }
  if (S.prefs.npc) npcSocketStart();
  if (window.NutAudio && !(window.Arcade && window.Arcade.playing())) { if (tab === 'arcade') window.NutAudio.music('title'); else window.NutAudio.stopMusic(); }
  if (tab === 'wallet' && window.Arcade) { const el = $('#topScore'); if (el) el.innerHTML = window.Arcade.topLine(); }
  if (window.PriceChart) { if (tab === 'wallet') window.PriceChart.mount($('#priceMount')); else window.PriceChart.disconnect(); }
}
function refresh() { if ($('#layer .sheet')) { /* keep sheet */ } const y = window.scrollY; render(); window.scrollTo(0, y); }

function txRow(t) {
  const sign = t.type === 'in' ? '+' : '−';
  const method = { ln: 'LN', ecash: 'ECASH', onchain: 'ON-CHAIN' }[t.method];
  const stat = (t.status !== 'done' ? `<span class="chip ${t.status === 'pending' ? 'pending' : t.status === 'claimed' || t.status === 'reclaimed' ? 'claimed' : 'failed'}">${esc(t.status.toUpperCase())}</span>` : '') + (t.lockUntil && t.status === 'pending' ? '<span class="chip ecash">LOCKED</span>' : '') + (t.move ? '<span class="chip claimed">MOVE</span>' : '') + (t.cashier ? '<span class="chip ln">SALE</span>' : '');
  const amt = t.method === 'onchain' && t.type === 'in' && !t.amount ? 'WAIT' : sign + fmt(t.amount);
  return `<button class="tx ${t.type}" data-act="tx" data-id="${t.id}"><span class="ico" aria-hidden="true">${t.type === 'in' ? '↓' : '↑'}</span>
    <span class="mid"><div class="note ${t.note ? '' : 'empty'}">${esc(t.note || 'Add a note…')}</div>
    <div class="meta"><span class="chip ${t.method === 'ecash' ? 'ecash' : 'ln'}">${method}</span>${stat}<span>${timeAgo(t.ts)}</span></div></span>
    <span class="amt">${amt}</span></button>`;
}
function timeAgo(ts) {
  const d = (Date.now() - ts) / 1000;
  if (d < 60) return 'just now'; if (d < 3600) return Math.floor(d / 60) + 'm ago'; if (d < 86400) return Math.floor(d / 3600) + 'h ago';
  if (d < 604800) return Math.floor(d / 86400) + 'd ago';
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

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
  return `<ol class="words" aria-label="Recovery phrase">${words.map((w, i) => `<li><span>${i + 1}</span>${esc(w)}</li>`).join('')}</ol>`;
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
    <div class="field"><div class="row between"><label>Mints to scan</label><button class="btn sm violet" data-act="findMints">Find my mints on Nostr</button></div><div id="nostrMints" class="tiny muted"></div><div class="txs" id="rmList">${urls.map((u, i) => `<label class="toggle" for="rm${i}" style="font-size:19px"><span style="overflow-wrap:anywhere;min-width:0">${esc(host(u))}</span><input id="rm${i}" type="checkbox" data-rmint="${esc(u)}" ${S.mints.find(m => m.url === u) ? 'checked' : ''}></label>`).join('')}</div></div>
    <div class="field"><label for="rmExtra">Other mint addresses (one per line)</label><textarea id="rmExtra" class="inp" placeholder="https://mint.example.com" autocomplete="off" autocapitalize="off" spellcheck="false"></textarea></div>
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
    <button class="linkbtn tiny" style="justify-self:center;color:var(--pink)" data-act="support">♥ Support NUTCADE</button>
  </section>`;
  const bal = balanceOf(m.url), tot = totalBalance(), po = pendingOut();
  const recent = S.txs.slice(0, 4);
  return `<section class="screen">${nag}${legacy}
    <div class="credits">
      <div class="row between"><span class="label">Credits</span><span class="row" style="gap:10px">${tot !== bal ? `<span class="tiny muted">All mints ${money(tot)}</span>` : ''}${vault.on ? '<button class="lockbtn" data-act="lockNow" aria-label="Lock wallet" title="Lock wallet"><svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M5 7V5a3 3 0 0 1 6 0v2h1v8H4V7zm1 0h4V5a2 2 0 0 0-4 0zm1 3v3h2v-3z"/></svg></button>' : ''}</span></div>
      <div class="credit-num" aria-live="polite">${S.prefs.btcSymbol ? '₿' : ''}${fmt(bal)}<small>${unitTag()}</small></div>
      ${fiatOf(bal) ? `<div class="tiny muted fiat" data-sats="${bal}">≈ ${fiatOf(bal)}</div>` : ''}
      ${piggySaved() ? `<div class="tiny piggy-line">${pigSVG('tiny')}<span>${money(piggySaved())} in your piggy bank · ${money(Math.max(0, tot - piggySaved()))} to spend</span></div>` : ''}
      <button class="mint-pill" data-act="pickMint" aria-label="Change mint"><span class="dot"></span><span>${esc(m.name)}</span><span class="muted">▾</span></button>
      ${po ? `<div class="tiny" style="color:var(--violet)">${money(po)} in flight. <button class="linkbtn" data-act="reconcileAll">Check now</button></div>` : ''}
    </div>
    <div class="pushes">
      <button class="push recv" data-act="receive"><span class="cap" aria-hidden="true">↓</span><span class="t">RECEIVE</span></button>
      <button class="push send" data-act="send"><span class="cap" aria-hidden="true">↑</span><span class="t">SEND</span></button>
    </div>
    <div class="scanrow"><button class="btn violet scan-btn" data-act="scan"><svg class="ico-scan" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M1 1h5v1H2v4H1zm9 0h5v5h-1V2h-4zM1 10h1v4h4v1H1zm13 0h1v5h-5v-1h4zM4 4h3v3H4zm5 0h3v3H9zM4 9h3v3H4zm5 0h1v1H9zm2 0h1v1h-1zm-2 2h1v1H9zm2 1h1v1h-1z"/></svg>Scan QR code</button>${window.Chiptune && window.Chiptune.canListen() ? '<button class="btn violet" data-act="ctListen" aria-label="Listen for a code sent as sound"><svg class="ico-scan" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M6 1h4v8H6zM4 6h1v3a3 3 0 0 0 6 0V6h1v3a4 4 0 0 1-3.5 4V15h-1v-2A4 4 0 0 1 4 9z"/></svg>Listen</button>' : ''}</div>
    <div class="toolrow"><button class="btn sm gold" data-act="cashier">Cashier mode</button><button class="btn sm pink" data-act="splitOpen">Split a bill</button>${S.extra ? '' : '<button class="btn sm lime" data-act="extraOpen">Extra Life</button>'}</div>
    ${splitPanels()}${piggyPanel()}${extraPanel()}
    <div id="priceMount"></div>
    <div class="panel">
      <div class="row between"><span class="h2">Recent</span>${S.txs.length ? '<button class="linkbtn" data-act="tab" data-tab="history">All notes</button>' : ''}</div>
      ${recent.length ? `<div class="txs">${recent.map(txRow).join('')}</div>` : `<div class="empty-state"><b>NO PLAYS YET</b>Receive some sats and every transaction shows up here with room for a note.</div>`}
    </div>
    <div class="panel"><div class="row between"><span class="h2">Arcade</span><button class="btn sm violet" data-act="tab" data-tab="arcade">Play</button></div><div id="topScore" class="tiny muted"></div></div>
    <button class="linkbtn tiny" style="justify-self:center;color:var(--pink)" data-act="support">♥ Support NUTCADE</button>
  </section>`;
}

function viewHistory() {
  const q = histQuery.toLowerCase();
  const list = S.txs.filter(t => (histFilter === 'all' || t.type === histFilter) && (!histTag || tagsOf(t.note).includes(histTag)) && (!q || (t.note || '').toLowerCase().includes(q) || String(t.amount).includes(q)));
  const noted = S.txs.filter(t => t.note).length;
  const counts = {}; S.txs.forEach(t => tagsOf(t.note).forEach(g => { counts[g] = (counts[g] || 0) + 1; }));
  const tags = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 14);
  return `<section class="screen">
    <div class="row between"><h2 class="h2">Transaction notes</h2><span class="row" style="gap:10px"><span class="tiny muted">${noted}/${S.txs.length} noted</span>${S.txs.length ? '<button class="btn sm" data-act="csv">Export CSV</button>' : ''}</span></div>
    <div class="field"><label for="hq">Search notes</label><input id="hq" class="inp" type="search" placeholder="pizza, rent, Satoshi…" value="${esc(histQuery)}" data-input="hq" autocomplete="off"></div>
    <div class="seg three" role="group" aria-label="Filter">${[['all', 'ALL'], ['in', 'IN'], ['out', 'OUT']].map(([k, l]) => `<button data-act="hf" data-f="${k}" aria-pressed="${histFilter === k}">${l}</button>`).join('')}</div>
    ${tags.length ? `<div class="tagrow" role="group" aria-label="Tags">${tags.map(([g, n]) => `<button class="tag" data-act="htag" data-tag="${esc(g)}" aria-pressed="${histTag === g}">#${esc(g)} <span>${n}</span></button>`).join('')}</div>` : `<div class="tiny muted">Tip: add #tags to notes, like #food or #rent, to group them.</div>`}
    <div class="txs" id="txList">${list.length ? list.map(txRow).join('') : `<div class="empty-state"><b>${S.txs.length ? 'NO MATCH' : 'GAME OVER?'}</b>${S.txs.length ? 'No transaction matches that search.' : 'Not yet. Your first transaction will land here.'}</div>`}</div>
  </section>`;
}

function viewMints() {
  return `<section class="screen">
    <div class="row between"><h2 class="h2">Your mints</h2><button class="btn sm gold" data-act="pickMint">Add mint</button></div>
    ${healthPanel()}
    ${S.mints.length ? `<div class="txs">${S.mints.map(m => `<div class="panel ${m.url === S.active ? 'hot' : ''}" style="gap:8px">
      <div class="row between" style="align-items:flex-start"><div style="min-width:0"><div style="font-family:var(--f-display);font-size:11px;color:var(--gold)">${esc(m.name)}</div><div class="tiny muted" style="overflow-wrap:anywhere">${esc(host(m.url))}</div></div>
      <div style="font-family:var(--f-display);font-size:12px;white-space:nowrap">${fmt(balanceOf(m.url))}</div></div>
      <div class="row between" style="gap:8px">${mintHealthLine(m)}${reportChip(m.url)}</div>
      <div class="row" style="flex-wrap:wrap;gap:6px">${methodChips(m)}</div>
      <div class="row" style="flex-wrap:wrap">${m.url === S.active ? '<span class="chip ecash">ACTIVE</span>' : `<button class="btn sm lime" data-act="useMint" data-url="${esc(m.url)}">Use</button>`}
      <button class="btn sm" data-act="refreshMint" data-url="${esc(m.url)}">Refresh</button>
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
  S.seed = d.seed || null; S.proofs = d.proofs || {}; S.pending = d.pending || []; S.quotes = d.quotes || []; S.txs = d.txs || []; S.p2pk = d.p2pk || []; S.requests = d.requests || []; S.contacts = d.contacts || [];
  seedBytes = null; raw.del('pinfails'); requestPersist();
}
function padHTML(title, sub, opts = {}) {
  const n = pinUI.value.length, slots = Math.max(PIN_MIN, n);
  return `<div class="pinpad" data-pinpad="${pinUI.mode}">
    <div class="pin-title">${esc(title)}</div>${sub ? `<div class="th" style="text-align:center">${esc(sub)}</div>` : ''}
    <div class="pin-dots" aria-label="${n} digits entered">${Array.from({ length: slots }, (_, i) => `<i class="${i < n ? 'on' : ''}"></i>`).join('')}</div>
    <div id="pinErr" class="pin-err" role="alert"></div>
    <div class="pin-keys">${['1', '2', '3', '4', '5', '6', '7', '8', '9', 'del', '0', 'ok'].map(k => `<button type="button" class="pin-k ${k === 'ok' ? 'ok' : ''}" data-act="pinKey" data-k="${k}" aria-label="${k === 'del' ? 'Delete' : k === 'ok' ? 'Enter' : k}">${k === 'del' ? '⌫' : k === 'ok' ? 'OK' : k}</button>`).join('')}</div>
    ${opts.extra || ''}</div>`;
}
function viewLock() {
  const rec = raw.get('vault', {}); const f = pinFails(); const wait = Math.max(0, Math.ceil((f.until - Date.now()) / 1000));
  if (pinUI.mode !== 'unlock') { pinUI.mode = 'unlock'; pinUI.value = ''; }
  return `<section class="screen"><div class="panel hot gate" style="justify-items:center">
    ${padHTML('ENTER PIN', wait ? `Too many wrong tries. Wait ${wait}s.` : 'Your wallet is locked.', { extra:
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
  const n = pinUI.value.length, slots = Math.max(PIN_MIN, n);
  pad.querySelector('.pin-dots').innerHTML = Array.from({ length: slots }, (_, i) => `<i class="${i < n ? 'on' : ''}"></i>`).join('');
  pad.querySelector('.pin-dots').setAttribute('aria-label', `${n} digits entered`);
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
      const dek = await pinToDek(v);
      if (!dek) { const f2 = notePinFail(); return pinError(f2.until > Date.now() ? `Wrong PIN. Wait ${Math.ceil((f2.until - Date.now()) / 1000)}s.` : `Wrong PIN. ${Math.max(0, 5 - f2.n)} tries before a wait.`); }
      await openVault(dek); hydrateFromVault(); pinUI.mode = null; sfx('start'); render(); armAutoLock();
      setTimeout(() => backgroundTick(true).then(() => { if (!$('#layer .sheet') && tab !== 'arcade') refresh(); }), 300);
      return;
    }
    if (m === 'set') { pinUI.first = v; nextPad('setConfirm'); setBody(padHTML('CONFIRM PIN', 'Enter the same PIN again.') + '<div id="sheetErr"></div>'); return; }
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
    if (m === 'changeOld') { busy('CHECKING…'); if (!(await pinToDek(v))) return pinError('That PIN is wrong.'); pinUI.old = v; nextPad('changeNew'); setBody(padHTML('NEW PIN', `Choose a new PIN (${PIN_MIN} to ${PIN_MAX} digits).`) + '<div id="sheetErr"></div>'); return; }
    if (m === 'changeNew') { pinUI.first = v; nextPad('changeConfirm'); setBody(padHTML('CONFIRM NEW PIN', 'Enter it again.') + '<div id="sheetErr"></div>'); return; }
    if (m === 'changeConfirm') {
      if (v !== pinUI.first) { nextPad('changeNew'); setBody(padHTML('NEW PIN', "Those didn't match. Start again.") + '<div id="sheetErr"></div>'); return; }
      busy('ENCRYPTING…'); await changePin(pinUI.old, v); pinUI.old = pinUI.first = ''; sfx('coin'); closeSheet(); toast('PIN changed', 'lime'); return;
    }
    if (m === 'remove') { busy('CHECKING…'); await removeVault(v).catch(e => { throw e; }); sfx('blip'); closeSheet(); refresh(); toast('PIN removed. Your wallet is no longer encrypted.', 'gold'); return; }
    if (m === 'bioVerify') { busy('CHECKING…'); const dek = await pinToDek(v); if (!dek) return pinError('That PIN is wrong.'); await enableBio(); closeSheet(); refresh(); toast('Face ID / fingerprint unlock is on', 'lime'); return; }
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
const APP_VERSION = '1.9.0';
const CURRENCIES = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'CHF', 'JPY', 'BRL', 'MXN', 'INR', 'ZAR', 'NGN', 'ARS', 'SEK'];
const THEMES = [['neon', 'Neon arcade'], ['amber', 'Amber CRT'], ['phosphor', 'Green phosphor']];
const SECTIONS = [['set-security', 'Security'], ['set-backup', 'Backup'], ['set-contacts', 'Contacts'], ['set-lnaddr', 'Lightning address'], ['set-look', 'Look & sound'], ['set-privacy', 'Privacy'], ['set-piggy', 'Piggy bank'], ['set-tools', 'Wallet tools'], ['set-about', 'About']];
const toggle = (k, label, help) => `<label class="toggle set" for="p_${k}"><span><span class="tl">${label}</span>${help ? `<span class="th">${help}</span>` : ''}</span><input id="p_${k}" type="checkbox" data-act="pref" data-k="${k}" ${S.prefs[k] ? 'checked' : ''}></label>`;
function viewSettings() {
  const inflight = S.pending.length;
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
    </div>

    <div class="panel" id="set-backup"><span class="h2">Backup</span>
      <div class="row between tiny"><span>Recovery phrase backed up</span><span style="color:${S.seed && S.seed.backedUp ? 'var(--lime)' : 'var(--red)'}">${S.seed && S.seed.backedUp ? 'YES' : 'NOT YET'}</span></div>
      <div class="row between tiny"><span>Protected from browser clean-up</span><span style="color:${persisted ? 'var(--lime)' : 'var(--gold)'}">${persisted ? 'YES' : persisted === false ? 'NOT GRANTED' : 'CHECKING'}</span></div>
      ${persisted ? '' : '<div class="th">On iPhone, add NUTCADE to your home screen so Safari keeps its data.</div>'}
      <div class="row wrap"><button class="btn sm gold" data-act="seedShow">Show recovery phrase</button><button class="btn sm violet" data-act="findLost">Find lost ecash</button></div>
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
      <div class="row between tiny"><span>Payments go to</span><span style="color:var(--ink)">${esc((S.mints.find(m => m.url === S.prefs.npcMint) || {}).name || host(S.prefs.npcMint || ''))}</span></div>
      <div class="row wrap"><button class="btn sm gold" data-act="lnAddr">Manage</button><button class="btn sm" data-act="copy" data-text="${esc(npcAddress())}">Copy</button></div>`
      : `<p class="th" style="margin:0">A permanent address like name@npub.cash that anyone can pay from any Lightning wallet. It's free, uses npub.cash, and is the same address cashu.me gives these 12 words.</p><button class="btn sm gold" data-act="lnAddr">Set it up</button>`}
    </div>

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
      <div class="field"><label for="p_currency">Currency</label><select id="p_currency" class="inp" data-act="prefSelect" data-k="currency" ${S.prefs.fiat ? '' : 'disabled'}>${CURRENCIES.map(c => `<option ${c === S.prefs.currency ? 'selected' : ''}>${c}</option>`).join('')}</select></div>
      ${toggle('checkSent', 'Check if sent ecash was claimed', 'Asks your mints in the background. Turn off to contact them less.')}
      ${toggle('nostrInbox', 'Receive ecash sent over Nostr', 'Listens on Nostr relays for ecash friends send to your ecash address. Requests you made still arrive for 30 days when this is off.')}
    </div>

    <div class="panel" id="set-piggy"><span class="h2">Piggy bank</span>
      ${toggle('piggy', 'Round up my payments', 'Each payment rounds up and the difference is set aside in your piggy bank. The sats stay in your wallet; NUTCADE makes you wait through a countdown before you spend them.')}
      ${S.prefs.piggy ? `<div class="field"><label for="p_piggyStep">Round up to the nearest</label><select id="p_piggyStep" class="inp" data-act="prefSelect" data-k="piggyStep">${[10, 100, 1000].map(v => `<option value="${v}" ${(+S.prefs.piggyStep || 100) === v ? 'selected' : ''}>${fmt(v)} sat</option>`).join('')}</select></div>
      <div class="row between tiny"><span>Saved so far</span><span style="color:var(--gold)">${money(piggySaved())}</span></div>${piggySaved() ? '<button class="btn sm" data-act="piggyEmpty">Empty piggy bank</button>' : ''}` : ''}
    </div>

    <div class="panel" id="set-tools"><span class="h2">Wallet tools</span>
      <p class="th" style="margin:0">Use these if your balance looks wrong or a payment seems stuck.</p>
      <div class="row wrap"><button class="btn sm gold" data-act="cashier">Cashier mode</button><button class="btn sm" data-act="tillOpen">Today's till</button><button class="btn sm" data-act="moveOpen">Move sats between mints</button><button class="btn sm lime" data-act="extraOpen">Extra Life</button></div>
      <div class="row wrap"><button class="btn sm violet" data-act="clean">Remove spent ecash</button><button class="btn sm" data-act="reconcileAll">Check stuck payments${inflight ? ` (${inflight})` : ''}</button></div>
    </div>

    <div class="panel" id="set-about"><span class="h2">About</span>
      <dl class="kv"><dt>Version</dt><dd>${APP_VERSION}</dd><dt>Works with</dt><dd>Any Cashu wallet</dd></dl>
      <div class="row wrap"><a class="btn sm" href="https://github.com/Random21m/nutcade" target="_blank" rel="noopener">Source on GitHub</a><a class="btn sm" href="https://cashu.space" target="_blank" rel="noopener">What is Cashu?</a></div>
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
const fiatOf = sats => (S.prefs.fiat && price.rate && price.cur === S.prefs.currency) ? (sats / 1e8 * price.rate).toLocaleString(undefined, { style: 'currency', currency: S.prefs.currency }) : null;

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
function relayQuery(filter, timeout = 7000) {
  return new Promise(res => {
    const out = new Map(); let left = 0; const socks = []; let fin = false;
    const end = () => { if (fin) return; fin = true; socks.forEach(s => { try { s.close(); } catch (e) {} }); res([...out.values()]); };
    for (const r of relays()) {
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
  for (const p of S.pending.filter(p => p.kind === 'ln')) {
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
      const fees = parts.reduce((t, p) => t + num(p.mq.fee_reserve), 0);
      setBody(`<p style="margin:0">NUTCADE will pay this ${money(amount)} invoice in ${parts.length} parts at once. The payment only completes if every part goes through; if one fails, all the sats come back.</p>
        <div class="txs">${parts.map((p, i) => `<div class="tx out" data-part="${i}"><span class="ico" aria-hidden="true">${i + 1}</span><span class="mid"><div class="note">${esc(p.c.name)}</div><div class="meta">fee reserve ${fmt(p.mq.fee_reserve)} · holds ${fmt(p.c.bal)}</div></span><span class="amt">${fmt(p.mq.amount)}</span></div>`).join('')}</div>
        <dl class="kv"><dt>Pay</dt><dd>${money(amount)}</dd><dt>Fee reserve</dt><dd>${money(fees)}</dd><dt>To</dt><dd class="tiny">${esc(dest.length > 40 ? dest.slice(0, 18) + '…' + dest.slice(-14) : dest)}</dd></dl>
        <div class="tiny muted">Unused fee reserve comes back as change.</div>
        <button class="btn solid pink block" id="mppPay">Pay ${money(amount)}</button><div id="sheetErr"></div>`, b2 => {
        b2.querySelector('#mppPay').onclick = e => run(e.currentTarget, 'PAYING', async () => {
          const n = parts.length;
          const res = await Promise.allSettled(parts.map((p, i) => payMelt('ln', p.mq, 0, `${note || 'Lightning payment'} (part ${i + 1} of ${n})`, dest, p.c.url)));
          const txs = res.map(r => r.status === 'fulfilled' ? r.value : null);
          refresh();
          if (txs.every(t => t && t.status === 'done')) return showDone('out', amount, `Lightning · ${n} mints`);
          for (const p of [...S.pending]) if (parts.some(x => x.mq.quote === p.quote)) await reconcile(p).catch(() => {});
          const st = parts.map(p => (S.txs.find(t => t.quote === p.mq.quote) || {}).status);
          refresh();
          if (st.every(s => s === 'done')) return showDone('out', amount, `Lightning · ${n} mints`);
          if (st.some(s => s === 'pending')) setBody(`<div class="notice">The payment is in flight. NUTCADE will settle each part when the mints confirm. Check the parts in your notes.</div><button class="btn block gold" data-act="close">OK</button>`);
          else setBody(`<div class="notice red">The payment didn't go through, so the parts that were sent came back to your wallet.</div><button class="btn block gold" data-act="close">OK</button>`);
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
    if (p && p.t === 'nutcade-challenge' && p.ev) { onChallenge(p.ev, 'nostr', p.bounty, rumor.pubkey); return; }
    if (p && p.t === 'nutcade-result' && p.ev) { await onResult(p.ev); return; }
    if (p && p.t === 'nutcade-bounty' && p.re && typeof p.pre === 'string') { const rec = S.challenges.find(x => x.id === p.re && x.dir === 'in'); if (rec) await claimBounty(rec, p.pre, rumor.pubkey); return; }
    if (p && (p.t === 'nutcade-extralife' || p.t === 'nutcade-extralife-end')) { onExtraLife(p, rumor.pubkey); return; }
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
  if (!S.mints.find(m => m.url === mint)) {
    if (!req && !who) return;   // ecash from an unknown mint is only kept when it answers one of our requests or comes from a contact
    addTx({ type: 'in', method: 'ecash', amount: sum(proofs), mint, note, status: 'pending', incoming: token, reqId: p.id || null });
    sfx('blip'); refresh();
    toast(`${money(sum(proofs))} arrived from ${host(mint)}, a mint you don't use yet. Open it in your notes to claim it.`, 'gold');
    return;
  }
  try {
    const tx = await receiveToken(token, note);
    updTx(tx.id, { reqId: p.id || null });
    if (req) { req.paid.push(tx.id); store.set('requests', S.requests); }
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
async function deliverPayment(pr, payload) {
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
  const ev = L.nip17.wrapEvent(rnd(32), { publicKey: to }, JSON.stringify(payload));
  const ok = await relayPublish(ev, 8000, list);
  if (!ok) throw new Error('No Nostr relay accepted the payment.');
  return true;
}
async function payRequest(pr, amount, url, note) {
  const lock = pr.nut10 && pr.nut10.kind === 'P2PK' && validPub(pr.nut10.data) ? pr.nut10.data : null;
  const tx = await sendEcash(amount, note, lock, url);
  const payload = { id: pr.id, mint: url, unit: 'sat', proofs: tx.sent };
  if (pr.description) payload.memo = pr.description;
  let sent = false, why = '';
  try { sent = await deliverPayment(pr, payload); } catch (e) { why = e.message; }
  if (sent) updTx(tx.id, { delivered: true });
  return { tx, sent, why };
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
const nfcBtn = (act, label, extra = '') => nfcOK() ? `<button class="btn sm violet" data-act="${act}" ${extra}><svg class="ico-scan" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3 2h1v12H3zm2 2h1v8H5zm5-2h1v12h-1zm2 2h1v8h-1zM7 3h2v1h1v2H9V5H7zm0 5h2v1h1v2H9v-1H7z"/></svg>${label}</button>` : '';


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
  return `<div class="field"><label>To a contact</label><div class="tagrow">${S.contacts.slice(0, 12).map(c => `<button class="tag" data-act="payContact" data-id="${c.id}">${esc(c.name)}</button>`).join('')}<button class="tag" data-act="contactsOpen">Manage</button></div></div>`;
}
function openContacts() {
  if (needSeed()) return;
  openSheet('Contacts', `
    <p style="margin:0">Save the people you pay. A contact can have a Lightning address, a Nostr address for sending ecash (npub or nprofile), or both. Contacts stay on this device${vault.on ? ', encrypted with your PIN' : ''}.</p>
    ${S.contacts.length ? `<div class="txs">${S.contacts.map(c => `<div class="tx in contact"><span class="ico" aria-hidden="true">${esc(c.name.slice(0, 1).toUpperCase())}</span><span class="mid"><div class="note">${esc(c.name)}</div><div class="meta">${c.ln ? `<span class="chip ln">LN</span>` : ''}${c.pubkey ? '<span class="chip ecash">NOSTR</span>' : ''}<span style="overflow-wrap:anywhere">${esc(c.ln || (c.nostr.slice(0, 16) + '…'))}</span></div></span><span class="row" style="gap:6px"><button class="btn sm pink" data-act="payContact" data-id="${c.id}">Pay</button><button class="btn sm" data-act="contactEdit" data-id="${c.id}">Edit</button></span></div>`).join('')}</div>` : '<div class="empty-state"><b>NO CONTACTS</b>Add someone you pay often.</div>'}
    <button class="btn solid gold block" data-act="contactEdit">Add a contact</button>
    <div class="sub">Your ecash address</div>
    <p class="th" style="margin:0">Give this to friends so they can send you ecash over Nostr from NUTCADE or cashu.me.</p>
    <div class="code">${esc(myEcashAddress())}</div>
    <div class="row wrap"><button class="btn sm" data-act="copy" data-text="${esc(myEcashAddress())}">Copy</button><button class="btn sm violet" data-act="myAddrQR">Show QR</button></div>`);
}
function openContactEdit(id, prefill = {}) {
  const c = id ? contactById(id) : Object.assign({ name: '', ln: '', nostr: '' }, prefill);
  openSheet(id ? 'Edit contact' : 'Add a contact', `
    <div class="field"><label for="cName">Name</label><input id="cName" class="inp" maxlength="40" value="${esc(c.name)}" placeholder="Alex" autocomplete="off"></div>
    <div class="field"><label for="cLn">Lightning address (optional)</label><input id="cLn" class="inp" value="${esc(c.ln)}" placeholder="alex@wallet.com" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
    <div class="field"><label for="cNostr">Nostr address for ecash (optional)</label><input id="cNostr" class="inp" value="${esc(c.nostr)}" placeholder="npub1… or nprofile1…" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
    <button class="btn solid gold block" data-act="contactSave" data-id="${id || ''}">Save</button>
    ${id ? `<button class="btn block red" data-act="contactDel" data-id="${id}">Delete contact</button>` : ''}<div id="sheetErr"></div>`);
}
function openPayContact(id) {
  const c = contactById(id); if (!c) return;
  if (needMint()) return;
  const m = activeMint();
  const canLn = c.ln && supports(m, 'melt', 'bolt11');
  openSheet(`Pay ${c.name}`, `
    <div class="tiny muted">From <b style="color:var(--ink)">${esc(m.name)}</b> · ${money(balanceOf(m.url))} available</div>
    <div class="field"><label for="amtIn">Amount (sat)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="1000" autocomplete="off"></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="Lunch"></div>
    ${c.pubkey ? `<button class="btn solid pink block" data-act="contactEcash" data-id="${c.id}">Send ecash over Nostr</button>` : ''}
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
  const have = S.proofs[url] || [];
  const pick = pickExact(have, amount);
  if (!pick) { const near = offlineAmounts(have, amount); throw new Error(`Offline, NUTCADE can only send amounts made of the exact coins you hold.${near.length ? ` Try ${near.map(fmt).join(' or ')} sat.` : ''}`); }
  const ids = new Set(pick.map(p => p.secret));
  S.proofs[url] = have.filter(p => !ids.has(p.secret));
  const token = L.getEncodedToken({ mint: url, proofs: pick, unit: 'sat' });
  save();
  return addTx({ type: 'out', method: 'ecash', amount, mint: url, note, status: 'pending', token, sent: plain(pick), offline: true });
}
function holdIncoming(token, note) {
  const meta = peekToken(token);
  if (S.txs.some(t => t.incoming === cleanToken(token))) throw new Error('This token is already saved and waiting.');
  return addTx({ type: 'in', method: 'ecash', amount: meta.amount, mint: meta.mint, note: note || meta.memo || '', status: 'pending', incoming: cleanToken(token), offline: true });
}
async function claimSaved() {
  if (isOffline()) return 0;
  let n = 0;
  for (const t of S.txs.filter(t => t.status === 'pending' && t.incoming && t.offline && S.mints.find(m => m.url === t.mint))) {
    try { const nt = await receiveToken(t.incoming, t.note); S.txs = S.txs.filter(x => x.id !== t.id); save(); n += nt.amount; }
    catch (e) { if (!netErr(e)) { updTx(t.id, { status: 'failed', note: (t.note ? t.note + ' · ' : '') + 'already claimed by someone else' }); } }
  }
  if (n) { sfx('coin'); refresh(); toast(`Back online: claimed ${money(n)} you saved offline`, 'lime'); }
  return n;
}
function netBanner() {
  let b = document.getElementById('netBanner');
  if (!isOffline()) { if (b) b.remove(); return; }
  if (!b) { b = document.createElement('div'); b.id = 'netBanner'; b.className = 'netbanner'; b.setAttribute('role', 'status'); document.body.appendChild(b); }
  b.textContent = "OFFLINE · You can still send exact amounts and save tokens to claim later";
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
      if (found.length) {
        const w = await getWallet(url);
        const mine = await withRepair(url, () => w.receive(found));
        addProofs(url, mine); total += sum(mine);
        addTx({ type: 'in', method: 'ecash', amount: sum(mine), fee: Math.max(0, sum(found) - sum(mine)), mint: url, note: 'Restored from another phrase' });
      }
    } catch (e) { fails.push(host(url)); }
  }
  return { total, fails };
}

/* Receive swap: claim at the foreign mint, then pay ourselves over Lightning into the active mint. */
async function swapIn(token, note) {
  token = cleanToken(token);
  const meta = peekToken(token);
  const dest = activeMint();
  if (!dest || !supports(dest, 'mint', 'bolt11')) throw new Error('Your active mint must accept Lightning deposits to swap into it.');
  if (!S.mints.find(m => m.url === meta.mint)) await addMint(meta.mint);
  const fw = await getWallet(meta.mint), dw = await getWallet(dest.url);
  const got = await withRepair(meta.mint, () => fw.receive(token, S.p2pk.length ? { privkey: p2pkPrivs() } : undefined));
  addProofs(meta.mint, got);
  const total = sum(S.proofs[meta.mint]);
  let amt = total - Math.max(2, Math.ceil(total * 0.02)), mq, melt, need;
  for (let i = 0; i < 4; i++) {
    if (amt < 1) throw new Error('This token is too small to cover Lightning fees for a swap. Claim it at its own mint instead.');
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
  try { await payMelt('ln', melt, 0, `Swap to ${dest.name}`, mq.request); }
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
    <div class="row between" style="align-items:flex-start"><div style="min-width:0"><div class="row" style="gap:8px"><span class="dot off"></span><span style="font-family:var(--f-display);font-size:10px;color:var(--gold)" data-name>${esc(name)}</span></div>
    <div class="tiny muted" style="overflow-wrap:anywhere">${esc(host(u))}</div></div>
    ${known.has(u) ? '<span class="chip ecash">ADDED</span>' : `<button class="btn sm lime" data-act="addMint" data-url="${esc(u)}">Add</button>`}</div>
    <div class="tiny">${esc(blurb)}</div><div class="row" style="gap:6px;flex-wrap:wrap" data-chips>${extra}</div></div>`;
  openSheet('Choose a mint', `
    <div class="notice cyan">A mint holds the Bitcoin behind your ecash. Only add mints you trust, and spread larger amounts across several.</div>
    ${S.mints.length ? `<div class="field"><label>Your mints</label><div class="txs">${S.mints.map(m => `<button class="tx in" data-act="useMint" data-url="${esc(m.url)}"><span class="ico">${m.url === S.active ? '★' : '·'}</span><span class="mid"><div class="note">${esc(m.name)}</div><div class="meta">${esc(host(m.url))}</div></span><span class="amt">${fmt(balanceOf(m.url))}</span></button>`).join('')}</div></div>` : ''}
    <div class="field"><label for="mintUrl">Mint address</label><div class="row"><input id="mintUrl" class="inp" placeholder="https://mint.example.com" autocomplete="off" autocapitalize="off" spellcheck="false"><button class="btn solid gold" data-act="addMintUrl">Add</button></div></div>
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
    <div class="tiny muted" style="overflow-wrap:anywhere">${esc(host(u))}</div></div>
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
    <div class="field"><label for="amtIn">Amount (sat)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="2100" autocomplete="off"></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="Arcade fund"></div>
    <button class="btn solid lime block" data-act="doLnInvoice">Create invoice</button>` : notSupported('Lightning deposits');
  else inner = supports(m, 'mint', 'onchain') ? `
    <div class="notice">On-chain deposits need ${esc(methodInfo(m, 'mint', 'onchain')?.confirmations || 'a few')} confirmation(s). NUTCADE watches the address while it's open.${minMax(methodInfo(m, 'mint', 'onchain'))}</div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="Savings top-up"></div>
    <button class="btn solid lime block" data-act="doOnchainAddr">Get Bitcoin address</button>` : notSupported('On-chain deposits');
  openSheet('Receive', `${methodSeg('recv', method)}${m && method !== 'ecash' ? `<div class="tiny muted">Into <b style="color:var(--ink)">${esc(m.name)}</b></div>` : ''}${inner}<div id="sheetErr"></div>`);
}
function minMax(mi) { if (!mi) return ''; const a = []; if (mi.min) a.push(`min ${fmt(mi.min)}`); if (mi.max) a.push(`max ${fmt(mi.max)}`); return a.length ? ` Limits: ${a.join(', ')} sat.` : ''; }
function notSupported(what) { return `<div class="notice red">${what} aren't offered by ${esc(activeMint().name)}. Pick a mint that lists them in the mint picker.</div><button class="btn block gold" data-act="pickMint">Open mint picker</button>`; }

function openSend(method = 'ecash') {
  if (needMint()) return;
  const m = activeMint(); let inner = '';
  if (method === 'ecash') inner = `
    <div class="field"><label for="amtIn">Amount (sat)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="500" autocomplete="off"></div>
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
    <div class="field"><label for="amtIn">Amount (sat)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="50000" autocomplete="off"></div>
    <div class="field"><label for="noteIn">Note (only you see it)</label><input id="noteIn" class="inp" maxlength="200" placeholder="Move to cold storage"></div>
    <button class="btn solid pink block" data-act="doMeltQuote" data-k="onchain">Get fee options</button>${minMax(methodInfo(m, 'melt', 'onchain')) ? `<div class="tiny muted">${minMax(methodInfo(m, 'melt', 'onchain'))}</div>` : ''}` : notSupported('On-chain withdrawals');
  openSheet('Send', `${contactChips()}${methodSeg('send', method)}<div class="tiny muted">From <b style="color:var(--ink)">${esc(m.name)}</b> · ${money(balanceOf(m.url))} available</div>${inner}<div id="sheetErr"></div>`);
}
const val = id => ($('#' + id) || {}).value || '';
const amt = () => { const n = satsOf('amtIn'); if (!n || n <= 0) throw new Error('Enter an amount in sats, like 1000.'); return n; };
function showErr(e) { sfx('err'); const el = $('#sheetErr'); if (el) el.innerHTML = errHTML(e); else toast(e.message || String(e), 'red'); }
async function run(btn, label, fn) {
  const old = btn ? btn.innerHTML : ''; if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner">${label}</span>`; }
  try { return await fn(); } catch (e) { if (e && e.piggy) { piggyBreak(e.piggy, () => run(btn, label, fn)); return; } showErr(friendly(e, S.active)); }
  finally { if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = old; } }
}

function showInvoice(tx) {
  const q = S.quotes.find(x => x.quote === tx.quote);
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
    <div class="credit-num" style="font-size:30px">${dir === 'in' ? '+' : '−'}${fmt(amount)}<small>${unitTag()}</small></div>
    <div class="muted">${esc(how)}</div>
    ${extra}<button class="btn solid gold block" data-act="close">Continue</button></div>`);
  refresh();
}
function showMeltQuote(kind, mq, dest, note) {
  const amount = num(mq.amount);
  const opts = kind === 'onchain' ? (mq.fee_options || []) : [];
  const feeRow = kind === 'ln' ? `<dt>Fee reserve</dt><dd>${money(mq.fee_reserve)}</dd>` : '';
  setBody(`<dl class="kv"><dt>Pay</dt><dd>${money(amount)}</dd>${feeRow}<dt>To</dt><dd class="tiny">${esc(dest.length > 40 ? dest.slice(0, 18) + '…' + dest.slice(-14) : dest)}</dd>${note ? `<dt>Note</dt><dd>${esc(note)}</dd>` : ''}</dl>
    ${opts.length ? `<div class="field"><label>Fee speed</label><div class="txs">${opts.map((o, i) => `<label class="tx out" style="cursor:pointer"><span class="ico"><input type="radio" name="fee" value="${o.fee_index}" ${i === 0 ? 'checked' : ''} style="accent-color:var(--pink)"></span><span class="mid"><div class="note">~${o.estimated_blocks} block${o.estimated_blocks === 1 ? '' : 's'}</div><div class="meta">≈ ${Math.round(o.estimated_blocks * 10)} min</div></span><span class="amt">${fmt(o.fee_reserve)}</span></label>`).join('')}</div></div>` : ''}
    ${kind === 'ln' ? '<div class="tiny muted">Unused fee reserve comes back as change.</div>' : ''}
    ${kind === 'ln' && balanceOf(S.active) < amount + num(mq.fee_reserve) ? `<div class="notice">${esc((activeMint() || {}).name || 'This mint')} holds ${money(balanceOf(S.active))}, not enough on its own.${S.mints.filter(m => balanceOf(m.url) > 0).length > 1 ? ' You can split the payment across your mints.' : ''}</div>` : ''}
    <button class="btn solid pink block" id="payBtn">Pay ${money(amount)}</button>
    ${kind === 'ln' && S.mints.filter(m => balanceOf(m.url) > 0).length > 1 ? `<button class="btn block violet" id="mppBtn">Pay from several mints</button>` : ''}<div id="sheetErr"></div>`, body => {
    const mb = body.querySelector('#mppBtn'); if (mb) mb.onclick = () => openMultinut(mq.request, amount, dest, note);
    body.querySelector('#payBtn').onclick = e => run(e.currentTarget, 'PAYING', async () => {
      const fi = kind === 'onchain' ? parseInt((body.querySelector('input[name=fee]:checked') || {}).value || '0', 10) : 0;
      const tx = await payMelt(kind, mq, fi, note, dest);
      const isAddr = kind === 'ln' && /^[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i.test(dest);
      const ct = isAddr && (S.contacts.find(c => c.ln === dest.toLowerCase()) || null);
      if (ct) updTx(tx.id, { contactId: ct.id, contactName: ct.name });
      lastContact = null;
      const save = isAddr && !ct ? `<button class="btn block violet" data-act="contactFrom" data-ln="${esc(dest.toLowerCase())}">Save ${esc(dest)} as a contact</button>` : '';
      if (tx.status === 'done') showDone('out', amount, kind === 'ln' ? (ct ? `Lightning to ${ct.name}` : 'Lightning') : 'On-chain' + (tx.outpoint ? ' · ' + tx.outpoint.slice(0, 12) + '…' : ''), save);
      else { setBody(`<div class="notice">Payment is in flight. NUTCADE will settle it when the mint confirms. Check the transaction in your notes.</div><button class="btn block gold" data-act="close">OK</button>`); refresh(); }
    });
    return null;
  });
}

function openTx(id) {
  const t = txById(id); if (!t) return;
  const method = { ln: 'Lightning', ecash: 'Ecash', onchain: 'On-chain' }[t.method];
  const mint = S.mints.find(m => m.url === t.mint);
  let extra = '';
  if (t.status === 'pending' && t.incoming && t.offline) extra = `<div class="notice">Saved while offline. NUTCADE claims it automatically when the mint can be reached.</div><button class="btn block lime" data-act="claimIncoming" data-id="${t.id}">Claim now</button>`;
  else if (t.status === 'pending' && t.incoming) extra = `<div class="notice">This ecash came from <b>${esc(host(t.mint))}</b>, a mint you don't use yet. Claiming adds that mint and trusts it with ${money(t.amount)}.</div><button class="btn block lime" data-act="claimIncoming" data-id="${t.id}">Trust mint &amp; claim</button>`;
  else if (t.status === 'pending' && t.method === 'ecash' && t.token) extra = `${t.lockUntil ? `<div class="notice cyan">Locked to ${esc(t.giftTo || 'one person')}. ${Date.now() < t.lockUntil ? `If they haven't claimed it by ${fmtDay(t.lockUntil)}, it comes back to you automatically.` : 'The lock has run out, so you can take it back.'}</div>` : ''}${qrBlock(t.token, 'Ecash token QR')}<div class="code">${esc(t.token)}</div>
    <div class="row" style="flex-wrap:wrap"><button class="btn sm pink" data-act="copy" data-text="${esc(t.token)}">Copy token</button>${nfcOK() ? `<button class="btn sm violet" data-act="nfcWrite" data-text="${esc(t.token)}">Write to NFC</button>` : ''}${ctBtn(t.token)}<button class="btn sm" data-act="checkClaim" data-id="${t.id}">Check claimed</button>${t.lockUntil ? (Date.now() < t.lockUntil ? `<button class="btn sm" disabled>Back on ${fmtDay(t.lockUntil)}</button>` : `<button class="btn sm gold" data-act="giftTake" data-id="${t.id}">Take it back</button>`) : `<button class="btn sm gold" data-act="reclaim" data-id="${t.id}">Reclaim</button>`}</div>`;
  else if (t.status === 'pending' && t.type === 'in' && t.method === 'ln') extra = `<button class="btn block lime" data-act="resumeInvoice" data-id="${t.id}">Show invoice</button>`;
  else if (t.status === 'pending' && t.type === 'in' && t.method === 'onchain') extra = `<div class="row" style="flex-wrap:wrap"><button class="btn sm lime" data-act="resumeAddr" data-id="${t.id}">Show address</button><button class="btn sm red" data-act="stopWatch" data-id="${t.id}">Stop watching</button></div>`;
  else if (t.status === 'pending' && t.type === 'out') extra = `<button class="btn block violet" data-act="reconcileTx" data-id="${t.id}">Check payment</button>`;
  openSheet(t.type === 'in' ? 'Received' : 'Sent', `
    <div class="credit-num" style="font-size:28px;color:${t.type === 'in' ? 'var(--lime)' : 'var(--pink)'}">${t.type === 'in' ? '+' : '−'}${t.amount ? fmt(t.amount) : '…'}<small>${unitTag()}</small></div>
    <div class="field"><label for="noteEdit">Note</label><textarea id="noteEdit" class="inp" maxlength="500" placeholder="What was this for?">${esc(t.note)}</textarea></div>
    <button class="btn solid gold block" data-act="saveNote" data-id="${t.id}">Save note</button>
    <dl class="kv"><dt>Method</dt><dd>${method}</dd><dt>Status</dt><dd>${esc(t.status)}</dd>${t.fee ? `<dt>Fee</dt><dd>${money(t.fee)}</dd>` : ''}
    <dt>Mint</dt><dd>${esc(mint ? mint.name : host(t.mint))}</dd><dt>When</dt><dd>${new Date(t.ts).toLocaleString()}</dd>
    ${t.outpoint ? `<dt>Tx</dt><dd class="tiny">${esc(t.outpoint)}</dd>` : ''}${t.roundup ? `<dt>Round-up</dt><dd>+${money(t.roundup)} to piggy bank</dd>` : ''}${t.lockUntil ? `<dt>Locked to</dt><dd ${t.giftTo ? 'data-noi18n' : ''}>${esc(t.giftTo || 'one person')}</dd>` : ''}${t.type === 'out' && t.method !== 'ecash' && t.request ? `<dt>To</dt><dd class="tiny">${esc(t.request.slice(0, 24))}…</dd>` : ''}</dl>
    ${extra}<div id="sheetErr"></div>`);
}


/* ---------- payment request sheets ---------- */
function openRequest() {
  if (needSeed()) return;
  const recent = S.requests.slice(0, 5);
  openSheet('Request a payment', `
    <p style="margin:0">Make a payment request that any Cashu wallet (like cashu.me) can pay. The ecash comes straight to this wallet over Nostr, even if you're not looking at this screen.</p>
    <div class="field"><label for="amtIn">Amount (sat, optional)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="Any amount" autocomplete="off"></div>
    <div class="field"><label for="memoIn">What it's for (the payer sees this)</label><input id="memoIn" class="inp" maxlength="120" placeholder="Pizza night"></div>
    ${S.mints.length ? `<label class="toggle" for="onlyMine"><span><span class="tl">Only from my mints</span><span class="th">The payer must use one of the mints you use, so you never get ecash from a mint you don't trust.</span></span><input id="onlyMine" type="checkbox" checked></label>` : ''}
    <button class="btn solid lime block" data-act="reqCreate">Create request</button>
    <button class="btn block pink" data-act="splitOpen">Split a bill with friends instead</button>
    ${recent.length ? `<div class="sub">Recent requests</div><div class="txs">${recent.map(r => `<button class="tx in" data-act="reqShow" data-id="${r.id}"><span class="ico" aria-hidden="true">?</span><span class="mid"><div class="note ${r.memo ? '' : 'empty'}">${esc(r.memo || 'No description')}</div><div class="meta"><span>${timeAgo(r.created)}</span>${r.paid.length ? `<span class="chip claimed">PAID ×${r.paid.length}</span>` : ''}</div></span><span class="amt">${r.amount ? fmt(r.amount) : 'ANY'}</span></button>`).join('')}</div>` : ''}
    <div id="sheetErr"></div>`);
}
function showRequest(r) {
  const paidBefore = r.paid.length;
  openSheet('Payment request', `
    <div class="label" style="text-align:center">${r.memo ? esc(r.memo) : 'Pay me'}</div>
    <div class="credit-num" style="text-align:center;font-size:26px">${r.amount ? fmt(r.amount) : 'ANY'}<small>${unitTag()}</small></div>
    ${qrBlock(r.encoded, 'Payment request QR')}
    <div class="code">${esc(r.encoded)}</div>
    <div class="row wrap"><button class="btn sm" data-act="copy" data-text="${esc(r.encoded)}">Copy request</button>${nfcBtn('nfcWrite', 'Write to NFC', `data-text="${esc(r.encoded)}"`)}${ctBtn(r.encoded)}</div>
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
  let body = `<div class="label">${pr.description ? esc(pr.description) : 'Payment request'}</div>
    ${amount ? `<div class="credit-num" style="font-size:26px">${fmt(amount)}<small>${unitTag()}</small></div>` : `<div class="field"><label for="amtIn">Amount (sat)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="1000" autocomplete="off"></div>`}`;
  if (pr.unit && pr.unit !== 'sat') body += `<div class="notice red">This request asks for ${esc(pr.unit)}. NUTCADE pays in sats only.</div>`;
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
  const pick = lnMints.length ? `<div class="field"><label for="npcMint">Mint that receives the payments</label><select id="npcMint" class="inp">${lnMints.map(m => `<option value="${esc(m.url)}" ${m.url === cur ? 'selected' : ''}>${esc(m.name)}</option>`).join('')}</select></div>` : '';
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
    <dl class="kv"><dt>Payments go to</dt><dd>${esc(name)}</dd><dt>Checked</dt><dd>${npcWs && npcWs.readyState === 1 ? 'Live' : 'Every 30 seconds while open'}</dd>${waiting ? `<dt>Claiming</dt><dd>${waiting} payment${waiting === 1 ? '' : 's'}</dd>` : ''}</dl>
    ${pick}${lnMints.length > 1 ? '<button class="btn sm" data-act="lnAddrMint">Use this mint</button>' : ''}
    <div class="row wrap"><button class="btn sm violet" data-act="lnAddrSync">Check for payments</button><button class="btn sm red" data-act="lnAddrOff">Turn off</button></div>
    <div class="tiny muted">Turning it off only stops this device checking. Payments sent meanwhile wait at npub.cash and arrive when you turn it back on.</div><div id="sheetErr"></div>`);
}

/* ---------- support / donations ---------- */
const DONATE = { address: 'dev@breez.tips', lnurl: 'LNURL1DP68GURN8GHJ7CNJV4JH5TN5D9C8XTMVDE6HYMRS9AJX2ASZ5RD0C' };
function openSupport() {
  const m = activeMint();
  const canTip = m && supports(m, 'melt', 'bolt11');
  openSheet('Support NUTCADE', `
    <p style="margin:0">NUTCADE is free and open source, and it stays that way. If you enjoy it and want to support its development, you can send a few sats over Lightning. It's entirely optional and changes nothing about how the wallet or the arcade work.</p>
    <div class="panel" style="background:var(--panel-2)">
      <span class="h2" style="color:var(--pink)">Tip from this wallet</span>
      ${canTip ? `<div class="seg three" role="group" aria-label="Tip amount">${[21, 210, 2100].map(a => `<button data-act="tipPreset" data-a="${a}" aria-pressed="${a === 210}">${fmt(a)}</button>`).join('')}</div>
      <div class="field"><label for="tipAmt">Amount (sat)</label><input id="tipAmt" class="inp amount" inputmode="numeric" value="210" autocomplete="off"></div>
      <button class="btn solid pink block" data-act="tipQuote">Tip ${'♥'} from ${esc(m.name)}</button>
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

/* ---------- actions ---------- */
const A = {
  close: () => closeSheet(),
  tab: b => { tab = b.dataset.tab; closeSheet(); render(); window.scrollTo(0, 0); sfx('blip'); },
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
  addMint: b => run(b, 'ADDING', async () => { const m = await addMint(b.dataset.url, { activate: true }); sfx('coin'); toast(`${m.name} added`, 'lime'); closeSheet(); render(); }),
  addMintUrl: b => run(b, 'ADDING', async () => { const u = val('mintUrl'); if (!u.trim()) throw new Error('Type a mint address first.'); const m = await addMint(u, { activate: true }); sfx('coin'); toast(`${m.name} added`, 'lime'); closeSheet(); render(); }),
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
    if (!S.mints.find(m => m.url === meta.mint) && !b.dataset.trust) {
      setTrust(meta); return;
    }
    if (isOffline()) { holdIncoming(tok, val('noteIn').trim()); sfx('blip'); refresh(); setBody(`<div class="notice">You're offline, so this token is saved and will be claimed automatically when you're back online. Until then it isn't yours yet: the sender could still spend it.</div><button class="btn solid gold block" data-act="close">OK</button>`); return; }
    let tx; try { tx = await receiveToken(tok, val('noteIn').trim()); }
    catch (e) { if (!netErr(e)) throw e; holdIncoming(tok, val('noteIn').trim()); refresh(); setBody(`<div class="notice">The mint can't be reached right now, so the token is saved and will be claimed automatically when it can. Until then it isn't yours yet.</div><button class="btn solid gold block" data-act="close">OK</button>`); return; }
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
    else { try { tx = await sendEcash(a, note, null); } catch (e) { if (!netErr(e)) throw e; tx = sendOffline(a, note); } } sfx('coin'); refresh(); showToken(tx); }),
  doMeltQuote: b => run(b, 'QUOTING', async () => {
    const k = b.dataset.k; let dest = val('destIn').trim().replace(/^(lightning|bitcoin):/i, '').split('?')[0];
    const note = val('noteIn').trim();
    if (k === 'ln') { const c = classify(dest); if (c.kind === 'lnaddress' || c.kind === 'lnurl') { const n = val('noteIn').trim(); openPayLnurl(c.value); if (n && $('#noteIn')) $('#noteIn').value = n; return; }
      if (!/^ln(bc|tb|bcrt|tbs)[0-9a-z]{50,}$/i.test(dest)) throw new Error("That isn't a complete Lightning invoice. Copy the whole invoice (it starts with lnbc) and paste again."); dest = dest.toLowerCase(); let mq; try { mq = await meltQuote('ln', dest); } catch (e) { if (/bech32|checksum|decode|invalid invoice|parse/i.test(e.message)) throw new Error("That Lightning invoice isn't valid. Check you copied all of it."); throw e; } showMeltQuote('ln', mq, dest, note); }
    else { if (!/^(bc1|tb1|bcrt1|[13mn2])[a-zA-HJ-NP-Z0-9]{20,90}$/.test(dest)) throw new Error('That Bitcoin address looks wrong. Check it and paste again.'); const a = amt(); const mq = await meltQuote('onchain', dest, a); showMeltQuote('onchain', mq, dest, note); }
  }),
  saveNote: b => { updTx(b.dataset.id, { note: val('noteEdit').trim() }); sfx('coin'); toast('Note saved', 'gold'); closeSheet(); refresh(); },
  checkClaim: b => run(b, '…', async () => { const t = txById(b.dataset.id); const c = await checkClaim(t); toast(c ? 'Claimed by the receiver' : 'Not claimed yet', c ? 'lime' : 'gold'); if (c) { closeSheet(); refresh(); } }),
  reclaim: b => run(b, 'RECLAIMING', async () => { const t = txById(b.dataset.id); reclaiming.add(t.id); try { await receiveToken(t.token, 'Reclaimed: ' + (t.note || 'ecash token')); } finally { setTimeout(() => reclaiming.delete(t.id), 5000); } updTx(t.id, { status: 'reclaimed' }); sfx('coin'); toast('Token reclaimed', 'lime'); closeSheet(); refresh(); }),
  resumeInvoice: b => { const t = txById(b.dataset.id); showInvoice(t); },
  resumeAddr: b => { const t = txById(b.dataset.id); showAddress(t); },
  stopWatch: b => { const t = txById(b.dataset.id); S.quotes = S.quotes.filter(q => q.quote !== t.quote); updTx(t.id, { status: 'expired' }); closeSheet(); refresh(); },
  reconcileTx: b => run(b, 'CHECKING', async () => { const t = txById(b.dataset.id); const p = S.pending.find(x => x.txId === t.id); if (!p) { toast('Nothing pending for this one', 'cyan'); return; } const r = await reconcile(p); toast({ paid: 'Payment confirmed', returned: 'Payment failed. Sats returned.', pending: 'Still in flight' }[r], r === 'pending' ? 'gold' : 'lime'); closeSheet(); refresh(); }),
  reconcileAll: b => run(b, '…', async () => { for (const p of [...S.pending]) await reconcile(p).catch(() => {}); refresh(); }),
  pref: b => { S.prefs[b.dataset.k] = b.checked; save(); if (!S.prefs.sound || !S.prefs.music) window.NutAudio && window.NutAudio.stopMusic(); if (b.dataset.k === 'fiat' && b.checked) fetchPrice(true); if (b.dataset.k === 'nostrBackup' && b.checked) { S.prefs.mintBackupList = ''; scheduleMintBackup(0); } refresh(); sfx('blip'); },
  backup: () => {
    const data = JSON.stringify({ app: 'nutcade', v: 2, at: new Date().toISOString(), seed: S.seed ? S.seed.mnemonic : null, counters: S.counters, mints: S.mints, proofs: S.proofs, pending: S.pending, txs: S.txs });
    openSheet('Backup', `<div class="notice red">This contains your recovery phrase and spendable ecash. Keep it private.</div><div class="code" style="max-height:200px">${esc(data)}</div><button class="btn solid gold block" data-act="copy" data-text="${esc(data)}">Copy backup</button>`);
  },
  restore: () => openSheet('Import backup', `<div class="field"><label for="restoreFile">Backup file</label><input id="restoreFile" class="inp" type="file" accept=".json,application/json" style="font-size:16px"></div><div class="field"><label for="restoreIn">Or paste the backup text</label><textarea id="restoreIn" class="inp" spellcheck="false"></textarea></div><button class="btn solid gold block" data-act="doRestore">Restore</button><div id="sheetErr"></div>`),
  doRestore: () => {
    try {
      const d = JSON.parse(val('restoreIn')); if (d.app !== 'nutcade') throw new Error('Not a NUTCADE backup.');
      if (d.seed && (!S.seed || (S.seed.mnemonic !== d.seed && totalBalance() === 0))) setSeed(d.seed, true);
      for (const k in d.counters || {}) counterSource.advanceToAtLeast(k, d.counters[k]);
      for (const k of d.p2pk || []) if (!S.p2pk.find(x => x.pub === k.pub)) S.p2pk.push(k); store.set('p2pk', S.p2pk);
      for (const m of d.mints || []) if (!S.mints.find(x => x.url === m.url)) S.mints.push(m);
      for (const u in d.proofs || {}) addProofs(u, d.proofs[u]);
      const ids = new Set(S.txs.map(t => t.id)); for (const t of d.txs || []) if (!ids.has(t.id)) S.txs.push(t);
      S.txs.sort((a, b) => b.ts - a.ts);
      for (const p of d.pending || []) if (!S.pending.find(x => x.id === p.id)) S.pending.push(p);
      // Extra Life, the copies we hold as an heir, and challenges (bounty secrets live there)
      if (d.extra && !S.extra) { S.extra = d.extra; saveExtra(); }
      for (const h of d.heirlooms || []) if (!S.heirlooms.find(x => x.token === h.token)) S.heirlooms.push(h); saveHeir();
      for (const c of d.challenges || []) if (!S.challenges.find(x => x.id === c.id && x.dir === c.dir)) S.challenges.push(c); saveChallenges();
      if (!S.active && S.mints[0]) S.active = S.mints[0].url;
      save(); closeSheet(); render(); toast('Backup restored. Run Check proofs to drop spent ecash.', 'lime');
    } catch (e) { showErr(new Error(e.message.includes('JSON') ? "That isn't valid backup text." : e.message)); }
  },
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
  bioUnlock: async b => {
    try { b.disabled = true; const dek = await bioToDek(); await openVault(dek); hydrateFromVault(); pinUI.mode = null; sfx('start'); render(); armAutoLock(); setTimeout(() => backgroundTick(true).then(() => { if (!$('#layer .sheet') && tab !== 'arcade') refresh(); }), 300); }
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
    const data = JSON.stringify({ app: 'nutcade', v: 2, at: new Date().toISOString(), seed: S.seed ? S.seed.mnemonic : null, counters: S.counters, mints: S.mints, proofs: S.proofs, pending: S.pending, txs: S.txs, p2pk: S.p2pk, extra: S.extra, heirlooms: S.heirlooms, challenges: S.challenges }, null, 1);
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
      <div class="field"><label for="rmExtra">Other mint addresses (one per line)</label><textarea id="rmExtra" class="inp" autocomplete="off" autocapitalize="off" spellcheck="false"></textarea></div>
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
    try { for (const k of Object.keys(localStorage)) if (/^nutcade:(seed|counters|mints|active|proofs|pending|txs|quotes|p2pk|requests|contacts|dmseen|vault|pinfails|piggy|challenges)$/.test(k)) localStorage.removeItem(k); } catch (e) {}
    try { npcSocketStop(); dmStop(); for (const k of ['npc', 'npcSince', 'npcName', 'npcMint', 'mintBackupAt', 'mintBackupList', 'dmSince']) delete S.prefs[k]; store.set('prefs', S.prefs); } catch (e) {}
    location.reload();
  },
  swapToken: b => run(b, 'SWAPPING', async () => {
    const r = await swapIn(val('tokIn'), val('noteIn').trim());
    sfx('coin'); refresh();
    setBody(`<div style="text-align:center;display:grid;gap:12px"><div style="font-family:var(--f-display);font-size:16px;color:var(--lime)">SWAPPED!</div><div class="credit-num" style="font-size:28px">+${fmt(r.amt)}<small>${unitTag()}</small></div>
      <p style="margin:0">Claimed at ${esc(host(r.from))} and moved into ${esc((S.mints.find(m => m.url === r.to) || {}).name || host(r.to))} over Lightning.</p><button class="btn solid gold block" data-act="close">Continue</button></div>`);
  }),
  tipPreset: b => { const i = $('#tipAmt'); if (i) setSats(i, b.dataset.a); b.parentElement.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); sfx('blip'); },
  tipQuote: b => run(b, 'ASKING', async () => {
    const sats = satsOf('tipAmt');
    if (!sats || sats < 1) throw new Error('Enter a tip amount in sats, like 210.');
    if (balanceOf(S.active) < sats) throw new Error(`Not enough credits. This mint holds ${money(balanceOf(S.active))}.`);
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
      else { const i = list.querySelectorAll('[data-rmint]').length; list.insertAdjacentHTML('afterbegin', `<label class="toggle" for="rmn${i}" style="font-size:19px"><span style="overflow-wrap:anywhere;min-width:0">${esc(host(u))}</span><input id="rmn${i}" type="checkbox" data-rmint="${esc(u)}" checked></label>`); }
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
    const r = newRequest(a, val('memoIn').trim(), !!($('#onlyMine') || {}).checked); sfx('coin'); showRequest(r);
  }),
  reqShow: b => { const r = S.requests.find(x => x.id === b.dataset.id); if (r) showRequest(r); },
  reqPayOpen: () => openSheet('Pay a payment request', `<div class="field"><label for="pasteIn">Paste the request (starts with creqA)</label><textarea id="pasteIn" class="inp" autocomplete="off" spellcheck="false"></textarea></div><div class="row wrap"><button class="btn solid gold" data-act="pasteGo">Continue</button><button class="btn sm violet" data-act="scan" data-hint="Point at a payment request.">Scan</button>${nfcBtn('nfcScan', 'Tap NFC')}</div><div id="sheetErr"></div>`, () => nfcStop),
  payReq: b => run(b, 'PAYING', async () => {
    const pr = decodeRequest(b.dataset.req);
    const a = pr.amount ? num(pr.amount) : amt();
    const url = val('reqMint'); if (!url) throw new Error('Pick a mint to pay from.');
    if (balanceOf(url) < a) throw new Error(`Not enough credits. That mint holds ${money(balanceOf(url))}.`);
    const { tx, sent, why } = await payRequest(pr, a, url, val('noteIn').trim() || pr.description || 'Payment request');
    sfx('coin'); refresh();
    if (sent) return showDone('out', a, 'Payment request');
    if (!(pr.transport || []).length) return showToken(tx);
    setBody(`<div class="notice red">The ecash was made but couldn't be delivered${why ? ': ' + esc(why) : ''}. It's safe in this token: send it another way, or reclaim it from your notes.</div>${qrBlock(tx.token, 'Ecash token QR')}<button class="btn solid pink block" data-act="copy" data-text="${esc(tx.token)}">Copy token</button><button class="btn block" data-act="close">Close</button>`);
  }),
  claimIncoming: b => run(b, 'CLAIMING', async () => {
    const t = txById(b.dataset.id); if (!t || !t.incoming) return;
    const nt = await receiveToken(t.incoming, t.note);
    S.txs = S.txs.filter(x => x.id !== t.id); updTx(nt.id, { reqId: t.reqId || null });
    const r = t.reqId && S.requests.find(x => x.id === t.reqId); if (r) { r.paid.push(nt.id); store.set('requests', S.requests); }
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
function setTrust(meta) {
  const el = $('#tokPeek'); const dest = activeMint();
  const canSwap = dest && supports(dest, 'mint', 'bolt11') && dest.url !== meta.mint;
  el.innerHTML = `<div class="notice">This token is from <b>${esc(host(meta.mint))}</b>, a mint you haven't added. Claiming adds it and trusts it with ${money(meta.amount)}.${canSwap ? ` Or swap it into ${esc(dest.name)} over Lightning (small fee).` : ''}</div>`;
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
  if (e.target.id === 'restoreFile' && e.target.files[0]) { e.target.files[0].text().then(t => { const box = $('#restoreIn'); if (box) box.value = t; }).catch(() => {}); }
  const sel = e.target.closest('[data-act="prefSelect"]'); if (sel) { S.prefs[sel.dataset.k] = sel.dataset.k === 'lockAfter' ? +sel.value : sel.value; save(); if (sel.dataset.k === 'lockAfter') { armAutoLock(); return; } if (sel.dataset.k === 'lang') { setLang(); refresh(); return; } if (sel.dataset.k === 'piggyStep') { S.prefs.piggyStep = +sel.value; save(); refresh(); return; } price = { rate: null, at: 0, cur: null }; fetchPrice(true); }
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
    try { const m = peekToken(v); el.innerHTML = `<dl class="kv"><dt>Amount</dt><dd style="color:var(--gold)">${money(m.amount)}</dd><dt>Mint</dt><dd>${esc(host(m.mint))}</dd>${m.memo ? `<dt>Memo</dt><dd>${esc(m.memo)}</dd>` : ''}</dl>`; }
    catch (x) { el.innerHTML = '<div class="tiny muted">Waiting for a valid cashu token…</div>'; }
  }
});
document.addEventListener('keydown', e => {
  if (document.querySelector('[data-pinpad]') && !e.target.matches('input,textarea,select')) {
    const k = /^[0-9]$/.test(e.key) ? e.key : e.key === 'Backspace' ? 'del' : e.key === 'Enter' ? 'ok' : null;
    if (k) { e.preventDefault(); const b = document.querySelector(`[data-pinpad] [data-k="${k}"]`); if (b) A.pinKey(b); return; }
  } if (e.key === 'Enter' && e.target.dataset && e.target.dataset.cw !== undefined && $('[data-act=gateConfirm]')) { e.preventDefault(); A.gateConfirm($('[data-act=gateConfirm]')); } if (e.key === 'Escape' && $('#layer .sheet')) closeSheet(); if (e.key === 'Enter' && e.target.id === 'mintUrl') A.addMintUrl($('[data-act="addMintUrl"]')); });

/* ---------- background checks ---------- */
async function backgroundTick(startup) {
  if (!S.seed || tabLocked) return;
  {
    const now = Date.now(), maxAge = 14 * 86400000;
    const qs = S.quotes.filter(q => q.kind === 'onchain' || now - (txById(q.txId)?.ts || 0) < maxAge);
    for (const q of qs) await checkQuote(q).catch(() => {});
  }
  for (const p of [...S.pending]) await reconcile(p).catch(() => {});
  if (S.prefs.npc) await npcSync().catch(() => {});
  await claimSaved().catch(() => {});
  await refundExpiredGifts().catch(() => {});
  await extraTick().catch(() => {}); await claimHeirlooms().catch(() => {}); await retryBounties().catch(() => {});
  if (S.prefs.nostrBackup && S.mints.length && S.prefs.mintBackupList !== S.mints.map(m => m.url).join(' ') && Date.now() - mintBackupTry > 10 * 60e3) scheduleMintBackup(startup ? 4000 : 0);
  if (S.prefs.checkSent) for (const t of S.txs.filter(t => t.status === 'pending' && t.method === 'ecash' && t.sent).slice(0, 10)) await checkClaim(t).catch(() => {});
}
let tickCount = 0;
setInterval(() => { if (document.hidden || tabLocked || $('#layer .sheet')) return; tickCount++; backgroundTick().then(() => { if (!$('#layer .sheet') && tab !== 'arcade') refresh(); }); }, 30000);

function livePrice(v, cur) {
  if (cur !== S.prefs.currency) return;
  const had = price.rate; price = { rate: v, at: Date.now(), cur };
  const f = $('.credits .fiat'); if (f) f.textContent = '≈ ' + fiatOf(+f.dataset.sats);
  else if (!had && tab === 'wallet' && !$('#layer .sheet')) refresh();
}
/* A link like …/#token=cashuB… (from an NFC card or a shared link) opens the token once the wallet is unlocked. */
let pendingLink = null;
function readHashLink() { try { const h = decodeURIComponent(location.hash || ''); const m = h.match(/(cashu[AB][A-Za-z0-9_\-+/=]{20,}|creqA[A-Za-z0-9_\-+/=]+|challenge=[A-Za-z0-9_-]{40,})/); if (m) { pendingLink = m[1]; history.replaceState(null, '', location.pathname + location.search); return true; } } catch (e) {} return false; }
readHashLink();
window.addEventListener('hashchange', () => { if (readHashLink()) refresh(); });   // a link opened while NUTCADE is already open
window.Nutcade = { render, refresh, S, toast, logoSVG, sfx, openSheet, closeSheet, esc, fmt, livePrice, celebrate, classify, handleScan, vault, live, startChallenge, challengeDone, sendResult, canChallenge: () => !!(S.seed && S.seed.backedUp), soundBytes, soundText, health, piggySaved };
setLang();
/* Offline: a service worker keeps a copy of the app (network first, so updates still arrive right away). */
try { if ('serviceWorker' in navigator && window.top === window.self && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) navigator.serviceWorker.register('sw.js').catch(() => {}); } catch (e) {}
render();
if (S.mints.length && !(vault.on && !vault.open)) setTimeout(() => backgroundTick(true).then(() => { if (!$('#layer .sheet') && tab !== 'arcade') refresh(); }), 1200);
})();
