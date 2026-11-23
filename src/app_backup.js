/* ---------- Better backups (1.23) ----------
   1. A password on the backup file (optional): PBKDF2-SHA256 (600,000 rounds, like the PIN) and AES-256-GCM, with a random
      salt and iv, in a small self-describing JSON envelope. Without a password the file is exactly as before. A locked
      file asks for its password on import; a wrong one is an error and nothing changes. The password is never stored.
   2. The file also carries contacts, settings (the ones listed in BK_SET: how NUTCADE looks and behaves, never a key,
      a relay or a Lightning address), trophies and arcade progress (high scores, plays, the Daily Challenge days, your initials).
      Importing adds them next to what is here and never touches money: coins, history and steps come in as before.
   3. Back up with my phone: a passkey (WebAuthn, its PRF extension) locks the 12 words, and the locked copy is kept on
      Nostr relays, like the mint-list backup. The passkey's PRF output for a fixed salt goes through HKDF into two keys:
      a Nostr key that signs the copy (so the passkey alone finds it again on a new phone), and an AES-256-GCM key that
      locks the words. No server of ours is involved. Restoring fetches the copy, opens it and hands the words to the usual
      Restore wallet screen, so a wallet that holds sats is never replaced silently (its sats move into the restored one).
      Never offered by the duress PIN's wallet: it answers "not available right now", as a passkey that can't be used
      would, and no passkey is made. */
const BK_SCORE_SKIP = ['daily-run', 'daily-clock'];   // (a run in progress and the clock check belong to this device)
function bkSettings() { const o = {}; for (const k of Object.keys(BK_SET)) if (S.prefs[k] !== undefined) o[k] = S.prefs[k]; return o; }
function bkArcade() {
  const scores = {};
  try { for (let i = 0; i < localStorage.length; i++) { const key = localStorage.key(i); if (!key || !key.startsWith('nutcade:scores:')) continue; const id = key.slice(15); if (!BK_SCORE_SKIP.includes(id)) scores[id] = raw.get('scores:' + id, null); } } catch (e) {}
  return { scores, initials: raw.get('initials', null) };
}
// the history in a backup file: the lines that moved sats to or from the duress PIN's wallet keep their amounts but lose
// their note and mark, so a backup of the real wallet shows nothing of a duress PIN (the wallet itself keeps them)
const DURESS_NOTE = /^(Sats for the duress PIN wallet|Back from the duress PIN's wallet)$/;
const bkTx = t => t && (t.duressFund || DURESS_NOTE.test(t.note || '')) ? Object.assign({}, t, { note: '', duressFund: undefined }) : t;
const bkTxs = () => S.txs.map(bkTx);
const bkImports = () => S.imports.map(r => Object.assign({}, r, { txs: (r.txs || []).map(bkTx) }));
const bkTrophies = () => (window.Trophies && window.Trophies.got) ? window.Trophies.got() : store.get('trophies', null);
// contacts, settings, trophies and arcade progress from a backup: added next to what is here (nothing about money)
// Each part of a backup's extras is checked value by value (a backup file can be written by anyone) and imported on its
// own: a bad part is skipped and never stops the rest, or the import of the coins around it.
function importExtras(d) {
  if (!d || typeof d !== 'object') return;
  for (const f of [bkInContacts, bkInSettings, bkInTrophies, bkInArcade]) { try { f(d); } catch (e) {} }
}
const isStr = v => typeof v === 'string', isNum = v => typeof v === 'number' && Number.isFinite(v), isObj = v => !!v && typeof v === 'object' && !Array.isArray(v);
const BK_ID = /^[\w-]{1,40}$/;
let bkContactsIn = null;   // (what the last import did with the file's contacts: { added, skipped }, told to you after it)
// contacts: through the same rules as saving one by hand (saveContact), never replacing one that is here: a name, a
// Lightning address of the right shape and/or a Nostr address read from its npub (never a key taken from the file)
function bkInContacts(d) {
  if (!Array.isArray(d.contacts)) return;
  let n = 0; bkContactsIn = { added: 0, skipped: 0 };
  for (const c of d.contacts.slice(0, 200)) {
    if (S.contacts.length >= 200) break;
    const bad = () => { bkContactsIn.skipped++; };
    if (!isObj(c) || !isStr(c.name) || (c.ln != null && !isStr(c.ln)) || (c.nostr != null && !isStr(c.nostr))) { bad(); continue; }
    const name = c.name.trim().slice(0, 40); if (!name) { bad(); continue; }
    const ln = (c.ln || '').trim().toLowerCase(); if (ln && !contactLnOk(ln)) { bad(); continue; }
    let nostr = null; if ((c.nostr || '').trim()) { nostr = parseNostrAddr(c.nostr); if (!nostr) { bad(); continue; } }
    if (!ln && !nostr) { bad(); continue; }
    const nm = name.toLowerCase();   // (a twin here, by address or by name, "Mom" and "mom " alike: the one here stays as it is)
    if (S.contacts.some(x => (ln && x.ln === ln) || (nostr && x.pubkey === nostr.pubkey) || String(x.name || '').trim().toLowerCase() === nm)) { bkContactsIn.skipped++; continue; }
    const id = isStr(c.id) && BK_ID.test(c.id) && !S.contacts.some(x => x.id === c.id) ? c.id : uid();
    S.contacts.push({ id, name, ln, nostr: nostr ? c.nostr.trim().replace(/^nostr:/i, '') : '', pubkey: nostr ? nostr.pubkey : '', relays: nostr ? nostr.relays : [], created: isNum(c.created) ? c.created : Date.now() });
    n++; bkContactsIn.added++;
  }
  if (n) { S.contacts.sort((a, b) => a.name.localeCompare(b.name)); store.set('contacts', S.contacts); }
}
// settings: only how NUTCADE looks and behaves, each value of its own type and range; nothing that would reach out to a
// new service, weaken a protection or point Nostr elsewhere (relays, a longer auto-lock, the price feed, notifications)
const BK_SET = {
  sound: v => typeof v === 'boolean', music: v => typeof v === 'boolean', crt: v => typeof v === 'boolean', btcSymbol: v => typeof v === 'boolean',
  hideAmounts: v => typeof v === 'boolean', amtFiat: v => typeof v === 'boolean',
  fiat: v => v === false, arrNotify: v => v === false, nostrBackup: v => v === false, nostrInbox: v => v === false,   // (off only)
  checkSent: v => v === true, ksAuto: v => v === true,   // (on only)
  theme: v => isStr(v) && THEMES.some(t => t[0] === v), currency: v => isStr(v) && CURRENCIES.includes(v), qrLogo: v => v === 'acorn' || v === 'none',
  recentN: v => Number.isInteger(v) && v >= 0 && v <= 6, piggyStep: v => [10, 100, 1000].includes(v),
  lockAfter: v => [1, 5, 15, 60].includes(v) && ((S.prefs.lockAfter ?? 5) === 0 || v <= (S.prefs.lockAfter ?? 5))   // (only a shorter auto-lock)
};
function bkInSettings(d) {
  const st = d.settings; if (!isObj(st)) return;
  let lock = false;
  for (const k of Object.keys(BK_SET)) { if (!Object.prototype.hasOwnProperty.call(st, k)) continue; const v = st[k]; if (BK_SET[k](v)) { S.prefs[k] = v; if (k === 'lockAfter') lock = true; } }
  if (typeof setLang === 'function') setLang();
  if (lock) armAutoLock();
}
// trophies: every one earned on either side (the earlier date kept); games played: the larger counts
function bkInTrophies(d) {
  if (isObj(d.trophies)) {
    const got = Object.assign({}, store.get('trophies', null) || {}); let ch = false;
    for (const k of Object.keys(d.trophies).slice(0, 100)) { const v = d.trophies[k]; if (BK_ID.test(k) && isNum(v) && v > 0 && (!isNum(got[k]) || v < got[k])) { got[k] = v; ch = true; } }
    if (ch) { store.set('trophies', got); if (window.Trophies && window.Trophies.reload) window.Trophies.reload(); }
  }
  const pl = d.plays;
  if (isObj(pl)) {
    const p = store.get('plays', null); const out = { n: isNum(p && p.n) ? p.n : 0, by: isObj(p && p.by) ? Object.assign({}, p.by) : {} };
    if (isNum(pl.n) && pl.n >= 0) out.n = Math.max(out.n, Math.floor(pl.n));
    if (isObj(pl.by)) for (const k of Object.keys(pl.by).slice(0, 100)) { const v = pl.by[k]; if (BK_ID.test(k) && isNum(v) && v >= 0) out.by[k] = Math.max(isNum(out.by[k]) ? out.by[k] : 0, Math.floor(v)); }
    store.set('plays', out);
  }
}
// arcade: high-score tables (the best five of both), the Daily Challenge days (this device's day kept), initials if none
const INI = /^[A-Z0-9]{3}$/;
function bkInArcade(d) {
  const ar = d.arcade; if (!isObj(ar)) return;
  if (isObj(ar.scores)) for (const id of Object.keys(ar.scores).slice(0, 60)) {
    const list = ar.scores[id];
    if (!BK_ID.test(id) || BK_SCORE_SKIP.includes(id) || !Array.isArray(list)) continue;
    const mine0 = raw.get('scores:' + id, []), mine = Array.isArray(mine0) ? mine0 : [];
    if (id === 'daily') {
      const have = new Set(mine.map(x => x && x.d));
      const add = list.slice(0, 400).filter(x => isObj(x) && isStr(x.d) && /^\d{4}-\d\d-\d\d$/.test(x.d) && isNum(x.o) && isStr(x.g) && BK_ID.test(x.g) && !have.has(x.d) && have.add(x.d)).map(x => ({ d: x.d, o: x.o, g: x.g }));
      if (add.length) raw.set('scores:daily', mine.concat(add).sort((a, b) => a.d < b.d ? -1 : 1).slice(-366));
      continue;
    }
    const ok = x => isObj(x) && isStr(x.n) && INI.test(x.n) && isNum(x.s) && x.s >= 0;
    const seen = new Set(), all = mine.filter(ok).concat(list.slice(0, 20).filter(ok)).map(x => ({ n: x.n, s: x.s, t: isNum(x.t) ? x.t : 0 })).filter(x => { const k = x.n + ':' + x.s + ':' + x.t; return !seen.has(k) && seen.add(k); });
    all.sort((a, b) => b.s - a.s); raw.set('scores:' + id, all.slice(0, 5));
  }
  if (isStr(ar.initials) && INI.test(ar.initials) && !raw.get('initials', null)) raw.set('initials', ar.initials);
}

/* ---------- the password on the backup file ---------- */
const LOCK_AAD = new TextEncoder().encode('nutcade-locked-backup-v1');
const isLocked = d => !!d && d.app === 'nutcade' && d.kind === 'locked-backup';
async function lockKey(pw, salt, iter) {
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(String(pw)), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'PBKDF2', salt, iterations: iter, hash: 'SHA-256' }, base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
}
async function lockBackup(text, pw) {
  const salt = rnd(16), iv = rnd(12), key = await lockKey(pw, salt, PBKDF2_ITER);
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: LOCK_AAD }, key, new TextEncoder().encode(text));
  return JSON.stringify({ app: 'nutcade', kind: 'locked-backup', v: 1, kdf: { alg: 'PBKDF2-SHA256', iter: PBKDF2_ITER, salt: b64e(salt) }, cipher: { alg: 'AES-256-GCM', iv: b64e(iv) }, ct: b64e(ct) }, null, 1);
}
// the backup inside a locked file, or an error (wrong password and a damaged file read the same: nothing was changed)
async function unlockBackup(d, pw) {
  const bad = () => new Error('Wrong password, or the file is damaged. Nothing was changed.');
  if (d.v !== 1 || !d.kdf || d.kdf.alg !== 'PBKDF2-SHA256' || !Number.isInteger(d.kdf.iter) || d.kdf.iter < 100000 || d.kdf.iter > 10000000 || !d.cipher || d.cipher.alg !== 'AES-256-GCM') throw new Error('This locked backup was made by a newer NUTCADE or is damaged. Nothing was changed.');
  let pt;
  try { const key = await lockKey(pw, b64d(d.kdf.salt), d.kdf.iter); pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(d.cipher.iv), additionalData: LOCK_AAD }, key, b64d(d.ct)); } catch (e) { throw bad(); }
  let inner; try { inner = JSON.parse(new TextDecoder().decode(pt)); } catch (e) { throw bad(); }
  if (!inner || inner.app !== 'nutcade' || isLocked(inner)) throw bad();
  return inner;
}
let bkLockOn = false;   // "Protect with a password" (this screen only: never stored)
const backupName = () => `nutcade-backup-${new Date().toISOString().slice(0, 10)}.json`;
function saveBackupFile(data) {
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([data], { type: 'application/json' }));
  a.download = backupName(); document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000); S.prefs.backupFileAt = Date.now(); save();
}
function openLockSheet() {
  openSheet('Backup file', `<p style="margin:0">Choose a password for the file. Anyone with the file and the password can spend your sats.</p>
    <div class="field"><label for="bkPw">Password</label><input id="bkPw" class="inp" type="password" autocomplete="new-password"></div>
    <div class="field"><label for="bkPw2">Same password again</label><input id="bkPw2" class="inp" type="password" autocomplete="new-password"></div>
    <div class="th">NUTCADE can't recover a forgotten password. Your 12 words still restore your sats.</div>
    <button class="btn solid gold block" data-act="bkLockGo">Download locked backup</button><div id="sheetErr"></div>`);
}
// the password field of the Import sheet, shown once the text is a locked backup
function restorePwField() {
  let d = null; try { d = JSON.parse(val('restoreIn')); } catch (e) {}
  if (!isLocked(d) || $('#restorePw')) return !!$('#restorePw');
  const box = $('#restoreIn'); const f = box && box.closest('.field'); if (!f) return false;
  f.insertAdjacentHTML('afterend', `<div class="field" id="restorePwF"><label for="restorePw">Backup password</label><input id="restorePw" class="inp" type="password" autocomplete="current-password"><div class="th">This backup is locked with a password.</div></div>`);
  const i = $('#restorePw'); if (i && !matchMedia('(pointer:coarse)').matches) i.focus();
  return false;
}

/* ---------- Back up with my phone ---------- */
const PB_D = 'nutcade-phone-backup', PB_TAG = new TextEncoder().encode('NCPB');
let phoneCap = null, pbSalt = null;
async function phoneCapCheck() {
  let ok = false;
  try {
    if (window.PublicKeyCredential && navigator.credentials && window.isSecureContext !== false) {
      if (PublicKeyCredential.getClientCapabilities) { const c = await PublicKeyCredential.getClientCapabilities(); ok = !!c['extension:prf'] && !!(c.userVerifyingPlatformAuthenticator || c.passkeyPlatformAuthenticator || c.hybridTransport); }
      else ok = await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
    }
  } catch (e) { ok = false; }
  phoneCap = ok;
  document.querySelectorAll('[data-phonecap]').forEach(x => { x.hidden = !ok; });
  return ok;
}
phoneCapCheck();
const pbRec = () => { const r = store.get('phonebk', null); return r && r.pk && Array.isArray(r.erase) ? r : null; };
// the phone backup goes to NUTCADE's default relays and the ones you set (both), so a new phone with the defaults finds it
const pbRelays = () => [...new Set(BACKUP_RELAYS.concat(relays()))];
// what removes the copy later, signed now: an empty copy one second newer and a deletion request (NIP-09). The record keeps
// these two events, not the key that signed them, so Reset and Remove need no passkey and no key is kept on this phone
const pbTombs = (sk, pk, at) => [
  L.finalizeEvent({ kind: 30078, created_at: at + 1, tags: [['d', PB_D]], content: '' }, sk),
  L.finalizeEvent({ kind: 5, created_at: at + 1, tags: [['a', `30078:${pk}:${PB_D}`], ['k', '30078']], content: '' }, sk)];
const pbFp = async m => hex(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode('nutcade-phone-backup-fp:' + m)))).slice(0, 16);
const pbOff = what => { const e = new Error(what === 'restore' ? "Restore with my phone isn't available right now. Try again later." : "Back up with my phone isn't available right now. Try again later."); e.keep = true; return e; };
async function pbKeys(secret) {
  if (!pbSalt) pbSalt = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode('nutcade-phone-backup-v1')));
  const base = await crypto.subtle.importKey('raw', secret, 'HKDF', false, ['deriveBits', 'deriveKey']);
  const h = info => ({ name: 'HKDF', hash: 'SHA-256', salt: pbSalt, info: new TextEncoder().encode(info) });
  const sk = new Uint8Array(await crypto.subtle.deriveBits(h('nostr-key'), base, 256));
  const aes = await crypto.subtle.deriveKey(h('aes-key'), base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
  return { sk, pk: L.nostrPub(sk), aes };
}
const pbPrfSalt = async () => { await pbKeys(new Uint8Array(32)); return pbSalt; };
const pbForgetPasskey = credId => { try { if (credId && PublicKeyCredential.signalUnknownCredential) PublicKeyCredential.signalUnknownCredential({ rpId: location.hostname, credentialId: b64e(b64d(credId)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '') }).catch(() => {}); } catch (e) {} };
// the passkey's secret (PRF) for the phone backup: a new passkey, or the one this wallet made before
async function pbSecret(rec, what) {
  const salt = await pbPrfSalt();
  const noPrf = () => new Error("This phone or browser can't lock your words with a passkey. Nothing was saved. Your 12 words are still your backup.");
  try {
    if (rec && rec.credId) {
      let a;
      try { a = await navigator.credentials.get({ publicKey: { challenge: rnd(32), allowCredentials: [{ type: 'public-key', id: b64d(rec.credId) }], userVerification: 'required', timeout: 120000, extensions: { prf: { eval: { first: salt } } } }, signal: pbSig || undefined }); }
      catch (e) {   // (no such passkey any more, or the step was cancelled: Remove phone backup needs no passkey, then a new one can be made)
        if (e && /NotAllowed|Abort|InvalidState|Security|NotSupported/i.test(e.name || '')) { const x = new Error("Your phone backup's passkey wasn't found, or the step was cancelled. If you deleted the passkey, tap Remove phone backup, then back up again."); x.fix = { act: 'phoneRemoveAsk', label: 'Remove phone backup' }; throw x; }
        throw e;
      }
      const r = a.getClientExtensionResults().prf; if (!r || !r.results || !r.results.first) throw noPrf();
      return { secret: new Uint8Array(r.results.first), credId: rec.credId };
    }
    const id = new Uint8Array(16); id.set(PB_TAG); id.set(rnd(12), 4);
    const cred = await navigator.credentials.create({ publicKey: {
      rp: { name: 'NUTCADE', id: location.hostname }, user: { id, name: 'NUTCADE 12-word backup', displayName: 'NUTCADE 12-word backup' },
      challenge: rnd(32), pubKeyCredParams: [{ type: 'public-key', alg: -7 }, { type: 'public-key', alg: -257 }],
      authenticatorSelection: { residentKey: 'required', requireResidentKey: true, userVerification: 'required' },
      timeout: 120000, extensions: { prf: { eval: { first: salt } } } }, signal: pbSig || undefined });
    const credId = b64e(new Uint8Array(cred.rawId)), ext = cred.getClientExtensionResults().prf;
    if (!ext || ext.enabled === false) { pbForgetPasskey(credId); throw noPrf(); }
    if (ext.results && ext.results.first) return { secret: new Uint8Array(ext.results.first), credId };
    const a = await navigator.credentials.get({ publicKey: { challenge: rnd(32), allowCredentials: [{ type: 'public-key', id: b64d(credId) }], userVerification: 'required', timeout: 120000, extensions: { prf: { eval: { first: salt } } } }, signal: pbSig || undefined });
    const r = a.getClientExtensionResults().prf; if (!r || !r.results || !r.results.first) { pbForgetPasskey(credId); throw noPrf(); }
    return { secret: new Uint8Array(r.results.first), credId };
  } catch (e) { if (e && /NotAllowed|Abort|InvalidState|Security|NotSupported/i.test(e.name || '')) throw pbOff(what); throw e; }
}
// lock the 12 words and put them on the relays; the local record only once a relay said OK
// the copy on the relays for this passkey now: { ev, words } (words null when it can't be opened), null when there is none
async function pbCurrent(k) {
  const evs = await relayQuery({ kinds: [30078], authors: [k.pk], '#d': [PB_D], limit: 5 }, 5000, pbRelays());   // (every relay asked, up to 5 s: the newest copy wins, never only the fastest relay's)
  if (!evs.length && !evs.answered) throw new Error('No Nostr relay answered, so nothing was saved. Check your connection and try again.');
  const ev = evs.filter(e => e.pubkey === k.pk && e.kind === 30078 && (e.tags || []).some(t => t[0] === 'd' && t[1] === PB_D) && L.verifyEvent(e)).sort((x, y) => y.created_at - x.created_at || (x.id < y.id ? -1 : x.id > y.id ? 1 : 0))[0];
  if (!ev || !ev.content) return null;
  try {
    const box = JSON.parse(ev.content);
    const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(box.iv), additionalData: new TextEncoder().encode(k.pk) }, k.aes, b64d(box.ct));
    return { ev, words: cleanPhrase(JSON.parse(new TextDecoder().decode(pt)).words) };
  } catch (e) { return { ev, words: null }; }
}
async function phoneBackup(force) {
  const sig = pbSig;
  if (vault.on && vault.decoy) throw pbOff('backup');   // (the duress PIN's wallet: no passkey is made, nothing is sent)
  if (!S.seed) throw new Error('Create or restore a wallet first.');
  if (isOffline()) throw new Error('Back up with my phone needs a connection. Try again online.');
  const old = pbRec(), mnemonic = S.seed.mnemonic;
  const { secret, credId } = await pbSecret(old, 'backup');
  const k = await pbKeys(secret);
  // a synced passkey is shared by your phones: a copy of other 12 words (another phone, another wallet) is never replaced
  // without asking; if no relay can say what is there, nothing is replaced
  let cur; try { cur = await pbCurrent(k); } catch (e) { if (!old) pbForgetPasskey(credId); throw e; }
  // (a copy this phone saved itself, and nothing newer since, is simply updated: new words after New recovery phrase)
  const mine = cur && old && old.pk === k.pk && cur.ev.created_at <= old.at && cur.words && old.fp === await pbFp(cur.words);
  if (cur && cur.words !== mnemonic && !mine && !force) { const x = new Error('The copy on the Nostr relays for this passkey holds other 12 words, saved from another phone or another wallet. Replacing it means that phone backup is lost.'); x.fix = { act: 'phoneGoForce', label: 'Replace anyway' }; throw x; }
  const iv = rnd(12), body = JSON.stringify({ v: 1, words: mnemonic, mints: mintAddrs().slice(0, 20), at: Math.floor(Date.now() / 1000) });
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: new TextEncoder().encode(k.pk) }, k.aes, new TextEncoder().encode(body));
  const ts = Math.max(Math.floor(Date.now() / 1000), ((old && old.pk === k.pk && old.at) || 0) + 1, cur ? cur.ev.created_at + 1 : 0);
  const ev = L.finalizeEvent({ kind: 30078, created_at: ts, tags: [['d', PB_D]], content: JSON.stringify({ v: 1, alg: 'A256GCM', iv: b64e(iv), ct: b64e(new Uint8Array(ct)) }) }, k.sk);
  try { pbStop(sig); } catch (e) { if (!old) pbForgetPasskey(credId); throw e; }   // (a step replaced or closed meanwhile publishes nothing, and leaves no new passkey behind)
  const n = await relayPublish(ev, 6000, pbRelays(), 1500);
  if (!n) { if (!old) pbForgetPasskey(credId); throw new Error('No Nostr relay answered, so nothing was saved. Check your connection and try again.'); }
  if (old && old.pk !== k.pk) await pbErase(old).catch(() => 0);
  store.set('phonebk', { pk: k.pk, credId, at: ts, fp: await pbFp(mnemonic), n, erase: pbTombs(k.sk, k.pk, ts) });
  return n;
}
// the copy on the relays replaced by an empty one, and a deletion request (NIP-09) for it: returns how many relays took it
async function pbErase(rec, timeout) {
  const [blank, del] = rec.erase, list = pbRelays();
  const [n] = await Promise.all([relayPublish(blank, timeout || 6000, list, 1500), relayPublish(del, timeout || 6000, list, 1500)]);
  return n;
}
async function phoneRemove() {
  const rec = pbRec(); if (!rec) return 0;
  const n = await pbErase(rec);
  if (!n) throw new Error('No Nostr relay answered, so the phone backup is still there. Try again online.');
  pbForgetPasskey(rec.credId); raw.del('phonebk');
  return n;
}
// the 12 words from the relays, opened with a passkey; nothing here changes the wallet
async function phoneFetch() {
  if (vault.on && vault.decoy) throw pbOff('restore');
  if (isOffline()) throw new Error('Restore with my phone needs a connection. Try again online.');
  const salt = await pbPrfSalt();
  let a;
  try { a = await navigator.credentials.get({ publicKey: { challenge: rnd(32), userVerification: 'required', timeout: 120000, extensions: { prf: { eval: { first: salt } } } }, signal: pbSig || undefined }); }
  catch (e) { if (e && /NotAllowed|Abort|Security|NotSupported|InvalidState/i.test(e.name || '')) throw new Error('The passkey step was cancelled. Nothing was changed.'); throw e; }
  const uh = a.response && a.response.userHandle ? new Uint8Array(a.response.userHandle) : null;
  if (!uh || uh.length < 4 || PB_TAG.some((x, i) => uh[i] !== x)) throw new Error("That passkey isn't a NUTCADE phone backup. Nothing was changed.");
  const r = a.getClientExtensionResults().prf;
  if (!r || !r.results || !r.results.first) throw new Error("This phone or browser can't open a phone backup. Nothing was changed. Use your 12 words.");
  const k = await pbKeys(new Uint8Array(r.results.first));
  const evs = await relayQuery({ kinds: [30078], authors: [k.pk], '#d': [PB_D], limit: 5 }, 5000, pbRelays());   // (every relay asked, up to 5 s: the newest copy wins, never only the fastest relay's)
  if (!evs.length && !evs.answered) throw new Error('No Nostr relay answered. Check your connection and try again. Nothing was changed.');
  const ev = evs.filter(e => e.pubkey === k.pk && e.kind === 30078 && (e.tags || []).some(t => t[0] === 'd' && t[1] === PB_D) && L.verifyEvent(e)).sort((x, y) => y.created_at - x.created_at || (x.id < y.id ? -1 : x.id > y.id ? 1 : 0))[0];
  if (!ev || !ev.content) throw new Error('No phone backup was found for this passkey. Nothing was changed.');
  const bad = () => new Error("This phone backup couldn't be opened with this passkey. Nothing was changed.");
  let body;
  try {
    const box = JSON.parse(ev.content); if (box.v !== 1 || box.alg !== 'A256GCM') throw 0;
    const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(box.iv), additionalData: new TextEncoder().encode(k.pk) }, k.aes, b64d(box.ct));
    body = JSON.parse(new TextDecoder().decode(pt));
  } catch (e) { throw bad(); }
  const words = cleanPhrase(body && body.words);
  if (!validPhrase(words)) throw bad();
  return { words, mints: (Array.isArray(body.mints) ? body.mints : []).filter(u => typeof u === 'string' && /^https?:\/\/\S+$/i.test(u)).map(extUrlOr).filter(Boolean),
    rec: { pk: k.pk, credId: b64e(new Uint8Array(a.rawId)), at: ev.created_at, n: 0, erase: pbTombs(k.sk, k.pk, ev.created_at) } };
}
// the Restore wallet sheet, filled from a phone backup: the words are kept in a hidden field (never shown), the mints ticked
// one passkey step at a time (a second tap, or a button drawn again while one runs, does nothing)
// A new tap replaces a step still waiting for its passkey (that one is cancelled and says nothing), and closing the
// screen a step was started on cancels it, so nothing is left holding the next step up
let pbRun = null, pbSig = null;
const pbOnce = fn => async () => {
  if (pbRun) pbRun.ac.abort();
  const me = pbRun = { ac: new AbortController(), sheet: $('#layer .sheet') }; pbSig = me.ac.signal;
  try { const r = await fn(me.ac.signal); return r; }
  catch (e) { if (pbRun !== me || me.ac.signal.aborted) return; throw e; }
  finally { if (pbRun === me) { pbRun = null; pbSig = null; } }
};
function pbSheetClosed(sheet) { try { if (pbRun && sheet && pbRun.sheet === sheet) pbRun.ac.abort(); } catch (e) {} }   // (also before this file's lines have run)
const pbStop = sig => { if (sig && sig.aborted) throw Object.assign(new Error('replaced'), { name: 'AbortError' }); };
let pbFrom = null;   // (the phone backup the Restore sheet was filled from: once restored, this wallet keeps its record)
function phoneFill(r) {
  const f = $('#phraseField'); if (!f) return;
  pbFrom = r;
  f.innerHTML = '<div class="notice cyan">Your 12 words came from your phone backup. They are not shown here.</div>';
  const i = document.createElement('input'); i.type = 'hidden'; i.id = 'phraseIn'; i.value = r.words; f.appendChild(i);
  const pb = $('#layer [data-act=phoneRestore]'); if (pb) pb.remove();
  const list = $('#rmList');
  if (list) for (const u of r.mints) {
    const box = [...list.querySelectorAll('[data-rmint]')].find(x => x.dataset.rmint === u);
    if (box) box.checked = true;
    else { const n = list.querySelectorAll('[data-rmint]').length; list.insertAdjacentHTML('afterbegin', `<label class="toggle" for="rmp${n}" style="font-size:19px"><span style="overflow-wrap:anywhere;min-width:0" data-noi18n>${esc(host(u))}</span><input id="rmp${n}" type="checkbox" data-rmint="${esc(u)}" checked></label>`); }
  }
  const fm = $('#layer [data-act=findMints]'); if (fm) fm.click();   // (the mint-list backup on Nostr, as for typed words)
}
// what a step does to a phone backup made in this wallet, said on that step's screen (nothing when there is none)
function pbWarn(kind) {
  if (!pbRec()) return '';
  if (kind === 'reset') return '<div class="notice red">This also deletes your phone backup from the Nostr relays, so Restore with my phone will not bring this wallet back. Without your 12 words, your sats are gone for good.</div>';
  return '<div class="notice">Your phone backup holds this wallet\'s 12 words. If this changes them, the phone backup is out of date until you tap Back up again in Settings.</div>';
}
function phonePanel() {
  const rec = pbRec();
  if (rec) setTimeout(() => pbStateCheck().catch(() => {}), 0);
  return `<div data-phonecap ${phoneCap ? '' : 'hidden'}><div class="sub">Back up with my phone</div>
      <p class="th" style="margin:0">Locks your 12 words with a passkey (Face ID or fingerprint) and keeps the locked copy on Nostr relays. A new phone gets them back with the same passkey. Your 12 words stay your main backup.</p>
      <div class="row between tiny"><span>Phone backup</span><span data-pbstate style="color:${rec ? 'var(--lime)' : 'var(--dim)'}">${rec ? esc(timeAgo(rec.at * 1000).toUpperCase()) : 'NOT SET UP'}</span></div>
      <p class="th" style="margin:0;color:var(--gold)" data-pbstale hidden>It holds your old 12 words. Tap Back up again to save the new ones.</p>
      <div class="row wrap"><button class="btn sm violet" data-act="phoneOpen">${rec ? 'Back up again' : 'Back up with my phone'}</button>${rec ? '<button class="btn sm" data-act="phoneRemoveAsk">Remove phone backup</button>' : ''}</div></div>`;
}
// an older phone backup (other words than this wallet's now) is shown as out of date
async function pbKeep(phrase) {
  const r = pbFrom; pbFrom = null;
  if (!r || r.words !== phrase || (vault.on && vault.decoy)) return;
  store.set('phonebk', Object.assign({}, r.rec, { fp: await pbFp(phrase) }));
}
async function pbStateCheck() {
  const rec = pbRec(), el = document.querySelector('[data-pbstate]'); if (!rec || !el || !S.seed) return;
  if (rec.fp && rec.fp !== await pbFp(S.seed.mnemonic)) { el.textContent = tr('OUT OF DATE'); el.style.color = 'var(--gold)'; const n = document.querySelector('[data-pbstale]'); if (n) n.hidden = false; }
}
