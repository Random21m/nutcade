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
  const canMove = bal > 0 && S.mints.filter(m => m.url !== url && !isBlocked(m.url) && supports(m, 'mint', 'bolt11')).length && supports(S.mints.find(m => m.url === url), 'melt', 'bolt11');
  openSheet('Block mint', `<p style="margin:0">Block ${esc(n)}? NUTCADE will refuse ecash, payment requests and new deposits from it, and always tell you when it does. You can unblock it any time.</p>
    ${bal ? `<div class="notice">Your ${money(bal)} at ${esc(n)} stays usable: you can still send it or move it to another mint. Moving it out is a good idea.</div>` : ''}
    ${S.prefs.npc && S.prefs.npcMint === url ? `<div class="notice">Your Lightning address still sends payments to ${esc(n)}. Change its mint in Settings → Lightning address.</div>` : ''}
    <button class="btn solid gold block" data-act="blockMintGo" data-url="${esc(url)}">Block this mint</button>
    ${canMove ? `<button class="btn block" data-act="moveOpen" data-from="${esc(url)}">Move sats out first</button>` : ''}<div id="sheetErr"></div>`);
}
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
      // the service said no: one last look in case it paid anyway, then the invoice is dropped
      // (a background check may be minting it at this very moment: wait for it rather than race it)
      let st = 'busy';
      for (let i = 0; i < 60 && st === 'busy'; i++) { st = q ? await checkQuote(q).catch(() => 'waiting') : 'gone'; if (st === 'busy') await sleep(250); }
      if (st === 'paid' || (txById(tx.id) || {}).status === 'done') { wdUsed.add(v.k1); raw.set('lnurlwUsed', [...wdUsed].slice(-200)); return { tx, q, paid: true }; }
      drop(); refresh();
      const used = /used|already|claimed|redeem|spent|exhaust|no (more )?(balance|funds)/i.test(r.reason || '');
      const exp = /expire/i.test(r.reason || '');
      throw serviceErr(used ? 'This voucher was already used.' : exp ? 'This voucher has expired.' : 'The voucher service turned this down.', r.reason, 'Nothing was received and nothing was spent.');
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
    <div class="row" style="justify-content:center"><span class="spinner" id="payState">WAITING FOR THE VOUCHER TO PAY</span></div>
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
            if (alive) { alive = false; setBody(`${errHTML(serviceErr("The voucher didn't pay before the invoice expired.", '', 'Nothing was received and nothing was spent.'))}<button class="btn solid gold block" data-act="close">OK</button>`); refresh(); }
            return;
          }
        } catch (e) {}
        await sleep(2000);
      }
    })();
    return () => { alive = false; document.removeEventListener('nutcade:paid', onPaid); };
  });
}

