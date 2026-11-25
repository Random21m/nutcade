/* ---------- Mint login (1.33.0): NUT-21 clear auth and NUT-22 blind auth ----------
   A mint can ask for a login before it mints, pays out, swaps or answers the other requests it lists (NUT-21: an
   OpenID Connect account at the login server its info names), and then for one blind auth token (a BAT, NUT-22) with
   each of those requests. The protocol is cashu-ts's own: the Mint object gets an auth provider (authProvider below)
   and the library adds the Blind-auth and Clear-auth headers exactly where the mint's info says; cashu-ts's
   AuthManager mints and checks the BATs (with the mint's DLEQ proof); its OIDCAuth does the login (device code,
   RFC 8628, when the login server offers it; otherwise code + PKCE in a login window that comes back to this page).
   - The login: the access token (the CAT) and the refresh token are kept per mint address in S.auth (store 'auth':
     inside the PIN vault with a PIN, each wallet its own), never in a backup file, a phone backup or wallet sync,
     dropped by a restore from other words, Log out and Reset. A refresh is silent; one the login server refuses
     ends the login ("log in again"); one it doesn't answer keeps it ("isn't answering", tried again 30 s later).
     The refresh token goes only to the token address the login was made with: a mint whose info changes its login
     server or client id (or a login server whose token address changes) needs a new login.
   - Addresses: the login server's discovery document, token, device and login page addresses must be https (plain
     http only on this computer, 127.0.0.1 or localhost, for a mint on this computer too). Anything else is refused
     before anything is sent there.
   - BATs (unit 'auth') are not money: they live only in S.auth[mint].bats, never with the coins, so no balance, token,
     Send all, backup, sync or restore ever sees one. A small stock (at most the mint's bat_max_mint, and 5), minted
     with the CAT when none is left, one taken for each protected request and saved as gone before the request
     leaves. The mint answers decide what happens to it (auReq): an answer that isn't 31002 means the mint used it;
     no answer (offline, a time limit, 429) puts it back; 31002 (spent elsewhere, from an old login, or Nutshell
     refusing the request itself) is tried once more with a BAT minted right then: refused again means the mint
     turned the request down, and both go back (Nutshell keeps a refused request's BAT unspent).
   - Nothing is booked from a request that found no login: authErr is a refusal (code 30001, status 401) thrown before
     the request leaves, so the journal treats the step as signed-nothing, and authGate refuses a step before it is
     written down when no BAT can be had. A step that loses its login midway (a deposit paid, a payment's coins made
     ready) is settled by the journal once logged in again (authAfter runs the mint's background check and auto-move).
   - Nothing about the login is written to the console. */
const AUTH_POOL = 5, AUTH_MS = 15000;
S.auth = store.get('auth', {}) || {};
const au = { info: new Map(), mgr: new Map(), chain: new Map(), out: new Map(), cool: new Map(), refresh: new Map(), oidc: new Map(), live: null };
const auQuiet = { error() {}, warn() {}, info() {}, debug() {}, trace() {}, log() {} };
let auBase = null; try { const r = new L.Mint('https://localhost')._request; if (typeof r === 'function') auBase = r; } catch (e) {}   // (the library's own request function, wrapped by auReq)
const saveAuth = () => store.set('auth', S.auth);
const auLoop = h => /^(127\.0\.0\.1|localhost|\[::1\])$/i.test(h);
// an address NUTCADE may send a login to: https, or plain http on this computer for a mint on this computer
function auSafe(u, mint) {
  try {
    const x = new URL(String(u == null ? '' : u)); if (x.username || x.password || !x.hostname) return null;
    if (x.protocol === 'https:') return x.href;
    if (x.protocol === 'http:' && auLoop(x.hostname) && auLoop(new URL(mint).hostname)) return x.href;
  } catch (e) {}
  return null;
}
// what the mint's info asks (cashu-ts normalised it; anything malformed counts as no login)
function auInfo(info) {
  let n = {}; try { n = info.nuts || {}; } catch (e) {}
  const eps = s => s && typeof s === 'object' && Array.isArray(s.protected_endpoints) ? s.protected_endpoints.filter(p => p && typeof p.method === 'string' && typeof p.path === 'string') : [];
  const n21 = n[21] && typeof n[21] === 'object' ? n[21] : null, n22 = n[22] && typeof n[22] === 'object' ? n[22] : null;
  const blind = eps(n22).length > 0, clear = eps(n21).some(p => p.path !== '/v1/auth/blind/mint');
  const disc = n21 && typeof n21.openid_discovery === 'string' ? n21.openid_discovery.slice(0, 500) : '';
  const cid = n21 && typeof n21.client_id === 'string' && /^[\x21-\x7e]{1,200}$/.test(n21.client_id) ? n21.client_id : 'cashu-client';
  const max = n22 && Number.isSafeInteger(n22.bat_max_mint) && n22.bat_max_mint > 0 ? n22.bat_max_mint : 1;
  return { need: blind || clear, blind, clear, disc, cid, max };
}
const auDrop = e => { for (const k of ['at', 'rt', 'exp', 'who', 'tep', 'since']) delete e[k]; e.bats = []; e.gen = (e.gen || 0) + 1; };
// the mint's info, each time its wallet is loaded: a login asked for (or no longer), its login server
function authSeen(addr, w) {
  let i; try { const mi = w.getMintInfo(); au.info.set(addr, mi); i = auInfo(mi); } catch (e) { return; }
  const e = S.auth[addr];
  if (!i.need) { if (e) { delete S.auth[addr]; au.mgr.delete(addr); saveAuth(); } return; }
  const x = e || (S.auth[addr] = { gen: 0, bats: [] });
  let ch = !e;
  if (x.disc !== i.disc || x.cid !== i.cid) { if (e) auDrop(x); x.disc = i.disc; x.cid = i.cid; ch = true; }   // (another login server or client: the old login is never sent there)
  for (const k of ['blind', 'clear', 'max']) if (x[k] !== i[k]) { x[k] = i[k]; ch = true; }
  const bad = auSafe(i.disc, addr) ? 0 : 1; if (x.bad !== bad) { x.bad = bad; ch = true; }
  if (!x.need) { x.need = 1; ch = true; }
  if (ch) { saveAuth(); au.mgr.delete(addr); }
}
const AUTH_TXT = {
  login: 'This mint needs a login. Log in on the Mints tab, then try again.',
  again: 'Your login at this mint has ended. Log in again on the Mints tab, then try again.',
  down: "The mint's login server isn't answering. Try again in a moment.",
  refused: "The mint's login server turned the login down.",
  bad: "This mint asks for a login NUTCADE can't use: its login server must be on https and offer a code or a browser login.",
  expired: 'The login code expired. Tap Log in to start again.',
  popup: 'The login window was blocked. Allow pop-ups for NUTCADE, then tap Log in again.',
  busy: 'The mint is busy. Wait a moment and try again.'
};
function authErr(addr, kind) {
  const e = new Error(AUTH_TXT[kind] || AUTH_TXT.login);
  return Object.assign(e, { keep: true, login: kind, code: 30001, status: 401, authMint: addr }, ['login', 'again'].includes(kind) ? { fix: { act: 'authLogin', label: 'Log in', a: addr } } : {});
}
function authState(addr) {
  const e = S.auth[acctUrl(addr)];
  if (!e || !e.need) return { need: false, inn: false, again: false, who: '', bats: 0, bad: false };
  return { need: true, inn: !!(e.rt || (e.at && (!e.exp || e.exp > Date.now()))), again: !!e.again, who: e.who || '', bats: (e.bats || []).length, bad: !!e.bad };
}
function auOidc(e) {
  const k = e.disc + '\n' + e.cid;
  if (!au.oidc.has(k)) au.oidc.set(k, new L.OIDCAuth(e.disc, { clientId: e.cid, logger: auQuiet }));
  return au.oidc.get(k);
}
const auCfg = async (addr, e) => { try { return await inTime(auOidc(e).loadConfig(), AUTH_MS); } catch (x) { au.oidc.delete(e.disc + '\n' + e.cid); throw authErr(addr, 'down'); } };
// who is logged in, from the access token (shown as text only)
function auWho(at) {
  try { const p = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(at.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0)))); return clipText(String(p.preferred_username || p.email || p.name || p.sub || ''), 60); } catch (e) { return ''; }
}
function auExp(at) { try { const p = JSON.parse(atob(at.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))); return Number.isFinite(p.exp) ? p.exp * 1000 : 0; } catch (e) { return 0; } }
function authKeep(e, t) {
  if (!t || typeof t.access_token !== 'string' || !t.access_token || t.access_token.length > 16384) throw new Error('bad token');
  e.at = t.access_token;
  if (typeof t.refresh_token === 'string' && t.refresh_token && t.refresh_token.length <= 16384) e.rt = t.refresh_token;
  const ei = Number(t.expires_in); e.exp = Number.isFinite(ei) && ei > 0 ? Date.now() + Math.min(ei, 366 * 86400) * 1000 : auExp(t.access_token);
  e.who = auWho(t.access_token) || e.who || ''; e.again = 0;
}
// the login ended (the login server refused the refresh): everything of it goes, "log in again"
function authEnd(addr) { const e = S.auth[addr]; if (!e) return; auDrop(e); e.again = 1; saveAuth(); au.mgr.delete(addr); setTimeout(authRedraw, 0); }
function authLogout(addr) { const e = S.auth[addr]; if (!e) return; auDrop(e); e.again = 0; saveAuth(); au.mgr.delete(addr); au.cool.delete(addr); }
const authRedraw = () => { try { if (tab === 'mints' && !$('#layer .sheet')) refresh(); } catch (e) {} };
// a CAT good for 30 s more, refreshed silently when it isn't (one refresh at a time per mint)
async function authCAT(addr, force) {
  const e = S.auth[addr];
  if (!e || !e.need) throw authErr(addr, 'login');
  if (e.bad) throw authErr(addr, 'bad');
  if (!e.at && !e.rt) throw authErr(addr, e.again ? 'again' : 'login');
  if (!force && e.at && (!e.exp || e.exp - Date.now() > 30e3)) return e.at;
  if (!e.rt) { authEnd(addr); throw authErr(addr, 'again'); }
  if ((au.cool.get(addr) || 0) > Date.now()) throw authErr(addr, 'down');
  let f = au.refresh.get(addr);
  if (!f) { f = authRefresh(addr, e).finally(() => au.refresh.delete(addr)); au.refresh.set(addr, f); }
  return f;
}
async function authRefresh(addr, e) {
  const gen = e.gen; let t;
  try {
    let cfg = await auCfg(addr, e);
    if (e.tep && cfg.token_endpoint !== e.tep) { au.oidc.delete(e.disc + '\n' + e.cid); cfg = await auCfg(addr, e); }   // (read once more before giving up on it)
    if (!e.tep || cfg.token_endpoint !== e.tep) { authEnd(addr); throw authErr(addr, 'again'); }   // (never sent to a token address the login wasn't made with)
    t = await inTime(auOidc(e).refresh(e.rt), AUTH_MS);
  } catch (x) {
    if (x && x.login) { if (x.login === 'down') au.cool.set(addr, Date.now() + 30e3); throw x; }
    if (/invalid_grant|invalid_token|invalid_client|unauthorized|access_denied|HTTP 40[0-3]/i.test(String(x && x.message))) { if (S.auth[addr] === e && e.gen === gen) authEnd(addr); throw authErr(addr, 'again'); }
    au.cool.set(addr, Date.now() + 30e3); throw authErr(addr, 'down');
  }
  if (S.auth[addr] !== e || e.gen !== gen) throw authErr(addr, 'login');   // (logged out meanwhile: nothing kept)
  try { authKeep(e, t); } catch (x) { authEnd(addr); throw authErr(addr, 'again'); }
  saveAuth(); return e.at;
}
/* ---------- BATs ---------- */
function auMgr(addr) {
  if (!au.mgr.has(addr)) au.mgr.set(addr, new L.AuthManager(addr, { desiredPoolSize: AUTH_POOL, logger: auQuiet }));
  return au.mgr.get(addr);
}
// one BAT step at a time per mint (the stock is read from S.auth and written back each time)
function auLock(addr, fn) {
  const prev = au.chain.get(addr) || Promise.resolve(), run = prev.catch(() => {}).then(fn);
  au.chain.set(addr, run.catch(() => {})); return run;
}
const auCap = e => Math.max(1, Math.min(num(e.max) || 1, AUTH_POOL));
async function auTopUp(addr, e, m) {
  const mint = async force => { m.setCAT(await authCAT(addr, force)); await m.init(); await m.topUp(Math.max(1, auCap(e) - m.poolSize)); };
  try { await mint(false); }
  catch (x) {
    if (x && x.login) throw x;
    const c = num(x && x.code);
    if (c === 30002 || c === 30001) {   // the mint refused the CAT: one fresh one, then the login has ended
      try { await mint(true); return; } catch (y) { if (y && y.login) throw y; if ([30001, 30002].includes(num(y && y.code))) { authEnd(addr); throw authErr(addr, 'again'); } throw y; }
    }
    if (c === 31004 || (x && x.status === 429)) throw authErr(addr, 'busy');
    throw x;
  }
}
const auEnc = p => 'authA' + btoa(unescape(encodeURIComponent(JSON.stringify({ id: p.id, secret: p.secret, C: p.C })))).replace(/\+/g, '-').replace(/\//g, '_');
// a BAT for one request: taken from the stock (topped up with the CAT when empty), saved as gone before it is sent
function auTake(addr, fresh) {
  return auLock(addr, async () => {
    const e = S.auth[addr]; if (!e || !e.need) throw authErr(addr, 'login');
    const m = auMgr(addr); m.importPool(e.bats || [], 'replace');
    if (fresh || !m.poolSize) { try { await auTopUp(addr, e, m); } finally { e.bats = m.exportPool(); saveAuth(); } }
    const p = m.pool.pop(); if (!p) throw authErr(addr, 'login');
    e.bats = m.exportPool(); saveAuth();
    const t = auEnc(p); au.out.set(t, { p, gen: e.gen }); if (au.out.size > 200) au.out.delete(au.out.keys().next().value);
    return t;
  });
}
// BATs the mint didn't use, back in the stock (used next); never into a login that has ended or changed since
function auGive(addr, recs) {
  return auLock(addr, async () => {
    const e = S.auth[addr]; if (!e) return;
    const ok = recs.filter(r => r && r.gen === e.gen).map(r => r.p); if (!ok.length) return;
    const have = new Set((e.bats || []).map(p => p.secret));
    e.bats = (e.bats || []).concat(ok.filter(p => !have.has(p.secret))); saveAuth();
  });
}
const auAnswered = e => !!e && (typeof e.status === 'number' || typeof e.code === 'number') && e.status !== 429;
// the library's request, watching what the mint does with each BAT (see the top of this file)
const auReq = addr => async o0 => {
  const o = await auFill(addr, o0);
  const h = (o && o.headers) || {}, k = Object.keys(h).find(x => x.toLowerCase() === 'blind-auth'), t = k ? h[k] : null;
  if (!t) return auBase(o);
  const rec = au.out.get(t); au.out.delete(t);
  try { return await auBase(o); }
  catch (e) {
    if (!rec) throw e;
    if (!auAnswered(e)) { await auGive(addr, [rec]); throw e; }
    if (num(e.code) !== 31002) throw e;   // (the mint answered: it used the BAT)
    let t2; try { t2 = await auTake(addr, true); } catch (x) { await auGive(addr, [rec]); throw x && x.login ? x : e; }
    const rec2 = au.out.get(t2); au.out.delete(t2);
    try { return await auBase(Object.assign({}, o, { headers: Object.assign({}, h, { [k]: t2 }) })); }   // (the first BAT stays out: spent elsewhere or no longer good)
    catch (e2) {
      if (!auAnswered(e2)) await auGive(addr, [rec2]);
      else if (num(e2.code) === 31002) { await auGive(addr, [rec, rec2]); await auTruth(addr, o, e2).catch(() => {}); }   // (a BAT minted a moment ago refused too: it is the request the mint turned down, and the mint is asked why)
      throw e2;
    }
  }
};
/* Nutshell answers a refused protected request with 31002 whatever the reason ("Blind authentication failed"). Every
   place that acts on the mint's reason (spent coins pruned and tried again, a pending step left to wait, "already
   claimed", a deposit already issued) would see only "the mint turned this down". So the mint is asked what is true,
   and the refusal gets the answer a mint without login would have given: the request's coins SPENT (11001) or
   PENDING (11002), else its quote (a deposit ISSUED, PENDING or UNPAID, or any deposit of a batch, NUT-29; a payment PAID or
   PENDING). Nothing found:
   authMasked, so the usual catch-up scan may run once ("outputs already signed", 11003, the one reason left unseen). */
async function auTruth(addr, o, e) {
  const say = (code, detail) => { e.code = code; e.message = detail; e.detail = detail; delete e.authMasked; };
  e.authMasked = true;
  let path; try { path = new URL(o.endpoint).pathname; } catch (x) { return; }
  // (cashu-ts 5 hands the request body over as the very text sent, NUT-22 signs those bytes; an object before)
  let body = {}; try { body = typeof o.requestBody === 'string' ? JSON.parse(o.requestBody) : o.requestBody && typeof o.requestBody === 'object' ? o.requestBody : {}; } catch (x) { body = {}; }
  if (!body || typeof body !== 'object') body = {};
  const acct = (S.mints.find(m => acctUrl(m.url) === addr) || {}).url; if (!acct) return;
  const w = await getWallet(acct);
  const ins = Array.isArray(body.inputs) ? body.inputs.filter(p => p && typeof p.secret === 'string') : [];
  if (ins.length) {
    const st = await inTime(w.checkProofsStates(ins.map(p => ({ secret: p.secret, id: String(p.id || w.keysetId) }))), 20000);
    if (st.some(x => x && x.state === 'SPENT')) return say(11001, 'proofs already spent');
    if (st.some(x => x && x.state === 'PENDING')) return say(11002, 'proofs are pending');
  }
  const q = typeof body.quote === 'string' ? body.quote : '';
  if (q && path === '/v1/mint/bolt11') {
    const r = await inTime(w.checkMintQuoteBolt11(q), 20000), st = r && r.state;
    if (st === 'ISSUED') say(20002, 'quote already issued'); else if (st === 'PENDING') say(20005, 'quote is pending'); else if (st === 'UNPAID') say(20001, 'quote not paid');
  } else if (path === '/v1/mint/bolt11/batch' && Array.isArray(body.quotes) && body.quotes.length && body.quotes.length <= 100) {   // (a batch, NUT-29: each of its deposits)
    const sts = await Promise.all(body.quotes.map(x => typeof x === 'string' ? inTime(w.checkMintQuoteBolt11(x), 20000).then(r => r && r.state, () => null) : null));
    if (sts.includes('ISSUED')) say(20002, 'quote already issued'); else if (sts.includes('PENDING')) say(20005, 'quote is pending'); else if (sts.includes('UNPAID')) say(20001, 'quote not paid');
  } else if (q && path === '/v1/melt/bolt11') {
    const r = await inTime(w.checkMeltQuoteBolt11(q), 20000), st = r && r.state;
    if (st === 'PAID') say(20006, 'invoice already paid'); else if (st === 'PENDING') say(20005, 'quote is pending');
  }
}
/* The few requests cashu-ts sends without its auth step (NUT-09 restore): the headers the mint's info asks for are added
   here, the same way (one BAT; the CAT only where NUT-21 lists the endpoint). */
async function auFill(addr, o) {
  const mi = au.info.get(addr); if (!mi || !o || !o.endpoint) return o;
  const h = o.headers || {}; if (Object.keys(h).some(x => /^(blind|clear)-auth$/i.test(x))) return o;
  let path, method = String(o.method || 'GET').toUpperCase(); try { path = new URL(o.endpoint).pathname; } catch (e) { return o; }
  if (/^\/v1\/(info|keys|keysets|auth\/)/.test(path)) return o;
  let hb = false, hc = false; try { hb = mi.requiresBlindAuthToken(method, path); hc = mi.requiresClearAuthToken(method, path); } catch (e) {}
  if (!hb && !hc) return o;
  const add = {}; if (hc) add['Clear-auth'] = await authCAT(addr); if (hb) add['Blind-auth'] = await auTake(addr);
  return Object.assign({}, o, { headers: Object.assign({}, h, add), redirect: 'error' });
}
const authProvider = addr => ({ getBlindAuthToken: () => auTake(addr), getCAT: () => (S.auth[addr] || {}).at, ensureCAT: () => authCAT(addr) });
// a mint built with its login (any mint: one that asks for none never calls the provider)
// a wallet loaded with the mint's info as the mint gives it now: cashu-ts 5's loadMint reuses the info its Mint holds (here
// the last one seen, for the login), where 4.x fetched /v1/info for every new wallet; so it is fetched first, once, as before
async function loadFresh(w) {
  try { if (w.mint && typeof w.mint.fetchMintInfo === 'function') await w.mint.fetchMintInfo({ forceRefresh: true }); } catch (e) { throw e; }
  await w.loadMint();
}
function authMint(addr) {
  if (!auBase) return addr;
  const m = new L.Mint(addr, { authProvider: authProvider(addr), customRequest: auReq(addr) });
  try { const mi = au.info.get(addr); if (mi) m.setMintInfo(mi); } catch (e) {}   // (the mint's info as last loaded: no second /v1/info for a wallet built here)
  return m;
}
/* Before a step is written down (journaled, a payment): at a mint with a login, a BAT (or n, up to its stock) in hand,
   or the login error now, with nothing recorded. With BATs left but no login, the step goes ahead on those. */
async function authGate(url, n = 1) {
  const addr = acctUrl(url), e = S.auth[addr]; if (!e || !e.need) return;
  if (e.clear) await authCAT(addr);
  if (!e.blind) return;
  await auLock(addr, async () => {
    const m = auMgr(addr); m.importPool(e.bats || [], 'replace');
    if (m.poolSize >= Math.min(n, auCap(e))) return;
    try { await auTopUp(addr, e, m); } catch (x) { if (!m.poolSize) throw x; } finally { e.bats = m.exportPool(); saveAuth(); }
  });
}
/* ---------- logging in ---------- */
// after a login: the mint's waiting steps, deposits and payments are settled now, and auto-move runs again
function authAfter(addr) {
  render();
  setTimeout(async () => {
    for (const m of S.mints.filter(x => acctUrl(x.url) === addr)) await mintTick(m.url, true).catch(() => {});
    try { if (amOn()) amRun('login').catch(() => {}); } catch (e) {}
    authRedraw();
  }, 0);
}
async function authLogin(addr, ui) {
  const e = S.auth[addr]; if (!e || !e.need) throw new Error("This mint doesn't ask for a login.");
  if (e.bad || !auSafe(e.disc, addr)) throw authErr(addr, 'bad');
  au.oidc.delete(e.disc + '\n' + e.cid);   // (a login reads the login server's discovery document afresh)
  const gen = e.gen, o = auOidc(e), cfg = await auCfg(addr, e);
  const tep = auSafe(cfg.token_endpoint, addr); if (!tep) throw authErr(addr, 'bad');
  const live = au.live = { addr, stop: false, cancel: () => { live.stop = true; } };
  const oerr = x => x && x.login ? x : /cancel/i.test(String(x && x.message)) ? Object.assign(new Error('cancelled'), { cancelled: true })
    : /expired_token/i.test(String(x && x.message)) ? authErr(addr, 'expired') : /access_denied|invalid_client|unauthorized_client|invalid_request|invalid_grant|HTTP 4/i.test(String(x && x.message)) ? authErr(addr, 'refused') : authErr(addr, 'down');
  let t;
  try {
    if (cfg.device_authorization_endpoint) {
      if (!auSafe(cfg.device_authorization_endpoint, addr)) throw authErr(addr, 'bad');
      let d; try { d = await inTime(o.startDeviceAuth(3), AUTH_MS); } catch (x) { throw oerr(x); }
      const link = auSafe(d.verification_uri_complete, addr) || auSafe(d.verification_uri, addr), code = clipText(String(d.user_code || ''), 40);
      if (!link || !code) { d.cancel(); throw authErr(addr, 'bad'); }
      live.cancel = () => { live.stop = true; d.cancel(); };
      if (live.stop) { d.cancel(); throw Object.assign(new Error('cancelled'), { cancelled: true }); }
      ui.code({ code, link, host: host(link) });
      const life = Math.min(Math.max(num(d.expires_in) || 600, 60), 1800) * 1000;
      let tm; const late = new Promise((_, no) => { tm = setTimeout(() => { d.cancel(); no(authErr(addr, 'expired')); }, life); });
      try { t = await Promise.race([d.poll(), late]); } catch (x) { throw oerr(x); } finally { clearTimeout(tm); }
    } else if (cfg.authorization_endpoint) {
      if (!auSafe(cfg.authorization_endpoint, addr)) throw authErr(addr, 'bad');
      const { verifier, challenge } = o.generatePKCE(), state = hex(rnd(16)), redirectUri = location.origin + location.pathname;
      const url = auSafe(await o.buildAuthCodeUrl({ redirectUri, codeChallenge: challenge, state }), addr); if (!url) throw authErr(addr, 'bad');
      raw.set('authwait', { state, at: Date.now() }); lsDel('authcode');
      ui.popup({ host: host(url) });
      window.open(url, 'nutcade-login', 'popup=yes,width=520,height=720,noopener,noreferrer');
      const t0 = Date.now(); let got = null;
      while (!got) {
        if (live.stop) throw Object.assign(new Error('cancelled'), { cancelled: true });
        if (Date.now() - t0 > 10 * 60e3) throw authErr(addr, 'expired');
        const c = raw.get('authcode', null); if (c && c.state === state) got = c; else await sleep(400);
      }
      lsDel('authcode'); lsDel('authwait');
      if (got.error || !got.code) throw authErr(addr, 'refused');
      try { t = await inTime(o.exchangeAuthCode({ code: String(got.code), codeVerifier: verifier, redirectUri }), AUTH_MS); } catch (x) { throw oerr(x); }
    } else throw authErr(addr, 'bad');
  } finally { if (au.live === live) au.live = null; }
  if (live.stop || S.auth[addr] !== e || e.gen !== gen) throw Object.assign(new Error('cancelled'), { cancelled: true });
  auDrop(e); e.tep = tep;
  try { authKeep(e, t); } catch (x) { auDrop(e); saveAuth(); throw authErr(addr, 'refused'); }
  e.since = Date.now(); au.cool.delete(addr); saveAuth(); au.mgr.delete(addr);
  authAfter(addr);
}
// a login window from an earlier visit (the page was reloaded meanwhile) has nothing to finish: its leftovers go
{ const w = raw.get('authwait', null); if (!w || !(Date.now() - num(w.at) < 15 * 60e3)) { lsDel('authwait'); lsDel('authcode'); } else lsDel('authcode'); }
function authLine(m) {
  const addr = acctUrl(m.url), st = authState(addr); if (!st.need) return '';
  const a = esc(addr);
  const s = st.bad ? `<span style="color:var(--gold)">${AUTH_TXT.bad}</span>`
    : st.inn ? `<span style="color:var(--lime)">Logged in</span>${st.who ? ` <span class="uname" data-noi18n style="overflow-wrap:anywhere">${esc(st.who)}</span>` : ''}`
    : st.again ? '<span style="color:var(--gold)">Your login ended. Log in again.</span>' : '<span>Not logged in</span>';
  const btn = st.bad ? '' : st.inn ? `<button class="btn sm" data-act="authLogout" data-url="${a}">Log out</button>` : `<button class="btn sm gold" data-act="authLogin" data-url="${a}">Log in</button>`;
  return `<div class="authline" data-auth="${a}"><div class="tiny" style="min-width:0;overflow-wrap:anywhere"><b>This mint needs a login</b><br>${s}</div>${btn}</div>`;
}
function openAuth(addr) {
  addr = acctUrl(addr);
  const m = S.mints.find(x => acctUrl(x.url) === addr) || { name: host(addr) };
  if (au.live) au.live.cancel();
  openSheet('Log in', `<div class="h2 uname" data-noi18n style="overflow-wrap:anywhere">${esc(m.name)}</div>
    <p style="margin:0">This mint needs a login before it mints, pays out or swaps your ecash. The login stays on this device: it is not in your backups.</p>
    <div id="authBody">${busyHTML('ASKING THE LOGIN SERVER')}</div><div id="sheetErr"></div>`, body => {
    let alive = true; const put = h => { const b = $('#authBody'); if (alive && b) b.innerHTML = h; };
    const where = h => `<div class="tiny muted">Login server</div><div class="tiny" data-noi18n style="overflow-wrap:anywhere">${esc(h)}</div>`;
    authLogin(addr, {
      code: d => put(`<p style="margin:0">Open the login page and log in. If it asks for a code, enter this one:</p>
        <div id="authCode" class="authcode" data-noi18n>${esc(d.code)}</div>
        <a id="authLink" class="btn solid gold block" href="${esc(d.link)}" target="_blank" rel="noopener noreferrer">Open the login page</a>
        <button class="btn block" data-act="copy" data-text="${esc(d.code)}">Copy code</button>${where(d.host)}
        <div class="row" style="justify-content:center"><span class="spinner">WAITING FOR YOUR LOGIN</span></div>`),
      popup: d => put(`<p style="margin:0">A login window opened. Log in there; this screen updates by itself.</p>${where(d.host)}
        <div class="row" style="justify-content:center"><span class="spinner">WAITING FOR YOUR LOGIN</span></div>
        <div class="tiny muted">${AUTH_TXT.popup}</div>`)
    }).then(() => { if (!alive) return; closeSheet(); toast('Logged in to this mint', 'lime'); sfx('coin'); },
      e => { if (!alive || (e && e.cancelled)) return; put(''); showErr(e); });
    return () => { alive = false; if (au.live && au.live.addr === addr) au.live.cancel(); };
  });
}
// a failure at a mint that needs a login this device doesn't have (the error itself may come wrapped by the library)
const authWant = (e, url) => !!(e && e.login) || (() => { const st = authState(url); return st.need && !st.inn && !st.bats; })();
// a deposit or payment screen waiting on a login: says so (polled again; it goes on once logged in)
const authHint = e => { if (e && (e.login === 'login' || e.login === 'again')) { const s = $('#payState'); if (s) s.textContent = 'PAID: LOG IN TO COLLECT'; } };
const authHooks = {   // (tests and the language check: Nutcade.auth)
  state: a => authState(a), cool: a => au.cool.delete(acctUrl(a)),
  texts: () => Object.values(AUTH_TXT).concat(['This mint needs a login', 'Logged in', 'Not logged in', 'Your login ended. Log in again.', 'Log in', 'Log out', 'Logged in to this mint', 'Logged out. This mint\'s login is deleted from this device.',
    'This mint needs a login before it mints, pays out or swaps your ecash. The login stays on this device: it is not in your backups.', 'Open the login page and log in. If it asks for a code, enter this one:', 'Open the login page', 'Copy code', 'Login server',
    'A login window opened. Log in there; this screen updates by itself.', 'ASKING THE LOGIN SERVER', 'WAITING FOR YOUR LOGIN', 'PAID: LOG IN TO COLLECT', 'Logged in. You can close this window.', "This mint doesn't ask for a login.",
    'Log in to these mints on the Mints tab, then scan them with Find lost ecash:', 'Some mints need a login first: log in on the Mints tab, then scan again.', 'Mint logins on this device are deleted too.'])
};
