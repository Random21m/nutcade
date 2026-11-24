/* ===================== Auto-move into your mint (1.32) ===================== */
/* "Move what I receive into my mint" (Settings, Auto-move), off by default and kept per wallet (in the PIN vault with a
   PIN; not in backup files; a restore or new phrase turns it off). You pick "my mint" yourself, from your own SAT mints
   that take Lightning deposits AND pay out over Lightning (never a blocked mint, never one below NUTCADE's request
   minimum); NUTCADE never guesses it.
   When it runs: a moment after money arrives (a line that counts as an arrival, app_arrive.js arrQual: never a move,
   a check-up or your own coins coming back) while the app is open and unlocked, and once after the start-up checks
   (tickBody(startup)), to catch up. Nothing runs while NUTCADE is closed or locked, in a paused tab, or in the duress
   PIN's wallet. There is no timer and no retry loop: what didn't move waits for the next arrival or the next start.
   What it does: for each other SAT mint holding at least "don't move below" (amMin, default 1,000 SAT; the balance
   there is what is compared, so exactly the threshold moves), the most that fits after the fees is moved to my mint
   with the one Lightning move between mints (moveQuotes / doMove, app_r4.js): the receiving side recorded first, the
   payment journaled and recovered after a crash exactly like a move by hand. The amount is found as Send all finds it
   (allFit, app_sendall.js), with quotes from both mints.
   A move never goes ahead when:
   - the most it can cost (the Lightning fee reserve and the mint's input fees) is more than 2% of the amount (AM_FEE_PCT);
   - the spending limit would refuse it: it is an ordinary payment, checked before (the "with the PIN" limit for one
     payment, the day limit), and the payment itself passes limitGate with `auto` so a PIN you entered for something
     else is never used for it. It never asks for the PIN: such a move waits, and you can move it yourself;
   - my mint isn't answering, asks for a login (NUT-21/22 errors), or can't take deposits any more: the whole run stops;
   - the sending mint can't pay over Lightning, isn't answering or asks for a login: that mint is skipped.
   Each of these leaves one plain line in Settings (and one toast for a run that a new reason stopped).
   USD, EUR and CHF accounts are never moved and never added to anything here: the line says they were skipped.
   It waits (one line, no run) while wallet sync is on and until the 12 words are written down.
   One run at a time (amBusy); an arrival during a run asks for one more run after it, never more. */
const AM_FEE_PCT = 2, AM_MIN_DEF = 1000, AM_MIN_MAX = 2100000000000000;
const am = { busy: null, again: false, t: 0, lines: [], at: 0, lastKey: '', seen: new Set() };
const amDecoy = () => !!(vault.on && vault.decoy);
const amOn = () => S.prefs.amOn === true && !!S.seed;
// the threshold as a whole number of SAT, 1 or more (anything else stored reads as the default)
function amMin() { const v = S.prefs.amMin; return Number.isSafeInteger(v) && v >= 1 && v <= AM_MIN_MAX ? v : AM_MIN_DEF; }
// a mint that can be "my mint": a SAT account that takes Lightning deposits and pays out over Lightning, not blocked, not below the minimum
const amFit = m => !!m && isSatAcct(m.url) && supports(m, 'mint', 'bolt11') && supports(m, 'melt', 'bolt11') && !isBlocked(m.url) && !belowMin(m.url);
const amMine = () => { const u = S.prefs.amMint; return typeof u === 'string' && u ? S.mints.find(m => m.url === u) || null : null; };
const amAuth = e => { if (!e) return false; const c = Number(e.code); return (c >= 30000 && c < 32000) || e.status === 401 || /\b(clear|blind) auth|auth(entication|orization)? (required|failed)|login/i.test(String(e.raw || e.message || '')); };
const amSide = (s, p) => p.catch(e => { if (e && typeof e === 'object') e.amSide = s; throw e; });
// no answer at all (offline, refused connection, a request past its time limit): "isn't answering". A mint that answered
// with an error is not "down": it turned the request down.
const amNet = e => !!e && !e.raw && typeof e.code !== 'number' && typeof e.status !== 'number' && (e.name === 'AbortError' || /Failed to fetch|NetworkError|Load failed|network|didn't answer in time|Can't reach|aborted|timed? ?out/i.test(String(e.message || e)));
// the lines (English, translated whole; a mint's name is shown apart from them, never inside)
const AM_TXT = {
  unset: () => 'Pick your mint below. Nothing moves until you do.',
  mybad: () => "Your mint can't take Lightning deposits now, so nothing moved. Pick another mint.",
  mydown: () => "Your mint isn't answering, so nothing moved. NUTCADE tries again when sats arrive or when you open it.",
  mylogin: () => 'Your mint asks for a login, so nothing moved. NUTCADE tries again when sats arrive or when you open it.',
  none: a => `Nothing to move: no other mint holds ${money(a[0])} or more.`,
  moved: a => `Moved ${money(a[0])} to your mint.`,
  waiting: a => `${money(a[0])} on its way to your mint.`,
  noln: () => "Can't pay out over Lightning, so its sats stay there.",
  down: () => "Isn't answering, so its sats stay there for now.",
  login: () => 'Asks for a login, so its sats stay there for now.',
  fee: a => `The fees (up to ${money(a[0])}) are more than 2% of ${money(a[1])}, so nothing moved.`,
  per: a => `This move (${money(a[0])} with fees) is over your limit for one payment and needs your PIN, so nothing moved. You can move it yourself.`,
  day: a => `This move (${money(a[0])} with fees) is more than what is left of your daily limit, so nothing moved.`,
  fail: () => "The move didn't go through, so the sats stayed where they were.",
  inflight: () => 'The move is still in flight. It will finish by itself.',
  error: () => 'Something went wrong, so nothing moved. NUTCADE tries again when sats arrive or when you open it.',
  myrefused: () => 'Your mint turned the request down, so nothing moved. NUTCADE tries again when sats arrive or when you open it.',
  refused: () => 'Turned the request down, so its sats stay there for now.',
  dust: () => 'After the fees, less than the smallest payment allowed would be left, so nothing moved.',
  quote: () => "The mints' quotes didn't settle on an amount, so nothing moved.",
  sync: () => 'Auto-move waits while wallet sync is on: two devices could move the same sats back and forth.',
  backup: () => 'Auto-move waits until you have written down your 12 words.',
  unit: () => 'Skipped: auto-move moves SAT only.'
};
const amLine = (k, n, a) => ({ k, n: n || '', a: (a || []).map(x => Math.max(0, Math.round(num(x)))) });
function amFlush(why) {
  am.at = Date.now();
  const GOOD = ['moved', 'waiting', 'inflight'];   // (a payment still in flight has left: it finishes by itself)
  const bad = am.lines.filter(l => !GOOD.includes(l.k) && !['none', 'unit'].includes(l.k)), key = bad.map(l => l.k + l.n).join('|');
  const moved = am.lines.filter(l => GOOD.includes(l.k)).reduce((t, l) => t + (l.a[0] || 0), 0), going = am.lines.some(l => l.k === 'waiting' || l.k === 'inflight');
  if (why !== 'test') {
    if (moved > 0) toast(going ? `${arrMoney(moved)} on its way to your mint.` : `Moved ${arrMoney(moved)} to your mint`, 'lime');   // (Hide amounts: •••)
    else if (bad.length && key !== am.lastKey) toast('Auto-move: nothing moved. See Settings, Auto-move.', 'gold');   // (once per new reason)
  }
  am.lastKey = key;
  if (tab === 'settings') amRefresh();
}
// a background redraw, only when it can't get in the way: no sheet open, not in the arcade, nothing being typed
function amRefresh() {
  const f = document.activeElement;
  if ($('#layer .sheet') || tab === 'arcade' || (f && /^(INPUT|SELECT|TEXTAREA)$/.test(f.tagName))) return;
  refresh();
}
// can this tab and wallet run at all? (never the duress PIN's wallet, a locked or paused tab)
const amCan = () => amOn() && !amDecoy() && !tabLocked && !writeGuard.paused && !(vault.on && !vault.open);
// why it waits although it is on: the 12 words not written down yet, or wallet sync on (two devices with sync and
// different "my mints" would move the same sats back and forth at every start, paying fees each time)
const amWait = () => !(S.seed && S.seed.backedUp) ? 'backup' : S.prefs.sync === true ? 'sync' : null;
/* money arrived: one run a moment later (a receive in parts, or two at once, makes one run). Only a new arrival: a line
   seen for the first time (in this tab) and made in the last 10 minutes, as for the arrival notices; a later change to
   an old line (its note edited, say) starts nothing. */
function amArrived(t) {
  if (!amCan() || amWait() || !t || !isSatAcct(t.mint)) return;
  if (t.id) { if (am.seen.has(t.id)) return; am.seen.add(t.id); if (am.seen.size > 2000) am.seen.delete(am.seen.values().next().value); }
  if (!(Date.now() - num(t.ts) <= 10 * 60e3)) return;
  clearTimeout(am.t); am.t = setTimeout(() => { am.t = 0; amRun('arrival').catch(() => {}); }, 1500);
}
function amRun(why) {
  if (!amCan()) return Promise.resolve(null);
  const w = amWait();
  if (w) { if (why === 'start' || why === 'arrival') return Promise.resolve(null); am.lines = [amLine(w)]; amFlush(why); return Promise.resolve(am.lines); }
  if (am.busy) { am.again = true; return am.busy; }
  const me = am.busy = (async () => {
    try { await amBody(why); } catch (e) { am.lines = [amLine('fail')]; }
    amFlush(why);
    return am.lines;
  })().finally(() => {
    if (am.busy === me) am.busy = null;
    if (am.again) { am.again = false; amRun(why).catch(() => {}); }   // (once more, for what arrived during this run)
  });
  return me;
}
async function amBody(why) {
  am.lines = [];
  const my = amMine();
  if (!my) { am.lines.push(amLine('unset')); return; }
  if (!amFit(my)) { am.lines.push(amLine('mybad')); return; }
  for (const m of S.mints) if (!isSatAcct(m.url) && balanceOf(m.url) > 0) am.lines.push(amLine('unit', acctName(m)));   // (never moved, never added in)
  const min = amMin();
  const srcs = satMints().filter(m => m.url !== my.url && !isBlocked(m.url) && balanceOf(m.url) >= min);
  if (!srcs.length) { am.lines.push(amLine('none', '', [min])); return; }
  const mi = methodInfo(my, 'mint', 'bolt11') || {};
  for (const src of srcs) {
    if (!amCan() || amWait() || amMine() !== my) return;   // (turned off, locked, sync turned on or my mint changed meanwhile)
    if (!supports(src, 'melt', 'bolt11')) { am.lines.push(amLine('noln', src.name)); continue; }
    const r = await amOne(src, my, mi).catch(e => e);
    if (r && r.stop) { am.lines.push(r.line); return; }   // my mint: nothing more this run
    am.lines.push(r && r.line ? r.line : amLine('fail', src.name));
  }
}
// one source mint: the most that fits, checked, then the one move between mints. Returns { line, stop? }.
async function amOne(src, my, mi) {
  const so = methodInfo(src, 'melt', 'bolt11') || {}, quotes = new Map();
  const maxes = [num(mi.max), num(so.max)].filter(x => x > 0), lim = { min: Math.max(1, num(mi.min) || 0, num(so.min) || 0), max: maxes.length ? Math.min(...maxes) : 0 };
  const mine = e => e && e.amSide === 'to', theirs = e => e && e.amSide === 'from';
  const why = e => amAuth(e) ? (mine(e) ? { stop: true, line: amLine('mylogin') } : { line: amLine('login', src.name) })
    : mine(e) ? { stop: true, line: amLine(amNet(e) ? 'mydown' : 'myrefused') } : theirs(e) ? { line: amLine(amNet(e) ? 'down' : 'refused', src.name) } : null;
  let best;
  try {
    await amSide('from', getWallet(src.url));
    best = await allFit(src.url, async a => { const mv = await moveQuotes(src.url, my.url, a, amSide); quotes.set(a, mv); return mv.mq; }, mq => mq.fee_reserve == null ? null : num(mq.fee_reserve), lim);
  } catch (e) {   // (Send all's own refusals: the fees take it all, or less than the smallest payment is left, or the quotes kept moving)
    const k = e && e.allKind;   // (any other error: the plain line, never a misleading one)
    return why(e) || { line: k === 'fee' ? amLine('fee', src.name, [e.fees, e.bal]) : amLine(k === 'dust' ? 'dust' : k === 'quote' ? 'quote' : 'error', src.name) };
  }
  const amount = best.amount, most = num(best.cost.total), fee = most - amount;
  if (!(Number.isSafeInteger(amount) && amount > 0 && Number.isSafeInteger(most) && most >= amount)) return { line: amLine('quote', src.name) };
  if (!(fee * 100 <= amount * AM_FEE_PCT)) return { line: amLine('fee', src.name, [fee, amount]) };   // (fail-closed: anything but a clear yes refuses)
  // an ordinary payment: the spending limit, as limitGate will check it, and never with a PIN entered for something else
  if (limitsOn()) {
    if (S.limits.per > 0 && !(most <= S.limits.per)) return { line: amLine('per', src.name, [most]) };
    if (S.limits.day > 0 && !(limitUsed() + most <= S.limits.day)) return { line: amLine('day', src.name, [most]) };
  }
  const mv = quotes.get(amount); if (!mv) return { line: amLine('fail', src.name) };
  // the payment's own line, once it is on record: what it says decides "in flight" from "didn't go through"
  const outTx = () => S.txs.find(t => t.type === 'out' && t.quote === mv.mq.quote && t.mint === src.url);
  const flying = () => { const t = outTx(); return !!t && (t.status === 'pending' || S.pending.some(p => p.txId === t.id)); };
  let r;
  try { r = await doMove(mv, { auto: true }); }
  catch (e) {
    amRefresh();
    if (flying()) return { line: amLine('inflight', src.name, [amount]) };   // (its answer was lost and the mint says it is still pending: the journal finishes it)
    if (e && e.limit) return { line: amLine(e.limit.kind === 'per' ? 'per' : 'day', src.name, [e.limit.spend]) };
    return (outTx() ? null : why(e)) || { line: amLine('fail', src.name) };
  }
  amRefresh();
  if (!r || !r.ok) return flying() ? { line: amLine('inflight', src.name, [amount]) } : { line: amLine('fail', src.name) };
  return { line: amLine(r.waiting ? 'waiting' : 'moved', src.name, [amount]) };
}
function amSettingsHTML() {
  const on = amOn(), my = amMine(), fit = satMints().filter(amFit);
  return `<div class="panel" id="set-automove"><span class="h2">Auto-move</span>
    ${toggle('amOn', 'Move what I receive into my mint', 'When sats arrive at another of your mints, NUTCADE moves them to the mint you pick here, over Lightning, while it is open. It also catches up when you open it. Never while closed. Off by default.')}
    ${on ? `<div class="field"><label for="p_amMint">My mint</label><select id="p_amMint" class="inp"><option value="" ${my ? '' : 'selected'} data-noi18n>${esc(tr('Pick a mint'))}</option>${fit.map(m => `<option value="${esc(m.url)}" ${my && my.url === m.url ? 'selected' : ''} data-noi18n>${esc(m.name)}</option>`).join('')}</select></div>
    <div class="field"><label for="p_amMin">Don't move below (SAT)</label><input id="p_amMin" class="inp amount" inputmode="numeric" autocomplete="off" value="${amMin()}"></div>
    <div class="th">A move happens only when another mint holds at least this much, and only when its fees are 2% of the amount or less. Moves count toward your spending limit like any payment; one that would need your PIN waits for you. USD, EUR and CHF are never moved.</div>
    ${amWait() ? `<div class="tiny muted" data-am="${amWait()}">${esc(AM_TXT[amWait()]())}</div>` : ''}
    ${am.at ? `<div class="am-lines">${am.lines.map(l => `<div class="tiny ${['moved', 'waiting'].includes(l.k) ? '' : 'muted'}" data-am="${esc(l.k)}">${l.n ? `<b data-noi18n>${esc(l.n)}</b>: ` : ''}<span>${esc(AM_TXT[l.k] ? AM_TXT[l.k](l.a) : '')}</span></div>`).join('')}</div>` : my ? '' : `<div class="tiny muted" data-am="unset">${esc(AM_TXT.unset())}</div>`}` : ''}
  </div>`;
}
// Settings: my mint picked, the threshold typed (a whole number of SAT, 1 or more; anything else is refused and the old one kept)
function amSetMint(v) {
  const m = S.mints.find(x => x.url === v);
  S.prefs.amMint = m && amFit(m) ? m.url : ''; am.lines = []; am.at = 0; am.lastKey = ''; save(); sfx('blip'); refresh();   // (nothing moves now: the next arrival or start does it)
}
function amSetMin(v) {
  let n = null; try { n = parseSat(v); } catch (e) {}
  if (!(Number.isSafeInteger(n) && n >= 1 && n <= AM_MIN_MAX)) { toast('Type a whole number of SAT, 1 or more.', 'red'); refresh(); return; }
  S.prefs.amMin = n; save(); sfx('blip'); refresh();
}
function amToggled() { am.lines = []; am.at = 0; am.lastKey = ''; }
window.NutAutoMove = { run: why => amRun(why || 'test'), arrived: t => amArrived(t), last: () => am.lines.map(l => Object.assign({}, l)), at: () => am.at, busy: () => !!am.busy, fit: () => satMints().filter(amFit).map(m => m.url), min: () => amMin(), txt: (k, a) => AM_TXT[k](a || []), pct: AM_FEE_PCT };
