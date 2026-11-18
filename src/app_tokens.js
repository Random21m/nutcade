/* ===================== Printable NUTCADE tokens + the logo in QR codes ===================== */
/* (its own file; the few hooks in app.js, trophies.js and style.css are marked "tokens:") */

/* ---------- QR codes, with the NUTCADE acorn in the middle ----------
   One setting (Settings → Look & sound → QR code center): None, or the NUTCADE acorn (the default). It applies to
   every QR code NUTCADE shows and prints. A code with the acorn uses error correction H (up to 30% of it can be
   covered and it still reads), and only while it stays easy to scan (at most 117 modules across). Every code is
   read back by the app's own reader (zxing, or jsQR where zxing can't load) once drawn: a code with the acorn that
   doesn't read back is drawn again plain. Big animated codes (BC-UR) always stay plain. */
const QR_LOGO_MAX = 117;   // modules across (version 25)
const qrLogoOn = () => (S.prefs.qrLogo || 'acorn') === 'acorn';
function qrMake(text, ecl, mode) { const qr = L.qrcode(0, ecl); qr.addData(text, mode); qr.make(); return qr; }
function qrPlan(text, mode, plain) {
  if (!plain && qrLogoOn()) { try { const qr = qrMake(text, 'H', mode); if (qr.getModuleCount() <= QR_LOGO_MAX) return { qr, logo: true, ecl: 'H' }; } catch (e) {} }
  const ecl = text.length > 600 ? 'L' : 'M';
  return { qr: qrMake(text, ecl, mode), logo: false, ecl };
}
// the acorn's square, in modules: about a fifth of the code across (4-5% of its area), odd so it sits centred
function logoSpan(n) { let k = Math.max(5, Math.round(n * (window.NutTokens && NutTokens._logoScale || 0.21))); if ((n - k) % 2) k++; return Math.min(k, n - 2); }
const ACORN_INK = { '1': '#ffffff', '2': '#000000', '3': '#000000', '4': '#000000' };
const ACORN_COL = { '1': '#d9822b', '2': '#6b3b12', '3': '#3d2208', '4': '#ffd79a' };
function drawBadge(x, bx, by, size, ink) {
  const r = size * 0.18, m = size * 0.06, s = size - 2 * m;
  x.save();
  x.beginPath(); if (x.roundRect) x.roundRect(bx + m, by + m, s, s, r); else x.rect(bx + m, by + m, s, s);
  x.fillStyle = ink ? '#ffffff' : '#1d0b33'; x.fill();
  x.lineWidth = Math.max(1, size * 0.07); x.strokeStyle = ink ? '#000000' : '#3ee6ff'; x.stroke();
  const px = (s * 0.72) / ACORN.length, ax = bx + size / 2 - ACORN[0].length * px / 2, ay = by + size / 2 - ACORN.length * px / 2;
  const pal = ink ? ACORN_INK : ACORN_COL;
  if (ink) { x.fillStyle = '#000'; ACORN.forEach((row, ry) => [...row].forEach((c, rx) => { if (c !== '.') x.fillRect(ax + rx * px - px * 0.25, ay + ry * px - px * 0.25, px * 1.5, px * 1.5); })); }   // (an outline, so the white body shows)
  ACORN.forEach((row, ry) => [...row].forEach((c, rx) => { if (c !== '.') { x.fillStyle = pal[c]; x.fillRect(ax + rx * px, ay + ry * px, Math.ceil(px), Math.ceil(px)); } }));
  x.restore();
}
// a QR code drawn at (ox, oy): `quiet` light modules around it, dark modules on light, the acorn in the middle if planned
function qrDraw(x, plan, ox, oy, cell, o = {}) {
  const { qr } = plan, n = qr.getModuleCount(), q = o.quiet == null ? 2 : o.quiet;
  x.fillStyle = o.light || '#ffffff'; x.fillRect(ox, oy, (n + 2 * q) * cell, (n + 2 * q) * cell);
  const k = plan.logo ? logoSpan(n) : 0, a = (n - k) / 2;
  x.fillStyle = o.dark || '#0a0717';
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) {
    if (k && r >= a && r < a + k && c >= a && c < a + k) continue;
    if (qr.isDark(r, c)) x.fillRect(ox + (c + q) * cell, oy + (r + q) * cell, cell, cell);
  }
  if (k) drawBadge(x, ox + (a + q) * cell, oy + (a + q) * cell, k * cell, !!o.ink);
}
// tokens: replaces app.js's qrCanvas. plain: never the logo (the frames of an animated code)
function qrCanvas(text, mode, plain) {
  try {
    const p = qrPlan(text, mode, plain), n = p.qr.getModuleCount(), sc = 4, q = 2;
    const c = document.createElement('canvas'); c.width = c.height = (n + q * 2) * sc;
    qrDraw(c.getContext('2d'), p, 0, 0, sc, { quiet: q });
    c.dataset.ecl = p.ecl; c.dataset.logo = p.logo ? '1' : '0';
    return c;
  } catch (e) { return null; }
}
// the app's own reader on a drawn code: zxing when it loads (served with the app), else jsQR
async function qrRead(src) {
  try {
    const d = frameData(src, 0); if (!d) return null;
    if (await loadZxing()) { qrRead.by = 'zxing'; const r = await L.readBarcodes(d, ZX_OPTS); return r[0] && r[0].isValid && r[0].text ? r[0].text : null; }
    qrRead.by = 'jsqr'; const r = L.jsQR(d.data, d.width, d.height, { inversionAttempts: 'dontInvert' }); return r && r.data ? r.data : null;
  } catch (e) { return null; }
}
// tokens: called by qrBlock with the code it just showed. A code with the acorn that doesn't read back is drawn plain.
async function qrVerify(el, c, text, label) {
  el.dataset.logo = c.dataset.logo; el.dataset.check = 'pending';
  let ok = (await qrRead(c)) === text;
  if (!ok && c.dataset.logo === '1' && el.isConnected) {
    const p = qrCanvas(text, undefined, true);
    if (p) { p.setAttribute('aria-label', tr(label || 'QR code')); c.replaceWith(p); c = p; el.dataset.logo = '0'; el.dataset.fallback = '1'; ok = (await qrRead(p)) === text; }
  }
  el.dataset.check = ok ? 'ok' : 'fail';
}
// a code checked before it is used (the score card that pays out, printed tokens): the acorn if it reads back, else plain
async function qrVerified(text, cell, o = {}) {
  for (const plain of qrLogoOn() && !o.plain ? [false, true] : [true]) {
    let p; try { p = qrPlan(text, undefined, plain); } catch (e) { return null; }
    const n = p.qr.getModuleCount(), q = o.quiet == null ? 4 : o.quiet, cl = typeof cell === 'function' ? cell(n + 2 * q) : cell;
    const c = document.createElement('canvas'); c.width = c.height = (n + 2 * q) * cl;
    qrDraw(c.getContext('2d'), p, 0, 0, cl, Object.assign({}, o, { quiet: q }));
    if ((await qrRead(c)) === text) return { canvas: c, logo: p.logo, n, ok: true, by: qrRead.by };
    if (plain) return { canvas: c, logo: false, n, ok: false, by: qrRead.by };
  }
  return null;
}
window.NutQR = { draw: qrDraw, plan: qrPlan, read: qrRead, verified: qrVerified };

/* ---------- printable tokens ----------
   Pick an amount per token and how many (1 to 20): NUTCADE makes each one as its own Cashu token, one after another,
   through the normal way of making a token (sendEcash: the journal, the spending limit, the fees as the mint keeps
   them), so each is an ordinary unclaimed sent token, with a print record on its history line ({ b: batch, i, n,
   code, style }). The batch is checked against the spending limit as a whole first (a PIN lets the whole batch
   through). Every code is read back before anything prints; if one wouldn't scan, nothing prints and the screen says
   which and why. Printed tokens live in the history and in the Printed tokens list (claimed or not, checked at the
   mint, NUT-07), and unclaimed ones can be taken back the usual way. A backup carries them like any open send.
   The page: fold-over cards, front and back side by side, so plain single-sided printing gives both sides lined up
   (double-sided printing lines up differently on every printer). Cut along the dashed lines, fold on the dotted
   one: printed sides out for a two-sided token, printed sides in to keep the code hidden until it is handed over. */
const PT_MAX = 20;
const PT_MAX_MODULES = 133;   // a printed code at most 133 modules across (0.33 mm each at 44 mm): denser ones don't scan reliably on paper
const ptMax = () => (window.NutTokens && +NutTokens.maxModules) || PT_MAX_MODULES;   // (the tests lower it to see a preset refused)
const PT_PRESETS = [1000, 2100, 5000, 21000];
/* The first-scan rule, shown before the first Print tokens: once for each wallet on each device (the flag is kept like
   the other "seen" lists, raw: inside the vault with a PIN), so a wallet restored on another phone shows it again. */
const ptWalletTag = () => S.seed ? hex(L.sha256(new TextEncoder().encode('nutcade-print-intro:' + S.seed.mnemonic))).slice(0, 16) : '';
const ptIntroSeen = () => (raw.get('ptintro', []) || []).includes(ptWalletTag());
function ptIntroDone() { const a = (raw.get('ptintro', []) || []).filter(x => x !== ptWalletTag()); a.push(ptWalletTag()); raw.set('ptintro', a.slice(-20)); }
const ptUI = { mint: null, amount: 0, count: 0, style: 'arcade', est: null };
const printedTxs = () => S.txs.filter(t => t.print && t.type === 'out');
const PT_APP = 'random21m.github.io/nutcade';
const ptCode = () => { const h = hex(rnd(4)).toUpperCase(); return h.slice(0, 4) + '-' + h.slice(4); };
let ptLast = { b: null, check: null };

/* What a batch costs, worked out once and then made exactly that way. Each token's coins are picked by ptPick, which
   gives the same pick for the same coins (the library's own pick is randomised, so two estimates could differ). The
   change of a swap comes back as plain binary coins (the library's split when it isn't told what the wallet holds),
   so the coins each next token can use are known in advance too. Making a token then uses exactly the pick ptPick
   makes at that moment (sendEcash's opts.pick, under the mint's lock), and the batch stops before any token that
   would take the total over what was shown (only possible if another payment changed the coins meanwhile). */
// one token's coins: the smallest single coin that covers it with its fee, else the largest coins until they do
function ptPick(w, have, h) {
  const cs = [...have].sort((a, b) => num(b.amount) - num(a.amount) || String(a.id).localeCompare(String(b.id)) || String(a.secret).localeCompare(String(b.secret)));
  for (let i = cs.length - 1; i >= 0; i--) if (num(cs[i].amount) >= h + feeOfPs(w, [cs[i]])) return [cs[i]];
  const sel = []; let t = 0;
  for (const c of cs) { sel.push(c); t += num(c.amount); if (t >= h + feeOfPs(w, sel)) return sel; }
  return null;
}
// what one token of `amount` takes before input fees (the amount and the fee coins it carries for its receiver), and its coins
function ptOuts(w, amount) {
  const ot = w.configureOutputs(w.parseAmount(amount, 'limit'), w.getOutputKeyset(), w.defaultOutputType(), true);
  const denoms = (ot.denominations || []).map(num);
  return { h: num(w.preparedTotal(ot)), denoms };
}
// the whole batch: { spend, fee, per: [each token's spend], denoms } (null: not enough at this mint; { tooMany })
function ptPlan(w, url, amount, count) {
  const { h, denoms } = ptOuts(w, amount), m = mintMax(url);
  let have = [...(S.proofs[url] || [])], spend = 0, ks = null; const per = [];
  try { ks = w.getOutputKeyset().id; } catch (e) {}
  for (let i = 0; i < count; i++) {
    const sel = ptPick(w, have, h);
    if (!sel) return null;
    if (m && sel.length > m) return { tooMany: m };
    const s_ = h + feeOfPs(w, sel); spend += s_; per.push(s_);
    const used = new Set(sel.map(x => x.secret)), back = sum(sel) - s_;
    have = have.filter(x => !used.has(x.secret)).concat(back > 0 ? splitAmt(back).map((a, j) => ({ id: ks || sel[0].id, amount: a, secret: `plan${i}.${j}`, C: '' })) : []);
  }
  return { spend, fee: spend - amount * count, per, denoms };
}
const ptBadPlan = (url, amount, count, plan) => {
  if (!plan) return new Error(`${count} × ${money(amount)} plus the mint's fees is more than this mint holds (${money(balanceOf(url))}).`);
  if (plan.tooMany) return manyErr(url, plan.tooMany);
  return null;
};
const ptStyleName = s => s === 'ink' ? 'Ink saver' : '<span data-noi18n>Arcade</span>';   // (Arcade: the style's name, the same in every language)
function openPrint() {
  if (needMint()) return;
  if (!ptIntroSeen()) {
    openSheet('Print tokens', `<div class="pt-intro"><div class="pb-h" style="text-align:center">BEFORE YOU PRINT</div>
      <p class="pt-rule" style="margin:0">A printed token is cash. Whoever scans it first gets the sats. Keep it folded or hidden until you hand it over.</p>
      <button class="btn solid gold block" data-act="ptIntroOk">I understand</button></div>`);
    return;
  }
  const m = activeMint(); ptUI.mint = m.url;
  const n = printedTxs().length, fx = a => { const f = fiatOf(a); return f ? '≈ ' + f : ''; };
  const pressed = a => String(ptUI.amount ? (PT_PRESETS.includes(ptUI.amount) ? ptUI.amount : 'other') : '') === String(a);
  openSheet('Print tokens', `<p style="margin:0">Hand sats over on paper, like arcade tokens. Each token is its own Cashu token with its own QR code: whoever scans it first gets its sats, with any Cashu wallet.</p>
    <div class="tiny muted">From <b style="color:var(--ink)" data-noi18n>${esc(m.name)}</b> · ${money(balanceOf(m.url))} available</div>
    <div class="field"><label>Amount per token</label><div class="pt-presets" role="group" aria-label="Amount per token">
      ${PT_PRESETS.map(a => `<div class="pt-pre"><button type="button" data-act="ptPreset" data-a="${a}" aria-pressed="${pressed(a)}"><span data-noi18n>${fmt(a)}</span></button><span class="pt-fiat tiny muted" data-a="${a}" data-noi18n>${esc(fx(a))}</span></div>`).join('')}
      <div class="pt-pre"><button type="button" data-act="ptPreset" data-a="other" aria-pressed="${pressed('other')}">OTHER</button><span class="pt-fiat" data-a="other"></span></div></div>
      <div class="tiny muted pt-pre-why"></div></div>
    <div class="row" style="gap:10px"><div class="field" style="flex:3"><label for="ptAmt">Amount per token (SAT)</label><input id="ptAmt" class="inp amount" inputmode="numeric" placeholder="1000" autocomplete="off" value="${ptUI.amount || ''}"></div>
    <div class="field" style="flex:2"><label for="ptCount">How many (1 to 20)</label><input id="ptCount" class="inp" inputmode="numeric" autocomplete="off" value="${ptUI.count || 4}"></div></div>
    <div class="field"><label>Style</label><div class="seg pt-seg" role="group" aria-label="Style">${[['arcade', 'ARCADE'], ['ink', 'INK SAVER']].map(([k, l]) => `<button type="button" data-act="ptStyle" data-s="${k}" aria-pressed="${ptUI.style === k}"${k === 'arcade' ? ' data-noi18n' : ''}>${l}</button>`).join('')}</div>
      <div class="tiny muted" id="ptStyleHelp">${ptUI.style === 'ink' ? 'Black on white.' : 'Full color. The QR code is always dark on light.'}</div></div>
    <button class="btn solid gold block" data-act="ptNext">Next</button>
    ${n ? `<button class="linkbtn tiny" data-act="ptList" style="justify-self:start">Printed tokens (${n})</button>` : ''}
    <div id="sheetErr"></div>`, body => {
    const el = body.querySelector('#ptAmt');
    if (el) el.addEventListener('input', () => { const v = satsOf('ptAmt'); body.querySelectorAll('[data-act=ptPreset]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.a === (PT_PRESETS.includes(v) ? String(v) : 'other')))); });
    ptPresetCheck(m.url, body);
  });
}
// each preset as this mint would make it (the receiver's fee coins too): one whose code would be too dense is disabled, saying why
async function ptPresetInfo(url) {
  const w = await getWallet(url);
  return PT_PRESETS.map(a => { const { denoms } = ptOuts(w, a), modules = ptModules(url, w, denoms); return { a, coins: denoms.length, modules, fits: modules <= ptMax() }; });
}
async function ptPresetCheck(url, body) {
  let info; try { info = await ptPresetInfo(url); } catch (e) { return; }
  if (!body.isConnected) return;
  const why = [];
  for (const x of info) {
    const b = body.querySelector(`[data-act=ptPreset][data-a="${x.a}"]`); if (!b) continue;
    b.disabled = !x.fits;
    if (!x.fits) why.push(`${money(x.a)} would need ${x.coins} coins here, too dense to scan reliably on paper.`);
  }
  const box = body.querySelector('.pt-pre-why'); if (box) box.innerHTML = why.map(t => `<div>${esc(t)}</div>`).join('');
}
function ptRead() {
  const amount = satsOf('ptAmt'); if (!amount || amount <= 0) throw new Error('Enter an amount in sats, like 1000.');
  const s = String(val('ptCount')).trim(), count = /^\d+$/.test(s) ? +s : NaN;
  if (!(count >= 1 && count <= PT_MAX)) throw new Error('Pick how many tokens: 1 to 20.');
  return { amount, count };
}
// the size across of a token's code made of exactly these coins (the receiver's fee coins too), as printed (no DLEQ)
function ptModules(url, w, denoms) {
  const r = k => hex(rnd(k)); let id; try { id = w.getOutputKeyset().id; } catch (e) { id = '00' + r(7); }
  const text = L.getEncodedToken({ mint: url, unit: 'sat', proofs: denoms.map(a => ({ id, amount: a, secret: r(32), C: '02' + r(32) })) });
  try { return qrPlan(text, undefined, true).qr.getModuleCount(); } catch (e) { return Infinity; }
}
const ptFits = (url, w, denoms) => ptModules(url, w, denoms) <= ptMax();
async function ptSummary() { const { amount, count } = ptRead(); return ptShowCost(amount, count); }
async function ptShowCost(amount, count) {
  const url = ptUI.mint;
  if (isOffline()) throw new Error("Making tokens needs the mint, and you're offline. Try again online.");
  const w = await getWallet(url);
  if (belowMin(url)) { const e = new Error(`${host(url)} takes too few coins per request to print tokens from it.`); e.keep = true; throw e; }
  const { denoms } = ptOuts(w, amount);
  if (!ptFits(url, w, denoms)) throw new Error(`A ${money(amount)} token needs ${denoms.length} coins, and its QR code would be too dense to scan reliably on paper. Pick an amount made of fewer coins: ${fmt(1024)} or ${fmt(2048)} are one coin each, ${fmt(1000)} is six.`);
  const est = ptPlan(w, url, amount, count), bad = ptBadPlan(url, amount, count, est); if (bad) throw bad;
  Object.assign(ptUI, { amount, count, est });
  setBody(`<div class="pt-sum"><dl class="kv"><dt>Tokens</dt><dd>${count} × ${money(amount)}</dd><dt>Total</dt><dd>${money(amount * count)}</dd>
      <dt>Fees</dt><dd>${est.fee > 0 ? `up to ${money(est.fee)}` : 'None at this mint'}</dd><dt>Style</dt><dd>${ptStyleName(ptUI.style)}</dd><dt>Mint</dt><dd data-noi18n>${esc(host(url))}</dd></dl>
    ${est.fee > 0 ? `<div class="tiny muted">The mint's fee for making each token, and the fee each token carries so whoever claims it gets the full ${money(amount)}.</div>` : ''}
    <div class="notice cyan">The sats leave your balance now. Unclaimed tokens can be taken back any time from Printed tokens. A photo of a code is enough to take its sats, so keep them hidden until you hand them over.</div>
    <button class="btn solid pink block" data-act="ptMake">Make ${count === 1 ? '1 token' : `${count} tokens`}</button><button class="btn block" data-act="ptOpen">Back</button><div id="sheetErr"></div></div>`);
}
async function ptMakeBatch(btn) {
  const { amount, count, style } = ptUI, url = ptUI.mint, shown = ptUI.est;
  if (isOffline()) throw new Error("Making tokens needs the mint, and you're offline. Try again online.");
  const say = t => { const sp = btn && btn.querySelector('.spinner'); if (sp) sp.textContent = t; };
  const w = await getWallet(url), plan = ptPlan(w, url, amount, count), bad = ptBadPlan(url, amount, count, plan); if (bad) throw bad;
  // the coins changed since the cost was shown (a payment came in or went out): the new cost is shown, nothing is made
  if (!shown || plan.spend !== shown.spend) { await ptShowCost(amount, count); const e = new Error('Your balance changed since, so the cost was worked out again. Check it and tap Make again.'); e.keep = true; throw e; }
  piggyGuard(shown.spend);
  // the spending limit: the batch as a whole, once, with the cost shown (a PIN entered for it lets every token of it
  // through); each token is then made, held and counted the normal way
  const approved = !!(limitOK && limitOK.until > Date.now());
  limitGate(shown.spend).release();
  const b = uid(), at = Date.now(), made = []; let paid = 0;
  try {
    for (let i = 1; i <= count; i++) {
      say(`MAKING TOKEN ${i} OF ${count}`);
      const pick = (w2, have) => {   // (under the mint's lock, from the coins held right then)
        const sel = ptPick(w2, have, ptOuts(w2, amount).h); if (!sel) return null;
        const spend = ptOuts(w2, amount).h + feeOfPs(w2, sel);
        if (paid + spend > shown.spend) { const e = new Error('Another payment changed the coins at this mint during the batch, so the next token would cost more than shown.'); e.keep = true; throw e; }
        return { sel: { send: sel }, spend };
      };
      const tx = await sendEcash(amount, `Printed token ${i} of ${count}`, null, url, { approved, pick, txx: { print: { b, i, n: count, code: ptCode(), style, at } } });
      made.push(tx.id); paid += num(tx.amount) + num(tx.fee);
    }
  } catch (e) {
    if (!made.length) throw e;   // (nothing made: the usual error, and a retry after a PIN starts the batch from the start)
    // stopped part way: never made again (no retry), and the screen says exactly what was made
    refresh(); sfx('err');
    const why = friendly(e, url);
    setBody(`<div class="pt-stopped" data-b="${esc(b)}"><div class="pb-h" style="text-align:center">STOPPED AFTER ${made.length} OF ${count}</div>
      ${errHTML(why)}
      <p style="margin:0">${made.length} of ${count} tokens were made before this. They are in Printed tokens: print them or take them back.</p>
      <p class="tiny muted" style="margin:0">Nothing more was made.</p>
      <button class="btn solid gold block" data-act="ptReprint" data-b="${esc(b)}">Print what was made</button>
      <button class="btn block" data-act="ptList">Printed tokens</button><div id="sheetErr"></div></div>`);
    return;
  }
  sfx('coin'); refresh();
  say('CHECKING CODES');
  await ptReady(b, style);
}
// the slim token on paper: without the DLEQ proofs, which a wallet doesn't need to claim it (a smaller code)
function ptText(t) { try { return slimToken(t.token); } catch (e) { return t.token; } }
// every code of a batch drawn and read back (the acorn if it reads back, else plain); a code that won't read refuses the print
async function ptImages(txs, style) {
  const ink = style === 'ink', out = [], check = [];
  for (const t of txs) {
    const text = ptText(t);
    const r = await qrVerified(text, 8, { quiet: 4, ink, light: ink ? '#ffffff' : '#fff8e6', dark: ink ? '#000000' : '#0a0717' });
    check.push({ i: t.print.i, code: t.print.code, ok: !!(r && r.ok), logo: !!(r && r.logo), by: r && r.by });
    if (!r) { ptLast.check = check; const e = new Error(`Token #${t.print.code} is too long for one printed QR code, so nothing was printed. It is kept in Printed tokens: take it back, or send it another way.`); e.keep = true; throw e; }
    if (r.ok && r.n > ptMax()) { ptLast.check = check; const e = new Error(`The QR code of token #${t.print.code} is too dense to scan reliably on paper, so nothing was printed. It is kept in Printed tokens: take it back, or send it another way.`); e.keep = true; throw e; }
    if (!r.ok) { ptLast.check = check; const e = new Error(`The QR code of token #${t.print.code} didn't read back, so nothing was printed. Your tokens are kept in Printed tokens: try printing again, or take them back.`); e.keep = true; throw e; }
    out.push({ t, src: r.canvas.toDataURL('image/png'), logo: r.logo });
  }
  ptLast.check = check;
  return out;
}
const ptBatch = b => printedTxs().filter(t => t.print.b === b).sort((x, y) => x.print.i - y.print.i);
const ptOpenOf = b => ptBatch(b).filter(t => t.status === 'pending');
async function ptReady(b, style) {
  const txs = ptOpenOf(b); if (!txs.length) throw new Error('Every token of this batch was claimed or taken back, so there is nothing to print.');
  style = style || txs[0].print.style || 'arcade';
  const imgs = await ptImages(txs, style);
  ptLast = { b, style, imgs, check: ptLast.check };
  const all = ptBatch(b), fees = all.reduce((s, t) => s + num(t.fee), 0), total = txs.reduce((s, t) => s + num(t.amount), 0);
  setBody(`<div class="pt-ready" data-b="${esc(b)}"><div class="pb-h" style="text-align:center">${txs.length === 1 ? '1 TOKEN READY' : `${txs.length} TOKENS READY`}</div>
    <dl class="kv"><dt>Total</dt><dd>${money(total)}</dd><dt>Fees paid</dt><dd>${money(fees)}</dd><dt>Style</dt><dd>${ptStyleName(style)}</dd></dl>
    <div class="tiny muted">✓ Every code was read back and scans.</div>
    <div class="pt-preview ${style === 'ink' ? 'ink' : 'arcade'}">${imgs.map(x => ptCardHTML(x.t, x.src)).join('')}</div>
    <div class="notice">Cut along the dashed lines. Fold each card on the dotted line, printed sides out: front and back of one token. Fold it the other way to keep the code hidden until you hand it over.</div>
    <button class="btn solid gold block" data-act="ptPrint" data-b="${esc(b)}">Print</button>
    <button class="btn block" data-act="ptList">Printed tokens</button><div id="sheetErr"></div></div>`);
}
function ptAmtStyle(a) { const s = fmt(a), mm = Math.min(6, 29 / (s.length + 1.6)); return `font-size:${mm.toFixed(2)}mm`; }
function ptCardHTML(t, src) {
  const p = t.print, code = '#' + p.code;
  return `<div class="pt-card"><div class="pt-front"><div class="pt-l">
      <div class="pt-mq">NUTCADE</div><div class="pt-sub">TOKEN</div><div class="pt-dots" aria-hidden="true"></div>
      <div class="pt-amt" style="${ptAmtStyle(t.amount)}"><span data-noi18n>${fmt(t.amount)}</span><span class="pt-unit">SAT</span></div>
      <div class="pt-meta"><div><span>Mint:</span> <span data-noi18n>${esc(host(t.mint))}</span></div><div><span>Made</span> <span data-noi18n>${esc(fmtDate(p.at || t.ts))}</span></div><div><span>Token</span> <span data-noi18n>${esc(code)}</span></div></div></div>
      <div class="pt-r"><img class="pt-qr" src="${src}" alt="QR code of token ${esc(code)}"><div class="pt-cap">SCAN TO CLAIM</div></div></div>
    <div class="pt-fold" aria-hidden="true"></div>
    <div class="pt-back"><div class="pt-h">HOW TO CLAIM</div>
      <ol><li>Open any Cashu wallet (NUTCADE, Minibits, cashu.me…).</li><li>Scan the code on the front. The sats are now yours.</li><li><span>New to this? Open</span> <span data-noi18n>${PT_APP}</span></li></ol>
      <div class="pt-warn">This token IS the money. Whoever scans it first gets the sats. Keep the code hidden until you hand it over.</div>
      <div class="pt-foot"><span>CHECK IT'S STILL GOOD: SCAN IN NUTCADE</span><span>NO ACCOUNT. NO TRACKING.</span><span data-noi18n>${esc(code)}</span></div></div></div>`;
}
// the pages the printer gets: 4 cards a page, in a box of their own next to the app (only it prints, see style.css)
async function preparePrint(b, style) {
  b = b || ptLast.b; style = style || (b === ptLast.b && ptLast.style) || 'arcade';
  let imgs = b === ptLast.b ? ptLast.imgs : null; if (!imgs) return false;
  if (style !== ptLast.style) imgs = await ptImages(imgs.map(x => x.t), style);   // (the other style's colors, read back again)
  let box = document.getElementById('tokPrint'); if (!box) { box = document.createElement('div'); box.id = 'tokPrint'; document.body.appendChild(box); }
  box.className = 'tok-print ' + (style === 'ink' ? 'ink' : 'arcade');
  const pages = []; for (let i = 0; i < imgs.length; i += 4) pages.push(imgs.slice(i, i + 4));
  box.innerHTML = pages.map(pg => `<div class="pt-page">${pg.map(x => ptCardHTML(x.t, x.src)).join('')}</div>`).join('');
  document.documentElement.classList.add('print-tokens');
  return true;
}
function endPrint() { document.documentElement.classList.remove('print-tokens'); const b = document.getElementById('tokPrint'); if (b) b.remove(); }
async function ptPrintNow(b) {
  if (!(await preparePrint(b))) throw new Error('Make the tokens again to print them.');
  for (const t of ptOpenOf(b)) if (!t.print.printed) { t.print.printed = Date.now(); }
  save();
  const done = () => { window.removeEventListener('afterprint', done); setTimeout(endPrint, 0); };
  window.addEventListener('afterprint', done);
  try { window.print(); } catch (e) { done(); }
  const r = document.querySelector('#layer .pt-ready');
  if (r && !r.querySelector('.pt-after')) r.querySelector('[data-act=ptPrint]').insertAdjacentHTML('afterend', `<div class="notice cyan pt-after"><span>Nobody claimed it? Take it back any time in</span> <a href="#" class="pt-link" data-act="ptList">Notes → Printed tokens</a></div>`);
}

/* ---------- the Printed tokens list ---------- */
const PT_ST = { pending: ['○', 'UNCLAIMED'], claimed: ['✓', 'CLAIMED'], reclaimed: ['↩', 'TAKEN BACK'] };
function ptListHTML() {
  const all = printedTxs(), by = new Map();
  for (const t of all) { if (!by.has(t.print.b)) by.set(t.print.b, []); by.get(t.print.b).push(t); }
  const n = s => all.filter(t => t.status === s).length, waiting = n('pending');
  const batches = [...by.values()].sort((a, b) => (b[0].print.at || b[0].ts) - (a[0].print.at || a[0].ts));
  return `<div class="pt-list">
    <div class="tiny">${all.length} printed · ${waiting} unclaimed · ${n('claimed')} claimed · ${n('reclaimed')} taken back</div>
    <div class="row wrap" style="gap:8px"><button class="btn sm violet" data-act="ptCheck" ${waiting ? '' : 'disabled'}>Check claimed</button><button class="btn sm gold" data-act="ptTakeAll" ${waiting ? '' : 'disabled'}>Take back all unclaimed</button></div>
    ${batches.map(ts => { ts.sort((a, b) => a.print.i - b.print.i); const f = ts[0], open = ts.some(t => t.status === 'pending');
      return `<div class="pt-batch"><div class="row between" style="gap:8px"><span class="tiny"><span data-noi18n>${esc(fmtDate(f.print.at || f.ts))}</span> · <span>${ts.length} × ${money(f.amount)}</span> · <span data-noi18n>${esc(host(f.mint))}</span></span>${open ? `<button class="btn sm" data-act="ptReprint" data-b="${esc(f.print.b)}">Print again</button>` : ''}</div>
        ${ts.map(t => { const st = PT_ST[t.status] || ['·', String(t.status || '').toUpperCase()];
          return `<div class="pt-row st-${esc(t.status)}" data-id="${esc(t.id)}"><span class="pt-st"><span aria-hidden="true">${st[0]}</span> <span>${st[1]}</span></span><span class="pt-code" data-noi18n>#${esc(t.print.code)}</span><span class="pt-a">${money(t.amount)}</span>${t.status === 'pending' ? `<button class="btn sm gold" data-act="ptTake" data-id="${esc(t.id)}">Take back</button>` : '<span></span>'}</div>`; }).join('')}</div>`; }).join('') || '<div class="empty-state">No printed tokens yet.</div>'}
    <div id="sheetErr"></div></div>`;
}
function ptListOpen(keep) {
  if (keep && $('#layer .pt-list')) { const e = $('#sheetErr'), err = e ? e.innerHTML : ''; setBody(ptListHTML()); if (err && $('#sheetErr')) $('#sheetErr').innerHTML = err; return; }
  openSheet('Printed tokens', ptListHTML());
}
// claimed or not, asked at each mint (NUT-07). A mint that doesn't answer changes nothing.
async function ptCheckAll() {
  const open = printedTxs().filter(t => t.status === 'pending'), down = new Set(); let got = 0;
  for (const t of open) {
    if (down.has(t.mint)) continue;
    try { if (await inTime(checkClaim(t), 20000)) got++; } catch (e) { down.add(t.mint); }
  }
  return { got, down: [...down] };
}
// Take back: the usual reclaim (the token claimed back into this wallet). Claimed by someone else first: said so, and
// the token is marked claimed (the mint says its coins are spent); nothing else changes.
async function ptTakeOne(t) {
  reclaiming.add(t.id);
  try { await receiveToken(t.token, 'Reclaimed: ' + (t.note || 'ecash token'), { own: true }); }
  catch (e) {
    if (isSpentErr(e) || /already spent/i.test(String(e && (e.raw || e.message)))) {
      let claimed = false; try { claimed = await checkClaim(t); } catch (x) {}
      if (claimed || (txById(t.id) || {}).status === 'claimed') { const f = new Error(`Someone already claimed token #${t.print ? t.print.code : ''}, so there is nothing to take back. Your balance didn't change.`); f.keep = true; throw f; }
    }
    throw e;
  } finally { setTimeout(() => reclaiming.delete(t.id), 5000); }
  if ((txById(t.id) || {}).status === 'pending') updTx(t.id, { status: 'reclaimed' });
}

/* ---------- for the tests (and nothing else) ---------- */
window.NutTokens = {
  get lastCheck() { return ptLast.check; },
  get lastEstimate() { return ptUI.est; },
  maxModules: PT_MAX_MODULES, presetInfo: url => ptPresetInfo(url || S.active),
  planNow: async (amount, count, url) => { url = url || S.active; const p = ptPlan(await getWallet(url), url, amount, count); return p && { spend: p.spend, fee: p.fee }; },
  preparePrint, endPrint, printed: () => printedTxs(),
  showQR: text => openSheet('QR code', qrBlock(text, 'QR code')),
  // a token of n coins at the active mint, with DLEQ proofs, like a real one (only for measuring QR sizes)
  sampleToken: n => { const r = k => hex(rnd(k)); const id = Object.keys(S.counters)[0] || '00' + r(7);
    return L.getEncodedToken({ mint: S.active, unit: 'sat', proofs: Array.from({ length: n }, (_, i) => ({ id, amount: 2 ** (i % 12), secret: r(32), C: '02' + r(32), dleq: { e: r(32), s: r(32), r: r(32) } })) }); },
  _logoScale: 0
};
