/* NUTCADE arcade: ACORN LINKS, an overhead nine-hole arcade golf game.
   Every hole is built from the seeded RNG in init(), so a seed gives the same nine holes (and challenges, the daily and replays all play the same course).
   Play: drag back from anywhere on the screen like a slingshot and let go (the ball goes the other way, the pull is the power), or tap the field to aim,
   hold A to run the power meter and let go to swing. A tap on the panel at the bottom changes the club.
   update() uses only + - * / and sqrt (no sin, cos or atan2 of the browser) and the seeded RNG, so a replay gives the same score on every phone. */
(window.NutCabinets = window.NutCabinets || []).push(function (K) {
'use strict';
const { W, H, C, Math, text, T, rnd, ri, clamp, boom, tickFx, drawFx } = K;

const HOLES = 9, VIEW_TOP = 22, VIEW_H = 232, PANEL = VIEW_TOP + VIEW_H;      // the course shows between the score bar and the panel
const PX_YD = 2;                                                               // one pixel is two yards
const PULL = 56;                                                               // pixels of pull for full power
const CLUBS = [                                                                // max carry (px), flight frames, loft (arc height), roll factor, aim error, wind effect
  { n: 'DRIVER', max: 128, air: 64, hi: 26, roll: 0.22, err: 0.07, wk: 1.0 },
  { n: 'IRON', max: 88, air: 50, hi: 22, roll: 0.14, err: 0.045, wk: 0.8 },
  { n: 'WEDGE', max: 48, air: 38, hi: 18, roll: 0.05, err: 0.02, wk: 0.6 },
  { n: 'PUTTER', max: 74, air: 0, hi: 0, roll: 1, err: 0.008, wk: 0 }
];
const FRIC = { tee: 0.965, fairway: 0.965, rough: 0.9, sand: 0.6, green: 0.975 };   // speed kept each frame, by surface
const LIE_CARRY = { tee: 1, fairway: 1, rough: 0.75, sand: 0.6, green: 1 };
const LIE_ROLL = { tee: 1, fairway: 1, rough: 0.35, sand: 0.12, green: 0.7 };
const CUP = 3.4, CUP_SPEED = 1.25, GIMME = 5;                                    // the ball drops if it is this close to the pin and slow enough
const ROT_C = 0.9998, ROT_S = 0.0199987;                                        // a keyboard aim step of 0.02 rad as constants (no sin or cos)

const PAL = { rough: '#0b2f1c', rough2: '#0e3a22', fair: '#16662f', fair2: '#1a7436', green: '#35cc60', green2: '#2eb956', sand: '#e0c878', sand2: '#c8ae5c', water: '#1c5fe0', water2: '#4a8bff', tree: '#0a5a2a', tree2: '#1c9a45', trunk: '#6a3a14' };

/* ---------- geometry ---------- */
const inEll = (e, x, y) => { const dx = (x - e.x) / e.rx, dy = (y - e.y) / e.ry; return dx * dx + dy * dy <= 1; };
function segDist(px, py, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, L = dx * dx + dy * dy || 1, t = clamp(((px - a.x) * dx + (py - a.y) * dy) / L, 0, 1), qx = a.x + dx * t - px, qy = a.y + dy * t - py;
  return Math.sqrt(qx * qx + qy * qy);
}
function lieAt(h, x, y) {
  if (x < 6 || x > W - 6 || y < 8 || y > h.H - 4) return 'oob';
  for (const w of h.water) if (inEll(w, x, y)) return 'water';
  if (inEll(h.green, x, y)) return 'green';
  for (const b of h.sand) if (inEll(b, x, y)) return 'sand';
  for (const t of h.trees) { const dx = x - t.x, dy = y - t.y; if (dx * dx + dy * dy <= t.r * t.r) return 'tree'; }
  if (Math.hypot(x - h.tee.x, y - h.tee.y) < 9) return 'tee';
  if (segDist(x, y, h.tee, h.mid) < h.fw || segDist(x, y, h.mid, h.pin) < h.fw) return 'fairway';
  return 'rough';
}

/* ---------- the nine holes, from the seed ---------- */
function buildHole(i) {
  const len = Math.min(330, 150 + ri(0, 60) + i * 14);                        // tee to pin, in pixels
  const par = len < 185 ? 3 : len < 270 ? 4 : 5;
  const Hh = len + 64, pin = { x: ri(70, 154), y: 34 }, tee = { x: ri(80, 144), y: 34 + len };
  const mid = { x: clamp(Math.round((tee.x + pin.x) / 2) + ri(-34, 34), 44, W - 44), y: Math.round((tee.y + pin.y) / 2) + ri(-12, 12) };
  const fw = par === 3 ? 13 : 19;
  const h = { par, len, H: Hh, tee, mid, pin, fw, green: { x: pin.x + ri(-3, 3), y: pin.y + ri(-2, 4), rx: ri(19, 25), ry: ri(15, 19) }, sand: [], water: [], trees: [], wind: null, slope: null };
  h.pin.x = h.green.x; h.pin.y = h.green.y;
  const side = () => (ri(0, 1) ? 1 : -1);
  const nsand = 1 + (i % 3);
  for (let k = 0; k < nsand; k++) {
    if (k === 0) h.sand.push({ x: h.green.x + side() * (h.green.rx + 6), y: h.green.y + ri(-8, 14), rx: ri(8, 11), ry: ri(5, 8) });
    else { const f = rnd(0.25, 0.75), bx = tee.x + (mid.x - tee.x) * f, by = tee.y + (pin.y - tee.y) * f; h.sand.push({ x: clamp(bx + side() * (fw + 10), 14, W - 14), y: by, rx: ri(8, 12), ry: ri(5, 8) }); }
  }
  if (i % 3 === 1 || i === 8) { const by = tee.y + (pin.y - tee.y) * 0.55, bx = tee.x + (mid.x - tee.x) * 0.55; h.water.push({ x: clamp(bx + side() * (fw + 18), 22, W - 22), y: by, rx: ri(13, 18), ry: ri(16, 22) }); }
  const ntree = 3 + (i >> 1);
  for (let k = 0; k < ntree; k++) {
    const f = rnd(0.12, 0.92), cx = tee.x + (mid.x - tee.x) * f, cy = tee.y + (pin.y - tee.y) * f, tx = clamp(cx + side() * (fw + ri(6, 22)), 12, W - 12), ty = cy + ri(-14, 14);
    if (Math.hypot(tx - pin.x, ty - pin.y) > 30 && Math.hypot(tx - tee.x, ty - tee.y) > 22) h.trees.push({ x: tx, y: ty, r: ri(4, 6) });
  }
  const wm = 1 + i * 0.7; h.wind = { x: Math.round(rnd(-wm, wm) * 10) / 10, y: Math.round(rnd(-wm * 0.6, wm * 0.6) * 10) / 10 };
  h.slope = { x: Math.round(rnd(-0.9, 0.9) * 10) / 10, y: Math.round(rnd(-0.9, 0.9) * 10) / 10 };
  return h;
}

const yards = px => Math.round(px * PX_YD);
const norm = (x, y) => { const d = Math.sqrt(x * x + y * y) || 1; return [x / d, y / d]; };
function holePoints(strokes, par) {
  if (strokes === 1) return 1000;
  const d = strokes - par;
  return d <= -2 ? 700 : d === -1 ? 400 : d === 0 ? 250 : d === 1 ? 100 : d === 2 ? 50 : 0;
}

const links = {
  id: 'links', daily: true, name: 'ACORN LINKS', year: '1989', blurb: 'Nine holes of overhead golf. Pull back, let go, mind the wind.', track: 'bounce', noStick: true,
  help: 'drag back and let go to swing · tap to aim', keys: '← → aim · ↑ ↓ club · hold Space, let go to swing',
  init(G) {
    const holes = []; for (let i = 0; i < HOLES; i++) holes.push(buildHole(i));
    const s = { t: 0, holes, hole: 0, strokes: 0, total: 0, par: 0, mode: 'aim', ball: null, last: null, ax: 0, ay: -1, club: 0, pw: 0, pdir: 1, charge: false, drag: null, dragDown: false, camY: 0,
      fx: [], msg: '', msgT: 0, banner: 0, bannerTxt: '', f: 0, fF: 0, vx: 0, vy: 0, a0: null, a1: null, z: 0, rollT: 0, name: '', lie: 'tee', holed: false, lastHole: -1, intro: 150 };
    this.startHole(s); return s;
  },
  startHole(s) {
    const h = s.holes[s.hole]; s.strokes = 0; s.mode = 'aim'; s.ball = { x: h.tee.x, y: h.tee.y }; s.last = { x: h.tee.x, y: h.tee.y }; s.holed = false; s.z = 0; s.charge = false; s.drag = null; s.dragDown = false; s.pw = 0;
    const d = norm(h.pin.x - h.tee.x, h.pin.y - h.tee.y); s.ax = d[0]; s.ay = d[1]; s.lie = 'tee'; this.pickClub(s); s.banner = 0;
  },
  pickClub(s) {
    const h = s.holes[s.hole], b = s.ball, d = Math.hypot(h.pin.x - b.x, h.pin.y - b.y), lie = lieAt(h, b.x, b.y);
    let c = 3;
    if (lie !== 'green' || d > 90) { c = 0; if (!(s.strokes === 0 && h.par > 3)) { if (d * 1.05 < CLUBS[2].max * LIE_CARRY[lie === 'tree' ? 'rough' : lie]) c = 2; else if (d * 1.05 < CLUBS[1].max * LIE_CARRY[lie === 'tree' ? 'rough' : lie]) c = 1; } }
    if (d < 14 && lie !== 'sand') c = 3;
    s.club = c;
  },
  say(s, m, n = 100) { s.msg = m; s.msgT = n; },
  carryOf(s, p) { const c = CLUBS[s.club], lie = s.lie === 'tree' ? 'rough' : s.lie; return c.max * p * (s.club === 2 && lie === 'sand' ? 0.8 : LIE_CARRY[lie]); },
  windShift(s, c, air) { const h = s.holes[s.hole], k = c.wk * air / 60; return [h.wind.x * k, h.wind.y * k]; },
  swing(s, G, p) {
    const h = s.holes[s.hole], c = CLUBS[s.club], b = s.ball, lie = lieAt(h, b.x, b.y); s.lie = lie === 'tree' ? 'rough' : lie;
    p = clamp(p, 0.04, 1);
    const spread = rnd(-1, 1) * c.err * (0.45 + p * 0.55) * (s.lie === 'rough' ? 1.8 : s.lie === 'sand' ? 1.5 : 1);
    let ax = s.ax - s.ay * spread, ay = s.ay + s.ax * spread; [ax, ay] = norm(ax, ay);
    s.strokes++; s.last = { x: b.x, y: b.y }; s.a0 = { x: b.x, y: b.y };
    if (s.club === 3) {                                                          // a putt: no flight, the ball starts rolling
      const f = FRIC[s.lie], v0 = c.max * p * (1 - f) / f; s.vx = ax * v0; s.vy = ay * v0; s.mode = 'roll'; s.rollT = 0; s.z = 0; G.sfx('hit'); return;
    }
    const carry = this.carryOf(s, p), air = Math.floor(c.air * (0.55 + 0.45 * p)), w = this.windShift(s, c, air);
    s.a1 = { x: b.x + ax * carry + w[0], y: b.y + ay * carry + w[1] }; s.dirx = ax; s.diry = ay; s.carry = carry;
    s.f = 0; s.fF = Math.max(14, air); s.mode = 'fly'; s.hi = c.hi * (0.4 + 0.6 * p); G.sfx(s.club === 0 ? 'launch' : 'shoot');
  },
  land(s, G) {
    const h = s.holes[s.hole], c = CLUBS[s.club], x = s.a1.x, y = s.a1.y, lie = lieAt(h, x, y);
    s.ball = { x, y }; s.z = 0;
    if (lie === 'water') return this.penalty(s, G, 'water');
    if (lie === 'oob') return this.penalty(s, G, 'oob');
    if (lie === 'tree') {                                                        // the ball drops dead at the foot of the tree
      for (const t of h.trees) { const dx = x - t.x, dy = y - t.y; if (dx * dx + dy * dy <= t.r * t.r) { const [ux, uy] = norm(dx || 1, dy || 0.01); s.ball = { x: t.x + ux * (t.r + 2), y: t.y + uy * (t.r + 2) }; break; } }
      G.sfx('wall'); return this.settle(s, G);
    }
    boom(s.fx, x, y, lie === 'sand' ? C.gold : lie === 'green' ? C.lime : C.dim, 6); G.sfx('tick');
    const f = FRIC[lie], roll = s.carry * c.roll * LIE_ROLL[lie], v0 = roll * (1 - f) / f;
    s.vx = s.dirx * v0; s.vy = s.diry * v0; s.mode = 'roll'; s.rollT = 0;
  },
  penalty(s, G, why) {
    s.ball = { x: s.last.x, y: s.last.y }; s.strokes++; s.mode = 'drop'; s.rollT = 60; G.sfx(why === 'water' ? 'splash' : 'err');
    boom(s.fx, s.a1 ? s.a1.x : s.ball.x, s.a1 ? s.a1.y : s.ball.y, C.water2, 12); this.say(s, why === 'water' ? 'SPLASH! +1' : 'OUT OF BOUNDS +1', 70);
  },
  settle(s, G) {                                                               // the ball has stopped: holed, picked up, or the next stroke
    const h = s.holes[s.hole], d = Math.hypot(h.pin.x - s.ball.x, h.pin.y - s.ball.y);
    if (d <= GIMME && lieAt(h, s.ball.x, s.ball.y) === 'green') return this.holeOut(s, G);
    if (s.strokes >= h.par + 4) { s.strokes = h.par + 4; return this.holeOut(s, G, true); }
    s.mode = 'aim'; s.pw = 0; s.charge = false; s.drag = null; s.dragDown = false; s.lie = lieAt(h, s.ball.x, s.ball.y); if (s.lie === 'tree') s.lie = 'rough';
    const nd = norm(h.pin.x - s.ball.x, h.pin.y - s.ball.y); s.ax = nd[0]; s.ay = nd[1]; this.pickClub(s);
  },
  holeOut(s, G, pick) {
    const h = s.holes[s.hole], pts = pick ? 0 : holePoints(s.strokes, h.par); s.holed = true; s.mode = 'hole'; s.banner = 130; s.ball = { x: h.pin.x, y: h.pin.y };
    const d = s.strokes - h.par;
    s.bannerTxt = pick ? 'PICK UP' : s.strokes === 1 ? 'HOLE IN ONE!' : d <= -2 ? 'EAGLE' : d === -1 ? 'BIRDIE' : d === 0 ? 'PAR' : d === 1 ? 'BOGEY' : d === 2 ? 'DOUBLE BOGEY' : 'TRIPLE BOGEY';
    s.bannerPts = pts; s.total += s.strokes - h.par; G.addScore(pts);
    boom(s.fx, h.pin.x, h.pin.y, pts >= 400 ? C.gold : C.lime, pts >= 400 ? 30 : 14); G.sfx(pts >= 400 ? 'levelup' : pts > 0 ? 'coin' : 'die');
  },
  update(s, G) {
    s.t++; if (s.msgT) s.msgT--; if (s.intro) s.intro--; tickFx(s.fx);
    const h = s.holes[s.hole];
    if (s.mode === 'aim') {
      // aim: keys, a tap on the field, or a drag back (slingshot)
      const hold = G.held('a');
      if (G.held('left') || G.held('right')) {
        const sn = G.held('left') ? -ROT_S : ROT_S; const ax = s.ax * ROT_C - s.ay * sn, ay = s.ay * ROT_C + s.ax * sn; [s.ax, s.ay] = norm(ax, ay);
      }
      if (G.hit('up')) { s.club = (s.club + 1) % 4; G.sfx('blip'); } else if (G.hit('down')) { s.club = (s.club + 3) % 4; G.sfx('blip'); }
      if (G.tap) {
        if (G.tap.y >= PANEL) { s.club = (s.club + 1) % 4; G.sfx('blip'); }
        else { const sy = s.ball.y - s.camY + VIEW_TOP; const n = norm(G.tap.x - s.ball.x, G.tap.y - sy); if (Math.hypot(G.tap.x - s.ball.x, G.tap.y - sy) > 6) { s.ax = n[0]; s.ay = n[1]; G.sfx('tick'); } }
      }
      if (hold) { if (!s.charge) { s.charge = true; s.pw = 0; s.pdir = 1; } s.pw += s.pdir / 55; if (s.pw >= 1) { s.pw = 1; s.pdir = -1; } if (s.pw <= 0 && s.pdir < 0) { s.pw = 0; s.pdir = 1; } }
      else if (s.charge) { s.charge = false; const p = s.pw; s.pw = 0; if (p > 0.03) this.swing(s, G, p); }
      // the drag
      if (G.ptr.down && !s.dragDown && !hold) { if (G.ptr.y < PANEL) { s.dragDown = true; s.drag = { x0: G.ptr.x, y0: G.ptr.y, x: G.ptr.x, y: G.ptr.y }; } }
      else if (G.ptr.down && s.dragDown) { s.drag.x = G.ptr.x; s.drag.y = G.ptr.y; }
      if (s.dragDown && (!G.ptr.down || G.ptr.cancel)) {
        const d = s.drag, cancel = G.ptr.cancel; s.dragDown = false; s.drag = null;
        const dx = d.x - d.x0, dy = d.y - d.y0, len = Math.sqrt(dx * dx + dy * dy);
        if (!cancel && len >= 10) { const n = norm(-dx, -dy); s.ax = n[0]; s.ay = n[1]; this.swing(s, G, len / PULL); }
      }
      return;
    }
    if (s.mode === 'fly') {
      s.f++; const u = s.f / s.fF; s.ball = { x: s.a0.x + (s.a1.x - s.a0.x) * u, y: s.a0.y + (s.a1.y - s.a0.y) * u }; s.z = 4 * u * (1 - u) * s.hi;
      if (s.f >= s.fF) this.land(s, G);
      return;
    }
    if (s.mode === 'roll') {
      s.rollT++; const b = s.ball, lie = lieAt(h, b.x, b.y);
      if (lie === 'water') { s.a1 = { x: b.x, y: b.y }; return this.penalty(s, G, 'water'); }
      if (lie === 'oob') { s.a1 = { x: b.x, y: b.y }; return this.penalty(s, G, 'oob'); }
      if (lie === 'tree') { s.vx *= -0.3; s.vy *= -0.3; G.sfx('wall'); }          // it bounces back off a trunk
      const f = FRIC[lie === 'tree' ? 'rough' : lie];
      if (lie === 'green') { s.vx += h.slope.x * 0.0055; s.vy += h.slope.y * 0.0055; }
      s.vx *= f; s.vy *= f; b.x += s.vx; b.y += s.vy;
      const sp = Math.sqrt(s.vx * s.vx + s.vy * s.vy), d = Math.hypot(h.pin.x - b.x, h.pin.y - b.y);
      if (d < CUP && sp < CUP_SPEED) { b.x = h.pin.x; b.y = h.pin.y; return this.holeOut(s, G); }
      if (sp < 0.04 || s.rollT > 700) { s.vx = 0; s.vy = 0; this.settle(s, G); }
      return;
    }
    if (s.mode === 'drop') { if (--s.rollT <= 0) this.settle(s, G); return; }
    if (s.mode === 'hole') {
      if (--s.banner <= 0) { s.hole++; if (s.hole >= HOLES) { s.mode = 'end'; s.banner = 170; const under = Math.max(0, -s.total); if (under) { G.addScore(under * 250); s.bonusTxt = 'UNDER PAR BONUS ' + (under * 250); } else s.bonusTxt = ''; G.sfx('levelup'); } else this.startHole(s); }
      return;
    }
    if (s.mode === 'end') { if (--s.banner <= 0) G.over(); }
  },
  draw(s, G, ctx) {
    const h = s.holes[Math.min(s.hole, HOLES - 1)], b = s.ball;
    const cam = clamp(Math.round(b.y - 150), 0, h.H - VIEW_H); s.camY = cam;
    ctx.save(); ctx.beginPath(); ctx.rect(0, VIEW_TOP, W, VIEW_H); ctx.clip(); ctx.translate(0, VIEW_TOP - cam);
    ctx.fillStyle = PAL.rough; ctx.fillRect(0, cam, W, VIEW_H);
    ctx.fillStyle = PAL.rough2; for (let y = (cam >> 4) << 4; y < cam + VIEW_H + 16; y += 16) for (let x = ((y >> 4) & 1) * 8; x < W; x += 16) ctx.fillRect(x, y, 2, 2);
    ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = PAL.fair; ctx.lineWidth = h.fw * 2; ctx.beginPath(); ctx.moveTo(h.tee.x, h.tee.y); ctx.lineTo(h.mid.x, h.mid.y); ctx.lineTo(h.pin.x, h.pin.y); ctx.stroke();
    ctx.strokeStyle = PAL.fair2; ctx.lineWidth = Math.max(2, h.fw * 2 - 8); ctx.stroke(); ctx.lineWidth = 1; ctx.lineCap = 'butt'; ctx.lineJoin = 'miter';
    const ell = (e, col, col2) => { ctx.fillStyle = col; ctx.beginPath(); ctx.ellipse(e.x, e.y, e.rx, e.ry, 0, 0, 6.29); ctx.fill(); if (col2) { ctx.fillStyle = col2; ctx.beginPath(); ctx.ellipse(e.x, e.y, e.rx - 3, e.ry - 3, 0, 0, 6.29); ctx.fill(); } };
    ell(h.green, PAL.green2, PAL.green);
    for (const e of h.sand) ell(e, PAL.sand2, PAL.sand);
    for (const e of h.water) { ell(e, PAL.water, null); ctx.fillStyle = PAL.water2; ctx.fillRect(e.x - e.rx / 2 + ((s.t >> 4) & 3), e.y - 3, 6, 1); ctx.fillRect(e.x + 2 - ((s.t >> 4) & 3), e.y + 5, 5, 1); }
    ctx.fillStyle = '#c9b27a'; ctx.fillRect(h.tee.x - 8, h.tee.y - 3, 16, 6); ctx.fillStyle = C.white; ctx.fillRect(h.tee.x - 8, h.tee.y - 3, 2, 2); ctx.fillRect(h.tee.x + 6, h.tee.y - 3, 2, 2);
    for (const t of h.trees) { ctx.fillStyle = PAL.trunk; ctx.fillRect(t.x - 1, t.y + t.r - 2, 3, 4); ctx.fillStyle = PAL.tree; ctx.beginPath(); ctx.arc(t.x, t.y, t.r, 0, 6.29); ctx.fill(); ctx.fillStyle = PAL.tree2; ctx.beginPath(); ctx.arc(t.x - 1, t.y - 1, t.r - 2, 0, 6.29); ctx.fill(); }
    ctx.fillStyle = '#000'; ctx.beginPath(); ctx.arc(h.pin.x, h.pin.y, 3, 0, 6.29); ctx.fill();
    ctx.fillStyle = C.white; ctx.fillRect(h.pin.x, h.pin.y - 16, 1, 16); ctx.fillStyle = C.red; ctx.fillRect(h.pin.x + 1, h.pin.y - 16, 7 + ((s.t >> 4) & 1), 4);
    // aim line, landing marker and the swing pull
    if (s.mode === 'aim') {
      let p = s.dragDown && s.drag ? clamp(Math.hypot(s.drag.x - s.drag.x0, s.drag.y - s.drag.y0) / PULL, 0, 1) : s.charge ? s.pw : 0.7;
      let ax = s.ax, ay = s.ay;
      if (s.dragDown && s.drag) { const dx = s.drag.x - s.drag.x0, dy = s.drag.y - s.drag.y0; if (Math.hypot(dx, dy) > 3) [ax, ay] = norm(-dx, -dy); }
      const c = CLUBS[s.club], carry = this.carryOf(s, p), air = c.air ? Math.floor(c.air * (0.55 + 0.45 * p)) : 0, w = c.air ? this.windShift(s, c, air) : [0, 0];
      const ex = b.x + ax * carry + w[0], ey = b.y + ay * carry + w[1];
      ctx.strokeStyle = s.dragDown || s.charge ? C.gold : C.cyan; ctx.setLineDash([2, 3]); ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.lineTo(ex, ey); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = C.gold; ctx.fillRect(ex - 2, ey - 2, 4, 4);
    }
    // the ball, with its shadow while it is in the air
    if (s.mode === 'fly') { ctx.fillStyle = 'rgba(0,0,0,.45)'; ctx.fillRect(Math.round(b.x) - 1, Math.round(b.y), 3, 2); }
    if (s.mode !== 'hole' && s.mode !== 'end') { ctx.fillStyle = C.white; const bs = s.z > 8 ? 3 : 2; ctx.fillRect(Math.round(b.x - bs / 2), Math.round(b.y - s.z - bs / 2), bs, bs); }
    drawFx(ctx, s.fx);
    ctx.restore();
    // the pull-back line, in screen space
    if (s.mode === 'aim' && s.dragDown && s.drag) { ctx.strokeStyle = C.pink; ctx.beginPath(); ctx.moveTo(s.drag.x0, s.drag.y0); ctx.lineTo(s.drag.x, s.drag.y); ctx.stroke(); ctx.fillStyle = C.pink; ctx.fillRect(s.drag.x - 2, s.drag.y - 2, 4, 4); }
    // the panel
    ctx.fillStyle = '#05030c'; ctx.fillRect(0, PANEL, W, H - PANEL); ctx.fillStyle = '#1a1038'; ctx.fillRect(0, PANEL, W, 1);
    const club = CLUBS[s.club], dpin = yards(Math.hypot(h.pin.x - b.x, h.pin.y - b.y));
    text(ctx, T('HOLE') + ' ' + (Math.min(s.hole, HOLES - 1) + 1) + '  ' + T('PAR') + ' ' + h.par, 6, PANEL + 4, C.gold);
    text(ctx, T('STROKES') + ' ' + s.strokes, W - 6, PANEL + 4, C.ink, 8, 'right');
    text(ctx, T(club.n), 6, PANEL + 14, C.cyan);
    const wx = h.wind.x, wy = h.wind.y, wsp = Math.round(Math.hypot(wx, wy) * 2) / 2;
    text(ctx, T('WIND') + ' ' + (wsp === 0 ? '0' : (wx < -0.2 ? '< ' : wx > 0.2 ? '> ' : '') + (wy < -0.2 ? '^' : wy > 0.2 ? 'v' : '') + wsp), W - 6, PANEL + 14, C.lime, 8, 'right');
    text(ctx, T('PIN') + ' ' + dpin + 'Y', 6, PANEL + 24, C.ink); text(ctx, T((s.lie || 'tee').toUpperCase()), W - 6, PANEL + 24, C.dim, 8, 'right');
    if (s.mode === 'aim') { const mp = s.charge ? s.pw : 0; if (s.charge) { ctx.fillStyle = '#2a1a4a'; ctx.fillRect(60, PANEL + 15, 60, 5); ctx.fillStyle = mp > 0.85 ? C.red : C.lime; ctx.fillRect(60, PANEL + 15, Math.round(60 * mp), 5); } }
    G.hud(null, T('HOLE') + ' ' + (Math.min(s.hole, HOLES - 1) + 1));
    if (s.msgT) text(ctx, T(s.msg), W / 2, 60, C.gold, 8, 'center');
    else if (s.intro && s.mode === 'aim') { text(ctx, T('DRAG BACK AND LET GO'), W / 2, 40, C.ink, 8, 'center'); text(ctx, T('TAP TO AIM'), W / 2, 52, C.dim, 8, 'center'); }
    if (s.mode === 'hole') { ctx.fillStyle = 'rgba(5,3,12,.72)'; ctx.fillRect(0, 90, W, 52); text(ctx, T(s.bannerTxt), W / 2, 100, s.bannerPts >= 400 ? C.gold : C.lime, 8, 'center'); text(ctx, s.strokes + ' / ' + T('PAR') + ' ' + h.par, W / 2, 114, C.ink, 8, 'center'); text(ctx, '+' + s.bannerPts, W / 2, 126, C.gold, 8, 'center'); }
    if (s.mode === 'end') { ctx.fillStyle = 'rgba(5,3,12,.8)'; ctx.fillRect(0, 80, W, 70); text(ctx, T('ROUND OVER'), W / 2, 92, C.gold, 8, 'center'); text(ctx, (s.total > 0 ? '+' : '') + s.total + ' ' + T('PAR'), W / 2, 108, C.ink, 8, 'center'); if (s.bonusTxt) text(ctx, T('UNDER PAR BONUS') + ' ' + s.bonusTxt.split(' ').pop(), W / 2, 124, C.lime, 8, 'center'); }
  },
  thumb(ctx, t) {
    ctx.fillStyle = PAL.rough; ctx.fillRect(0, 0, 112, 84);
    ctx.strokeStyle = PAL.fair; ctx.lineWidth = 22; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(40, 76); ctx.lineTo(62, 42); ctx.lineTo(64, 18); ctx.stroke(); ctx.lineWidth = 1; ctx.lineCap = 'butt';
    ctx.fillStyle = PAL.green; ctx.beginPath(); ctx.ellipse(64, 16, 17, 11, 0, 0, 6.29); ctx.fill();
    ctx.fillStyle = PAL.sand; ctx.beginPath(); ctx.ellipse(88, 28, 8, 5, 0, 0, 6.29); ctx.fill();
    ctx.fillStyle = PAL.water; ctx.beginPath(); ctx.ellipse(18, 38, 11, 14, 0, 0, 6.29); ctx.fill();
    ctx.fillStyle = '#000'; ctx.fillRect(63, 15, 3, 3); ctx.fillStyle = C.white; ctx.fillRect(64, 3, 1, 14); ctx.fillStyle = C.red; ctx.fillRect(65, 3, 8, 4);
    const k = (t % 90) / 90, x = 40 + (64 - 40) * k, y = 76 - 60 * k - Math.sin(k * 3.14159) * 8; ctx.fillStyle = C.white; ctx.fillRect(Math.round(x), Math.round(y), 3, 3);
  }
};
return links;
});
