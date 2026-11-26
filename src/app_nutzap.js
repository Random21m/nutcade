/* ===================== Nutzaps (1.28, NIP-61) ===================== */
/* Ecash zaps over Nostr, opt-in and off by default ("Receive nutzaps" in Settings, Privacy).
   - Your nutzap info: a kind 10019 event signed with this wallet's Nostr key (the npub of your ecash address), with a
     "relay" tag per relay you listen on, a "mint" tag per mint you use (with the unit "sat"; never a blocked mint, one
     or one that limits request size below NUTCADE's minimum: a nutzap there might never be claimable) and
     one "pubkey" tag: the P2PK key nutzaps must be locked to. That key is NOT the Nostr key (NIP-61 says so): it is
     derived from the 12 words at NZ_PATH (BIP-32, under the Cashu purpose 129372', branch 61' for NIP-61), with its
     private key negated when needed so that its public key starts with 02, and it is published as "02" + its x
     coordinate. So restoring the 12 words gives the same key back, and nutzaps that came while the wallet was away can
     still be claimed. Republished when the relays or mints change.
     Turning nutzaps off withdraws it: every attempt to publish is written down (with its time and relays) BEFORE it is
     sent, so an attempt that timed out, or one still on its way when nutzaps were turned off, is withdrawn too. The
     withdrawal is an empty kind 10019 and a kind 5 deletion of it, both made once, at a time after anything published
     before (nzTs, a floor every new event of ours goes above), and sent to each relay ever used for it until that relay
     confirms the empty one. A later publish is always after the deletion, so a relay never deletes it.
   - Receiving: kind 9321 events tagged with your Nostr key ("p") are listened for on your relays (each relay reopened on
     its own when it drops). Only while nutzaps are on. One is taken only when: its signature is right; its "u" mint is
     one you use now (not blocked, not limited); its unit is sat; it has at most NZ_COINS coins; every coin is on one of
     that mint's sat keysets, with a secret of at most NZ_SECRET characters, P2PK-locked to your receiving key with no
     other condition (tags empty, or only sigflag SIG_INPUTS and n_sigs 1: no other keys, refund, locktime or SIG_ALL);
     and every coin carries a DLEQ proof that checks against the mint's saved keys (app_dleq.js), so made-up coins never
     become a line. Each event is taken once (its id is kept, per wallet, encrypted with the PIN); coins already waiting
     in another line are never saved twice; coins the mint says are spent are left out (claimed before a restore, or by
     the same 12 words elsewhere). When the mint can't say (down), nothing is saved: the event waits in a short queue
     (nzwait) and is looked at again later. At most NZ_LINES nutzaps wait at once.
     A nutzap taken is saved as a waiting line ("Nutzap from ..."), then claimed with the usual claim of a saved token (one
     claim at a time, through the journal, signed with the receiving key, in parts when the mint limits request size):
     never credited before the mint swapped its coins, never twice. Mint down: it waits and is tried again with backoff.
     Mint refusing it while its coins are unspent: after NZ_REJECT refusals it is marked failed (never credited; "Try
     again" on its screen). Coins it says are spent are dropped from the line (all of them: the line goes).
   - Sending: their kind 10019 is looked up on their relays (an nprofile's) and yours; no 10019, no receiving key that is
     a point on the curve or no mint with the unit sat: refused, nothing spent. Never an unlocked token instead. A mint
     you both accept that holds the amount is used (the active one first). The coins are made locked to their key with
     the usual send, so the journal covers a crash: the locked coins come back as the same nutzap. The kind 9321 event (a
     "proof" tag per coin, with its DLEQ proof, "u" with the mint exactly as their 10019 wrote it, "unit" sat, "p" their
     key, your comment as its content, signed with your Nostr key) is made once and kept on the line before it is sent,
     so sending it again is the same event. It goes to the relays in their 10019 (yours when it lists none) until one
     takes it or they have claimed it. A nutzap is public: the screen says so.
   The duress PIN's wallet never publishes, listens or sends: its setting is kept and shown like a wallet whose relays
   don't answer, and sending answers as when relays can't be reached, so it looks like any other wallet. */
const NZ_PATH = "m/129372'/61'/0'/0'/0'";
const NZ_BACK = 7 * 86400, NZ_REPUB = 10 * 60e3, NZ_WAIT_MAX = 6 * 3600e3;
const NZ_COINS = 64, NZ_SECRET = 512, NZ_LINES = 20, NZ_BYTES = 200000, NZ_REJECT = 5, NZ_QUEUE = 30, NZ_MINT_TAGS = 32;
let nzKeyC = null;
function nzKeys() {
  const s = seedFor();
  if (!nzKeyC || nzKeyC.seed !== s) {
    const k = L.HDKey.fromMasterSeed(s).derive(NZ_PATH);
    const priv = evenPriv(hex(k.privateKey));
    nzKeyC = { seed: s, priv, pub: hex(L.getPubKeyFromPrivKey(L.hexToBytes(priv))) };
  }
  return nzKeyC;
}
const nzPriv = () => nzKeys().priv, nzPub = () => nzKeys().pub;
const nzDecoy = () => !!(vault.on && vault.decoy);
const nzAllowed = () => !!(S.seed && S.seed.backedUp && !nzDecoy());
const nzOn = () => nzAllowed() && S.prefs.nutzap === true;
const nzLive = () => nzOn() && !tabLocked && !(vault.on && !vault.open) && !writeGuard.paused;
// the mints a nutzap is taken at: the ones you use, never blocked or limiting request size below NUTCADE's minimum (MIN_REQ,
// 128: twice the most coins a nutzap may hold, so one taken can always be claimed in one request at a mint listed here)
const nzMints = () => satMints().map(m => m.url).filter(u => !isBlocked(u) && !belowMin(u));   // (nutzaps are SAT only, NIP-61 unit sat)
const nzTrusted = url => nzMints().includes(url);
// THE check for every relay address nutzaps use (yours, a contact's, the ones a 10019 lists): ws:// or wss:// only, a host,
// no user name or password, no spaces or control characters, at most 200 characters; returned as one fixed spelling, or null
function nzRelay(u) {
  if (typeof u !== 'string' || u.length > 200 || /[\s\x00-\x1f\x7f]/.test(u) || !/^wss?:\/\//i.test(u)) return null;
  let x; try { x = new URL(u); } catch (e) { return null; }
  if ((x.protocol !== 'ws:' && x.protocol !== 'wss:') || !x.hostname || x.username || x.password || x.hash) return null;
  const out = (x.protocol + '//' + x.host + x.pathname + x.search).replace(/\/+$/, '');
  return out.length <= 200 ? out : null;
}
const nzRelays = list => { const out = []; for (const u of list || []) { const r = nzRelay(u); if (r && !out.includes(r)) out.push(r); } return out; };
const nzMyRelays = () => nzRelays(relays()).slice(0, 8);
// one of OUR mints, as we store it, for a mint address someone else wrote (exact match once normalised), or null:
// an address from a Nostr event is never fetched, stored or used as a key itself
const nzOwnMint = u => { if (typeof u !== 'string' || u.length > 300 || !/^https?:\/\//i.test(u.trim())) return null; const n = normUrl(u); return nzMints().find(x => x === n) || null; };
const nzHas = (o, k) => !!o && Object.prototype.hasOwnProperty.call(o, k);
const nzWant = () => [nzMyRelays().join(' '), nzMints().join(' '), nzPub(), idPub()].join('|');   // (idPub: the key it is signed with, app_identity.js)
const nzNextTs = () => Math.max(Math.floor(Date.now() / 1000), num(S.prefs.nzTs) + 1);   // (after anything of ours published before)
const nzSeen = new Set(raw.get('nzseen', []));
function nzMark(id) { if (!id || nzSeen.has(id)) return; nzSeen.add(id); raw.set('nzseen', [...nzSeen].slice(-1000)); }
// a receiving key someone published: "02" + x for an x-only key (NIP-61), a compressed key as it is; a point on the curve, or null
function nzKeyOf(v) {
  v = String(v || '').trim().toLowerCase();
  const k = /^[0-9a-f]{64}$/.test(v) ? '02' + v : validPub(v) ? v : null;
  return k && DQ.point(k) ? k : null;
}
// the key a coin is locked to (NUT-11), or null unless it is a plain P2PK lock: tags empty, or only sigflag SIG_INPUTS and n_sigs 1
function nzLock(secret) {
  if (typeof secret !== 'string' || secret.length > NZ_SECRET) return null;
  let s; try { s = JSON.parse(secret); } catch (e) { return null; }
  if (!Array.isArray(s) || s.length !== 2 || s[0] !== 'P2PK' || !s[1] || typeof s[1] !== 'object' || typeof s[1].data !== 'string' || typeof s[1].nonce !== 'string') return null;
  const tags = s[1].tags == null ? [] : s[1].tags; if (!Array.isArray(tags)) return null;
  const names = new Set();
  for (const t of tags) {
    if (!Array.isArray(t) || t.length !== 2 || names.has(t[0])) return null;
    names.add(t[0]);
    if (t[0] === 'sigflag' && t[1] === 'SIG_INPUTS') continue;
    if (t[0] === 'n_sigs' && String(t[1]) === '1') continue;
    return null;   // (other keys, refund keys, a locktime, SIG_ALL, anything else: not a nutzap this wallet takes)
  }
  return s[1].data.toLowerCase();
}
// a coin locked to our receiving key: the key itself with no E on the coin, or (Pay to Blinded Key, app_p2bk.js) our key
// blinded for slot 0 with the coin's E; never both, and the lock's other rules (nzLock) stay as they are
const nzMine = p => p2bkMine(nzLock(p.secret), nzPub(), nzPriv(), p.p2pk_e || null, 0);
const nzWho = pk => { const c = S.contacts.find(x => x.pubkey === pk); return c ? c.name : shortNpub(pk); };
// a sender's comment as it is shown: one line, no hashtags (they would become your history tags) and no quotes (it can't pass for the app's text)
const nzComment = c => String(c || '').replace(/[\s\u200b-\u200f\u2028-\u202e\u2066-\u2069]+/g, ' ').replace(/[#"\u201c\u201d\u00ab\u00bb]/g, '').trim().slice(0, 120);

/* ---------- your nutzap info (kind 10019) ---------- */
/* Signed with your Nostr identity when you are signed in (app_identity.js), else the 12-word key; every record of a
   publish keeps the key that signed it (pk; none before 1.37: the 12-word key). A signer that refuses or doesn't answer
   publishes nothing (never the 12-word key instead), and the background round doesn't ask it again until you do
   something (nzSignFail). After a switch of identity the info is published again under the new key; the one under the
   old key is kept in S.prefs.nzOld and Settings offers to withdraw it (app_identity.js). */
let nzState = null, nzTry = 0, nzDecoyT = 0, nzSignFail = false;
const nzKeyOfRec = r => (r && idHex(r.pk)) ? r.pk : seedPub();
// the nutzap info on the relays under a key now: { ev } (the newest, signature checked; null: none), or null when no relay answered
async function nzCurrent(pk, rl) {
  const evs = await relayQuery({ kinds: [10019], authors: [pk], limit: 5 }, 7000, nzRelays((rl || []).concat(nzMyRelays())).slice(0, 8), 1500);
  if (!evs.answered) return null;
  const ev = evs.filter(e => e && e.kind === 10019 && e.pubkey === pk && Array.isArray(e.tags) && rvSig(e)).sort((a, b) => num(b.created_at) - num(a.created_at))[0] || null;
  return { ev };
}
// NUTCADE's own (its receiving key), empty (withdrawn) or none: ours to replace or withdraw; anything else is another wallet's
const nzOursOrNone = cur => { const e = cur && cur.ev; if (!e || !e.tags.length) return true; const t = e.tags.find(x => Array.isArray(x) && x[0] === 'pubkey'); return !!t && String(t[1] || '').toLowerCase() === nzPub(); };
const nzForeignErr = () => keepErr(new Error("The nutzap info under this identity now belongs to another wallet, so NUTCADE left it as it is. Nothing was sent."));
function nzPublish(hand) { return single('nzpub', () => nzPublishNow(hand)); }
async function nzPublishNow(hand) {
  if (!nzOn()) return 0;
  if (nzSignFail && !hand && idActive()) return 0;   // (your signer said no or didn't answer: asked again only when you act)
  const rl = nzMyRelays(), mints = nzMints(), pub = nzPub(), key = nzWant(), signer = idPub(), g = idNow();
  // the first publish under an identity: another wallet's nutzap info there (cashu.me, Minibits...) is never replaced
  // without asking (nutzaps sent to this npub would then come to NUTCADE instead of that wallet)
  const ours = S.prefs.nzInfo && nzKeyOfRec(S.prefs.nzInfo) === signer;
  if (idActive() && !ours && S.prefs.nzReplaceOk !== signer) {
    const cur = await nzCurrent(signer, rl);
    if (idNow() !== g || !nzOn()) return 0;
    if (!cur) { nzState = 'failed'; refresh(); return 0; }   // (no relay answered: we can't tell, so nothing is published)
    if (!nzOursOrNone(cur)) { S.prefs.nzForeign = signer; save(); nzState = 'foreign'; refresh(); return 0; }
  }
  if (S.prefs.nzForeign) { delete S.prefs.nzForeign; save(); }
  const ts = nzNextTs();
  let ev;
  try { ev = await idSign({ kind: 10019, created_at: ts, tags: rl.map(r => ['relay', r]).concat(mints.map(u => ['mint', u, 'sat']), [['pubkey', pub]]), content: '' }, g); }
  catch (e) {
    if (e && e.gone) { nzState = null; return 0; }   // (another identity meanwhile: not the signer failing; the switch publishes again)
    nzSignFail = true; nzState = 'nosign'; refresh(); return 0;
  }
  nzSignFail = false;
  if (!nzOn() || nzWant() !== key || idNow() !== g) { nzState = null; return 0; }   // (turned off, or another identity, while it was being signed)
  const pk = ev.pubkey, prev = S.prefs.nzPubTry && nzKeyOfRec(S.prefs.nzPubTry) === pk ? S.prefs.nzPubTry.relays || [] : [];
  // the attempt is on disk before it goes out: if nutzaps are turned off meanwhile, or it times out but a relay kept it, it is withdrawn
  S.prefs.nzTs = ts; S.prefs.nzPubTry = { at: ts, relays: [...new Set(prev.concat(rl))].slice(0, 16), pk }; delete S.prefs.nzUnpub;
  await saveNow();
  nzState = 'saving'; nzTry = Date.now();
  const ok = await relayPublish(ev, 7000, rl, 1500);
  if (idPub() !== pk || idNow() !== g) {   // (another identity while it was on its way: it is old info now, offered for withdrawal)
    nzOldAdd(pk, rl); if (S.prefs.nzPubTry && nzKeyOfRec(S.prefs.nzPubTry) === pk) delete S.prefs.nzPubTry;
    if (S.prefs.nzInfo && nzKeyOfRec(S.prefs.nzInfo) === pk) delete S.prefs.nzInfo;
    save(); nzState = null; return 0;
  }
  if (!nzOn()) { nzState = null; if (nzAllowed()) await nzUnpublishStart(true).catch(() => {}); return 0; }   // (turned off while it was on its way)
  nzState = ok ? 'ok' : 'failed';
  if (ok) { S.prefs.nzInfo = { at: ts, mints, relays: rl, pub, key, pk }; if (S.prefs.nzReplaceOk === pk) delete S.prefs.nzReplaceOk; save(); }
  return ok;
}
// after a switch: whatever publish is on its way ends first, then one under the key now
function nzRepublish() { const f = flights.get('nzpub') || Promise.resolve(); return f.catch(() => {}).then(() => nzOn() ? nzPublish(true) : 0).then(() => refresh()).catch(() => {}); }
// withdraw everything published: the same two events, at a time after all of it, to every relay used, until each confirms.
// Signed by the key that published it; one under your identity only when you act (hand), never from the background round
async function nzUnpublishStart(hand) {
  if (!S.seed || !nzAllowed() || S.prefs.nutzap === true) return 0;
  const tried = S.prefs.nzPubTry, info = S.prefs.nzInfo;
  if (!tried && !info) return 0;
  const pk = nzKeyOfRec(tried || info), rl = nzRelays(((tried || {}).relays || []).concat((info || {}).relays || [], relays())).slice(0, 16);
  if (pk !== seedPub() && !(hand && idActive() && idPub() === pk)) {   // (another key's: offered in Settings, withdrawn when you tap)
    if (!hand) return 0;
    nzOldAdd(pk, rl); delete S.prefs.nzPubTry; delete S.prefs.nzInfo; save(); return 0;
  }
  const cur = await nzCurrent(pk, rl).catch(() => null);
  if (!cur && pk !== seedPub()) return 0;   // (no relay answered: an identity's info is withdrawn only once we can see it is ours)
  if (cur && !nzOursOrNone(cur)) { delete S.prefs.nzPubTry; delete S.prefs.nzInfo; save(); return 0; }   // (another wallet's now: left as it is)
  const ts = nzNextTs();
  let empty, del;
  try {
    empty = await idSignAs(pk, { kind: 10019, created_at: ts, tags: [], content: '' });
    del = await idSignAs(pk, { kind: 5, created_at: ts, tags: [['a', `10019:${pk}:`], ['k', '10019']], content: '' });
  } catch (e) { nzOldAdd(pk, rl); delete S.prefs.nzPubTry; delete S.prefs.nzInfo; save(); return 0; }   // (your signer said no: offered again in Settings)
  if (S.prefs.nutzap === true) return 0;   // (turned on again while it was being signed)
  S.prefs.nzTs = ts; S.prefs.nzUnpub = { evs: [empty, del], relays: rl, tries: 0 }; delete S.prefs.nzPubTry; delete S.prefs.nzInfo;
  await saveNow();
  return nzUnpublishRun();
}
async function nzUnpublishRun() {
  const u = S.prefs.nzUnpub; if (!u || !Array.isArray(u.relays) || !Array.isArray(u.evs) || writeGuard.paused) return 0;
  nzTry = Date.now();
  const done = await Promise.all(u.relays.map(async r => { const [a] = await Promise.all([relayPublish(u.evs[0], 7000, [r]), relayPublish(u.evs[1], 7000, [r])]); return a ? r : null; }));
  const cur = S.prefs.nzUnpub; if (cur !== u) return 0;   // (nutzaps turned on again meanwhile: a newer publish replaces it)
  const left = u.relays.filter(r => !done.includes(r));
  if (!left.length) delete S.prefs.nzUnpub;
  else { const tries = num(u.tries) + 1; S.prefs.nzUnpub = Object.assign({}, u, { relays: left, tries, next: Date.now() + Math.min(6 * 3600e3, 60e3 * 2 ** Math.min(tries - 1, 8)) }); }
  save();
  return u.relays.length - left.length;
}
function nzToggled(on) {
  if (nzDecoy()) {   // the duress PIN's wallet: kept and shown as a wallet whose relays don't answer; nothing is ever sent
    clearTimeout(nzDecoyT); nzState = on ? 'saving' : null;
    if (on) nzDecoyT = setTimeout(() => { if (S.prefs.nutzap === true) { nzState = 'failed'; refresh(); } }, 6000 + Math.floor(Math.random() * 2000));
    return;
  }
  if (on && !nzAllowed()) { S.prefs.nutzap = false; save(); return; }
  nzState = null;
  if (on) { nzSignFail = false; nzRepublish(); setTimeout(nzListen, 0); }
  else { nzStop(); nzUnpublishStart(true).then(() => refresh()).catch(() => {}); }
}
function nzSettingsHTML() {
  const on = S.prefs.nutzap === true && !!S.seed;
  const st = nzDecoy() ? (nzState === 'saving' ? 'SAVING…' : 'RELAYS DIDN\'T ANSWER') : nzState === 'saving' ? 'SAVING…' : nzState === 'nosign' ? "YOUR SIGNER DIDN'T SIGN" : nzState === 'failed' ? 'RELAYS DIDN\'T ANSWER' : S.prefs.nzInfo ? 'PUBLISHED' : 'NOT YET';
  const fg = on && !nzDecoy() && S.prefs.nzForeign && idActive() && S.prefs.nzForeign === idPub();
  return toggle('nutzap', 'Receive nutzaps', "Publishes your nutzap info on Nostr (NIP-61): your relays, the mints you use and a receiving key made from your 12 words, so people can send you ecash zaps. Nutzaps that arrive are claimed into this wallet. Off by default.")
    + (on ? `<div class="row between tiny"><span>Nutzap info</span><span style="color:${st === 'PUBLISHED' ? 'var(--lime)' : 'var(--gold)'}">${fg ? 'NOT PUBLISHED' : st}</span></div>` : '')
    + (on && !nzDecoy() && !fg && nzState === 'nosign' ? '<button class="btn sm" data-act="nzRepub">Try again</button>' : '')
    + (fg ? `<div class="notice" id="nzForeign">Another wallet already published nutzap info for your Nostr identity. Replace it with NUTCADE's? Nutzaps sent to this npub would then come to NUTCADE instead of the other wallet.</div><button class="btn sm gold" data-act="nzReplace">Replace with NUTCADE's</button>` : '');
}

/* ---------- a switch of identity (app_identity.js) ---------- */
// nutzap info published under a key no longer used for it: [{ pk, relays, at }], offered for withdrawal in Settings
function nzOldAdd(pk, rl) {
  const o = (Array.isArray(S.prefs.nzOld) ? S.prefs.nzOld : []).filter(x => x && idHex(x.pk) && x.pk !== pk);
  S.prefs.nzOld = [{ pk, relays: nzRelays(rl || []).slice(0, 16), at: Date.now() }].concat(o).slice(0, 4);
}
const nzOldList = () => (Array.isArray(S.prefs.nzOld) ? S.prefs.nzOld : []).filter(x => x && idHex(x.pk));
// the old nutzap info Settings offers to withdraw: one a key of yours can sign now (the 12-word key, or the identity you are in)
function nzOldOffer() {
  if (!S.seed || nzDecoy()) return null;
  let sp = null; try { sp = seedPub(); } catch (e) { return null; }
  const c = idConn();
  return nzOldList().find(x => x.pk === sp || (c && c.pub === x.pk)) || null;
}
// nutzap info is (or may be) published under this key now
const nzPublishedUnder = pk => !nzDecoy() && [S.prefs.nzInfo, S.prefs.nzPubTry].some(r => r && nzKeyOfRec(r) === pk);
function nzIdChanged(oldPub, newPub) {
  nzSignFail = false;
  if (nzDecoy() || !S.seed) return;
  for (const r of [S.prefs.nzPubTry, S.prefs.nzInfo]) if (r && nzKeyOfRec(r) !== newPub) { nzOldAdd(nzKeyOfRec(r), (r.relays || []).concat(relays())); }
  if (S.prefs.nzPubTry && nzKeyOfRec(S.prefs.nzPubTry) !== newPub) delete S.prefs.nzPubTry;
  if (S.prefs.nzInfo && nzKeyOfRec(S.prefs.nzInfo) !== newPub) delete S.prefs.nzInfo;
  S.prefs.nzOld = nzOldList().filter(x => x.pk !== newPub || !nzOn());   // (back on a key whose info we withdraw: published again below)
  save();
  nzStop();
  if (S.prefs.nzForeign && S.prefs.nzForeign !== newPub) delete S.prefs.nzForeign;
  if (nzOn()) { nzState = null; nzRepublish(); }   // (after any publish still on its way, so the key now is always asked)
  setTimeout(nzListen, 0);
}
// withdraw the nutzap info under one of your keys, now: an empty 10019 and a kind 5 for it, signed by that key, to every
// relay it went to and yours; at least one relay has to take them
async function nzRetract(pk, rl) {
  if (isOffline()) throw keepErr(new Error("You're offline. Your Nostr identity needs a connection. Nothing was sent."));
  const cur = await nzCurrent(pk, rl);
  if (!cur) throw keepErr(new Error('No relay accepted the withdrawal. Try again in a moment.'));
  if (!nzOursOrNone(cur)) throw nzForeignErr();   // (only NUTCADE's own nutzap info is ever withdrawn)
  const ts = nzNextTs();
  const empty = await idSignAs(pk, { kind: 10019, created_at: ts, tags: [], content: '' });
  const del = await idSignAs(pk, { kind: 5, created_at: ts, tags: [['a', `10019:${pk}:`], ['k', '10019']], content: '' });
  S.prefs.nzTs = Math.max(num(S.prefs.nzTs), ts); save();
  const list = nzRelays((rl || []).concat(relays())).slice(0, 16);
  const done = await Promise.all(list.map(async r => { const [a] = await Promise.all([relayPublish(empty, 7000, [r]), relayPublish(del, 7000, [r])]); return a ? 1 : 0; }));
  const n = done.reduce((a, b) => a + b, 0);
  if (!n) throw keepErr(new Error('No relay accepted the withdrawal. Try again in a moment.'));
  return n;
}
async function nzRetractOld(pk) {
  const o = nzOldList().find(x => x.pk === pk); if (!o) return 0;
  const n = await nzRetract(pk, o.relays);
  S.prefs.nzOld = nzOldList().filter(x => x.pk !== pk); save();
  return n;
}
// Sign out with "also withdraw": the info under this identity, signed by it, before the connection goes
async function nzWithdrawUnder(pk) {
  const recs = [S.prefs.nzInfo, S.prefs.nzPubTry].filter(r => r && nzKeyOfRec(r) === pk), o = nzOldList().find(x => x.pk === pk);
  if (!recs.length && !o) return 0;
  const n = await nzRetract(pk, recs.flatMap(r => r.relays || []).concat(o ? o.relays : []));
  if (S.prefs.nzInfo && nzKeyOfRec(S.prefs.nzInfo) === pk) delete S.prefs.nzInfo;
  if (S.prefs.nzPubTry && nzKeyOfRec(S.prefs.nzPubTry) === pk) delete S.prefs.nzPubTry;
  S.prefs.nzOld = nzOldList().filter(x => x.pk !== pk); save();
  return n;
}

/* ---------- receiving (kind 9321) ---------- */
const nzSocks = new Map(), nzBack = new Map();   // relay -> its socket; relay -> { n, at } (its own backoff)
function nzListen() {
  if (!nzLive()) { nzStop(); return; }
  const want = nzMyRelays();
  for (const [r, ws] of nzSocks) if (!want.includes(r)) { nzSocks.delete(r); try { ws.close(); } catch (e) {} }
  const f = { kinds: [9321], '#p': idKeys() };   // (every key of yours: the 12-word key, your identity, former identities; app_identity.js)
  if (S.prefs.nzSince) f.since = Math.max(0, num(S.prefs.nzSince) - NZ_BACK);   // (a restored wallet has none: everything sent to it is looked at)
  for (const r of want) {
    const old = nzSocks.get(r); if (old && old.readyState <= 1) continue;
    const b = nzBack.get(r); if (b && Date.now() < b.at) continue;
    let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
    nzSocks.set(r, ws);
    ws.onopen = () => ws.send(JSON.stringify(['REQ', 'ncnz', f]));
    ws.onmessage = m => { let d; try { d = JSON.parse(m.data); } catch (e) { return; } if (d[0] === 'EVENT' && d[2]) nzQueue(d[2]); else if (d[0] === 'EOSE') nzBack.delete(r); };
    ws.onclose = () => {   // (this relay alone is opened again, with its own backoff, while the others stay up)
      if (nzSocks.get(r) !== ws) return;
      const n = ((nzBack.get(r) || {}).n || 0) + 1, d = Math.min(120e3, 3000 * 2 ** (n - 1));
      nzBack.set(r, { n, at: Date.now() + d }); setTimeout(nzListen, d + 50);
    };
  }
}
function nzStop() { const s = [...nzSocks.values()]; nzSocks.clear(); s.forEach(w => { try { w.close(); } catch (e) {} }); }
let nzChain = Promise.resolve();
function nzQueue(ev) { const r = nzChain.then(() => nzEvent(ev)).catch(() => 'error'); nzChain = r; return r; }   // (one at a time, in order)
// events whose coins couldn't be checked with the mint (down): kept a while, looked at again (never a line before that)
function nzWaitSet(ev, keep) {
  let q = raw.get('nzwait', []); if (!Array.isArray(q)) q = [];
  q = q.filter(e => e && e.id !== ev.id); if (keep) q.push(ev);
  raw.set('nzwait', q.slice(-NZ_QUEUE));
}
const nzWaiting = () => { const q = raw.get('nzwait', []); return Array.isArray(q) ? q : []; };
// what became of an event: 'ok' (saved and claimed or waiting), or why it was not taken
async function nzEvent(ev) {
  if (!ev || typeof ev !== 'object' || ev.kind !== 9321 || typeof ev.id !== 'string' || !Array.isArray(ev.tags)) return 'bad';
  if (nzSeen.has(ev.id)) { nzWaitSet(ev, false); return 'seen'; }
  if (!nzOn() || tabLocked || (vault.on && !vault.open) || writeGuard.paused) return 'off';
  if (S.txs.some(t => t.nz && t.nz.id === ev.id)) { nzMark(ev.id); return 'seen'; }
  if (!L.verifyEvent(ev)) return 'bad';   // (not kept as seen: a forged copy must not hide the real one)
  const tg = k => ev.tags.filter(t => Array.isArray(t) && t[0] === k && typeof t[1] === 'string');
  const mine = idKeys(); if (!tg('p').some(t => mine.includes(t[1]))) return 'bad';
  const skip = why => { nzMark(ev.id); nzWaitSet(ev, false); return why; };
  const u = (tg('u')[0] || [])[1]; if (!u || !/^https?:\/\//i.test(u.trim())) return skip('bad');
  const mint = nzOwnMint(u);   // (our own stored address of that mint, or none: untrusted)
  const unit = (tg('unit')[0] || [])[1]; if (unit && unit !== 'sat') return skip('unit');
  if (!mint || !nzTrusted(mint)) { nzWaitSet(ev, false); return 'untrusted'; }   // (not kept as seen: taken if you add that mint and it comes again)
  const pt = tg('proof'); if (!pt.length || pt.length > NZ_COINS) return skip('bad');
  let proofs = [];
  for (const t of pt) {
    let p; try { p = JSON.parse(t[1]); } catch (e) { return skip('bad'); }
    const a = Number(p && p.amount);
    if (!p || typeof p.id !== 'string' || typeof p.secret !== 'string' || p.secret.length > NZ_SECRET || typeof p.C !== 'string' || !/^0[23][0-9a-f]{64}$/i.test(p.C) || !Number.isSafeInteger(a) || a <= 0) return skip('bad');
    const q = { id: p.id, amount: a, secret: p.secret, C: p.C };
    if (p.dleq && typeof p.dleq === 'object') q.dleq = { e: String(p.dleq.e || ''), s: String(p.dleq.s || ''), r: String(p.dleq.r || '') };
    if (nzHas(p, 'p2pk_e')) { const e = p2bkE(p.p2pk_e); if (!e) return skip('bad'); q.p2pk_e = e; }   // (a blinded lock: the sender's E, a point on the curve, kept on the coin)
    proofs.push(q);
  }
  if (new Set(proofs.map(p => p.secret)).size !== proofs.length) return skip('bad');
  if (!proofs.every(p => nzLock(p.secret)) || !proofs.every(nzMine)) return skip('lock');   // (every lock's rules first, a JSON read each; then one x(k·E) a blinded coin)
  // the coins must be the mint's: its sat keysets, and every DLEQ proof checked against its saved keys
  if (!S.mintkeys[mint]) { try { await getWallet(mint); } catch (e) {} }
  const ks = S.mintkeys[mint];
  if (!ks) { nzWaitSet(ev, true); return 'nokeys'; }   // (the mint can't be reached and its keys aren't saved: looked at again later)
  if (!proofs.every(p => nzHas(ks, p.id) && nzHas(ks[p.id], String(p.amount)))) return skip('keyset');   // (own keys only: never one from Object.prototype)
  let token; try { token = tokEnc({ mint, proofs, unit: 'sat' }); } catch (e) { return skip('bad'); }
  const dq = offlineCheck(token).state;
  if (dq !== 'ok') return skip(dq === 'bad' ? 'forged' : 'noproof');
  const secs = new Set(proofs.map(p => p.secret));
  if (S.txs.some(t => (t.status === 'pending' || t.status === 'failed') && t.incoming && (heldSecrets(t.incoming) || []).some(x => secs.has(x)))) return skip('dup');
  // coins the mint says are spent are left out (claimed before: never shown again); a mint that can't say: nothing saved yet
  let st = null;
  try { const w = await getWallet(mint); st = await inTime(w.checkProofsStates(proofs), 20000); } catch (e) { st = null; }
  if (!st || st.length !== proofs.length) { nzWaitSet(ev, true); return 'later'; }
  proofs = proofs.filter((p, i) => !(st[i] && st[i].state === 'SPENT'));
  if (!proofs.length) return skip('spent');
  if (nzSeen.has(ev.id) || S.txs.some(t => t.nz && t.nz.id === ev.id)) return 'seen';
  const open = S.txs.filter(t => t.type === 'in' && t.nz && t.status === 'pending' && t.incoming);
  if (open.length >= NZ_LINES || open.reduce((n, t) => n + t.incoming.length, 0) > NZ_BYTES) { nzWaitSet(ev, true); return 'full'; }   // (looked at again once some are claimed)
  try { token = tokEnc({ mint, proofs, unit: 'sat' }); } catch (e) { return skip('bad'); }
  const c = nzComment(ev.content);
  const t = addTx({ type: 'in', method: 'ecash', amount: sum(proofs), mint, note: `Nutzap from ${nzWho(ev.pubkey)}${c ? ': "' + c + '"' : ''}`, status: 'pending', incoming: token, dleq: 'ok', nz: { id: ev.id, from: ev.pubkey, at: num(ev.created_at) } });
  nzMark(ev.id); nzWaitSet(ev, false);
  S.prefs.nzSince = Math.max(num(S.prefs.nzSince), Math.min(num(ev.created_at), Math.floor(Date.now() / 1000)));
  await saveNow();   // (the line and the seen id are on disk before the mint is asked)
  await nzClaim(t, true).catch(() => {});
  return 'ok';
}
// the coins of a waiting nutzap the mint doesn't say are spent, and the token they are saved in again: each coin with
// every field it had (spend_info, witness, p2pk_e, dleq and anything else: a field dropped here can make a coin unspendable)
const nzLeft = (ps, st) => ps.filter((p, i) => !(st[i] && st[i].state === 'SPENT')).map(p => Object.assign({}, p, { amount: num(p.amount) }));
const nzLeftToken = (mint, left) => tokEnc({ mint, proofs: left, unit: 'sat' });
// a waiting nutzap claimed with the usual claim of a saved token; the mint down leaves it waiting, the mint refusing it
// (its coins unspent) NZ_REJECT times marks it failed
async function nzClaim(t0, force, hand) {
  const t = txById(t0.id); if (!t || t.type !== 'in' || !t.incoming || !t.nz || !(t.status === 'pending' || (hand && t.status === 'failed'))) return null;
  if (!force && t.nz.next && Date.now() < t.nz.next) return null;
  if (isBlocked(t.mint) || isOffline()) return null;
  if (t.status === 'failed') updTx(t.id, { status: 'pending', nz: Object.assign({}, t.nz, { rej: 0 }) });
  try {
    const nt = await claimHeld(txById(t.id));
    if (nt) { arrivalFrom(nt.id, 'nostr'); sfx('coin'); refresh(); arrToast(nt.id, `+${arrMoney(nt.amount)} nutzap received`, 'lime'); }
    return nt;
  } catch (e) {
    const cur = txById(t.id); if (!cur) return S.txs.find(x => x.fromIncoming === t.id) || null;
    // its coins now saved in other lines (claimed in parts, some parts left to claim): those lines hold them, this one goes
    const mine = new Set(heldSecrets(cur.incoming) || []);
    if (mine.size && S.txs.some(x => x.id !== cur.id && x.status === 'pending' && x.incoming && (heldSecrets(x.incoming) || []).some(s => mine.has(s)))) { S.txs = S.txs.filter(x => x.id !== cur.id); save(); refresh(); return null; }
    let refused = false;
    const turnedDown = isRefusal(e) || isRefusal(e.cause);   // (the mint answered no: its step signed nothing)
    if (!netErr(e) && !e.blocked && (!e.asked || turnedDown)) {   // the mint turned it down: which of its coins are still good?
      try {
        const w = await getWallet(cur.mint), ps = L.getDecodedToken(cleanToken(cur.incoming), Object.keys(S.mintkeys[cur.mint] || {}).concat(Object.keys(S.counters))).proofs || [];
        const st = await inTime(w.checkProofsStates(ps), 20000);
        if (st.length === ps.length && st.every(x => x && x.state === 'UNSPENT')) refused = true;   // (every coin unspent, and the mint still says no)
        else if (st.length === ps.length && !S.ops.some(o => o.follow && o.follow.k === 'incoming' && o.follow.txId === cur.id)) {
          const left = nzLeft(ps, st);
          if (!left.length) { S.txs = S.txs.filter(x => x.id !== cur.id); save(); refresh(); return null; }
          if (left.length < ps.length) { updTx(cur.id, { incoming: nzLeftToken(cur.mint, left), amount: sum(left) }); await saveNow(); }
        }
      } catch (x) {}
    }
    const now = txById(t.id); if (!now) return null;
    const tries = num(now.nz.tries) + 1, rej = num(now.nz.rej) + (refused ? 1 : 0);
    if (rej >= NZ_REJECT) { updTx(now.id, { status: 'failed', nz: Object.assign({}, now.nz, { tries, rej }) }); refresh(); }   // (never credited; Try again on its screen)
    else updTx(now.id, { nz: Object.assign({}, now.nz, { tries, rej, next: Date.now() + Math.min(NZ_WAIT_MAX, 30e3 * 2 ** Math.min(tries - 1, 10)) }) });
    if (hand) throw e;
    return null;
  }
}

/* ---------- sending ---------- */
const nzNoInfo = () => keepErr(new Error("This person can't receive nutzaps: they haven't published nutzap info (NIP-61) on Nostr. Nothing was sent. Send ecash over Nostr or Lightning instead."));
const nzNoRelay = () => keepErr(new Error("Couldn't reach your Nostr relays to look up their nutzap info. Nothing was sent. Try again in a moment."));
// the duress PIN's wallet: it answers as a wallet whose relays don't answer, after as long as they would take
const nzDecoyWait = async () => { await sleep(6500 + Math.floor(Math.random() * 1500)); throw nzNoRelay(); };
async function nzFind(pubkey, extra) {
  if (!/^[0-9a-f]{64}$/.test(String(pubkey || ''))) throw new Error("That Nostr address can't be read. Paste an npub or nprofile.");
  if (nzDecoy()) return nzDecoyWait();
  const list = nzRelays((extra || []).concat(relays())).slice(0, 8);
  const evs = await relayQuery({ kinds: [10019], authors: [pubkey], limit: 5 }, 7000, list, 1500);
  const ev = evs.filter(e => e && e.kind === 10019 && e.pubkey === pubkey && Array.isArray(e.tags) && L.verifyEvent(e)).sort((a, b) => b.created_at - a.created_at)[0];
  if (!ev && !evs.answered) throw nzNoRelay();
  if (!ev) throw nzNoInfo();
  const tg = k => ev.tags.filter(t => Array.isArray(t) && t[0] === k && typeof t[1] === 'string');
  const pub = nzKeyOf((tg('pubkey')[0] || [])[1]);
  const mints = [], urls = new Set();
  for (const t of tg('mint').slice(0, NZ_MINT_TAGS)) {   // (a list longer than that is cut: a lookup can't be made to take forever)
    if (t.length > 2 && !t.slice(2).includes('sat')) continue;   // (units listed, and sat isn't one of them)
    if (t[1].length > 300 || !/^https?:\/\//i.test(t[1].trim())) continue;
    const url = normUrl(t[1]); if (!urls.has(url)) { urls.add(url); mints.push({ u: t[1], url, own: nzOwnMint(t[1]) }); }   // (own: our stored address, the only one ever used)
  }
  if (!pub || !mints.length) throw nzNoInfo();
  return { pub, mints, relays: nzRelays(tg('relay').map(t => t[1])).slice(0, 8) };
}
const nzUsable = info => info.mints.filter(m => m.own && !isBlocked(m.own)).map(m => ({ u: m.u, url: m.own }));
function nzPick(info, amount) {
  const mine = nzUsable(info);
  if (!mine.length) { const e = keepErr(new Error("They take nutzaps only at mints you don't use. Add one of their mints to send them a nutzap. Nothing was sent.")); e.raw = info.mints.map(m => host(m.url)).join(', '); throw e; }
  const ok = mine.filter(m => balanceOf(m.url) >= amount);
  if (!ok.length) { const e = keepErr(new Error("You don't have that much at a mint they take nutzaps at. Nothing was sent.")); e.raw = mine.map(m => `${host(m.url)}: ${money(balanceOf(m.url))}`).join(', '); throw e; }
  return ok.find(m => m.url === S.active) || ok.sort((a, b) => balanceOf(b.url) - balanceOf(a.url))[0];
}
const nzProof = p => Object.assign({ id: p.id, amount: num(p.amount), secret: p.secret, C: p.C }, p.dleq && p.dleq.e && p.dleq.s && p.dleq.r ? { dleq: { e: String(p.dleq.e), s: String(p.dleq.s), r: String(p.dleq.r) } } : {}, p.p2pk_e ? { p2pk_e: String(p.p2pk_e) } : {}, p.spend_info ? { spend_info: p.spend_info } : {});   // (p2pk_e: a blinded lock's E, NUT-28; spend_info: a v3 coin's, cashu-ts 5, never dropped)
const nzRelaysFor = z => { const l = nzRelays(z.relays); return (l.length ? l : nzMyRelays()).slice(0, 8); };
// the nutzap's event, made once and kept on its line before it is sent (sending it again is the same event)
async function nzDeliverOne(id) {
  let t = txById(id); if (!t || t.type !== 'out' || t.delivered || t.status !== 'pending' || !t.nz || !Array.isArray(t.sent) || !t.sent.length) return !!(t && t.delivered);
  if (!S.seed || nzDecoy()) return false;
  if (!t.nz.ev) {
    const z = t.nz, tags = t.sent.map(p => ['proof', JSON.stringify(nzProof(p))]).concat([['u', z.u], ['unit', 'sat'], ['p', z.to]]);
    updTx(t.id, { nz: Object.assign({}, z, { ev: L.finalizeEvent({ kind: 9321, created_at: Math.floor(Date.now() / 1000), content: z.c || '', tags }, nostrKey()) }) });
    await saveNow(); t = txById(id);
  }
  const ok = await relayPublish(t.nz.ev, 8000, nzRelaysFor(t.nz), 1500);
  const cur = txById(id); if (!cur) return !!ok;
  if (ok) { const z = Object.assign({}, cur.nz); delete z.next; delete z.tries; updTx(id, { delivered: true, nz: z }); return true; }
  const tries = num(cur.nz.tries) + 1;
  updTx(id, { nz: Object.assign({}, cur.nz, { tries, next: Date.now() + Math.min(30 * 60e3, 30e3 * 2 ** Math.min(tries - 1, 8)) }) });
  return false;
}
async function nzDeliver(force) {
  for (const t of S.txs.filter(t => t.type === 'out' && t.nz && !t.delivered && t.status === 'pending' && Array.isArray(t.sent) && t.sent.length)) {
    if (!force && t.nz.next && Date.now() < t.nz.next) continue;
    await single('nzsend:' + t.id, () => nzDeliverOne(t.id)).catch(() => {});
  }
}
async function nzSendTo(target, info, amount, comment) {
  if (nzDecoy()) return nzDecoyWait();
  if (!nzAllowed()) throw new Error('Set up your recovery phrase first.');
  if (isOffline()) throw new Error("You're offline. A nutzap needs a connection.");
  amount = num(amount); if (!Number.isSafeInteger(amount) || amount <= 0) throw new Error('Enter an amount in sats, like 1000.');
  if (!info || !nzKeyOf(info.pub)) throw nzNoInfo();
  const m = nzPick(info, amount), name = String(target.name || shortNpub(target.pubkey)).trim().slice(0, 40);
  const txx = { nz: { to: target.pubkey, u: m.u, relays: nzRelays(info.relays).slice(0, 8), c: String(comment || '').slice(0, 280) } };
  if (target.contactId) Object.assign(txx, { contactId: target.contactId, contactName: name });
  // never blinded (app_p2bk.js), whatever Hide who gets it says: a nutzap can't come back, and kind 10019 doesn't say whether
  // the receiver's wallet supports NUT-28 (one that doesn't, NUTCADE 1.28 among them, could never spend it)
  const tx = await sendEcash(amount, `Nutzap to ${name}`, nzKeyOf(info.pub), m.url, { txx });
  const ok = await single('nzsend:' + tx.id, () => nzDeliverOne(tx.id)).catch(() => false);
  return { tx: txById(tx.id) || tx, ok: !!ok };
}
async function nzSend(target, amount, comment) {
  return nzSendTo(target, await nzFind(target.pubkey, target.relays), amount, comment);
}

/* ---------- the nutzap screen, history, the background round ---------- */
let curNz = null;
async function openNutzap(target) {
  if (needMint()) return;
  curNz = null;
  const name = String(target.name || shortNpub(target.pubkey)).trim().slice(0, 40);
  const head = `<div class="label">To</div><div class="code" style="color:var(--ink)" data-noi18n>${esc(name)}</div>`;
  openSheet('Nutzap', busyHTML('LOOKING UP THEIR NUTZAP INFO') + '<div id="sheetErr"></div>');
  let info;
  try { info = await nzFind(target.pubkey, target.relays); }
  catch (e) { if ($('#layer .sheet')) setBody(head + errHTML(friendly(e)) + '<button class="btn block" data-act="close">Close</button>'); return; }
  if (!$('#layer .sheet')) return;
  const mine = nzUsable(info), from = mine.find(m => m.url === S.active) || mine.slice().sort((a, b) => balanceOf(b.url) - balanceOf(a.url))[0];
  curNz = Object.assign({}, target, { name, info });
  setBody(`${head}
    <div class="tiny muted">They take nutzaps at</div><div class="tiny" data-noi18n>${info.mints.map(m => esc(host(m.url))).join(', ')}</div>
    ${from ? `<div class="tiny muted">From <b style="color:var(--ink)" data-noi18n>${esc(mintName(from.url))}</b> · ${money(balanceOf(from.url))} available</div>
    <div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="21" autocomplete="off"></div>
    <div class="field"><label for="nzComment">Comment (optional, public on Nostr)</label><input id="nzComment" class="inp" maxlength="280" autocomplete="off"></div>
    <div class="notice">A nutzap is public on Nostr: anyone can see who sent it, to whom and how much. Its ecash is locked to their key, so only they can claim it.</div>
    <button class="btn solid gold block" data-act="nzSend">Send nutzap</button>` : errHTML(keepErr(new Error("They take nutzaps only at mints you don't use. Add one of their mints to send them a nutzap. Nothing was sent.")))}
    <div id="sheetErr"></div>`);
}
// the history screen of a nutzap (src/app.js openTx)
function nzTxExtra(t) {
  if (!t.nz) return '';
  if (t.type === 'in' && t.status === 'pending' && t.incoming) return `${checkLine(t)}<div class="notice">This nutzap is waiting to be claimed. NUTCADE claims it as soon as the mint can be reached.</div><button class="btn block lime" data-act="nzClaim" data-id="${esc(t.id)}">Claim now</button>`;
  if (t.type === 'in' && t.status === 'failed' && t.incoming) return `<div class="notice">The mint turned this nutzap down several times, so NUTCADE stopped trying. Nothing was added to your balance.</div><button class="btn block" data-act="nzClaim" data-id="${esc(t.id)}">Try again</button>`;
  if (t.type === 'out' && t.status === 'pending') return `<div class="notice cyan">${t.delivered ? 'Sent as a nutzap over Nostr.' : 'Not delivered yet: no relay has taken this nutzap so far. NUTCADE keeps trying.'} Its ecash is locked to their key, so only they can claim it.</div>
    <div class="row" style="flex-wrap:wrap"><button class="btn sm" data-act="checkClaim" data-id="${esc(t.id)}">Check claimed</button>${t.delivered ? '' : `<button class="btn sm gold" data-act="nzRetry" data-id="${esc(t.id)}">Try now</button>`}</div>`;
  if (t.type === 'in' && t.status === 'done') return `<div class="notice cyan">Claimed at the mint.</div>`;
  return '';
}
const nzTxRow = t => t.nz ? `<dt>${t.type === 'in' ? 'From' : 'To'}</dt><dd class="tiny" data-noi18n>${esc(shortNpub(t.type === 'in' ? t.nz.from : t.nz.to))}</dd>` : '';
// every background round: waiting nutzaps claimed, undelivered ones sent, the info kept up to date (or withdrawn)
let nzTicking = Promise.resolve();
function nzTick(force) { const r = nzTicking.catch(() => {}).then(() => nzTickNow(force)); nzTicking = r; return r; }
async function nzTickNow(force) {
  if (!S.seed || tabLocked || (vault.on && !vault.open) || nzDecoy() || writeGuard.paused) return;
  for (const t of S.txs.filter(t => t.type === 'in' && t.nz && t.status === 'pending' && t.incoming)) await nzClaim(t, force).catch(() => {});
  if (nzOn()) for (const ev of nzWaiting()) await nzQueue(ev);
  await nzDeliver(force).catch(() => {});
  const due = force || Date.now() - nzTry > NZ_REPUB;
  if (nzOn()) {
    if ((S.prefs.nzInfo || {}).key !== nzWant() && due) {   // (with a signer: never awaited here, so a slow signer can't hold up claims and deliveries)
      if (idActive()) { if (!flights.has('nzpub')) nzPublish().catch(() => {}); } else await nzPublish().catch(() => {});
    }
  }
  else if (S.prefs.nzUnpub) { if (force || Date.now() >= num(S.prefs.nzUnpub.next)) await nzUnpublishRun().catch(() => {}); }
  else if (S.prefs.nzInfo || S.prefs.nzPubTry) await nzUnpublishStart().catch(() => {});
  nzListen();
}
window.NutZap = {
  pub: () => nzPub(), me: () => idPub(), keys: () => idKeys(), publish: hand => nzPublish(!!hand), state: () => nzState, old: () => nzOldList(), path: NZ_PATH, info: () => S.prefs.nzInfo || null, live: () => [...nzSocks.values()].filter(s => s.readyState <= 1).length,
  event: ev => nzQueue(ev), tick: force => nzTick(!!force), seen: () => [...nzSeen], find: (pk, rl) => nzFind(pk, rl || []), mints: () => nzMints(), waiting: () => nzWaiting().length,
  claim: id => nzClaim({ id }, true, true), left: (ps, st) => nzLeft(ps, st), leftToken: (m, l) => nzLeftToken(m, l), relay: u => nzRelay(u), lock: s => nzLock(s), socks: () => [...nzSocks.values()],
  send: (target, amount, comment) => nzSend(target, amount, comment), open: target => openNutzap(target), randomPub: () => hex(L.getPubKeyFromPrivKey(rnd(32)))
};
