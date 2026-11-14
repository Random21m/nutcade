/* ===================== Round 7: LNURL-withdraw vouchers, blocked mints, Nostr Wallet Connect, zaps ===================== */

const mintName = url => (S.mints.find(m => m.url === url) || {}).name || host(url || '');
// big byte arrays (a long list_transactions answer) in base64 without spreading them into one call
const b64big = u8 => { u8 = new Uint8Array(u8); let s = ''; for (let i = 0; i < u8.length; i += 8192) s += String.fromCharCode.apply(null, u8.subarray(i, i + 8192)); return btoa(s); };
// GET a JSON answer with a time limit. An LNURL service often answers {status:"ERROR"} with an HTTP error code, so that is read too.
async function getJson(url, ms = 15000) {
  const ac = new AbortController(), t = setTimeout(() => ac.abort(), ms);
  try {
    const r = await fetch(url, { signal: ac.signal });
    let j = null; try { j = await r.json(); } catch (e) {}
    if (!j || typeof j !== 'object') { const e = new Error('bad answer'); e.httpStatus = r.status; throw e; }
    return j;
  } catch (e) {
    if (e && e.name === 'AbortError') { const x = new Error('timeout'); x.timeout = true; throw x; }
    throw e;
  } finally { clearTimeout(t); }
}
const lnurlMs = () => (window.__nutcadeTest && __nutcadeTest.lnurlMs) || 20000;

/* ---------- blocked mints ----------
   A mint you block can't send you anything: tokens, ecash over Nostr, answers to your payment requests, Lightning
   deposits and LNURL vouchers into it are refused, and you're always told why, with an Unblock button. Ecash you
   already hold there stays yours and stays spendable, so you can move it out. The list is kept on this device and
   in the backup file. */
S.blocked = raw.get('blocked', []);   // [{url, name, at}]
const saveBlocked = () => raw.set('blocked', S.blocked);
const isBlocked = url => !!url && S.blocked.some(b => b.url === normUrl(url));
function blockedErr(url, what) {
  const n = (S.blocked.find(b => b.url === normUrl(url)) || {}).name || mintName(url);
  const e = new Error(what === 'add' ? `${n} is blocked. Unblock it to add it again.` : what === 'ln' ? `${n} is blocked, so NUTCADE won't receive into it. Unblock it or pick another mint.`
    : what === 'request' ? `This request only takes ecash from ${n}, which you blocked.`
    : `${n} is blocked, so NUTCADE refused this ecash.`);
  e.fix = { act: 'unblockMint', id: normUrl(url), label: 'Unblock' }; e.blocked = normUrl(url); e.keep = true;
  return e;
}
function blockMint(url) {
  url = normUrl(url);
  if (!isBlocked(url)) { S.blocked.push({ url, name: mintName(url), at: Date.now() }); saveBlocked(); }
}
function unblockMint(url) { url = normUrl(url); S.blocked = S.blocked.filter(b => b.url !== url); saveBlocked(); }
function openBlock(url) {
  const bal = balanceOf(url), n = mintName(url);
  const canMove = bal > 0 && S.mints.filter(m => m.url !== url && !isBlocked(m.url) && supports(m, 'mint', 'bolt11')).length && supports(S.mints.find(m => m.url === url), 'melt', 'bolt11');
  openSheet('Block mint', `<p style="margin:0">Block ${esc(n)}? NUTCADE will refuse ecash, payment requests and new deposits from it, and always tell you when it does. You can unblock it any time.</p>
    ${bal ? `<div class="notice">Your ${money(bal)} at ${esc(n)} stays usable: you can still send it or move it to another mint. Moving it out is a good idea.</div>` : ''}
    ${S.prefs.npc && S.prefs.npcMint === url ? `<div class="notice">Your Lightning address still sends payments to ${esc(n)}. Change its mint in Settings → Lightning address.</div>` : ''}
    <button class="btn solid gold block" data-act="blockMintGo" data-url="${esc(url)}">Block this mint</button>
    ${canMove ? `<button class="btn block" data-act="moveOpen" data-from="${esc(url)}">Move sats out first</button>` : ''}<div id="sheetErr"></div>`);
}
const blockedNotice = url => isBlocked(url) ? `<div class="notice red">${esc(mintName(url))} is blocked: its tokens, payment requests and deposits are refused.${balanceOf(url) ? ` Your ${money(balanceOf(url))} there still works, so you can move it out.` : ''}</div>` : '';

