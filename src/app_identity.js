/* ===================== Your own Nostr identity (1.37: NIP-07, NIP-46) ===================== */
/* Settings → Nostr identity: "Use my own Nostr identity", optional, off by default. Not signed in, everything is exactly
   as before 1.37: every Nostr event is signed with nostrKey() (the first 32 bytes of the 12 words' seed).
   Signed in, these PUBLIC actions use your identity, and nothing else:
     - mint reviews (kind 38000) and their deletion (kind 5; app_review.js), and which reviews the report card calls yours
     - the daily score note (kind 1; app_daily.js)
     - zap requests (kind 9734, not the anonymous ones; app_r7.js)
   Nutzaps stay on the 12-word key exactly as before 1.37 (app_nutzap.js does not use this layer): your nutzap info (kind
   10019), its withdrawal and the nutzaps you are listened for ('#p') are signed and read with nostrKey() whether you are
   signed in or not, so signing in or out publishes, withdraws and asks the signer nothing about them.
   Money never depends on the signer: P2PK locks (gifts' refund key, Extra Life), ecash sent to your ecash address (gift
   wraps), the ecash address itself, npub.cash, Extra Life's and bounties' messages, the nutzaps you send (kind 9321: it
   carries the locked coins), wallet sync and the mint-list backup all stay on the 12 words (each one's reason is in
   .claude notes and the README). Restoring the 12 words brings every coin back whatever identity you used.
   Two ways in:
     - NIP-07: a browser extension (window.nostr: getPublicKey, signEvent). Offered only when window.nostr exists.
     - NIP-46: a remote signer, from a bunker://<remote-signer-pubkey>?relay=wss://…&secret=… link (pasted or scanned),
       read strictly by idParse. NUTCADE makes its own client key (random), sends kind 24133 events whose content is NIP-44
       v2 encrypted JSON-RPC ({id, method, params}), tagged ["p", <remote-signer-pubkey>], and reads only replies from that
       key to its client key ('#p'), signed, decrypting to the same id: connect (with the secret: "ack"), get_public_key
       (the user's key, which may differ from the signer's own), sign_event. An auth_url reply is shown as a link the user
       opens (https only, never opened by the app) and the request keeps waiting for its answer.
   Every signature that comes back is checked: a valid signature (verifyEvent), the signed-in pubkey, and exactly the
   kind, created_at, tags and content that were asked; so a signer can't swap the event. The signer refusing, not
   answering (ID_MS), or gone (an extension missing after a reload) is said plainly and NOTHING is signed: there is never
   a fallback to the 12-word key. Signing needs a connection (offline: said, nothing queued); a locked wallet, a tab
   another tab took over, and the duress PIN's wallet sign nothing with it. Signing out (or a switch) while a signature
   is on its way: the answer is dropped. One request to the signer at a time.
   The connection is a secret (S.nid, store 'nid', one of VAULT_KEYS: inside the PIN vault with a PIN, like Wallet Connect's
   keys): {type, pub} for an extension, plus the signer's key, relays and the app's client key for a remote signer (the
   link's secret is used once by connect and never kept). Never in the backup file, NIP-60 sync or the mint-list backup.
   Sign out, Reset and other 12 words delete it. Former identities' public keys are kept (S.prefs.idOld, at most
   ID_OLD_MAX) so your reviews under them stay yours.
   The duress PIN's wallet has no identity: nothing shown or used, and signing in there answers like a signer that doesn't
   answer, keeps nothing and asks no signer. */
const ID_MS = 45000, ID_AUTH_MS = 180000, ID_AUTH_MAX = 3, ID_REPLY_MAX = 100000, ID_OLD_MAX = 3, ID_LINK_MAX = 1000;
const ID_PERMS = 'sign_event:1,sign_event:5,sign_event:9734,sign_event:27235,sign_event:38000';   // (every kind idSign / idProve asks for: the daily note, review deletions, zap requests, the sign-in check, reviews; never 10019: nutzaps stay on the 12-word key)
const idMs = () => { const t = window.__nutcadeTest; return t && Number(t.idMs) > 0 ? Number(t.idMs) : ID_MS; };
const idAuthMs = () => { const t = window.__nutcadeTest; return t && Number(t.idMs) > 0 ? 2 * Number(t.idMs) : ID_AUTH_MS; };   // (also the most one request may take in all, from when it was first sent)
const idHex = v => typeof v === 'string' && /^[0-9a-f]{64}$/.test(v);
const idDecoy = () => !!(vault.on && vault.decoy);
S.nid = store.get('nid', null);
let idGen = 0, idSeedC = null, idChain = Promise.resolve();
// every request to a signer that is still waiting: ended at once (with the .gone error) by a sign-out or a switch
const idAborts = new Set();
function idNext() { idGen++; const a = [...idAborts]; idAborts.clear(); for (const f of a) { try { f(); } catch (e) {} } }
// the 12-word key's public key (cached per seed)
function seedPub() { const s = seedFor(); if (!idSeedC || idSeedC.s !== s) idSeedC = { s, pk: L.nostrPub(s.slice(0, 32)) }; return idSeedC.pk; }
// THE check for a signer's relay: wss:// only, a host, no user name or password, no fragment, nothing odd, at most 200 characters
function idRelay(u) {
  if (typeof u !== 'string' || u.length > 200 || /[\s\x00-\x1f\x7f<>"'`\\]/.test(u) || !/^wss:\/\//i.test(u)) return null;
  let x; try { x = new URL(u); } catch (e) { return null; }
  if (x.protocol !== 'wss:' || !x.hostname || x.username || x.password || x.hash) return null;
  const out = ('wss://' + x.host + x.pathname + x.search).replace(/\/+$/, '');
  return out.length <= 200 ? out : null;
}
// the connection in use, or null (not signed in, locked, or the duress PIN's wallet)
function idConn() {
  if (idDecoy() || (vault.on && !vault.open) || !S.seed) return null;
  const c = S.nid;
  if (!c || typeof c !== 'object' || !idHex(c.pub)) return null;
  if (c.type === 'nip07') return { type: 'nip07', pub: c.pub };
  if (c.type === 'nip46' && idHex(c.remote) && idHex(c.csk) && Array.isArray(c.relays) && c.relays.length && c.relays.length <= 3 && c.relays.every(r => idRelay(r) === r)) return { type: 'nip46', pub: c.pub, remote: c.remote, relays: c.relays.slice(), csk: c.csk };
  return null;
}
const idActive = () => !!idConn();
const idPub = () => { const c = idConn(); return c ? c.pub : seedPub(); };
const idOld = () => idDecoy() ? [] : (Array.isArray(S.prefs.idOld) ? S.prefs.idOld : []).filter(idHex).slice(0, ID_OLD_MAX);
// every key of yours: the 12-word key, the identity you are signed in with, and your former identities
function idKeys() {
  const out = []; try { if (S.seed) out.push(seedPub()); } catch (e) {}
  const c = idConn(); if (c) out.push(c.pub);
  for (const k of idOld()) out.push(k);
  return [...new Set(out)];
}

/* ---------- errors (each a sentence in your language; what the signer itself said is shown small, as text) ---------- */
const idText = v => clipText(String(v == null ? '' : v), 200).trim();
const idLate = () => Object.assign(keepErr(new Error("Your signer didn't answer in time. Nothing was sent. Check it and try again.")), { idLate: true });
const idSaidNo = why => Object.assign(serviceErr('Your signer said no. Nothing was sent.', idText(why && typeof why === 'object' ? why.message : why) || null), { said: true });
const idSwap = () => keepErr(new Error('Your signer returned a different event from the one NUTCADE asked it to sign, so it was not used. Nothing was sent.'));
const idBadReply = () => keepErr(new Error("Your signer's answer can't be read. Nothing was sent."));
const idNoRelay = () => keepErr(new Error("Couldn't reach your signer's relays. Nothing was sent. Check your connection and try again."));
const idOffline = () => Object.assign(keepErr(new Error("You're offline. Your Nostr identity needs a connection. Nothing was sent.")), { offline: true });
const idNoExt = () => keepErr(new Error("Your browser extension isn't available here, so nothing can be signed with your Nostr identity. Nothing was sent. Open NUTCADE where the extension is installed, or sign out in Settings."));
const idGone = () => Object.assign(keepErr(new Error('Your Nostr identity changed while it was being signed. Nothing was sent.')), { gone: true });
const idTwice = () => keepErr(new Error("You're already signed in with a Nostr identity. Sign out first, then connect another one."));
const idLocked = () => keepErr(new Error('Unlock NUTCADE first.'));
function idGate() {
  if (vault.on && !vault.open) throw idLocked();
  if (writeGuard.paused || tabLocked) throw pausedErr();
  if (isOffline()) throw idOffline();
}
function idTimed(p, ms) {
  return new Promise((res, rej) => { const t = setTimeout(() => rej(idLate()), ms); Promise.resolve(p).then(v => { clearTimeout(t); res(v); }, e => { clearTimeout(t); rej(e); }); });
}
// one request to the signer at a time
function idQueue(fn) { const r = idChain.catch(() => {}).then(fn); idChain = r.catch(() => {}); return r; }

/* ---------- signing ---------- */
// the event as asked, checked against what came back: a valid signature by the signed-in key, nothing else changed
function idCheck(ev, t, pub) {
  if (!ev || typeof ev !== 'object' || Array.isArray(ev)) throw idSwap();
  let out; try { out = JSON.parse(JSON.stringify({ id: ev.id, pubkey: ev.pubkey, created_at: ev.created_at, kind: ev.kind, tags: ev.tags, content: ev.content, sig: ev.sig })); } catch (e) { throw idSwap(); }   // (our own copy: the signer's object can change later, ours can't)
  if (out.pubkey !== pub || out.kind !== t.kind || out.created_at !== t.created_at || out.content !== t.content || !Array.isArray(out.tags) || JSON.stringify(out.tags) !== JSON.stringify(t.tags)) throw idSwap();
  let ok = false; try { ok = L.verifyEvent(out); } catch (e) {}
  if (!ok) throw idSwap();
  return out;
}
// THE signing of the public actions: the identity when signed in (never the 12-word key then), else the 12-word key as before
// (gen: idGen when the step began, from idNow(): a switch or sign-out since then and nothing is signed, by any key)
const idNow = () => idGen;
async function idSign(tpl, gen0) {
  if (gen0 !== undefined && gen0 !== idGen) throw idGone();
  const t = { kind: tpl.kind, created_at: tpl.created_at, tags: JSON.parse(JSON.stringify(tpl.tags || [])), content: String(tpl.content == null ? '' : tpl.content) };
  const c = idConn();
  if (vault.on && !vault.open) throw idLocked();
  if (!c) return L.finalizeEvent(t, nostrKey());   // (not signed in, or the duress PIN's wallet: its own 12-word key, as before 1.37)
  idGate();
  const gen = idGen;
  const ev = await idQueue(async () => {
    if (gen !== idGen) throw idGone();
    idGate();
    return c.type === 'nip07' ? id07Sign(t) : id46Sign(c, t);
  });
  if (vault.on && !vault.open) throw idLocked();   // (locked meanwhile: said as such, before anything else)
  if (writeGuard.paused || tabLocked) throw pausedErr();
  const now = idConn();
  if (gen !== idGen || !now || now.pub !== c.pub) throw idGone();   // (signed out or switched while it was being signed: dropped)
  return idCheck(ev, t, c.pub);
}
// a key of yours by its pubkey, for an event that key published before (a review's deletion): the 12-word key, or the identity
// you are signed in with; another key can't be used
async function idSignAs(pk, t) {
  if (pk === seedPub()) return L.finalizeEvent(t, nostrKey());
  const c = idConn(); if (c && c.pub === pk) return idSign(t);
  throw keepErr(new Error("That was published under a Nostr identity you're not signed in with, so NUTCADE can't sign for it."));
}

/* ---------- NIP-07: a browser extension ---------- */
const id07 = () => { const n = window.nostr; return n && typeof n === 'object' && typeof n.signEvent === 'function' && typeof n.getPublicKey === 'function' ? n : null; };
async function id07Sign(t) {
  const n = id07(); if (!n) throw idNoExt();
  let abort; const gone = new Promise((_, rej) => { abort = () => rej(idGone()); idAborts.add(abort); });   // (a sign-out or switch ends the wait at once)
  try { return await Promise.race([idTimed(n.signEvent(JSON.parse(JSON.stringify(t))), idMs()), gone]); }
  catch (e) { if (e && (e.idLate || e.gone)) throw e; throw idSaidNo(e); }
  finally { idAborts.delete(abort); }
}
// at sign-in: one throwaway event signed by the key the signer named (never published), so a signer can't name a key it can't sign for
const idNoProof = () => keepErr(new Error("Your signer couldn't prove it holds the key it named, so NUTCADE didn't sign in."));
async function idProve(signFn, pub) {
  const t = { kind: 27235, created_at: Math.floor(Date.now() / 1000), tags: [], content: 'nutcade sign-in check ' + hex(rnd(16)) };   // (no "u" tag: useless as a NIP-98 login anywhere)
  let ev; try { ev = await signFn(t); } catch (e) { if (e && (e.idLate || e.gone || e.said || e.offline || e.paused)) throw e; throw idNoProof(); }   // (a refusal is shown as the signer's own words; a wrong key as idNoProof)
  try { idCheck(ev, t, pub); } catch (e) { throw idNoProof(); }
}

/* ---------- NIP-46: a remote signer ---------- */
const ID_E_LINK = "That isn't a bunker:// link NUTCADE can use. Copy the whole link from your signer app.";
const ID_E_RELAY = 'A bunker:// link needs one to three relays, each starting with wss://.';
const ID_E_NSEC = "That's a private key. NUTCADE never takes your private key (nsec): paste the bunker:// link from your signer app instead.";
const ID_E_NC = "NUTCADE doesn't take nostrconnect:// links yet. Look for a bunker:// link in your signer app.";
// bunker://<remote-signer-pubkey>?relay=wss://…&relay=…&secret=… read strictly: the key as 64 lowercase hex and a point on
// the curve, only relay and secret, 1 to 3 wss:// relays, the secret once (at most 128 plain characters), nothing else
function idParse(v) {
  if (typeof v !== 'string') return { error: ID_E_LINK };
  v = v.trim();
  if (/(^|[^a-z0-9])(nsec|ncryptsec)1[02-9ac-hj-np-z]{8,}/i.test(v)) return { error: ID_E_NSEC };
  if (/^nostrconnect:/i.test(v)) return { error: ID_E_NC };
  if (!v || v.length > ID_LINK_MAX || /[\s\x00-\x1f\x7f]/.test(v)) return { error: ID_E_LINK };
  const m = /^bunker:\/\/([0-9a-f]{64})\?([^#]+)$/.exec(v);
  if (!m || !DQ.point('02' + m[1])) return { error: ID_E_LINK };
  const relays = []; let secret = null, rel = 0;
  for (const part of m[2].split('&')) {
    const i = part.indexOf('='); if (i < 1) return { error: ID_E_LINK };
    const k = part.slice(0, i); let val; try { val = decodeURIComponent(part.slice(i + 1)); } catch (e) { return { error: ID_E_LINK }; }
    if (k === 'relay') { rel++; const r = idRelay(val); if (!r) return { error: ID_E_RELAY }; if (!relays.includes(r)) relays.push(r); }
    else if (k === 'secret') { if (secret !== null || !/^[A-Za-z0-9._~-]{1,128}$/.test(val)) return { error: ID_E_LINK }; secret = val; }
    else return { error: ID_E_LINK };
  }
  if (!relays.length || rel > 3) return { error: ID_E_RELAY };
  return { ok: true, remote: m[1], relays, secret };
}
// one JSON-RPC request and its answer (a string), over the signer's relays
function id46Rpc(c, method, params) {
  return new Promise((res, rej) => {
    const sk = L.hexToBytes(c.csk), me = L.nostrPub(sk), id = hex(rnd(16)), now = Math.floor(Date.now() / 1000);
    let ck, ev;
    try {
      ck = L.nip44.v2.utils.getConversationKey(sk, c.remote);
      ev = L.finalizeEvent({ kind: 24133, created_at: now, tags: [['p', c.remote]], content: L.nip44.v2.encrypt(JSON.stringify({ id, method, params }), ck) }, sk);
    } catch (e) { rej(keepErr(new Error(ID_E_LINK))); return; }
    const socks = [], shown = new Set(), until = Date.now() + idAuthMs(); let done = false, timer = 0, open = 0;   // (until: the whole request, auth_urls included)
    const end = (err, v) => { if (done) return; done = true; idAborts.delete(abort); clearTimeout(timer); socks.forEach(s => { try { s.close(); } catch (e) {} }); idAuthHide(id); if (err) rej(err); else res(v); };
    const abort = () => end(idGone()); idAborts.add(abort);   // (a sign-out or switch ends it at once)
    const arm = ms => { clearTimeout(timer); timer = setTimeout(() => end(idLate()), Math.max(0, Math.min(ms, until - Date.now()))); };
    arm(idMs());
    for (const r of c.relays) {
      let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
      socks.push(ws); open++;
      ws.onopen = () => { try { ws.send(JSON.stringify(['REQ', 'nid', { kinds: [24133], authors: [c.remote], '#p': [me], since: now - 10 }])); ws.send(JSON.stringify(['EVENT', ev])); } catch (e) {} };
      ws.onmessage = m => {
        if (done || typeof m.data !== 'string' || m.data.length > ID_REPLY_MAX) return;   // (a reply bigger than any answer we wait for is never read)
        let d; try { d = JSON.parse(m.data); } catch (e) { return; }
        if (!Array.isArray(d) || d[0] !== 'EVENT' || !d[2] || typeof d[2] !== 'object') return;
        const e = d[2];
        if (e.kind !== 24133 || e.pubkey !== c.remote || typeof e.content !== 'string' || !Array.isArray(e.tags) || !e.tags.some(t => Array.isArray(t) && t[0] === 'p' && t[1] === me)) return;
        let ok = false; try { ok = L.verifyEvent(e); } catch (x) {} if (!ok) return;
        let r; try { r = JSON.parse(L.nip44.v2.decrypt(e.content, ck)); } catch (x) { return; }
        if (!r || typeof r !== 'object' || r.id !== id) return;   // (another request's answer, or someone else's)
        if (r.result === 'auth_url') {   // the signer wants you to approve in its own page: shown, never opened; the answer comes later
          const u = typeof r.error === 'string' ? r.error : '';
          if (!shown.has(u) && shown.size < ID_AUTH_MAX) { shown.add(u); idAuthShow(id, u); arm(idAuthMs()); }   // (at most ID_AUTH_MAX links, never past the total time)
          return;
        }
        if (typeof r.error === 'string' && r.error) { end(idSaidNo(r.error)); return; }
        if (typeof r.result !== 'string') { end(idBadReply()); return; }
        end(null, r.result);
      };
      ws.onerror = ws.onclose = () => { if (ws._gone) return; ws._gone = true; if (--open <= 0) end(idNoRelay()); };
    }
    if (!open) end(idNoRelay());
  });
}
async function id46Sign(c, t) {
  const out = await id46Rpc(c, 'sign_event', [JSON.stringify(t)]);
  let ev; try { ev = JSON.parse(out); } catch (e) { throw idSwap(); }
  return ev;
}
// the approval link a remote signer sent (auth_url): a bar at the top of the screen, the link opened only by you
const idAuthOk = u => { if (typeof u !== 'string' || u.length > 1000 || /[\s\x00-\x1f\x7f]/.test(u)) return null; try { const x = new URL(u); return x.protocol === 'https:' && x.hostname && !x.username && !x.password ? x.href : null; } catch (e) { return null; } };
function idAuthShow(id, u) {
  let bar = document.getElementById('idAuth');
  if (!bar) { bar = document.createElement('div'); bar.id = 'idAuth'; bar.className = 'id-auth'; bar.setAttribute('role', 'alert'); document.body.appendChild(bar); }
  bar.dataset.req = id;
  const ok = idAuthOk(u);
  bar.innerHTML = `<div>${ok ? 'Your signer asks you to approve this first. Open its page, approve, then come back here.' : 'Your signer asks you to approve this first, in its own app. NUTCADE did not open the link it sent.'}</div>`
    + (ok ? `<a class="btn sm gold" href="${esc(ok)}" target="_blank" rel="noopener noreferrer">Open the signer's page</a><div class="tiny muted" data-noi18n style="overflow-wrap:anywhere">${esc(ok)}</div>` : `<div class="tiny muted" data-noi18n style="overflow-wrap:anywhere">${esc(idText(u))}</div>`);
}
function idAuthHide(id) { const bar = document.getElementById('idAuth'); if (bar && bar.dataset.req === id) bar.remove(); }

/* ---------- signing in and out ---------- */
const idDecoyWait = async () => { await sleep(idMs()); throw idLate(); };   // (the duress PIN's wallet: as a signer that doesn't answer)
let idSigning = null;   // (a sign-in on its way)
async function idSetConn(c) {
  const prev = S.nid, old = idActive() ? idPub() : seedPub();
  S.nid = c;
  if (!store.set('nid', c)) { S.nid = prev; throw new Error("This browser won't save data. Open NUTCADE in a normal browser tab."); }
  idNext();
  idSwitched(old, c.pub);
}
async function idSignInExt() {
  if (!S.seed) throw keepErr(new Error('Set up your recovery phrase first.'));
  idGate();
  if (idDecoy()) return idDecoyWait();
  if (idActive()) throw idTwice();   // (another identity is never replaced silently: Sign out first)
  const n = id07(); if (!n) throw idNoExt();
  let pub; try { pub = await idTimed(n.getPublicKey(), idMs()); } catch (e) { if (e && e.idLate) throw e; throw idSaidNo(e); }
  if (!idHex(pub)) throw keepErr(new Error("Your browser extension gave a key NUTCADE can't read."));
  await idProve(t => id07Sign(t), pub);
  idGate();
  if (idDecoy()) throw idLate();   // (the duress PIN's wallet opened meanwhile: nothing is kept there)
  if (idActive()) throw idTwice();
  await idSetConn({ type: 'nip07', pub, at: Date.now() });
  return pub;
}
async function idSignInBunker(link) {
  if (!S.seed) throw keepErr(new Error('Set up your recovery phrase first.'));
  const p = idParse(link); if (!p.ok) throw keepErr(new Error(p.error));
  idGate();
  if (idDecoy()) return idDecoyWait();
  if (idActive()) throw idTwice();   // (another identity is never replaced silently: Sign out first)
  const tok = {}; idSigning = tok;
  const c = { type: 'nip46', remote: p.remote, relays: p.relays, csk: hex(rnd(32)) };
  const ack = await id46Rpc(c, 'connect', [p.remote, p.secret || '', ID_PERMS]);
  if (ack !== 'ack' && !(p.secret && ack === p.secret)) throw keepErr(new Error("Your signer's answer didn't match the secret in the link, so NUTCADE didn't connect. Make a new bunker:// link in your signer app and try again."));
  const pub = await id46Rpc(c, 'get_public_key', []);
  if (!idHex(pub)) throw idBadReply();
  await idProve(t => id46Sign(c, t), pub);
  if (idSigning !== tok) throw idGone();
  idGate();
  if (idDecoy()) throw idLate();   // (the duress PIN's wallet opened meanwhile: nothing is kept there)
  if (idActive()) throw idTwice();
  await idSetConn(Object.assign(c, { pub, at: Date.now() }));
  idSigning = null;
  return pub;
}
// sign out: the connection goes, every signer request still waiting ends at once (nothing about nutzaps: they never used it)
async function idSignOut() {
  if (writeGuard.paused || tabLocked) throw pausedErr();   // (a paused tab can't delete anything: said, never "Signed out")
  const c = idConn(); idSigning = null;
  if (!c) { if (S.nid) { S.nid = null; raw.del('nid'); idNext(); } return; }
  S.nid = null; raw.del('nid'); idNext();
  idSwitched(c.pub, seedPub());
}
// other 12 words (setSeed) and Reset: the connection and the former identities go
function idSeedChanged() {
  idSigning = null; idSeedC = null;
  if (S.nid) { S.nid = null; raw.del('nid'); }
  idNext();
  if (S.prefs) delete S.prefs.idOld;
}
// after a switch (on, off, or another identity): your former key is remembered and your reviews are read again
function idSwitched(oldPub, newPub) {
  if (oldPub && newPub && oldPub !== newPub) {
    let sp = null; try { sp = seedPub(); } catch (e) {}
    const keep = idOld().filter(k => k !== oldPub && k !== newPub);
    S.prefs.idOld = (oldPub !== sp ? [oldPub] : []).concat(keep).slice(0, ID_OLD_MAX);
    save();
  }
  try { rvIdChanged(); } catch (e) {}
  refresh();
}

/* ---------- Settings ---------- */
const ID_NZ = "Nutzaps stay on this wallet's own key, made from your 12 words: signing in or out never changes your nutzap info.";
const idShort = pk => { try { const n = L.npubEncode(pk); return n.slice(0, 14) + '…' + n.slice(-6); } catch (e) { return ''; } };
function idSettingsHTML() {
  const c = idConn();
  if (!c) return `<div class="panel" id="set-identity"><span class="h2">Nostr identity</span>
      <p class="th" style="margin:0">Your public Nostr posts (mint reviews, the daily share post and zap requests) are signed with a key made from your 12 words. You can use your own Nostr identity for them instead.</p>
      <div class="row wrap">${id07() ? '<button class="btn sm violet" data-act="idExt">Use my browser extension</button>' : ''}<button class="btn sm violet" data-act="idBunker">Use a remote signer</button></div>
      <p class="th" style="margin:0">NUTCADE never asks for your private key (nsec). Your ecash always stays on your 12 words.</p>
      <p class="th" style="margin:0" id="idNz">${ID_NZ}</p></div>`;
  return `<div class="panel" id="set-identity"><span class="h2">Nostr identity</span>
      <div class="row between tiny"><span>Signed in as</span><span id="idWho" data-noi18n style="color:var(--lime);overflow-wrap:anywhere">${esc(idShort(c.pub))}</span></div>
      <div class="tiny muted">${c.type === 'nip07' ? 'With your browser extension' : 'With a remote signer'}</div>
      ${c.type === 'nip07' && !id07() ? `<div class="notice red" id="idWarn">Your browser extension isn't available here, so nothing can be signed with your Nostr identity. Open NUTCADE where the extension is installed, or sign out.</div>` : ''}
      <div class="th">Used for:</div>
      <ul id="idUses" class="tiny" style="margin:0;padding-left:18px"><li>Mint reviews</li><li>The daily share post</li><li>Zap requests</li></ul>
      <p class="th" style="margin:0" id="idNz">${ID_NZ}</p>
      <p class="th" style="margin:0">Your ecash, ecash address, Lightning address, Extra Life and wallet sync stay on your 12 words, so restoring them brings everything back.</p>
      <button class="btn sm red" data-act="idOut">Sign out</button></div>`;
}
function openIdBunker(link) {
  if (needSeed()) return;
  if (idActive()) { sfx('err'); toast(idTwice().message, 'gold'); return; }
  openSheet('Remote signer', `<p style="margin:0">Paste the bunker:// link from your signer app (Amber, nsec.bunker and others), or scan its QR code.</p>
    <div class="field"><label for="idLink">Bunker link</label><input id="idLink" class="inp" placeholder="bunker://…" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="${ID_LINK_MAX}"></div>
    <div class="btngrid"><button class="btn violet" data-act="idScan">Scan QR code</button><button class="btn solid gold" data-act="idConnect">Connect</button></div>
    <div class="notice">NUTCADE makes its own key for this connection and keeps it with your other secrets (encrypted with your PIN). Never paste your private key (nsec) here.</div>
    <div id="sheetErr"></div>`);
  const i = $('#idLink'); if (i && link) i.value = String(link).slice(0, ID_LINK_MAX);
}
function openIdOut() {
  const c = idConn(); if (!c) return;
  openSheet('Sign out', `<p style="margin:0">Sign out of this Nostr identity?</p><div class="code" style="color:var(--ink)" data-noi18n>${esc(idShort(c.pub))}</div>
    <p style="margin:0">Your public Nostr posts go back to the key made from your 12 words.</p>
    <button class="btn solid red block" data-act="idOutGo">Sign out</button><button class="btn block" data-act="close">Cancel</button><div id="sheetErr"></div>`);
}
// every English text of this feature, for the translation check (tests/signin_qa.py)
const idTexts = () => ['Nostr identity', 'Your public Nostr posts (mint reviews, the daily share post and zap requests) are signed with a key made from your 12 words. You can use your own Nostr identity for them instead.', ID_NZ,
  'Use my browser extension', 'Use a remote signer', 'NUTCADE never asks for your private key (nsec). Your ecash always stays on your 12 words.', 'Signed in as', 'With your browser extension', 'With a remote signer',
  "Your browser extension isn't available here, so nothing can be signed with your Nostr identity. Open NUTCADE where the extension is installed, or sign out.", 'Used for:', 'Mint reviews', 'The daily share post', 'Zap requests',
  'Your ecash, ecash address, Lightning address, Extra Life and wallet sync stay on your 12 words, so restoring them brings everything back.', 'Sign out', 'Remote signer',
  'Paste the bunker:// link from your signer app (Amber, nsec.bunker and others), or scan its QR code.', 'Bunker link', 'Scan QR code', 'Connect',
  'NUTCADE makes its own key for this connection and keeps it with your other secrets (encrypted with your PIN). Never paste your private key (nsec) here.',
  'Sign out of this Nostr identity?', 'Your public Nostr posts go back to the key made from your 12 words.',
  "Point at your signer's bunker:// QR code.", 'Your signer asks you to approve this first. Open its page, approve, then come back here.',
  'Your signer asks you to approve this first, in its own app. NUTCADE did not open the link it sent.', "Open the signer's page", 'Signed in', 'Signed out', 'WAITING FOR YOUR SIGNER',
  "Your signer didn't answer in time. Nothing was sent. Check it and try again.", 'Your signer said no. Nothing was sent.', 'Your signer returned a different event from the one NUTCADE asked it to sign, so it was not used. Nothing was sent.',
  "Your signer's answer can't be read. Nothing was sent.", "Couldn't reach your signer's relays. Nothing was sent. Check your connection and try again.", "You're offline. Your Nostr identity needs a connection. Nothing was sent.",
  "Your browser extension isn't available here, so nothing can be signed with your Nostr identity. Nothing was sent. Open NUTCADE where the extension is installed, or sign out in Settings.",
  'Your Nostr identity changed while it was being signed. Nothing was sent.', "Your signer couldn't prove it holds the key it named, so NUTCADE didn't sign in.", "You're already signed in with a Nostr identity. Sign out first, then connect another one.",
  'You also have an earlier review of this mint under your other key. Delete it? Deleting reviews under both keys at about the same time can publicly link the two keys.', 'Delete the earlier review', 'Earlier review deleted',
  'This deletes your reviews of this mint under both of your keys. Deleting under both at once can publicly link the two keys.', ID_E_LINK, ID_E_RELAY, ID_E_NSEC, ID_E_NC, "Your browser extension gave a key NUTCADE can't read.",
  "Your signer's answer didn't match the secret in the link, so NUTCADE didn't connect. Make a new bunker:// link in your signer app and try again.",
  "That was published under a Nostr identity you're not signed in with, so NUTCADE can't sign for it.", 'Paste a bunker:// link first.',
  'This zap is signed with your Nostr identity, so anyone can link it to you.'];
window.NutId = {
  active: () => idActive(), pub: () => idPub(), type: () => (idConn() || {}).type || null, keys: () => idKeys(), parse: v => { const r = idParse(v); return r.ok ? { ok: true, remote: r.remote, relays: r.relays, secret: r.secret } : { ok: false, error: r.error }; },
  sign: t => idSign(t), out: () => idSignOut(), ext: () => idSignInExt(), bunker: l => idSignInBunker(l), texts: () => idTexts(), ecashAddress: () => myEcashAddress()
};
