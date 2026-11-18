/* NUTCADE Daily Challenge: one cabinet a day, the same seeded level for everyone, no server.

   HOW IT WORKS
   - The day is the UTC date, "2026-11-18". The seed is FNV-1a (32 bit) of the UTF-8 text "nutcade-daily-2026-11-18".
     The engine in games.js feeds that seed to seeded() and RNG, exactly as it does for a friend's challenge.
   - Today's cabinet is picked from the date alone, by highest random weight: every cabinet that joins the daily gets a
     weight FNV-1a("nutcade-daily-pick-<date>-<id>"), and the biggest weight wins. It does not depend on the order of
     the GAMES list, and a new cabinet only changes the days it wins itself (about 1 in n), so phones on slightly
     different versions mostly agree.
   - The first run of the day is the official score. The day it counts for is the day the run STARTED, so playing past
     midnight UTC still counts for the day you began. Later runs are for fun. A run you quit halfway keeps the score
     it had (a run quit at 0 points doesn't use up the day).
   - History, the streak and the clock check live on this device only (storage keys scores:daily*, which are
     device-level like the arcade tables). Nothing is sent anywhere. The only network use is the Post button in the
     share sheet, which publishes one note you have just previewed.

   THE HOOK FOR NEW CABINETS (Corner Pocket and Neon Road joined this way; Nut Poker is truly random, so it does not)
   A cabinet joins the daily with one line in its object:   daily: true,
   It promises that all of its GAMEPLAY randomness comes from the engine's RNG (rnd(), ri(), RNG()), never from
   Math.random() (that is for sparks and stars only), so the same seed gives the same level. The seed also arrives as
   a second argument, init(G, seed), for a cabinet that wants its own generator, for example to shuffle a deck:
   `const deal = seeded(seed)`. Nothing else is needed: the daily panel, the title screen, the share note and the
   history pick the cabinet up by themselves. A cabinet without the flag is simply never chosen, and neither is one marked `noChallenge` (its play can't
   be replayed, like Nut Poker's truly random deck), flag or not. */
(() => {
'use strict';
const N = () => window.Nutcade;
const store = window.NutStore || { get: (k, d) => d, set() {} };
const KEY = 'scores:daily', RUNKEY = 'scores:daily-run', CLOCKKEY = 'scores:daily-clock';   // "scores:" keeps them on the device, outside any wallet
const SITE = 'https://random21m.github.io/nutcade/';
const MIN_DAY = '2025-01-01';   // a device date before this is a clock that lost its time (battery, reset)
const KEEP = 366;
const DAY = 86400000;

/* ---------- the clock (a test can replace it) ---------- */
let clock = () => Date.now();
let ver = 0;   // changes whenever anything cached below could be stale
const now = () => { const t = +clock(); return Number.isFinite(t) ? t : 0; };
const dateOf = ms => { try { return new Date(ms).toISOString().slice(0, 10); } catch (e) { return '1970-01-01'; } };
const dayMs = date => Date.parse(date + 'T00:00:00Z');
const prevDay = date => dateOf(dayMs(date) - DAY);

/* ---------- hashing: FNV-1a over the UTF-8 bytes (the text is plain ASCII) ---------- */
function fnv(str) { let h = 0x811c9dc5; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i) & 255; h = Math.imul(h, 0x01000193); } return h >>> 0; }
const seedOf = date => fnv('nutcade-daily-' + date);
function pick(date, ids) {
  let best = null, bw = -1;
  for (const id of ids) { const w = fnv('nutcade-daily-pick-' + date + '-' + id); if (w > bw || (w === bw && id < best)) { bw = w; best = id; } }
  return best;
}

/* ---------- saved data ---------- */
const get = (k, d) => { try { return store.get(k, d); } catch (e) { return d; } };
const put = (k, v) => { try { store.set(k, v); } catch (e) {} };
const cleanDays = a => (Array.isArray(a) ? a : []).filter(x => x && /^\d{4}-\d\d-\d\d$/.test(x.d) && Number.isFinite(x.o) && typeof x.g === 'string').sort((a, b) => a.d < b.d ? -1 : 1);
const days = () => cleanDays(get(KEY, []));
const saveDays = a => { put(KEY, a.slice(-KEEP)); ver++; };
const entryOn = (date, a) => (a || days()).find(x => x.d === date) || null;

/* The streak: days played in a row, ending today (or yesterday, while today isn't played yet). */
function streakOf(a, today) {
  const have = new Set(a.map(x => x.d)); let d = have.has(today) ? today : prevDay(today), n = 0;
  while (have.has(d) && n < 4000) { n++; d = prevDay(d); }
  return n;
}
function bestStreak(a) {
  let best = 0, run = 0, last = null;
  for (const x of a) { run = last && dayMs(x.d) - dayMs(last) === DAY ? run + 1 : 1; last = x.d; if (run > best) best = run; }
  return best;
}

/* ---------- the device clock ----------
   There is no server to ask, so the one thing checked is that the date never goes BACK: the latest day this device
   has seen is remembered. A clock set earlier than that (or to a date before this app existed) can still play
   the day's level, but those runs are not official and don't touch the streak, until the clock catches up or the
   player says it is right ("My clock is right"). A clock set forward simply moves to that day's challenge. */
function clockOK(date) {
  if (date < MIN_DAY) return false;
  const seen = (get(CLOCKKEY, {}) || {}).day;
  if (typeof seen === 'string' && date < seen) return false;
  if (typeof seen !== 'string' || date > seen) put(CLOCKKEY, { day: date });
  return true;
}
function trustClock() { put(CLOCKKEY, { day: dateOf(now()) }); ver++; }

/* ---------- today ---------- */
let games = [], opener = null;
const eligible = () => games.filter(g => g.daily === true && !g.noChallenge);   // a cabinet that is random by design (noChallenge, like Nut Poker) can never be the daily, flagged or not
const gameOf = id => games.find(g => g.id === id) || null;
let live = null;   // the run being played right now: { date, id, seed, official, s }
let cache = null;
function recover() {   // a run that was cut off (the app was closed mid-game) keeps the score it had reached
  const r = get(RUNKEY, null);
  if (r && !live && r.official && typeof r.date === 'string') { put(RUNKEY, null); if (r.s > 0) record(r.date, r.id, r.s); }
  else if (r) put(RUNKEY, null);
}
let recovered = false;
function info() {
  const t = now(), sec = Math.floor(t / 1000);
  if (cache && cache.sec === sec && cache.ver === ver) return cache;
  if (!recovered) { recovered = true; recover(); }
  const date = dateOf(t), a = days(), ok = clockOK(date);
  const ids = eligible().map(g => g.id), id = pick(date, ids);
  const entry = entryOn(date, a);
  const busy = !!(live && live.date === date && live.official);
  const next = dayMs(date) + DAY;
  cache = { sec, ver, now: t, date, seed: seedOf(date), id, game: gameOf(id), entry, ok, official: ok && !entry && !busy && !!id,
    streak: streakOf(a, date), best: bestStreak(a), nextMs: next, left: next - t, count: a.length };
  return cache;
}
function record(date, id, score) {   // write the official score of a day
  const a = days(); if (entryOn(date, a)) return;
  a.push({ d: date, g: id, o: Math.floor(score), b: Math.floor(score), n: 1 }); saveDays(a);
}

/* A run starts: which day, which seed, and whether it is the official one. */
function begin(openedId) {
  ver++; const i = info();
  const run = { date: i.date, id: i.id, seed: i.seed, official: i.official, why: i.official ? null : (!i.ok ? 'clock' : 'done'), s: 0, moved: !!openedId && openedId !== i.id };
  if (run.moved) return run;   // midnight passed while the title screen was open: the caller opens today's cabinet instead
  live = run; if (run.official) put(RUNKEY, run);
  return run;
}
function progress(run, score) { if (run && run === live && run.official && score !== run.s) { run.s = Math.floor(score); put(RUNKEY, run); } }
/* A run ends (game over, or the player left). Returns what to show. */
function finish(run, score, abandoned) {
  if (!run || run.done) return null;
  run.done = true; if (live === run) live = null; ver++;
  score = Math.max(0, Math.floor(score));
  const out = { date: run.date, id: run.id, score, official: run.official, why: run.why, abandoned: !!abandoned };
  if (run.official) {
    put(RUNKEY, null);
    if (abandoned && score <= 0) out.official = false, out.why = 'quit';   // quit at 0 points: the day is not used up
    else record(run.date, run.id, score);
  } else {
    const a = days(), e = entryOn(run.date, a);
    if (e) { e.b = Math.max(e.b, score); e.n++; saveDays(a); }
  }
  const a = days(), e = entryOn(run.date, a), today = info();
  out.officialScore = e ? e.o : null; out.streak = streakOf(a, today.date);
  return out;
}
window.addEventListener('pagehide', () => { if (live && live.official && window.Arcade) { try { put(RUNKEY, live); } catch (e) {} } });

/* ---------- words and numbers, in the app's language ---------- */
const loc = () => { try { return N().locale(); } catch (e) { return 'en-US'; } };
const tr = s => (N() && N().tr ? N().tr(s) : s);
const fill = (s, o) => s.replace(/\{(\w+)\}/g, (m, k) => k in o ? String(o[k]) : m);
const t = (s, o) => fill(tr(s), o || {});
const num = n => Math.round(n).toLocaleString(loc(), { useGrouping: 'always' });
const pad6 = n => String(Math.max(0, Math.floor(n))).padStart(6, '0');
function dateLabel(date, year) { try { return new Date(dayMs(date)).toLocaleDateString(loc(), Object.assign({ month: 'short', day: 'numeric', timeZone: 'UTC' }, year ? { year: 'numeric' } : {})); } catch (e) { return date; } }
function localTime(ms) { try { return new Date(ms).toLocaleTimeString(loc(), { hour: 'numeric', minute: '2-digit' }); } catch (e) { return ''; } }
function until(ms) {
  const tot = Math.max(1, Math.ceil(ms / 60000)), h = Math.floor(tot / 60), m = tot % 60;
  return h ? t('{h}h {m}m', { h: num(h), m: num(m) }) : t('{m}m', { m: num(m) });
}
const title = name => String(name || '').toLowerCase().replace(/(^|\s)\S/g, c => c.toUpperCase());
const nameOf = id => { const g = gameOf(id); return g ? g.name : String(id).toUpperCase(); };
const esc = s => N().esc(s);
const streakText = n => n <= 0 ? t('No streak yet') : n === 1 ? t('Streak: {n} day', { n: num(n) }) : t('Streak: {n} days', { n: num(n) });

/* The note people can post: short, in the app's language, with the date and score written the language's way. */
function noteText(entry) {
  return t('NUTCADE Daily Challenge {d}: {g} {s} 🕹️ #nutcade', { d: dateLabel(entry.d), g: title(nameOf(entry.g)), s: num(entry.o) });
}
const noteFull = entry => noteText(entry) + '\n' + SITE;

/* ---------- styles for the panel ---------- */
const CSS = `.daily{border-color:var(--gold);margin-bottom:14px}
.daily .dtop{display:grid;grid-template-columns:minmax(0,42%) minmax(0,1fr);gap:12px;align-items:start}
.daily .dthumb{display:block;padding:0;border:2px solid var(--grid);border-radius:var(--r);background:#05030c;overflow:hidden}
.daily .dthumb canvas{width:100%;aspect-ratio:4/3;display:block;image-rendering:pixelated}
.daily .dthumb:active{border-color:var(--pink)}
.daily .dname{font-family:var(--f-display);font-size:11px;line-height:1.5;letter-spacing:1px;color:var(--gold);overflow-wrap:anywhere}
.daily .dscore{font-family:var(--f-display);font-size:13px;color:var(--lime);line-height:1.5}
.daily .dscore.none{font-size:9px;color:var(--pink)}
.daily .dcol{display:grid;gap:6px;min-width:0}
.daily .dlab{font-family:var(--f-display);font-size:8px;letter-spacing:1px;color:var(--dim);line-height:1.5;overflow-wrap:anywhere}
.daily .dline{font-size:18px;color:var(--ink);overflow-wrap:anywhere}
.daily .dbtns{display:flex;flex-wrap:wrap;gap:8px}
.daily .dbtns .btn{flex:1 1 120px}
.daily .dbtns .btn.solid{flex-basis:100%}
.code.dy-note{white-space:pre-wrap;word-break:normal;overflow-wrap:break-word;color:var(--ink)}   /* wrap at spaces; a word (the link) is cut only if it is wider than the whole line. (.code alone says break-all, and this sheet loads first, so it needs the extra class to win) */
.dy-hist{display:grid;gap:4px;font-size:18px}
.dy-hist div{display:grid;grid-template-columns:minmax(0,5.5em) minmax(0,1fr) auto;gap:8px;align-items:center;min-height:30px;border-bottom:1px solid var(--grid)}
.dy-hist div span:last-child{font-family:var(--f-display);font-size:10px;color:var(--gold)}`;
function addCSS() { if (document.getElementById('dailyCss')) return; const s = document.createElement('style'); s.id = 'dailyCss'; s.textContent = CSS; document.head.appendChild(s); }

/* ---------- the lobby entry ---------- */
let tickT = 0;
function html() {
  addCSS();
  const i = info(); if (!i.game) return '';
  const e = i.entry, hasBest = e && e.b > e.o;
  const cabs = i.game;
  return `<div class="panel daily" data-daily="${esc(i.date)}">
    <div class="row between" style="gap:8px;flex-wrap:wrap"><span class="h2" style="color:var(--gold)">DAILY CHALLENGE</span><span class="tiny muted" data-noi18n>${esc(dateLabel(i.date, true))} · UTC</span></div>
    <div class="dtop">
      <button class="dthumb" data-daily-play aria-label="${esc(t('Play the daily challenge: {g}', { g: cabs.name }))}"><canvas width="112" height="84" data-thumb="${esc(cabs.id)}"></canvas></button>
      <div class="dcol">
        <div class="dname" data-noi18n>${esc(cabs.name)}</div>
        <div class="dlab">${e ? "TODAY'S SCORE" : 'NOT PLAYED YET'}</div>
        ${e ? `<div class="dscore" data-noi18n>${esc(num(e.o))}</div>` : '<div class="dline" style="color:var(--dim)">First run of the day counts. Replay for fun after that.</div>'}
        ${hasBest ? `<div class="dline" data-noi18n>${esc(t('Best today for fun: {s}', { s: num(e.b) }))}</div>` : ''}
        <div class="dline" data-noi18n>${esc(streakText(i.streak))}</div>
      </div>
    </div>
    ${i.ok ? '' : '<div class="notice" data-daily-clock>Your device clock looks wrong. You can still play for fun, but runs don\'t count as official or toward your streak until it\'s fixed.<div class="row" style="margin-top:8px"><button class="btn sm" data-daily-trust>My clock is right</button></div></div>'}
    <div class="dline" data-noi18n data-daily-left>${esc(t('Next challenge in {a}', { a: until(i.left) }))}</div>
    <div class="tiny muted" data-noi18n data-daily-reset>${esc(t('New one at {t} your time (midnight UTC)', { t: localTime(i.nextMs) }))}</div>
    <div class="dbtns"><button class="btn solid gold" data-daily-play>${e ? 'PLAY FOR FUN' : 'PLAY DAILY'}</button><button class="btn" data-daily-share ${e ? '' : 'disabled'}>Share my score</button><button class="btn" data-daily-hist>History</button></div>
  </div>`;
}
function bind(root) {
  clearInterval(tickT); tickT = 0;
  const p = root && root.querySelector('[data-daily]'); if (!p) return;
  const i0 = info();
  p.querySelectorAll('[data-daily-play]').forEach(b => b.onclick = () => { if (N()) N().sfx('select'); if (opener) opener(i0.id, { daily: true }); });
  const sb = p.querySelector('[data-daily-share]'); if (sb) sb.onclick = () => share();
  const hb = p.querySelector('[data-daily-hist]'); if (hb) hb.onclick = () => openHistory();
  const tb = p.querySelector('[data-daily-trust]'); if (tb) tb.onclick = () => { trustClock(); if (N()) N().refresh(); };
  tickT = setInterval(() => {
    if (!p.isConnected) { clearInterval(tickT); tickT = 0; return; }
    const i = info();
    if (i.date !== p.dataset.daily) { if (!(window.Arcade && window.Arcade.playing()) && !document.querySelector('#layer .sheet') && N()) N().refresh(); return; }
    const l = p.querySelector('[data-daily-left]'); if (l) l.textContent = t('Next challenge in {a}', { a: until(i.left) });
  }, 15000);
}

/* ---------- share ---------- */
function share(date) {
  const n = N(); const nn = window.NutDailyNostr;
  const e = entryOn(date || info().date); if (!e || !n) return;
  const can = !!(nn && nn.can()), text = noteFull(e), short = noteText(e);
  const relays = can ? nn.relayCount() : 0;
  const rel = relays === 1 ? t('{n} relay', { n: num(1) }) : t('{n} relays', { n: num(relays) });
  const body = n.openSheet('Share my score', `
    <div class="chal-card"><span class="label">DAILY CHALLENGE</span><b data-noi18n>${esc(num(e.o))}</b><span data-noi18n>${esc(nameOf(e.g))} · ${esc(dateLabel(e.d))}</span></div>
    <div class="field"><label>Preview of your note</label><div class="code dy-note" data-noi18n id="dyText">${esc(text)}</div></div>
    ${can ? `<p class="tiny muted" style="margin:0" data-noi18n>${esc(t('Posts a public note on Nostr, signed with your NUTCADE key ({k}), to your {r}. Nothing is sent until you tap Post.', { k: shortNpub(nn.npub()), r: rel }))}</p>`
      : '<p class="tiny muted" style="margin:0">There is no Nostr key on this device yet, so posting is off. Copy the text and post it anywhere you like. Nothing is sent from here.</p>'}
    <div id="dyMsg"></div>
    ${can ? '<button class="btn solid gold block" id="dyPost">Post</button>' : ''}
    <button class="btn block ${can ? '' : 'solid gold'}" data-act="copy" data-text="${esc(text)}">Copy text</button>
    <button class="btn block" data-act="close">Close</button>`);
  const post = body.querySelector('#dyPost'); if (!post) return;
  let ev = null, sending = false;
  const msg = (cls, key, o) => { const m = document.getElementById('dyMsg'); if (m) m.innerHTML = `<div class="notice ${cls}" data-noi18n role="status">${esc(t(key, o))}</div>`; };
  post.onclick = async () => {
    if (sending) return; sending = true; post.disabled = true; post.textContent = tr('POSTING…');
    let ok = 0;
    try { if (!ev) ev = nn.sign(text, [['t', 'nutcade']]); ok = await nn.publish(ev); } catch (x) { ok = 0; }
    sending = false;
    if (!post.isConnected) return;
    if (ok > 0) { post.textContent = tr('POSTED'); msg('cyan', ok === 1 ? 'Posted to {n} relay.' : 'Posted to {n} relays.', { n: num(ok) }); n.sfx('coin'); }
    else { post.disabled = false; post.textContent = tr('Try again'); msg('red', "Couldn't reach any relay. You may be offline. Nothing was lost: your score is saved here. Try again, or copy the text."); n.sfx('err'); }
  };
  return short;
}
const shortNpub = s => s ? s.slice(0, 10) + '…' + s.slice(-4) : '';

/* ---------- history ---------- */
function openHistory() {
  const n = N(); if (!n) return;
  const a = days().slice().reverse().slice(0, 30), i = info();
  n.openSheet('Daily history', `
    <div class="notice cyan" data-noi18n>${esc(streakText(i.streak))} · ${esc(t('Best streak: {n}', { n: num(i.best) }))}</div>
    ${a.length ? `<div class="dy-hist">${a.map(x => `<div><span data-noi18n>${esc(dateLabel(x.d))}</span><span data-noi18n>${esc(nameOf(x.g))}</span><span data-noi18n>${esc(num(x.o))}</span></div>`).join('')}</div>` : '<div class="empty-state"><b>NO DAILY RUNS YET</b>Your first run of each day is your official score.</div>'}
    <button class="btn block" data-act="close">Done</button>`);
}

/* ---------- title-screen lines, drawn by the engine (computed once a second) ---------- */
function titleLines() {
  const i = info(); if (live) return null;
  return { date: dateLabel(i.date).toUpperCase(), status: i.official ? 'FIRST RUN COUNTS' : !i.ok ? 'CLOCK WRONG: NOT COUNTED' : 'PRACTICE RUN', today: i.entry ? i.entry.o : null, best: i.entry ? i.entry.b : 0, ok: i.ok };
}

window.Daily = {
  html, bind, share, openHistory, begin, progress, finish, info, titleLines, trustClock, seedOf, pick, fnv, dateOf, noteText, noteFull, streakText, dateLabel, localTime, until, days, streakOf, eligible,
  attach(o) { games = o.games; opener = o.open; ver++; },
  setClock(fn) { clock = fn || (() => Date.now()); ver++; cache = null; },
  t, num, pad6, entry: date => entryOn(date)
};
})();
