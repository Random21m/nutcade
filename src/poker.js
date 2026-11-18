/* NUT POKER: five-card draw, jacks or better, for FREE CREDITS ONLY.
   Credits are never bought with sats, never cashed out and never linked to the wallet; this file touches no money code.
   It is a cabinet for the arcade engine in games.js: the engine calls the factory at the bottom with its drawing helpers.
   The deck is shuffled with crypto.getRandomValues (not the engine's seeded game RNG), and the draw comes from the same deck. */
(function () {
'use strict';
const root = typeof window !== 'undefined' ? window : globalThis;

/* ---------- the rules: pure functions, unit-tested (tests/game_poker_unit.js) ---------- */
const HANDS = [   // the 9/6 jacks-or-better pay table: k key, n name (translated on screen), m pays per credit bet
  { k: 'royal', n: 'ROYAL FLUSH', m: 250 }, { k: 'sflush', n: 'STRAIGHT FLUSH', m: 50 }, { k: 'quads', n: 'FOUR OF A KIND', m: 25 },
  { k: 'full', n: 'FULL HOUSE', m: 9 }, { k: 'flush', n: 'FLUSH', m: 6 }, { k: 'straight', n: 'STRAIGHT', m: 4 },
  { k: 'trips', n: 'THREE OF A KIND', m: 3 }, { k: 'twopair', n: 'TWO PAIR', m: 2 }, { k: 'jacks', n: 'JACKS OR BETTER', m: 1 }
];
const HIDX = {}; HANDS.forEach((h, i) => { HIDX[h.k] = i; });
const MAXBET = 5, START = 100, ROYAL_MAX = 4000;
// cards are 0..51: rank = c % 13 + 2 (2..14, ace high), suit = floor(c / 13) (0 spades, 1 hearts, 2 diamonds, 3 clubs)
const rankOf = c => c % 13 + 2, suitOf = c => (c / 13) | 0;

function evaluate(cards) {   // -> a hand key from HANDS, or null for nothing that pays
  if (!Array.isArray(cards) || cards.length !== 5) throw new RangeError('a hand is five cards');
  for (let i = 0; i < 5; i++) { if (!Number.isInteger(cards[i]) || cards[i] < 0 || cards[i] > 51) throw new RangeError('bad card'); for (let j = 0; j < i; j++) if (cards[j] === cards[i]) throw new RangeError('duplicate card'); }
  const cnt = new Array(15).fill(0); let flush = true;
  for (const c of cards) { cnt[rankOf(c)]++; if (suitOf(c) !== suitOf(cards[0])) flush = false; }
  let distinct = 0, lo = 99, hi = 0, pairs = 0, trips = false, quads = false, pairRank = 0;
  for (let r = 2; r <= 14; r++) {
    if (!cnt[r]) continue;
    distinct++; if (r < lo) lo = r; if (r > hi) hi = r;
    if (cnt[r] === 2) { pairs++; pairRank = r; } else if (cnt[r] === 3) trips = true; else if (cnt[r] === 4) quads = true;
  }
  const wheel = distinct === 5 && cnt[14] && cnt[2] && cnt[3] && cnt[4] && cnt[5];   // A-2-3-4-5: the ace plays low
  const straight = distinct === 5 && (hi - lo === 4 || wheel);
  if (straight && flush) return lo === 10 ? 'royal' : 'sflush';   // 10-J-Q-K-A is the only ace-high straight flush; the wheel is a plain straight flush
  if (quads) return 'quads';
  if (trips && pairs === 1) return 'full';
  if (flush) return 'flush';
  if (straight) return 'straight';
  if (trips) return 'trips';
  if (pairs === 2) return 'twopair';
  if (pairs === 1 && pairRank >= 11) return 'jacks';   // jacks or better: a pair of 10s and below pays nothing
  return null;
}
function payout(key, bet) {
  if (!(key in HIDX) || !Number.isInteger(bet) || bet < 1 || bet > MAXBET) return 0;
  return key === 'royal' && bet === MAXBET ? ROYAL_MAX : HANDS[HIDX[key]].m * bet;   // the royal pays 4000, not 1250, at max bet
}
function secureInt(n) {   // uniform in 0..n-1 from crypto.getRandomValues; rejects the top sliver so there is no modulo bias
  const lim = 4294967296 - (4294967296 % n), b = new Uint32Array(1);
  do { globalThis.crypto.getRandomValues(b); } while (b[0] >= lim);
  return b[0] % n;
}
function newDeck(int = secureInt) {   // a fresh fair 52-card deck, Fisher-Yates
  const d = new Array(52); for (let i = 0; i < 52; i++) d[i] = i;
  for (let i = 51; i > 0; i--) { const j = int(i + 1), t = d[i]; d[i] = d[j]; d[j] = t; }
  return d;
}
const Poker = { HANDS, MAXBET, START, ROYAL_MAX, rankOf, suitOf, evaluate, payout, secureInt, newDeck, state: () => null };   // state() is the running game's state, for the tests
root.NutPoker = Poker;
if (typeof module !== 'undefined' && module.exports) module.exports = Poker;

/* ---------- the cabinet ---------- */
const SUIT = [   // 7x7 pixel suits
  ['...#...', '..###..', '.#####.', '#######', '#######', '...#...', '..###..'],
  ['.##.##.', '#######', '#######', '#######', '.#####.', '..###..', '...#...'],
  ['...#...', '..###..', '.#####.', '#######', '.#####.', '..###..', '...#...'],
  ['..###..', '..###..', '#.###.#', '#######', '#.###.#', '...#...', '..###..']
];
const DIG = ['111101101101111', '010110010010111', '111001111100111', '111001111001111', '101101111001001', '111100111001111', '111100111101111', '111001010010010', '111101111101111', '111101111001111'];   // 3x5 digits for the pay table
const RANKS = { 11: 'J', 12: 'Q', 13: 'K', 14: 'A' };
const COLR = [145, 163, 181, 199, 217];   // right edge of each bet column in the pay table
const CW = 38, CH = 50, CGAP = 5, CX0 = 7, CY = 130, CRAISE = 5, FL = 8;
const BTN = [{ id: 'one', x: 6 }, { id: 'max', x: 79 }, { id: 'go', x: 152 }], BY = 230, BW = 68, BH = 22;
const KEYACT = { Digit1: 'h0', Digit2: 'h1', Digit3: 'h2', Digit4: 'h3', Digit5: 'h4', Numpad1: 'h0', Numpad2: 'h1', Numpad3: 'h2', Numpad4: 'h3', Numpad5: 'h4', KeyD: 'go', Enter: 'go', NumpadEnter: 'go', KeyB: 'one', KeyM: 'max', KeyE: 'end' };
const NF = n => { const f = root.Nutcade && root.Nutcade.fmt; return (f ? f(n) : String(n)).replace(/[  ]/g, ' '); };

function make(E) {
  const { W, C, spr, text, T, A, store } = E;
  const FACE = '#f4efe0', INK = '#1a1250', REDC = '#d6203a';
  let live = null, sheets = null, backImg = null;
  const mk = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; };
  function digitSheets() {
    if (sheets) return sheets;
    sheets = [C.violet, C.ink, C.gold].map(col => { const c = mk(30, 5), x = c.getContext('2d'); x.fillStyle = col; DIG.forEach((g, d) => { for (let i = 0; i < 15; i++) if (g[i] === '1') x.fillRect(d * 3 + (i % 3), (i / 3) | 0, 1, 1); }); return c; });
    return sheets;
  }
  function digits(ctx, n, rx, y, which) { const s = String(n), sh = digitSheets()[which]; let x = rx - s.length * 4 + 1; for (let i = 0; i < s.length; i++, x += 4) ctx.drawImage(sh, (s.charCodeAt(i) - 48) * 3, 0, 3, 5, x, y, 3, 5); }
  function cardBack() {
    if (backImg) return backImg;
    const c = mk(CW, CH), x = c.getContext('2d'); x.fillStyle = '#120c2e'; x.fillRect(0, 0, CW, CH); x.fillStyle = '#2a1c7a'; x.fillRect(1, 1, CW - 2, CH - 2);
    x.fillStyle = C.cyan; x.fillRect(3, 3, CW - 6, 1); x.fillRect(3, CH - 4, CW - 6, 1); x.fillRect(3, 3, 1, CH - 6); x.fillRect(CW - 4, 3, 1, CH - 6);
    x.fillStyle = '#4a36b8'; for (let yy = 6; yy < CH - 6; yy += 4) for (let xx = 6 + ((yy >> 2) & 1) * 2; xx < CW - 6; xx += 4) x.fillRect(xx, yy, 2, 2);
    x.fillStyle = C.pink; x.fillRect(CW / 2 - 2, CH / 2 - 2, 4, 4); backImg = c; return c;
  }
  // a face-up card: rank and small suit top left, a big suit in the middle (scale 2), or one pixel suit on tiny cards
  function face(ctx, x, y, w, h, c, big) {
    const su = suitOf(c), col = su === 1 || su === 2 ? REDC : INK, r = rankOf(c);
    ctx.fillStyle = '#120c2e'; ctx.fillRect(x - 1, y - 1, w + 2, h + 2); ctx.fillStyle = FACE; ctx.fillRect(x, y, w, h);
    ctx.fillStyle = '#fff'; ctx.fillRect(x, y, w, 1); ctx.fillStyle = '#d9d2bd'; ctx.fillRect(x, y + h - 1, w, 1);
    text(ctx, RANKS[r] || String(r), x + 3, y + 3, col, 8);
    spr(ctx, SUIT[su], x + 3, y + (big ? 14 : 12), { '#': col }, 1);
    if (big) spr(ctx, SUIT[su], x + ((w - 14) >> 1) + 4, y + h - 22, { '#': col }, 2);
  }
  function drawCard(ctx, s, i, x, y) {
    const p = (s.t - s.fa[i]) / FL;
    if (p >= 1 && s.hand[i] >= 0) { if (s.held[i]) { ctx.fillStyle = C.cyan; ctx.fillRect(x - 3, y - 3, CW + 6, CH + 6); ctx.fillStyle = '#b8f6ff'; ctx.fillRect(x - 3, y - 3, CW + 6, 1); } face(ctx, x, y, CW, CH, s.hand[i], true); return; }
    let w = CW, up = false;
    if (p > 0 && s.hand[i] >= 0) { up = p >= 0.5; w = Math.max(2, Math.round(CW * Math.abs(1 - 2 * p))); }
    const ox = x + ((CW - w) >> 1);
    if (up) { face(ctx, ox, y, w, CH, s.hand[i], false); } else ctx.drawImage(cardBack(), 0, 0, CW, CH, ox, y, w, CH);
  }
  function fit(ctx, str, x, y, col, max) { ctx.font = '12px "Press Start 2P", monospace'; if (ctx.measureText(str).width <= max) text(ctx, str, x, y, col, 12, 'center'); else text(ctx, str, x, y + 2, col, 8, 'center'); }   // 12px if it fits, else 8px
  function button(ctx, b, label, on, hot, col) {
    const y = BY + (hot ? 1 : 0);
    ctx.fillStyle = on ? (hot ? '#fff' : col) : '#2a2350'; ctx.fillRect(b.x, y, BW, BH - (hot ? 1 : 0));
    if (on) { ctx.fillStyle = 'rgba(255,255,255,.35)'; ctx.fillRect(b.x, y, BW, 1); ctx.fillStyle = 'rgba(0,0,0,.35)'; ctx.fillRect(b.x, y + BH - 3, BW, 2); }
    text(ctx, label, b.x + BW / 2, y + 7, on ? '#120a22' : C.dim, 8, 'center');
  }
  const idle = s => s.phase === 'ready' || s.phase === 'result';
  const btnOn = (s, id) => id === 'go' ? s.phase !== 'deal' && s.phase !== 'draw' : idle(s);
  const inRect = (p, x, y, w, h) => p && p.x >= x && p.x < x + w && p.y >= y && p.y < y + h;

  function spark(s, n) {
    const cols = [C.gold, C.pink, C.cyan, C.lime, C.white];
    for (let k = 0; k < s.fx.length && n > 0; k++) { const f = s.fx[k]; if (f.life > 0) continue; n--; const a = Math.random() * 6.283, v = 0.6 + Math.random() * 2.2; f.x = 112 + (Math.random() - .5) * 90; f.y = 205; f.vx = Math.cos(a) * v; f.vy = Math.sin(a) * v - 1.2; f.life = 24 + Math.random() * 26 | 0; f.col = cols[(Math.random() * 5) | 0]; }
  }
  function sync(s, G) { if (s.credits > s.peak) s.peak = s.credits; if (s.peak > START && s.peak > G.score) G.addScore(s.peak - G.score); }   // the score is the most credits you have held
  function refill(s) { s.credits = START; s.refill = 150; s.refillAt = 0; s.bet = Math.min(s.bet, START); A().sfx('start'); }
  function deal(s) {
    if (s.credits < 1) refill(s);
    s.bet = Math.min(s.bet, s.credits); s.credits -= s.bet; s.refillAt = 0; s.refill = 0;
    s.deck = newDeck(); s.pos = 5; s.win = 0; s.shown = 0; s.key = null;
    for (let i = 0; i < 5; i++) { s.hand[i] = s.deck[i]; s.held[i] = 0; s.fa[i] = s.t + 2 + i * 5; }
    s.endAt = s.fa[4] + FL; s.phase = 'deal'; A().sfx('select');
  }
  function drawCards(s) {
    let k = 0;
    for (let i = 0; i < 5; i++) if (!s.held[i]) { s.hand[i] = s.deck[s.pos++]; s.fa[i] = s.t + 6 + k * 6; k++; }   // replacements come off the same deck
    s.endAt = (k ? s.t + 6 + (k - 1) * 6 : s.t) + FL; s.phase = 'draw'; A().sfx('select');
  }
  function resolve(s, G) {
    s.key = evaluate(s.hand); s.win = payout(s.key, s.bet); s.shown = 0; s.phase = 'result';
    if (s.win) {
      s.credits += s.win; const i = HIDX[s.key];
      A().sfx(i <= 5 ? 'power' : 'levelup'); if (i <= 1) A().sfx('boom'); else if (i > 5) A().sfx('coin');
      spark(s, Math.min(60, 8 + (s.win >> 2)));
    } else { A().sfx('wall'); if (s.credits < 1) s.refillAt = s.t + 70; }
    if (s.bet > s.credits) s.bet = Math.max(1, s.credits);
  }
  function act(s, G, a) {
    if (a === 'one') { if (!idle(s)) return; s.bet = s.bet >= MAXBET || s.bet >= s.credits ? 1 : s.bet + 1; A().sfx('blip'); }
    else if (a === 'max') { if (!idle(s)) return; s.bet = Math.min(MAXBET, Math.max(1, s.credits)); A().sfx('coin'); }
    else if (a === 'go') { if (s.phase === 'hold') drawCards(s); else if (idle(s)) deal(s); }
    else if (a === 'end') { if (idle(s)) { s.shown = s.win; sync(s, G); G.over(); } }   // ends the run: the most credits held is saved as the high score
    else if (a.length === 2 && a[0] === 'h') { if (s.phase !== 'hold') return; const i = +a[1]; s.held[i] ^= 1; A().sfx('blip'); }
  }

  return {
    id: 'poker', name: 'NUT POKER', year: '1988', blurb: 'Five-card draw. Hold, draw, beat the pay table. Free credits only.', track: 'title', noStick: true, noChallenge: true, noSats: true,
    help: 'Tap cards to HOLD · A deal / draw', keys: '1-5 hold · D or Enter deal / draw · B bet · M max · E end run',
    init() {
      const s = { t: 0, credits: START, bet: 1, peak: START, phase: 'ready', hand: [-1, -1, -1, -1, -1], held: [0, 0, 0, 0, 0], fa: [1e9, 1e9, 1e9, 1e9, 1e9], deck: [], pos: 5, key: null, win: 0, shown: 0, endAt: 0, refill: 0, refillAt: 0, q: [], fx: [] };
      for (let i = 0; i < 64; i++) s.fx.push({ x: 0, y: 0, vx: 0, vy: 0, life: 0, col: C.gold });
      live = s; Poker.state = () => live; return s;
    },
    onKey(code, s, mode, e) {   // the engine offers each key first: D and Enter deal here instead of steering or pausing
      const a = KEYACT[code]; if (!a || mode !== 'play' || !s || (e && (e.ctrlKey || e.metaKey || e.altKey))) return false;
      if (!(e && e.repeat) && s.q.length < 8) s.q.push(a);
      return true;
    },
    onExit(s, G) {   // leaving mid-run saves the best of it under your usual initials
      sync(s, G);
      if (G.score > 0 && E.qualifies('poker', G.score)) E.addScore('poker', store.get('initials', 'AAA'), G.score);
    },
    update(s, G) {
      s.t++;
      while (s.q.length) act(s, G, s.q.shift());
      if (G.hit('a')) act(s, G, 'go');
      const tp = G.tap;
      if (tp) {
        for (const b of BTN) if (inRect(tp, b.x, BY, BW, BH)) { act(s, G, b.id); break; }
        if (inRect(tp, W - 100, 8, 100, 15)) act(s, G, 'end');
        for (let i = 0; i < 5; i++) if (inRect(tp, CX0 + i * (CW + CGAP) - 2, CY - CRAISE - 4, CW + CGAP, CH + CRAISE + 20)) { act(s, G, 'h' + i); break; }
      }
      for (let i = 0; i < 5; i++) if (s.fa[i] === s.t && (s.phase === 'deal' || s.phase === 'draw')) A().sfx('tick');
      if (s.phase === 'deal' && s.t >= s.endAt) s.phase = 'hold';
      else if (s.phase === 'draw' && s.t >= s.endAt) resolve(s, G);
      if (s.phase === 'result') {
        if (s.shown < s.win) { s.shown = Math.min(s.win, s.shown + Math.max(1, Math.ceil(s.win / 40))); if (s.t % 3 === 0) A().sfx('tick'); }
        else sync(s, G);
        if (s.refillAt && s.t >= s.refillAt) refill(s);
      }
      if (s.refill > 0) s.refill--;
      for (const f of s.fx) if (f.life > 0) { f.x += f.vx; f.y += f.vy; f.vy += 0.06; f.life--; }
    },
    draw(s, G, ctx) {
      const t = s.t, ph = s.phase, over = s.win - s.shown, dc = s.credits - (over > 0 ? over : 0);
      // header: credits and bet, the best (most credits held), and the end-of-run button
      ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, 22);
      text(ctx, T('CREDITS') + ' ' + NF(dc), 6, 3, C.cyan); text(ctx, T('BET') + ' ' + s.bet, W - 6, 3, C.gold, 8, 'right');
      text(ctx, T('BEST') + ' ' + NF(Math.max(E.hiOf('poker'), s.peak, dc)), 6, 12, C.dim);
      text(ctx, T('END RUN'), W - 6, 12, idle(s) ? C.pink : '#4a4070', 8, 'right');
      ctx.fillStyle = '#1b6b86'; ctx.fillRect(0, 21, W, 1);
      // pay table: the column of the current bet is lit and the winning row flashes
      ctx.fillStyle = '#0d0820'; ctx.fillRect(3, 24, 218, 96); ctx.strokeStyle = C.violet; ctx.lineWidth = 1; ctx.strokeRect(3.5, 24.5, 217, 95);
      ctx.fillStyle = 'rgba(255,61,139,.22)'; ctx.fillRect(COLR[s.bet - 1] - 17, 25, 19, 94);
      for (let r = 0; r < 9; r++) {
        const h = HANDS[r], y = 27 + r * 10, flash = ph === 'result' && s.key === h.k, on = flash && (t >> 3) & 1;
        if (on) { ctx.fillStyle = 'rgba(255,61,139,.6)'; ctx.fillRect(4, y - 1, 216, 10); }
        text(ctx, T(h.n), 7, y, flash ? (on ? C.white : C.gold) : C.gold);
        for (let b = 0; b < 5; b++) digits(ctx, payout(h.k, b + 1), COLR[b], y + 2, b === s.bet - 1 ? (flash ? 1 : 2) : 0);
      }
      // the five cards, held ones raised and framed, with HOLD under them
      for (let i = 0; i < 5; i++) {
        const x = CX0 + i * (CW + CGAP), up = s.held[i] && s.hand[i] >= 0 && t >= s.fa[i] + FL;
        drawCard(ctx, s, i, x, up ? CY - CRAISE : CY);
        if (s.held[i] && s.hand[i] >= 0) text(ctx, T('HOLD'), x + CW / 2, CY + CH + 7, C.cyan, 8, 'center');
      }
      // message: the hand you made and what it paid
      let l1 = '', l2 = '', c1 = C.ink, c2 = C.gold;
      if (s.refill > 0) { l1 = T('FREE REFILL'); c1 = (t >> 3) & 1 ? C.lime : C.white; l2 = '+' + START + ' ' + T('CREDITS'); c2 = C.lime; }
      else if (ph === 'ready') { l1 = T('PLACE YOUR BET'); c1 = C.pink; l2 = T('THEN PRESS DEAL'); c2 = C.dim; }
      else if (ph === 'result') {
        if (s.win) { l1 = T(HANDS[HIDX[s.key]].n); c1 = (t >> 3) & 1 ? C.pink : C.gold; l2 = T('WIN') + ' ' + NF(s.shown); }
        else { l1 = T('NO WIN'); c1 = C.dim; l2 = (t >> 5) & 1 ? T('PRESS DEAL') : ''; c2 = C.dim; }
      } else { l1 = T('HOLD CARDS THEN DRAW'); c1 = C.dim; }
      if (l1) { if (ph === 'ready' || ph === 'result' || s.refill > 0) fit(ctx, l1, W / 2, 200, c1, 212); else text(ctx, l1, W / 2, 203, c1, 8, 'center'); }
      if (l2) text(ctx, l2, W / 2, 218, c2, 8, 'center');
      for (const f of s.fx) if (f.life > 0) { ctx.fillStyle = f.life < 8 ? C.dim : f.col; ctx.fillRect(f.x | 0, f.y | 0, 2, 2); }
      // buttons
      const p = G.ptr, labels = { one: 'BET ONE', max: 'BET MAX', go: ph === 'hold' || ph === 'draw' ? 'DRAW' : 'DEAL' };
      for (const b of BTN) { const on = btnOn(s, b.id); button(ctx, b, T(labels[b.id]), on, on && p.down && inRect(p, b.x, BY, BW, BH), b.id === 'go' ? C.orange : C.violet); }
      text(ctx, T('FREE CREDITS · NEVER SATS'), W / 2, 260, C.dim, 8, 'center'); text(ctx, T('0 CREDITS = FREE REFILL'), W / 2, 271, C.dim, 8, 'center');
    },
    thumb(ctx, t) {
      ctx.fillStyle = C.bg; ctx.fillRect(0, 0, 112, 84);
      ctx.fillStyle = '#0d0820'; ctx.fillRect(4, 4, 104, 12); ctx.fillStyle = C.violet; ctx.fillRect(4, 4, 104, 1); ctx.fillRect(4, 15, 104, 1);
      for (let i = 0; i < 5; i++) { ctx.fillStyle = (t >> 4) % 5 === i ? C.pink : '#3a2a8f'; ctx.fillRect(10 + i * 19, 8, 12, 4); }
      const royal = [8, 9, 10, 11, 12].map(r => 13 + r);   // 10 J Q K A of hearts
      for (let i = 0; i < 5; i++) { const x = 6 + i * 21, held = (t >> 6) & 1 || i > 1; if (!((t >> 5) & 1) || i < 2) face(ctx, x, held ? 21 : 25, 19, 28, royal[i], false); else ctx.drawImage(cardBack(), 0, 0, CW, CH, x, 25, 19, 28); if (held) { ctx.fillStyle = C.cyan; ctx.fillRect(x, 55, 19, 1); } }
      if ((t >> 3) & 1) text(ctx, T('WIN') + ' 4000', 56, 66, C.gold, 8, 'center');
    }
  };
}
(root.NutCabinets = root.NutCabinets || []).push(make);
})();
