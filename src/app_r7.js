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

/* ---------- Lightning invoices (BOLT 11), read locally ----------
   The amount comes from the invoice's prefix (lnbc2500u…), in exact integer arithmetic. Also read: the payment
   hash, the description, when it was made and when it expires. Used to check every invoice before paying it. */
function decodeBolt11(pr) {
  pr = String(pr || '').trim().toLowerCase().replace(/^lightning:/, '');
  let d; try { d = L.bech32.decode(pr, 8000); } catch (e) { throw new Error("That Lightning invoice isn't valid. Check you copied all of it."); }
  const m = /^ln(bcrt|bc|tbs|tb|sb)(\d*)([munp]?)$/.exec(d.prefix);
  if (!m || d.words.length < 7 + 104) throw new Error("That Lightning invoice isn't valid. Check you copied all of it.");
  let msat = null;
  if (m[2]) {
    const n = BigInt(m[2]);
    if (m[3] === 'p') { if (n % 10n) throw new Error("That Lightning invoice isn't valid. Check you copied all of it."); msat = n / 10n; }
    else msat = n * { '': 100000000000n, m: 100000000n, u: 100000n, n: 100n }[m[3]];
  }
  const w = d.words, int = (a, b) => { let x = 0; for (let i = a; i < b; i++) x = x * 32 + w[i]; return x; };
  const bytes = (a, b) => { const out = []; let acc = 0, bits = 0; for (let i = a; i < b; i++) { acc = (acc << 5) | w[i]; bits += 5; while (bits >= 8) { bits -= 8; out.push((acc >> bits) & 255); } acc &= (1 << bits) - 1; } return new Uint8Array(out); };
  const out = { msat, sats: msat != null && msat % 1000n === 0n && msat / 1000n <= BigInt(MAX_SAT) ? Number(msat / 1000n) : null, timestamp: int(0, 7), expiry: 3600, paymentHash: '', description: '', descriptionHash: '' };
  for (let i = 7, end = w.length - 104; i + 3 <= end;) {
    const type = w[i], len = w[i + 1] * 32 + w[i + 2], s = i + 3; i = s + len; if (i > end) break;
    if (type === 1 && len === 52) out.paymentHash = hex(bytes(s, i));
    else if (type === 13) { try { out.description = new TextDecoder().decode(bytes(s, i)); } catch (e) {} }
    else if (type === 23 && len === 52) out.descriptionHash = hex(bytes(s, i));
    else if (type === 6) out.expiry = int(s, i);
  }
  return out;
}

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
  const canMove = canMoveFrom(url);
  openSheet('Block mint', `<p style="margin:0">Block ${esc(n)}? NUTCADE will refuse ecash, payment requests and new deposits from it, and always tell you when it does. You can unblock it any time.</p>
    ${bal ? `<div class="notice">Your ${money(bal)} at ${esc(n)} stays usable: you can still send it or move it to another mint. Moving it out is a good idea.</div>` : ''}
    ${S.prefs.npc && S.prefs.npcMint === url ? `<div class="notice">Your Lightning address still sends payments to ${esc(n)}. Change its mint in Settings → Lightning address.</div>` : ''}
    <button class="btn solid gold block" data-act="blockMintGo" data-url="${esc(url)}">Block this mint</button>
    ${canMove ? `<button class="btn block" data-act="moveOpen" data-from="${esc(url)}">Move sats out first</button>` : bal ? noMoveHTML(url) : ''}<div id="sheetErr"></div>`);
}
// sats can move out of a mint over Lightning only to another mint (not blocked) that takes Lightning deposits
const canMoveFrom = url => balanceOf(url) > 0 && supports(S.mints.find(m => m.url === url), 'melt', 'bolt11') && S.mints.some(m => m.url !== url && !isBlocked(m.url) && supports(m, 'mint', 'bolt11'));
const noMoveHTML = url => `<div class="notice">There's no other mint here that takes Lightning deposits, so these sats can't be moved yet. Add a mint to move them to, or send them from ${esc(mintName(url))}.</div>
  <div class="btngrid"><button class="btn" data-act="pickMint">Add a mint</button><button class="btn" data-act="sendFrom" data-url="${esc(url)}">Send from ${esc(mintName(url))}</button></div>`;
const blockedNotice = url => isBlocked(url) ? `<div class="notice red">${esc(mintName(url))} is blocked: its tokens, payment requests and deposits are refused.${balanceOf(url) ? ` Your ${money(balanceOf(url))} there still works, so you can move it out.` : ''}</div>` : '';

/* ---------- LNURL (LUD-01, LUD-17): a scanned or pasted LNURL is read first, to see what it is ---------- */
function lnurlHttp(v) {
  v = String(v || '').trim().replace(/^lightning:/i, '');
  const m = /^lnurl[pwc]:\/\/(.+)$/i.exec(v);   // LUD-17: lnurlw://host/path is https (http for .onion)
  if (m) return (/^[^/]+\.onion(\/|$)/i.test(m[1]) ? 'http://' : 'https://') + m[1];
  if (/^https?:\/\//i.test(v)) { try { const p = new URL(v).searchParams.get('lightning'); if (p && /^lnurl1/i.test(p)) return lnurlToUrl(p.toLowerCase()); } catch (e) {} return v; }
  return lnurlToUrl(v.toLowerCase());
}
const lnurlEncode = url => L.bech32.encode('lnurl', L.bech32.toWords(new TextEncoder().encode(url)), 2000);
// a service's own words ("Withdraw link already used") are shown small under a sentence in your language
const keepErr = e => { e.keep = true; return e; };   // a sentence that may start with a lowercase name: shown as it is
function serviceErr(say, reason, also) { const e = new Error(say); if (reason) e.raw = String(reason).slice(0, 200); if (also) e.also = also; e.keep = true; return e; }
async function openLnurl(value) {
  let url; try { url = lnurlHttp(value); new URL(url); } catch (e) { closeSheet(); sfx('err'); toast("That LNURL can't be read.", 'red'); return; }
  openSheet('Lightning', busyHTML('READING THE LINK') + '<div id="sheetErr"></div>');
  let j;
  try { j = await getJson(url, lnurlMs()); }
  catch (e) { if (!$('#layer .sheet')) return; setBody(errHTML(e.timeout ? serviceErr(`${host(url)} didn't answer in time. Try again in a moment.`) : serviceErr(`Couldn't reach ${host(url)}. Check your connection and try again.`)) + '<button class="btn block" data-act="close">Close</button>'); return; }
  if (!$('#layer .sheet')) return;
  if (j.status === 'ERROR') { setBody(errHTML(serviceErr('The service turned this link down.', j.reason)) + '<button class="btn block" data-act="close">Close</button>'); return; }
  if (j.tag === 'withdrawRequest') return showWithdraw(j, url);
  if (j.tag === 'payRequest') return openPayLnurl(value);
  setBody(errHTML(serviceErr("NUTCADE can't use this kind of LNURL. It reads vouchers (LNURL-withdraw) and payment links (LNURL-pay)."))
    + '<button class="btn block" data-act="close">Close</button>');
}

/* ---------- LNURL-withdraw (LUD-03): load a voucher's sats into one of your mints ----------
   The amount is checked against the voucher's limits, the mint makes an invoice for exactly that amount, the
   service is asked to pay it (k1 + pr), and NUTCADE mints once the mint says it's paid: never more than the
   invoice. If the service doesn't answer in time, the invoice stays watched until it expires, so a late payment
   still arrives. If it says no, the invoice is dropped and nothing was spent. */
let curWd = null;
const wdUsed = new Set(raw.get('lnurlwUsed', []));
const wdBusy = new Set();
function showWithdraw(j, url) {
  const min = Math.max(1, Math.ceil(num(j.minWithdrawable) / 1000)), max = Math.floor(num(j.maxWithdrawable) / 1000);
  const desc = String(j.defaultDescription || '').slice(0, 200);
  const head = $('#layer .sheet-head h3'); if (head) { head.textContent = tr('Withdraw voucher'); head.closest('.sheet').setAttribute('aria-label', tr('Withdraw voucher')); }
  if (!j.callback || !j.k1 || !/^https?:\/\//i.test(String(j.callback))) { setBody(errHTML(serviceErr("This voucher can't be read: it's missing its payment details.")) + '<button class="btn block" data-act="close">Close</button>'); return; }
  if (wdUsed.has(String(j.k1))) { setBody(errHTML(serviceErr('This voucher was already used in this wallet.', '', 'Nothing was received and nothing was spent.')) + '<button class="btn block" data-act="close">Close</button>'); return; }
  if (!(max >= 1) || max < min) { setBody(errHTML(serviceErr('This voucher has nothing left to withdraw. It may have been used already.', '', 'Nothing was received and nothing was spent.')) + '<button class="btn block" data-act="close">Close</button>'); return; }
  const mints = S.mints.filter(m => supports(m, 'mint', 'bolt11'));
  const ok = mints.filter(m => !isBlocked(m.url));
  curWd = { k1: String(j.k1), callback: String(j.callback), min, max, desc, host: host(url) };
  const pick = ok.find(m => m.url === S.active) || ok[0];
  setBody(`<div class="label">Voucher</div>
    <div class="code" style="color:var(--ink)" data-noi18n>${esc(desc || host(url))}</div>
    <dl class="kv"><dt>From</dt><dd data-noi18n>${esc(host(url))}</dd><dt>Limits</dt><dd>${min === max ? money(max) : `${money(min)} to ${money(max)}`}</dd></dl>
    ${!ok.length ? `<div class="notice red">${mints.length ? 'Every mint you have that takes Lightning deposits is blocked.' : 'None of your mints takes Lightning deposits.'} Add or unblock a mint to load this voucher.</div><button class="btn block gold" data-act="pickMint">Open mint picker</button>`
    : `<div class="field"><label for="wdMint">Into</label><select id="wdMint" class="inp">${ok.map(m => `<option value="${esc(m.url)}" ${m === pick ? 'selected' : ''} data-noi18n>${esc(m.name)} · ${fmt(balanceOf(m.url))}</option>`).join('')}</select></div>
    <div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" value="${max}" autocomplete="off"></div>
    <div class="tiny muted">${min === max ? `This voucher gives exactly ${money(max)}.` : `Any amount from ${money(min)} to ${money(max)}.`}</div>
    <button class="btn solid gold block" data-act="lnurlwGo">Withdraw</button>`}<div id="sheetErr"></div>`);
}
async function withdrawVoucher(v, sats, url) {
  if (wdBusy.has(v.k1)) throw serviceErr('This voucher is already being withdrawn. Wait for it to finish.');
  if (wdUsed.has(v.k1)) throw serviceErr('This voucher was already used in this wallet.', '', 'Nothing was received and nothing was spent.');
  if (sats < v.min || sats > v.max) throw amtErr(v.min === v.max ? `This voucher gives exactly ${money(v.max)}. Type that amount.` : `This voucher gives ${money(v.min)} to ${money(v.max)}. Type an amount in that range.`, 'range');
  const m = S.mints.find(x => x.url === url); if (!m) throw new Error('Pick a mint to load the voucher into.');
  if (isBlocked(url)) throw blockedErr(url, 'ln');
  const mi = methodInfo(m, 'mint', 'bolt11');
  if (mi && mi.min && sats < mi.min) throw keepErr(amtErr(`${m.name} takes Lightning deposits of at least ${money(mi.min)}.`, 'range'));
  if (mi && mi.max && sats > mi.max) throw keepErr(amtErr(`${m.name} takes Lightning deposits of at most ${money(mi.max)}.`, 'range'));
  wdBusy.add(v.k1);
  try {
    const tx = await lnMintQuote(sats, v.desc || 'LNURL voucher', url);
    updTx(tx.id, { lnurlw: v.host });
    const q = S.quotes.find(x => x.quote === tx.quote);
    const drop = () => { if (q) dropQuote(q); updTx(tx.id, { status: 'failed' }); };
    let inv = null; try { inv = decodeBolt11(tx.request); } catch (e) {}
    if (!inv || inv.sats !== sats) { drop(); throw serviceErr(`The mint's invoice isn't for ${money(sats)}, so the voucher wasn't asked to pay it.`, '', 'Nothing was received and nothing was spent.'); }
    const cb = new URL(v.callback); cb.searchParams.set('k1', v.k1); cb.searchParams.set('pr', tx.request);
    let r;
    try { r = await getJson(cb.toString(), lnurlMs()); }
    catch (e) {
      // the service may still pay: the invoice stays watched until it expires
      return { tx, q, late: true, why: e.timeout ? `${v.host} didn't answer in time.` : `Couldn't reach ${v.host}.` };
    }
    if (r.status === 'ERROR' || (r.status && String(r.status).toUpperCase() !== 'OK')) {
      // The service says no, but only the mint knows whether the invoice gets paid: it stays watched until it expires
      // at the mint, and is minted if it is paid after all. Nothing is dropped because of what the service says.
      const used = /used|already|claimed|redeem|spent|exhaust|no (more )?(balance|funds)/i.test(r.reason || '');
      const exp = /expire/i.test(r.reason || '');
      return { tx, q, refused: used ? 'The voucher service says this voucher was already used.' : exp ? 'The voucher service says this voucher has expired.' : 'The voucher service turned this down.', reason: r.reason ? String(r.reason).slice(0, 200) : '' };
    }
    wdUsed.add(v.k1); raw.set('lnurlwUsed', [...wdUsed].slice(-200));
    return { tx, q };
  } finally { wdBusy.delete(v.k1); }
}
function showWithdrawWait(res) {
  const { tx, q } = res;
  if (res.paid) return showDone('in', tx.amount, 'Lightning');
  const until = q && q.expiry ? fmtDate(q.expiry * 1000, true) : '';
  setBody(`<div class="label" style="text-align:center">Withdrawing</div>
    <div class="credit-num" style="text-align:center;font-size:26px">${fmt(tx.amount)}<small>${unitTag()}</small></div>
    ${res.late ? `<div class="notice">${esc(res.why)} If it pays, the sats arrive here while NUTCADE is open${until ? `, until the invoice expires on ${until}` : ''}.</div>` : ''}
    ${res.refused ? `<div class="notice red">${esc(res.refused)}${res.reason ? `<div class="tiny muted raw" data-noi18n>${esc(res.reason)}</div>` : ''}</div><div class="notice">Not confirmed yet: NUTCADE keeps watching the invoice${until ? ` until it expires on ${until}` : ' until it expires'}, and the sats arrive if it is paid after all. Nothing was spent.</div>` : ''}
    <div class="row" style="justify-content:center"><span class="spinner" id="payState">${res.refused ? 'STILL WATCHING' : 'WAITING FOR THE VOUCHER TO PAY'}</span></div>
    <div class="tiny muted" style="text-align:center">You can close this. NUTCADE keeps checking while it's open.</div>`, () => {
    if (!q) return null;
    let alive = true;
    const done = () => { if (alive) { alive = false; showDone('in', tx.amount, 'Lightning'); } };
    const onPaid = e => { if (e.detail === q.quote) done(); };
    document.addEventListener('nutcade:paid', onPaid); liveSync();
    (async () => {
      while (alive) {
        try {
          const r = await checkQuote(q);
          if (r === 'paid') return done();
          if (r === 'expired' || (r === 'gone' && (txById(tx.id) || {}).status === 'expired')) {
            if (alive) { alive = false; setBody(`${errHTML(serviceErr(res.refused ? 'The voucher service never paid, and the invoice has expired.' : "The voucher didn't pay before the invoice expired.", '', 'Nothing was received and nothing was spent.'))}<button class="btn solid gold block" data-act="close">OK</button>`); refresh(); }
            return;
          }
        } catch (e) {}
        await sleep(2000);
      }
    })();
    return () => { alive = false; document.removeEventListener('nutcade:paid', onPaid); };
  });
}

/* ---------- zaps (NIP-57) ----------
   Their kind-0 profile gives a Lightning address (lud16, or an lud06 LNURL). If its LNURL-pay endpoint says
   allowsNostr and names its nostrPubkey, a kind-9734 zap request signed with this wallet's Nostr key (the same key
   cashu.me uses, from the 12 words) goes with the amount; the invoice must be for exactly that amount, and is then
   paid like any Lightning payment, with the fee shown first. Without zap support, a plain payment is offered. */
let curZap = null;
const zapByQuote = new Map();
async function nostrProfile(pubkey, extra = []) {
  const list = [...new Set((extra || []).filter(u => /^wss?:\/\//.test(u)).concat(relays()))].slice(0, 8);
  const evs = await relayQuery({ kinds: [0], authors: [pubkey], limit: 3 }, 6000, list);
  const ev = evs.filter(e => e.pubkey === pubkey && e.kind === 0 && L.verifyEvent(e)).sort((a, b) => b.created_at - a.created_at)[0];
  if (!ev) return null;
  try { const p = JSON.parse(ev.content); return p && typeof p === 'object' ? p : null; } catch (e) { return null; }
}
const shortNpub = pk => { try { const n = L.npubEncode(pk); return n.slice(0, 12) + '…' + n.slice(-4); } catch (e) { return pk.slice(0, 8) + '…'; } };
async function openZap(target) {
  if (needMint()) return;
  const pk = target.pubkey;
  curZap = null;
  openSheet('Zap', busyHTML('LOOKING UP THEIR PROFILE') + '<div id="sheetErr"></div>');
  let prof = null;
  try { prof = await nostrProfile(pk, target.relays); } catch (e) {}
  if (!$('#layer .sheet')) return;
  const name = String(target.name || (prof && (prof.display_name || prof.displayName || prof.name)) || shortNpub(pk)).trim().slice(0, 40);
  const addr = prof ? String(prof.lud16 || '').trim().toLowerCase() || String(prof.lud06 || '').trim().toLowerCase() : '';
  const fail = msg => setBody(`<div class="label">To</div><div class="code" style="color:var(--ink)" data-noi18n>${esc(name)}</div>${errHTML(serviceErr(msg))}<button class="btn block" data-act="close">Close</button>`);
  if (!prof) return fail("Couldn't find this person's Nostr profile on your relays, so there's no Lightning address to zap.");
  if (!addr || !(/^[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}$/.test(addr) || /^lnurl1[0-9a-z]+$/.test(addr))) return fail("This Nostr profile has no Lightning address, so it can't be zapped.");
  let base;
  try { base = await getJson(lnurlToUrl(addr), lnurlMs()); } catch (e) { if ($('#layer .sheet')) fail(e.timeout ? `${addr} didn't answer in time. Try again in a moment.` : `Couldn't reach ${addr}. Check your connection and try again.`); return; }
  if (!$('#layer .sheet')) return;
  if (base.status === 'ERROR') { setBody(errHTML(serviceErr(`${addr} turned this down.`, base.reason)) + '<button class="btn block" data-act="close">Close</button>'); return; }
  if (base.tag !== 'payRequest' || !base.callback) return fail(`${addr} isn't set up to receive payments.`);
  const zapOk = base.allowsNostr === true && /^[0-9a-f]{64}$/i.test(String(base.nostrPubkey || ''));
  const min = Math.max(1, Math.ceil(num(base.minSendable) / 1000)), max = Math.floor(num(base.maxSendable) / 1000);
  curZap = { pubkey: pk, name, addr, base, zapOk, min, max, url: lnurlToUrl(addr), relays: (target.relays || []).slice(0, 3) };
  const m = activeMint();
  setBody(`<div class="label">To</div><div class="code" style="color:var(--ink)"><span data-noi18n>${esc(name)}</span><br><span class="tiny muted" data-noi18n>${esc(addr)}</span></div>
    ${zapOk ? '' : `<div class="notice">${esc(addr)} doesn't support zaps. You can pay it as a plain Lightning payment instead; it won't show as a zap on Nostr.</div>`}
    <div class="tiny muted">From <b style="color:var(--ink)" data-noi18n>${esc(m.name)}</b> · ${money(balanceOf(m.url))} available</div>
    <div class="field"><label for="amtIn">Amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="21" autocomplete="off"></div>
    ${max >= min ? `<div class="tiny muted">${min === max ? `Exactly ${money(max)}.` : `Any amount from ${money(min)} to ${money(max)}.`}</div>` : ''}
    ${zapOk || num(base.commentAllowed) > 0 ? `<div class="field"><label for="zapComment">${zapOk ? 'Comment (optional, public on Nostr)' : 'Comment (optional, the receiver sees it)'}</label><input id="zapComment" class="inp" maxlength="${zapOk ? 280 : Math.min(280, num(base.commentAllowed))}" autocomplete="off"></div>` : ''}
    <button class="btn solid gold block" data-act="zapQuote">${zapOk ? 'Zap' : 'Pay as a plain Lightning payment'}</button><div id="sheetErr"></div>`);
}
async function zapInvoice(z, sats, comment) {
  if (z.max < z.min) throw keepErr(new Error(`${z.addr} isn't accepting payments right now.`));
  if (sats < z.min || sats > z.max) throw keepErr(amtErr(z.min === z.max ? `${z.addr} takes exactly ${money(z.max)}.` : `${z.addr} takes ${money(z.min)} to ${money(z.max)}.`, 'range'));
  const msat = sats * 1000;
  const cb = new URL(z.base.callback); cb.searchParams.set('amount', String(msat));
  let zapReq = null;
  if (z.zapOk) {
    const lnurl = lnurlEncode(z.url);
    const rl = [...new Set(z.relays.concat(relays()))].slice(0, 5);
    zapReq = L.finalizeEvent({ kind: 9734, created_at: Math.floor(Date.now() / 1000), content: comment || '', tags: [['relays', ...rl], ['amount', String(msat)], ['lnurl', lnurl], ['p', z.pubkey]] }, nostrKey());
    cb.searchParams.set('nostr', JSON.stringify(zapReq)); cb.searchParams.set('lnurl', lnurl);
  } else if (comment && num(z.base.commentAllowed) > 0) cb.searchParams.set('comment', comment.slice(0, num(z.base.commentAllowed)));
  let r;
  try { r = await getJson(cb.toString(), lnurlMs()); }
  catch (e) { throw serviceErr(e.timeout ? `${z.addr} didn't answer in time. Nothing was sent.` : `Couldn't reach ${z.addr}. Nothing was sent.`); }
  if (r.status === 'ERROR' || !r.pr) throw serviceErr(`${z.addr} didn't give an invoice. Nothing was sent.`, r.reason);
  let d; try { d = decodeBolt11(r.pr); } catch (e) { throw serviceErr(`${z.addr} sent an invoice that can't be read. Nothing was sent.`); }
  if (d.msat == null || d.msat !== BigInt(msat)) throw serviceErr(d.msat == null ? `${z.addr} sent an invoice with no amount. Nothing was sent.` : `The invoice asked for ${money(Math.ceil(Number(d.msat) / 1000))} instead of ${money(sats)}. Nothing was sent.`);
  return { pr: String(r.pr).toLowerCase(), zapReq };
}

/* ---------- Nostr Wallet Connect (NIP-47), the wallet-service side ----------
   Each connection has its own service key (kept with your other secrets: encrypted when a PIN is set) and knows
   only the app's public key; the app's secret is in the link shown once at setup and is never stored here.
   Requests (kind 23194) are answered (kind 23195) while NUTCADE is open and unlocked in a tab, one at a time, so
   two payments can't race past a budget. NIP-44 is used when the app asks for it, NIP-04 otherwise. A request
   older than two minutes is ignored, so nothing made while NUTCADE was closed is paid later by surprise. */
S.nwc = store.get('nwc', []);   // [{id, name, sk, pub, client, relays, created, budget:{per, sats}, enc, used}]
const saveNwc = () => store.set('nwc', S.nwc);
const NWC_METHODS = ['pay_invoice', 'get_balance', 'get_info', 'make_invoice', 'lookup_invoice', 'list_transactions'];
const NWC_NOTES = ['payment_received', 'payment_sent'];
const nwcNote = c => `Wallet Connect: ${c.name}`;
const PERIODS = [['none', 'No budget'], ['day', 'Per day'], ['week', 'Per week'], ['month', 'Per month'], ['total', 'In total']];
function periodStart(per) {
  const d = new Date(); d.setHours(0, 0, 0, 0);
  if (per === 'day') return d.getTime();
  if (per === 'week') { d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return d.getTime(); }   // weeks start on Monday
  if (per === 'month') { d.setDate(1); return d.getTime(); }
  return 0;
}
// what a connection has spent in its budget period: payments that went through or are in flight, with their fees,
// and the mint fee of a failed one
function nwcSpent(c) {
  const from = periodStart(c.budget && c.budget.per);
  let s = 0;
  for (const t of S.txs) {
    if (t.ts < from) continue;
    if (t.nwc === c.id && t.type === 'out' && t.method !== 'fee' && t.status !== 'failed' && t.status !== 'expired') s += num(t.amount) + num(t.fee);
    else if (t.method === 'fee' && t.feeFor && (txById(t.feeFor) || {}).nwc === c.id) s += num(t.fee);
  }
  return s;
}
const nwcLeft = c => (c.budget && c.budget.per && c.budget.per !== 'none') ? Math.max(0, num(c.budget.sats) - nwcSpent(c)) : null;
function nwcBudgetText(c) {
  const left = nwcLeft(c);
  if (left == null) return 'No budget: it can spend your whole balance';
  const b = num(c.budget.sats);
  return { day: `${money(left)} of ${money(b)} left today`, week: `${money(left)} of ${money(b)} left this week`, month: `${money(left)} of ${money(b)} left this month`, total: `${money(left)} of ${money(b)} left in total` }[c.budget.per];
}
function nwcUri(c, clientSk) {
  const q = c.relays.map(r => 'relay=' + encodeURIComponent(r)).join('&') + '&secret=' + clientSk + (S.prefs.npc ? '&lud16=' + encodeURIComponent(npcAddress()) : '');
  return `nostr+walletconnect://${c.pub}?${q}`;
}
function nwcCreate(name, budget, seeAll) {
  name = String(name || '').trim().slice(0, 40);
  if (!name) throw new Error('Give the connection a name, like the app it is for.');
  const sk = rnd(32), csk = rnd(32);
  const c = { id: uid(), name, sk: hex(sk), pub: L.nostrPub(sk), client: L.nostrPub(csk), relays: relays().slice(0, 3), created: Date.now(), budget, seeAll: !!seeAll, enc: null, used: 0 };
  S.nwc.push(c);
  if (!saveNwc()) { S.nwc = S.nwc.filter(x => x.id !== c.id); throw new Error("This browser won't save data."); }
  nwcListen(true); nwcInfo(c).catch(() => {});
  return { c, uri: nwcUri(c, hex(csk)) };
}
function nwcRevoke(id) { S.nwc = S.nwc.filter(c => c.id !== id); saveNwc(); nwcInfoSent.delete(id); nwcListen(true); }

// NIP-04 needs the plain ECDH x-coordinate, which the bundled library doesn't expose: a small secp256k1 point
// multiplication (Jacobian coordinates, BigInt) gives it. Only used for apps that don't speak NIP-44.
const SECP = (() => {
  const P = 2n ** 256n - 2n ** 32n - 977n, N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141n;
  const md = a => { const r = a % P; return r >= 0n ? r : r + P; };
  const pw = (b, e) => { let r = 1n; b = md(b); while (e > 0n) { if (e & 1n) r = r * b % P; b = b * b % P; e >>= 1n; } return r; };
  const dbl = ([X, Y, Z]) => {
    if (!Z || !Y) return [0n, 1n, 0n];
    const A = X * X % P, B = Y * Y % P, C = B * B % P, D = md(2n * (md((X + B) ** 2n) - A - C)), E = 3n * A % P, F = E * E % P;
    const X3 = md(F - 2n * D); return [X3, md(E * (D - X3) - 8n * C), md(2n * Y * Z)];
  };
  const add = (p, q) => {
    if (!p[2]) return q; if (!q[2]) return p;
    const [X1, Y1, Z1] = p, [X2, Y2, Z2] = q, Z1Z1 = Z1 * Z1 % P, Z2Z2 = Z2 * Z2 % P, U1 = X1 * Z2Z2 % P, U2 = X2 * Z1Z1 % P, S1 = Y1 * Z2 % P * Z2Z2 % P, S2 = Y2 * Z1 % P * Z1Z1 % P;
    if (U1 === U2) return S1 === S2 ? dbl(p) : [0n, 1n, 0n];
    const H = md(U2 - U1), I = (2n * H) ** 2n % P, J = H * I % P, r = md(2n * (S2 - S1)), V = U1 * I % P, X3 = md(r * r - J - 2n * V);
    return [X3, md(r * (V - X3) - 2n * S1 * J), md((md((Z1 + Z2) ** 2n) - Z1Z1 - Z2Z2) * H)];
  };
  return {
    sharedX(sk, pubHex) {
      const k = BigInt('0x' + hex(sk)), x = BigInt('0x' + pubHex);
      if (!(k > 0n && k < N) || x >= P) throw new Error('bad key');
      const c = md(x * x % P * x + 7n), y = pw(c, (P + 1n) / 4n); if (y * y % P !== c) throw new Error('bad key');
      let R = [0n, 1n, 0n], Q = [x, y, 1n];
      for (let e = k; e > 0n; e >>= 1n) { if (e & 1n) R = add(R, Q); Q = dbl(Q); }
      const zi = pw(R[2], P - 2n);
      return L.hexToBytes((R[0] * zi % P * zi % P).toString(16).padStart(64, '0'));
    }
  };
})();
const nwcKeys = new Map();   // connection id -> { sk, ck (NIP-44), aes (NIP-04) }
function nwcKey(c) {
  let k = nwcKeys.get(c.id);
  if (!k || k.client !== c.client) { const sk = L.hexToBytes(c.sk); k = { client: c.client, sk, ck: L.nip44.v2.utils.getConversationKey(sk, c.client), aes: null }; nwcKeys.set(c.id, k); }
  return k;
}
async function nip04Key(c) { const k = nwcKey(c); if (!k.aes) k.aes = await crypto.subtle.importKey('raw', SECP.sharedX(k.sk, c.client), 'AES-CBC', false, ['encrypt', 'decrypt']); return k.aes; }
async function nwcEncrypt(c, enc, text) {
  if (enc === 'nip44') return L.nip44.v2.encrypt(text, nwcKey(c).ck);
  const iv = rnd(16), ct = await crypto.subtle.encrypt({ name: 'AES-CBC', iv }, await nip04Key(c), new TextEncoder().encode(text));
  return b64big(ct) + '?iv=' + b64e(iv);
}
async function nwcDecrypt(c, enc, payload) {
  if (enc === 'nip44') return L.nip44.v2.decrypt(payload, nwcKey(c).ck);
  const [ct, iv] = String(payload).split('?iv=');
  const pt = await crypto.subtle.decrypt({ name: 'AES-CBC', iv: b64d(iv) }, await nip04Key(c), b64d(ct));
  return new TextDecoder().decode(pt);
}

let nwcSocks = [], nwcKeyNow = '', nwcRetry = 0, nwcChain = Promise.resolve();
let nwcSince = 0;   // when this tab started answering (opened or unlocked): anything sent before is refused, never paid
const NWC_MAX_AGE = 60;
const nwcInfoSent = new Set();
const nwcSeen = new Set(raw.get('nwcseen', []));
const nwcWanted = () => !!(S.seed && S.nwc.length && !tabLocked && !(vault.on && !vault.open));
const nwcRelays = () => [...new Set(S.nwc.flatMap(c => c.relays || []))].slice(0, 6);
const nwcLive = () => nwcSocks.some(s => s.readyState === 1);
function nwcStop() { const s = nwcSocks; nwcSocks = []; nwcKeyNow = ''; s.forEach(w => { try { w.close(); } catch (e) {} }); }
function nwcListen(force) {
  if (!nwcWanted()) { nwcStop(); return; }
  const pubs = S.nwc.map(c => c.pub), key = pubs.join(',') + '|' + nwcRelays().join(',');
  if (!force && key === nwcKeyNow && nwcSocks.some(s => s.readyState <= 1)) return;
  nwcStop(); nwcKeyNow = key;
  if (!nwcSince) nwcSince = Math.floor(Date.now() / 1000);
  const since = Math.floor(Date.now() / 1000) - 600;   // recent requests are fetched so they can be refused with an answer
  for (const r of nwcRelays()) {
    let ws; try { ws = new WebSocket(r); } catch (e) { continue; }
    nwcSocks.push(ws);
    ws.onopen = () => {
      nwcRetry = 0;
      ws.send(JSON.stringify(['REQ', 'nwc', { kinds: [23194], '#p': pubs, since }]));
      for (const c of S.nwc) if (!nwcInfoSent.has(c.id)) nwcInfo(c).catch(() => {});
    };
    ws.onmessage = m => { let d; try { d = JSON.parse(m.data); } catch (e) { return; } if (d[0] === 'EVENT' && d[2]) onNwcEvent(d[2]); };
    ws.onclose = () => {
      if (!nwcSocks.includes(ws)) return;
      if (nwcSocks.every(s => s.readyState >= 2)) { const d = Math.min(120e3, 3000 * 2 ** nwcRetry++); nwcKeyNow = ''; setTimeout(() => nwcListen(), d); }
    };
  }
}
// the info event (kind 13194) tells apps what this wallet answers and which encryption it speaks
async function nwcInfo(c) {
  const ev = L.finalizeEvent({ kind: 13194, created_at: Math.floor(Date.now() / 1000), tags: [['encryption', 'nip44_v2 nip04'], ['notifications', NWC_NOTES.join(' ')]], content: NWC_METHODS.concat(['notifications']).join(' ') }, nwcKey(c).sk);
  const n = await relayPublish(ev, 6000, c.relays);
  if (n) nwcInfoSent.add(c.id);
}
function nwcSend(c, ev) {
  const open = nwcSocks.filter(s => s.readyState === 1);
  if (!open.length) return relayPublish(ev, 6000, c.relays);
  for (const s of open) { try { s.send(JSON.stringify(['EVENT', ev])); } catch (e) {} }
  return Promise.resolve(open.length);
}
function onNwcEvent(ev) {
  if (!ev || ev.kind !== 23194 || nwcSeen.has(ev.id)) return;
  const p = (ev.tags || []).find(t => t[0] === 'p'); const c = p && S.nwc.find(x => x.pub === p[1]);
  if (!c || ev.pubkey !== c.client) return;
  const now = Math.floor(Date.now() / 1000), exp = (ev.tags || []).find(t => t[0] === 'expiration');
  if (ev.created_at < now - 600 || ev.created_at > now + 300 || (exp && +exp[1] < now)) return;
  if (!L.verifyEvent(ev)) return;
  nwcSeen.add(ev.id); raw.set('nwcseen', [...nwcSeen].slice(-300));
  nwcChain = nwcChain.then(() => nwcHandle(c.id, ev)).catch(() => {});
}
const nwcErr = (code, message) => { const e = new Error(message); e.nwc = code; return e; };
async function nwcHandle(id, ev) {
  let c = S.nwc.find(x => x.id === id); if (!c) return;   // revoked: no answer
  const tagged = ((ev.tags || []).find(t => t[0] === 'encryption') || [])[1] || '';
  const enc = /nip44/.test(tagged) ? 'nip44' : /\?iv=/.test(ev.content) ? 'nip04' : 'nip44';
  let req; try { req = JSON.parse(await nwcDecrypt(c, enc, ev.content)); } catch (e) { return; }
  const method = String(req && req.method || '');
  let result = null, error = null;
  try {
    const now = Math.floor(Date.now() / 1000);
    if (ev.created_at < nwcSince - 2) throw nwcErr('OTHER', 'NUTCADE was closed or locked when this request was sent, so it was not carried out. Send it again.');
    if (now - ev.created_at > NWC_MAX_AGE) throw nwcErr('OTHER', 'This request is more than a minute old, so it was not carried out. Send it again.');
    if (!NWC_METHODS.includes(method)) throw nwcErr('NOT_IMPLEMENTED', `${method || 'This method'} is not supported.`);
    result = await NWC[method](c, req.params || {});
  } catch (e) { error = { code: e.nwc || 'INTERNAL', message: String(e.message || e).slice(0, 300) }; }
  c = S.nwc.find(x => x.id === id); if (!c) return;   // revoked while it ran: no answer
  c.used = Date.now(); c.enc = enc; saveNwc();
  const content = await nwcEncrypt(c, enc, JSON.stringify({ result_type: method, error, result }));
  const tags = [['p', ev.pubkey], ['e', ev.id]]; if (enc === 'nip44') tags.push(['encryption', 'nip44_v2']);
  await nwcSend(c, L.finalizeEvent({ kind: 23195, created_at: Math.floor(Date.now() / 1000), tags, content }, nwcKey(c).sk));
  if (tab === 'settings' && !$('#layer .sheet')) refresh();
}
async function nwcNotify(c, type, t) {
  try {
    const enc = c.enc === 'nip04' ? 'nip04' : 'nip44';
    const content = await nwcEncrypt(c, enc, JSON.stringify({ notification_type: type, notification: nwcTx(t) }));
    const tags = [['p', c.client]]; if (enc === 'nip44') tags.push(['encryption', 'nip44_v2']);
    await nwcSend(c, L.finalizeEvent({ kind: enc === 'nip44' ? 23197 : 23196, created_at: Math.floor(Date.now() / 1000), tags, content }, nwcKey(c).sk));
  } catch (e) {}
}
document.addEventListener('nutcade:paid', e => {
  const t = S.txs.find(x => x.quote === e.detail && x.nwc && x.type === 'in'); const c = t && S.nwc.find(x => x.id === t.nwc);
  if (c) nwcNotify(c, 'payment_received', t);
});
const bolt11Cache = new Map();
function invInfo(pr) { if (!pr) return null; let d = bolt11Cache.get(pr); if (d === undefined) { try { d = decodeBolt11(pr); } catch (e) { d = null; } bolt11Cache.set(pr, d); } return d; }
function nwcTx(t) {
  const d = invInfo(t.request) || {};
  const o = { type: t.type === 'in' ? 'incoming' : 'outgoing', state: { done: 'settled', pending: 'pending', failed: 'failed', expired: 'expired' }[t.status] || 'pending',
    invoice: t.request || '', description: d.description || '', description_hash: d.descriptionHash || '', preimage: t.preimage || '', payment_hash: d.paymentHash || '',
    amount: num(t.amount) * 1000, fees_paid: num(t.fee) * 1000, created_at: d.timestamp || Math.floor((t.created || t.ts) / 1000), expires_at: d.timestamp ? d.timestamp + d.expiry : null, metadata: {} };
  if (t.status === 'done') o.settled_at = Math.floor(t.ts / 1000);
  return o;
}
// an app sees only the payments and invoices it made, unless you let it see the whole wallet history
const lnTxs = c => S.txs.filter(t => t.method === 'ln' && t.request && (c.seeAll || t.nwc === c.id));
const NWC = {
  async get_info(c) { return { alias: 'NUTCADE', color: '#ffc700', pubkey: c.pub, network: 'mainnet', block_height: 0, block_hash: '', methods: NWC_METHODS, notifications: NWC_NOTES }; },
  async get_balance(c) {
    let b = Math.max(0, totalBalance() - (S.prefs.piggy ? piggySaved() : 0));
    const left = nwcLeft(c); if (left != null) b = Math.min(b, left);
    return { balance: b * 1000 };
  },
  async pay_invoice(c, p) {
    const inv = String(p.invoice || '').trim().toLowerCase().replace(/^lightning:/, '');
    let d; try { d = decodeBolt11(inv); } catch (e) { throw nwcErr('OTHER', "The invoice can't be read."); }
    if (d.msat == null) throw nwcErr('NOT_IMPLEMENTED', 'Invoices without an amount are not supported.');
    if (p.amount != null && String(p.amount) !== String(d.msat)) throw nwcErr('OTHER', 'The amount does not match the invoice.');
    if (d.sats == null) throw nwcErr('OTHER', 'Amounts that are not whole sats are not supported.');
    if (d.timestamp + d.expiry < Date.now() / 1000) throw nwcErr('OTHER', 'The invoice has expired.');
    const sats = d.sats;
    // the same invoice is never paid twice: a paid one answers with its proof, one in flight is refused
    const prev = S.txs.find(t => t.type === 'out' && t.method === 'ln' && t.request === inv && t.status !== 'failed' && t.status !== 'expired');
    if (prev && prev.status === 'done') return { preimage: prev.preimage || '', fees_paid: num(prev.fee) * 1000 };
    if (prev) throw nwcErr('OTHER', 'This invoice is already being paid.');
    const cands = S.mints.filter(m => supports(m, 'melt', 'bolt11') && balanceOf(m.url) >= sats).sort((a, b) => (b.url === S.active) - (a.url === S.active) || balanceOf(b.url) - balanceOf(a.url));
    if (!cands.length) throw nwcErr('INSUFFICIENT_BALANCE', `Not enough sats: no mint in this wallet holds ${sats} sat.`);
    let mq = null, url = null;
    for (const m of cands) {
      const w = await getWallet(m.url);
      const q = await w.createMeltQuoteBolt11(inv).catch(() => null);
      if (!q) continue;
      if (num(q.amount) !== sats) throw nwcErr('OTHER', `The mint read this invoice as ${num(q.amount)} sat instead of ${sats} sat, so it was not paid.`);
      if (balanceOf(m.url) >= sats + num(q.fee_reserve)) { mq = q; url = m.url; break; }
    }
    if (!mq) throw nwcErr('INSUFFICIENT_BALANCE', `Not enough sats for ${sats} sat plus the Lightning fee reserve in any one mint.`);
    // the budget is checked against the most this payment can cost: amount, Lightning fee reserve and the mint's fees
    const need = meltCost(url, sats, mq.fee_reserve).total, left = nwcLeft(c);
    if (left != null && need > left) { toast(`${c.name} asked to pay ${money(sats)}, more than its budget has left, so NUTCADE refused.`, 'gold'); throw nwcErr('QUOTA_EXCEEDED', `Over budget: this payment needs up to ${need} sat with its fee reserve, and ${left} sat of the budget is left.`); }
    if (!S.nwc.find(x => x.id === c.id)) throw nwcErr('UNAUTHORIZED', 'This connection was revoked.');
    let tx;
    // the payment carries the connection from the start (saved before anything is sent), so its cost counts against
    // the budget while it is in flight and after a reload; only a confirmed failure gives it back
    try { tx = await payMelt('ln', mq, 0, nwcNote(c), inv, url, { nwc: c.id, nwcName: c.name }); }
    catch (e) {
      refresh();
      if (e && e.piggy) throw nwcErr('RESTRICTED', 'This payment would dip into the piggy bank, which needs a countdown in NUTCADE.');
      const f = friendly(e, url);
      toast(`${c.name}'s payment of ${money(sats)} through Wallet Connect failed. ${f.also || f.message}`, 'red');
      throw nwcErr(/enough/i.test(f.message) ? 'INSUFFICIENT_BALANCE' : 'PAYMENT_FAILED', f.message + (f.also ? ' ' + f.also : ''));
    }
    for (let i = 0; i < 15 && tx.status === 'pending'; i++) { await sleep(2000); const pd = S.pending.find(x => x.txId === tx.id); if (pd) await reconcile(pd).catch(() => {}); tx = txById(tx.id); }
    sfx('coin'); refresh();
    if (tx.status === 'done') {
      toast(`${c.name} paid ${money(sats)} through Wallet Connect`, 'cyan');
      nwcNotify(c, 'payment_sent', tx);
      return { preimage: tx.preimage || '', fees_paid: num(tx.fee) * 1000 };
    }
    if (tx.status === 'failed') throw nwcErr('PAYMENT_FAILED', tx.cost ? `The payment failed; the mint kept ${tx.cost} sat as its fee.` : 'The payment failed. Nothing left the wallet.');
    throw nwcErr('OTHER', 'The payment is still pending at the mint. Look it up again later.');
  },
  async make_invoice(c, p) {
    const msat = Number(p.amount);
    if (!Number.isSafeInteger(msat) || msat <= 0) throw nwcErr('OTHER', 'Give an amount in millisats, more than 0.');
    if (msat % 1000) throw nwcErr('OTHER', 'Amounts that are not whole sats are not supported.');
    const sats = msat / 1000;
    if (sats > MAX_SAT) throw nwcErr('OTHER', 'That amount is too large.');
    const pick = [activeMint()].concat(S.mints).find(m => m && supports(m, 'mint', 'bolt11') && !isBlocked(m.url));
    if (!pick) throw nwcErr('OTHER', isBlocked(S.active) ? `${mintName(S.active)} is blocked in NUTCADE, and no other mint can receive Lightning.` : 'No mint in this wallet can receive Lightning.');
    const mi = methodInfo(pick, 'mint', 'bolt11');
    if (mi && ((mi.min && sats < mi.min) || (mi.max && sats > mi.max))) throw nwcErr('OTHER', `The mint takes ${mi.min || 1} to ${mi.max || MAX_SAT} sat.`);
    const tx = await lnMintQuote(sats, nwcNote(c), pick.url);
    updTx(tx.id, { nwc: c.id, nwcName: c.name, created: Date.now() });
    liveSync(); if (tab !== 'arcade' && !$('#layer .sheet')) refresh();
    const o = nwcTx(txById(tx.id)); if (p.description && !o.description) o.description = String(p.description).slice(0, 640);
    return o;
  },
  async lookup_invoice(c, p) {
    const inv = p.invoice ? String(p.invoice).trim().toLowerCase() : '', h = p.payment_hash ? String(p.payment_hash).toLowerCase() : '';
    if (!inv && !h) throw nwcErr('OTHER', 'Give a payment_hash or an invoice.');
    const t = lnTxs(c).find(t => (inv && t.request === inv) || (h && (invInfo(t.request) || {}).paymentHash === h));
    if (!t) throw nwcErr('NOT_FOUND', 'No invoice like that in this wallet.');
    return nwcTx(t);
  },
  async list_transactions(c, p) {
    const from = +p.from || 0, until = +p.until || Infinity, lim = Math.min(Math.max(+p.limit || 50, 1), 200), off = Math.max(+p.offset || 0, 0);
    const list = lnTxs(c).map(nwcTx).filter(o => (p.unpaid || o.state === 'settled' || (o.type === 'outgoing' && o.state === 'pending')) && (!p.type || o.type === p.type) && o.created_at >= from && o.created_at <= until)
      .sort((a, b) => b.created_at - a.created_at);
    return { transactions: list.slice(off, off + lim) };
  }
};

/* ---------- Wallet Connect sheets ---------- */
function budgetFields(b) {
  b = b || { per: 'none', sats: 0 };
  return `<div class="field"><label for="nwcPer">Budget</label><select id="nwcPer" class="inp">${PERIODS.map(([k, l]) => `<option value="${k}" ${b.per === k ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
    <div class="field" id="nwcAmtF" ${b.per && b.per !== 'none' ? '' : 'hidden'}><label for="amtIn">Budget amount (SAT)</label><input id="amtIn" class="inp amount" inputmode="numeric" placeholder="10000" value="${b.per && b.per !== 'none' && b.sats ? esc(b.sats) : ''}" autocomplete="off"></div>`;
}
function readBudget() {
  const per = val('nwcPer') || 'none';
  if (!PERIODS.some(p => p[0] === per)) throw new Error('Pick a budget.');
  if (per === 'none') return { per: 'none', sats: 0 };
  const n = satsOf('amtIn'); if (!n || n <= 0) throw amtErr('Type the budget in SAT, like 10000, or pick No budget.', 'zero');
  return { per, sats: n };
}
const NWC_HONEST = 'Wallet Connect only answers while NUTCADE is open and unlocked in a browser tab. Requests sent while it is closed or locked, or more than a minute old, are refused, never paid later.';
const seeAllField = on => `<label class="toggle" for="nwcAll"><span><span class="tl">Let this app see my whole wallet history</span><span class="th">Off, it sees only the payments and invoices it made itself. On, it sees every Lightning payment and invoice in this wallet: amounts, dates and descriptions.</span></span><input id="nwcAll" type="checkbox" ${on ? 'checked' : ''}></label>`;
const NWC_WARN = 'Whoever has this connection can spend from this wallet without asking you: up to its budget, or your whole balance if there is no budget.';
function openNwcNew() {
  if (needSeed()) return;
  openSheet('Connect an app', `<p style="margin:0">Let another app, like a Nostr client, pay and receive with this wallet using Nostr Wallet Connect (NWC).</p>
    <div class="notice">${NWC_HONEST}</div>
    <div class="field"><label for="nwcName">Name</label><input id="nwcName" class="inp" data-noi18n maxlength="40" placeholder="Damus" autocomplete="off"></div>
    ${budgetFields()}
    ${seeAllField(false)}
    <div class="notice red">${NWC_WARN}</div>
    <button class="btn solid gold block" data-act="nwcCreate">Create connection</button><div id="sheetErr"></div>`);
}
function showNwcUri(c, uri) {
  setBody(`<div class="label" style="text-align:center"><span data-noi18n>${esc(c.name)}</span></div>
    ${qrBlock(uri, 'Wallet Connect QR')}
    <div class="code" data-noi18n>${esc(uri)}</div>
    <button class="btn solid gold block" data-act="copy" data-text="${esc(uri)}">Copy connection link</button>
    <div class="notice red">This is shown only once. Paste or scan it into the app now. Anyone with it can spend from this wallet: up to its budget, or your whole balance if there is no budget.</div>
    <div class="notice">${NWC_HONEST}</div>
    <button class="btn block" data-act="close">Done</button>`);
}
function openNwcEdit(id) {
  const c = S.nwc.find(x => x.id === id); if (!c) return;
  openSheet('Wallet Connect', `<div class="field"><label for="nwcName">Name</label><input id="nwcName" class="inp" data-noi18n maxlength="40" value="${esc(c.name)}" autocomplete="off"></div>
    ${budgetFields(c.budget)}
    <div class="tiny muted">${nwcBudgetText(c)}</div>
    ${seeAllField(c.seeAll)}
    <div class="notice red">${NWC_WARN}</div>
    <button class="btn solid gold block" data-act="nwcSave" data-id="${esc(c.id)}">Save</button>
    <button class="btn block red" data-act="nwcRevokeAsk" data-id="${esc(c.id)}">Revoke</button><div id="sheetErr"></div>`);
}
function nwcPanel() {
  const live = nwcLive();
  return `<div class="panel" id="set-nwc"><span class="h2">Wallet Connect</span>
    <p class="th" style="margin:0">Let apps pay and receive with this wallet over Nostr (NWC, NIP-47).</p>
    <div class="notice">${NWC_HONEST}</div>
    ${S.nwc.length ? `<div class="row between tiny"><span>This tab</span><span style="color:${live ? 'var(--lime)' : 'var(--gold)'}">${live ? 'ANSWERING' : 'CONNECTING'}</span></div>
    <div class="txs">${S.nwc.map(c => `<div class="tx out contact"><span class="ico" aria-hidden="true">⚡</span><span class="mid"><div class="note" data-noi18n>${esc(c.name)}</div>
      <div class="meta"><span>${esc(nwcBudgetText(c))}</span></div><div class="meta"><span>${c.seeAll ? 'Sees your whole history' : 'Sees only its own payments'}</span></div><div class="meta"><span>${c.used ? `Last used ${timeAgo(c.used)}` : 'Not used yet'}</span></div></span>
      <span class="row cbtns"><button class="btn sm" data-act="nwcEdit" data-id="${esc(c.id)}">Edit</button><button class="btn sm red" data-act="nwcRevokeAsk" data-id="${esc(c.id)}">Revoke</button></span></div>`).join('')}</div>` : ''}
    <button class="btn sm gold" data-act="nwcNew">Connect an app</button>
  </div>`;
}
